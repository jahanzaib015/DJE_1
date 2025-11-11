import os
import time
import uuid
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from .llm_service import LLMService
from .rag_retrieve import retrieve_rules
from .rag_index import build_chunks
from .excel_mapping_service import ExcelMappingService
from ..models.analysis_models import AnalysisResult, AnalysisMethod, LLMProvider, AnalysisRequest
from ..models.llm_response_models import LLMResponse
from ..utils.trace_handler import TraceHandler
from ..utils.file_handler import FileHandler
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

def get_enum_value(value):
    """Safely get enum value, handling both enum objects and strings"""
    if hasattr(value, 'value'):
        return value.value
    return str(value)

class AnalysisService:
    """Core analysis service that orchestrates document analysis"""
    
    def __init__(self, excel_mapping_path: Optional[str] = None):
        try:
            self.llm_service = LLMService()
        except Exception as e:
            logger.warning(f"Failed to initialize LLMService in AnalysisService: {e}")
            self.llm_service = None
        self.trace_handler = TraceHandler()
        self.file_handler = FileHandler()
        
        # Initialize Excel mapping service
        try:
            self.excel_mapping = ExcelMappingService(excel_path=excel_mapping_path)
            logger.info(f"Excel mapping service initialized with {len(self.excel_mapping.get_all_entries())} entries")
        except Exception as e:
            logger.warning(f"Failed to initialize ExcelMappingService: {e}")
            self.excel_mapping = None
    
    async def analyze_document(
        self, 
        text: str, 
        analysis_method: AnalysisMethod,
        llm_provider: LLMProvider,
        model: str,
        fund_id: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Main analysis method that coordinates different analysis approaches"""
        
        start_time = time.time()
        
        # Create empty OCRD structure
        data = self._create_empty_ocrd_json(fund_id)
        
        # NEW: Search document text for ALL Excel entries (Column A) and use LLM to determine allowed/prohibited
        if self.excel_mapping:
            logger.info("🔍 Step 1: Searching document for all Excel entries (Column A terms) using LLM analysis...")
            search_stats = await self.excel_mapping.search_document_with_llm(
                text, 
                self.llm_service, 
                get_enum_value(llm_provider), 
                model
            )
            logger.info(f"✅ LLM search complete: {search_stats['matches_found']} entries found, {search_stats['allowed_found']} allowed, {search_stats['prohibited_found']} prohibited")
        
        # ONLY USE LLM ANALYSIS - No keyword analysis or fallback
        # All analysis methods use LLM only
        if trace_id:
            result, raw_analysis = await self._analyze_with_llm_traced(data, text, llm_provider, model, trace_id)
        else:
            result, raw_analysis = await self._analyze_with_llm(data, text, llm_provider, model, trace_id)
        analysis_method_used = f"llm_{get_enum_value(llm_provider)}"
        
        processing_time = time.time() - start_time
        
        # Calculate metrics
        total_instruments, allowed_instruments, evidence_coverage = self._calculate_metrics(result)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            result, 
            evidence_coverage, 
            model,
            raw_analysis
        )
        
        return {
            "fund_id": fund_id,
            "analysis_method": analysis_method_used,
            "llm_provider": get_enum_value(llm_provider),
            "model": model,
            "total_instruments": total_instruments,
            "allowed_instruments": allowed_instruments,
            "evidence_coverage": evidence_coverage,
            "confidence_score": confidence_score,
            "sections": result["sections"],
            "notes": result.get("notes", []),  # Include debug notes in response
            "processing_time": round(processing_time, 2),
            "created_at": datetime.now().isoformat()
        }
    
    async def analyze_document_rag(self, request: AnalysisRequest) -> Dict[str, Any]:
        """RAG-enhanced analysis method that uses document chunking and retrieval"""
        trace_id = str(uuid.uuid4())
        trace_handler = TraceHandler(trace_id)
        file_handler = FileHandler()

        try:
            # 1. Save uploaded PDF locally
            pdf_path = await file_handler.save_uploaded_file(request.file)
            trace_handler.log_step("file_saved", {"path": pdf_path})

            # 2. Extract raw text
            extracted_text = await file_handler.extract_pdf_text(pdf_path)
            trace_handler.log_step("text_extracted", {"length": len(extracted_text)})

            # 3. Chunk and build vector collection
            chunks = build_chunks(pdf_path, extracted_text)
            # Note: create_temp_collection method needs to be implemented in FileHandler
            # For now, we'll use the chunks directly
            trace_handler.log_step("collection_built", {"chunks": len(chunks)})

            # 4. Retrieve relevant context for this query
            user_query = "List all rules about allowed and restricted investment sectors, countries, and instruments."
            # Note: retrieve_rules expects a collection parameter, we'll adapt this
            # For now, we'll use the chunks directly as context
            results = {"documents": [chunks]}  # Simplified for now
            trace_handler.log_retrieval(results["documents"])

            # 5. Format retrieved context for LLM
            retrieved_chunks = [chunk for sublist in results["documents"] for chunk in sublist]
            combined_context = "\n\n".join(getattr(c, "text", str(c)) for c in retrieved_chunks)

            # ===== DEBUG: CHUNK COUNTS & CONTEXT LENGTH =====
            logger.info(
                "[RAG] job=%s fund=%s chunks=%d combined_context_len=%d",
                trace_id, request.fund_id, len(retrieved_chunks), len(combined_context)
            )

            # optional: peek at the first 2 chunks
            for i, ch in enumerate(retrieved_chunks[:2]):
                preview = getattr(ch, "text", "")[:200].replace("\n", " ")
                logger.info("[RAG] job=%s top%d score=%s preview=%r",
                            trace_id, i+1, getattr(ch, "score", None), preview)

            # also write the actual prompt context to traces so you can open it
            trace_dir = trace_handler.get_trace_dir(trace_id)
            os.makedirs(trace_dir, exist_ok=True)
            context_file_path = os.path.join(trace_dir, f"{trace_id}_context.txt")
            with open(context_file_path, 'w', encoding='utf-8') as f:
                f.write(combined_context)
            # ================================================

            # 6. Send to LLM
            llm_service = LLMService()
            llm_prompt = f"""
            You are a compliance analyst. Based on the following policy text, extract explicit investment permissions or prohibitions.

            Context:
            {combined_context}
            """
            llm_response = await llm_service.analyze_document(llm_prompt, get_enum_value(request.llm_provider), request.model, trace_id)
            trace_handler.log_step("llm_response", {"length": len(str(llm_response))})

            # 7. Convert LLM output into structured format
            # Note: save_excel_from_json method needs to be implemented in FileHandler
            # For now, we'll return the structured response
            trace_handler.log_step("analysis_completed", {"trace_id": trace_id})

            return {
                "trace_id": trace_id, 
                "analysis_result": llm_response,
                "chunks_processed": len(chunks),
                "context_length": len(combined_context)
            }
            
        except Exception as e:
            trace_handler.log_error(f"RAG analysis failed: {str(e)}")
            raise Exception(f"RAG analysis failed: {str(e)}")
    
    def _create_empty_ocrd_json(self, fund_id: str) -> Dict[str, Any]:
        """Create empty OCRD data structure"""
        # OCRD schema from your existing code
        OCRD_SCHEMA = {
            "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
            "certificate": ["bond_certificate", "commodity_certificate", "currency_certificate", "fund_certificate", "index_certificate", "stock_certificate"],
            "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", "preferred_stock", "reit", "right"],
            "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
            "deposit": ["call_money", "cash", "time_deposit"],
            "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
            "option": ["bond_future_option", "commodity_future_option", "commodity_option", "currency_future_option", "currency_option", "fund_future_option", "fund_option", "index_future_option", "index_option", "stock_option"],
            "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
            "commodity": ["precious_metal"],
            "forex": ["forex_outright", "forex_spot"],
            "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
            "loan": [],
            "private_equity": [],
            "real_estate": [],
            "rights": ["subscription_rights"]
        }
        
        out = {"fund_id": fund_id, "as_of": None, "sections": {}, "notes": []}
        for section, rows in OCRD_SCHEMA.items():
            out["sections"][section] = {}
            for r in rows:
                out["sections"][section][r] = {"allowed": False, "note": "", "evidence": {"page": None, "text": ""}}
            if section in ("stock", "fund", "bond", "certificate", "deposit", "future", "option", "warrant", "commodity", "forex", "swap", "loan", "private_equity", "real_estate", "rights"):
                out["sections"][section]["special_other_restrictions"] = []
        
        return out
    
    def _analyze_with_keywords(self, data: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Fast keyword-based analysis"""
        text_lower = text.lower()
        
        # Define keywords for each instrument type
        instrument_keywords = {
            "bond": ["bond", "anleihe", "pfandbrief", "commercial paper", "inflation linked", "plain vanilla", "convertible", "covered bond", "asset backed", "mortgage bond"],
            "stock": ["stock", "aktie", "equity", "share", "common stock", "preferred stock", "reit", "depositary receipt", "genussschein", "partizipationsschein"],
            "fund": ["fund", "fonds", "equity fund", "fixed income fund", "money market fund", "mixed allocation fund", "alternative investment fund", "commodity fund", "private equity fund", "real estate fund"],
            "certificate": ["certificate", "zertifikat", "bond certificate", "commodity certificate", "currency certificate", "fund certificate", "index certificate", "stock certificate"],
            "future": ["future", "futures", "terminkontrakt", "derivative", "bond future", "commodity future", "currency future", "index future"],
            "option": ["option", "options", "optionen", "derivative", "bond option", "commodity option", "currency option", "stock option"],
            "deposit": ["deposit", "einlage", "call money", "cash", "time deposit"],
            "forex": ["forex", "foreign exchange", "currency", "währung", "devisen", "forex outright", "forex spot"]
        }
        
        # Define permission keywords
        permission_keywords = ["may invest", "allowed", "permitted", "authorized", "darf", "berechtigt", "erlaubt", "zugelassen", "investieren", "anlegen"]
        
        # Check if document allows investments
        has_permission = any(keyword in text_lower for keyword in permission_keywords)
        
        if has_permission:
            # Check each instrument type
            for instrument_type, keywords in instrument_keywords.items():
                if instrument_type in data["sections"]:
                    found_keywords = [kw for kw in keywords if kw in text_lower]
                    
                    if found_keywords:
                        # Mark all items in this section as allowed
                        for key in data["sections"][instrument_type]:
                            if key != "special_other_restrictions":
                                data["sections"][instrument_type][key]["allowed"] = True
                                data["sections"][instrument_type][key]["note"] = f"Keyword analysis: Found {', '.join(found_keywords)}"
                                data["sections"][instrument_type][key]["evidence"] = {
                                    "page": 1,
                                    "text": f"Document mentions: {', '.join(found_keywords)}"
                                }
        
        return data
    
    async def _analyze_with_llm(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str, trace_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """LLM-based analysis - returns (structured_data, raw_analysis)"""
        try:
            logger.info(f"🔍 Starting LLM analysis with {get_enum_value(llm_provider)}/{model}, text length: {len(text)}")
            
            # Get LLM analysis
            analysis = await self.llm_service.analyze_document(text, get_enum_value(llm_provider), model, trace_id)
            
            # Log what LLM returned
            if isinstance(analysis, dict):
                instrument_count = len(analysis.get("instrument_rules", []))
                sector_count = len(analysis.get("sector_rules", []))
                country_count = len(analysis.get("country_rules", []))
                logger.info(f"📊 LLM returned: {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                
                if instrument_count > 0:
                    # Log first few instrument rules
                    for i, rule in enumerate(analysis.get("instrument_rules", [])[:3]):
                        allowed_val = rule.get("allowed") if isinstance(rule, dict) else getattr(rule, "allowed", None)
                        instrument_name = rule.get("instrument") if isinstance(rule, dict) else getattr(rule, "instrument", "unknown")
                        logger.info(f"  Instrument rule {i+1}: '{instrument_name}' = allowed={allowed_val}")
                else:
                    logger.warning("⚠️ LLM returned ZERO instrument rules! This is the root cause of 0 allowed instruments.")
            else:
                logger.error(f"❌ LLM returned non-dict response: {type(analysis)}")
            
            # Validate analysis response
            if not isinstance(analysis, dict):
                raise Exception(f"Invalid analysis response format: {type(analysis)}")
            
            # Convert LLM response using Excel mapping (includes negative logic detection)
            # Preserve original fund_id from data
            logger.info("🔄 Converting LLM response to OCRD format...")
            converted_data = self._convert_llm_response_to_ocrd_format(analysis, full_text=text)
            logger.info(f"✅ Conversion complete. Notes count: {len(converted_data.get('notes', []))}")
            # Merge with original data structure to preserve fund_id
            converted_data["fund_id"] = data.get("fund_id", "compliance_analysis")
            data = converted_data
            
            # Legacy code below - keeping for backward compatibility but not used if Excel mapping is active
            # Apply LLM results to data structure using helper function
            # self._apply_llm_decision(data, analysis, llm_provider, "bonds", list(data["sections"]["bond"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "stocks", list(data["sections"]["stock"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "funds", list(data["sections"]["fund"].keys()))
            
            # Handle derivatives for both future and option sections
            try:
                derivatives_decision = analysis.get("derivatives", {}).get("allowed")
                evidence_text = analysis.get("derivatives", {}).get("evidence", "")
                
                if derivatives_decision == True:
                    for key in data["sections"]["future"]:
                        if key != "special_other_restrictions":
                            data["sections"]["future"][key]["allowed"] = True
                            data["sections"]["future"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
                            data["sections"]["future"][key]["evidence"] = {
                                "page": 1,
                                "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                            }
                    for key in data["sections"]["option"]:
                        if key != "special_other_restrictions":
                            data["sections"]["option"][key]["allowed"] = True
                            data["sections"]["option"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
                            data["sections"]["option"][key]["evidence"] = {
                                "page": 1,
                                "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                            }
                elif derivatives_decision == "Uncertain":
                    for key in data["sections"]["future"]:
                        if key != "special_other_restrictions":
                            data["sections"]["future"][key]["allowed"] = False
                            data["sections"]["future"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives uncertain - {evidence_text}"
                            data["sections"]["future"][key]["evidence"] = {
                                "page": 1,
                                "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                            }
                    for key in data["sections"]["option"]:
                        if key != "special_other_restrictions":
                            data["sections"]["option"][key]["allowed"] = False
                            data["sections"]["option"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives uncertain - {evidence_text}"
                            data["sections"]["option"][key]["evidence"] = {
                                "page": 1,
                                "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                            }
            except Exception as e:
                logger.error(f"Error processing derivatives: {e}", exc_info=True)
                # Set derivatives to uncertain on error
                for key in data["sections"]["future"]:
                    if key != "special_other_restrictions":
                        data["sections"]["future"][key]["allowed"] = False
                        data["sections"]["future"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives error - {str(e)}"
                        data["sections"]["future"][key]["evidence"] = {
                            "page": 1,
                            "text": f"Error processing derivatives: {str(e)}"
                        }
                for key in data["sections"]["option"]:
                    if key != "special_other_restrictions":
                        data["sections"]["option"][key]["allowed"] = False
                        data["sections"]["option"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives error - {str(e)}"
                        data["sections"]["option"][key]["evidence"] = {
                            "page": 1,
                            "text": f"Error processing derivatives: {str(e)}"
                        }
            
            return data, analysis
            
        except Exception as e:
            logger.error(f"LLM analysis error: {e}", exc_info=True)
            # Return data with error notes instead of failing completely
            for section_name in ["bond", "stock", "fund", "future", "option"]:
                if section_name in data["sections"]:
                    for key in data["sections"][section_name]:
                        if key != "special_other_restrictions":
                            data["sections"][section_name][key]["allowed"] = False
                            data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Analysis error - {str(e)}"
                            data["sections"][section_name][key]["evidence"] = {
                                "page": 1,
                                "text": f"Analysis failed: {str(e)}"
                            }
            return data, {}
    
    async def _analyze_with_llm_traced(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str, trace_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """LLM-based analysis with forensic tracing - returns (structured_data, raw_analysis)"""
        try:
            logger.info(f"🔍 Starting LLM analysis (TRACED) with {get_enum_value(llm_provider)}/{model}, text length: {len(text)}")
            
            # Get LLM analysis with tracing
            analysis = await self.llm_service.analyze_document_with_tracing(text, get_enum_value(llm_provider), model, trace_id)
            
            # Log what LLM returned
            if isinstance(analysis, dict):
                instrument_count = len(analysis.get("instrument_rules", []))
                sector_count = len(analysis.get("sector_rules", []))
                country_count = len(analysis.get("country_rules", []))
                logger.info(f"📊 LLM returned (TRACED): {instrument_count} instrument rules, {sector_count} sector rules, {country_count} country rules")
                
                if instrument_count > 0:
                    # Log first few instrument rules
                    for i, rule in enumerate(analysis.get("instrument_rules", [])[:3]):
                        allowed_val = rule.get("allowed") if isinstance(rule, dict) else getattr(rule, "allowed", None)
                        instrument_name = rule.get("instrument") if isinstance(rule, dict) else getattr(rule, "instrument", "unknown")
                        logger.info(f"  Instrument rule {i+1}: '{instrument_name}' = allowed={allowed_val}")
                else:
                    logger.warning("⚠️ LLM returned ZERO instrument rules! This is the root cause of 0 allowed instruments.")
            
            # Validate analysis response
            if not isinstance(analysis, dict):
                raise Exception(f"Invalid analysis response format: {type(analysis)}")
            
            # Convert LLM response using Excel mapping (includes negative logic detection)
            # This is the SAME conversion method used in _analyze_with_llm
            logger.info("🔄 Converting LLM response to OCRD format (TRACED)...")
            converted_data = self._convert_llm_response_to_ocrd_format(analysis, full_text=text)
            logger.info(f"✅ Conversion complete (TRACED). Notes count: {len(converted_data.get('notes', []))}")
            
            # Merge with original data structure to preserve fund_id
            converted_data["fund_id"] = data.get("fund_id", "compliance_analysis")
            data = converted_data
            
            # Legacy code below - keeping for backward compatibility but not used if Excel mapping is active
            # Apply LLM results to data structure using helper function
            # self._apply_llm_decision(data, analysis, llm_provider, "bonds", list(data["sections"]["bond"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "stocks", list(data["sections"]["stock"].keys()))
            # self._apply_llm_decision(data, analysis, llm_provider, "funds", list(data["sections"]["fund"].keys()))
            
            # Handle derivatives for both future and option sections
            derivatives_decision = analysis.get("derivatives", {}).get("allowed")
            evidence_text = analysis.get("derivatives", {}).get("evidence", "")
            
            if derivatives_decision == True:
                for key in data["sections"]["future"]:
                    if key != "special_other_restrictions":
                        data["sections"]["future"][key]["allowed"] = True
                        data["sections"]["future"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
                        data["sections"]["future"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
                for key in data["sections"]["option"]:
                    if key != "special_other_restrictions":
                        data["sections"]["option"][key]["allowed"] = True
                        data["sections"]["option"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives allowed - {evidence_text}"
                        data["sections"]["option"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
            elif derivatives_decision == "Uncertain":
                for key in data["sections"]["future"]:
                    if key != "special_other_restrictions":
                        data["sections"]["future"][key]["allowed"] = False
                        data["sections"]["future"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives uncertain - {evidence_text}"
                        data["sections"]["future"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                        }
                for key in data["sections"]["option"]:
                    if key != "special_other_restrictions":
                        data["sections"]["option"][key]["allowed"] = False
                        data["sections"]["option"][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): Derivatives uncertain - {evidence_text}"
                        data["sections"]["option"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                        }
            
            return data, analysis
            
        except Exception as e:
            raise Exception(f"LLM analysis failed: {str(e)}")
    
    def _apply_llm_decision(self, data: Dict[str, Any], analysis: Dict, llm_provider: LLMProvider, 
                           investment_type: str, section_keys: list) -> None:
        """Apply LLM decision to data structure, handling Uncertain responses"""
        try:
            # Map plural investment types to singular section names
            section_mapping = {
                "bonds": "bond",
                "stocks": "stock", 
                "funds": "fund",
                "derivatives": "future"  # Map derivatives to future section
            }
            
            section_name = section_mapping.get(investment_type, investment_type)
            
            decision = analysis.get(investment_type, {}).get("allowed")
            evidence_text = analysis.get(investment_type, {}).get("evidence", "")
            
            if decision == True:
                for key in section_keys:
                    if key != "special_other_restrictions":
                        data["sections"][section_name][key]["allowed"] = True
                        data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} allowed - {evidence_text}"
                        data["sections"][section_name][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else f"LLM analysis indicates {investment_type} are permitted"
                        }
            elif decision == "Uncertain":
                for key in section_keys:
                    if key != "special_other_restrictions":
                        data["sections"][section_name][key]["allowed"] = False
                        data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} uncertain - {evidence_text}"
                        data["sections"][section_name][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "Uncertain - no explicit statement found"
                        }
            # If decision is False or any other value, leave as default (False)
        except Exception as e:
            logger.error(f"Error applying LLM decision for {investment_type}: {e}", exc_info=True)
            # Set all items to uncertain on error
            for key in section_keys:
                if key != "special_other_restrictions":
                    data["sections"][section_name][key]["allowed"] = False
                    data["sections"][section_name][key]["note"] = f"LLM ({get_enum_value(llm_provider)}): {investment_type.title()} error - {str(e)}"
                    data["sections"][section_name][key]["evidence"] = {
                        "page": 1,
                        "text": f"Error processing {investment_type}: {str(e)}"
                    }

    def _validate_llm_response(self, llm_response: Dict[str, Any]) -> LLMResponse:
        """Validate LLM response using Pydantic models"""
        # Check for errors first
        if "error" in llm_response:
            raise ValueError(f"LLM failed: {llm_response['error']}")
        
        # Use Pydantic for automatic validation
        try:
            validated_response = LLMResponse.from_dict(llm_response)
            logger.debug(f"✅ LLM response validated successfully with Pydantic")
            return validated_response
        except Exception as e:
            # Provide helpful error message
            error_msg = str(e)
            logger.error(f"❌ LLM response validation failed: {error_msg}")
            raise ValueError(f"Invalid LLM response structure: {error_msg}")
    
    def _convert_llm_response_to_ocrd_format(self, llm_response: Dict[str, Any], full_text: Optional[str] = None) -> Dict[str, Any]:
        """Convert LLM response to OCRD format for Excel export"""
        # Validate using Pydantic (returns LLMResponse object)
        validated_response = self._validate_llm_response(llm_response)
        
        # Use validated response for type-safe access
        sector_count = len(validated_response.sector_rules)
        country_count = len(validated_response.country_rules)
        instrument_count = len(validated_response.instrument_rules)
        
        logger.info(f"📊 LLM Response validated: sector_rules={sector_count}, "
              f"country_rules={country_count}, "
              f"instrument_rules={instrument_count}")
        
        if instrument_count > 0:
            logger.info("📋 First 3 instrument rules from LLM:")
            for i, rule in enumerate(validated_response.instrument_rules[:3]):
                logger.info(f"  [{i+1}] instrument='{rule.instrument}', allowed={rule.allowed}, reason='{rule.reason[:80]}...'")
        else:
            logger.warning("⚠️ instrument_rules is EMPTY! LLM didn't extract any instrument rules.")
        
        # Use validated response for type-safe access
        sector_count = len(validated_response.sector_rules)
        country_count = len(validated_response.country_rules)
        instrument_count = len(validated_response.instrument_rules)
        
        # Create empty OCRD structure
        data = {"fund_id": "compliance_analysis", "as_of": None, "sections": {}, "notes": []}
        
        # Add debug info to notes so it's visible in results
        debug_info = f"[DEBUG] LLM returned: {sector_count} sector rules, {country_count} country rules, {instrument_count} instrument rules"
        data["notes"].append(debug_info)
        logger.debug(debug_info)
        
        # Log actual instrument rules if any (using validated response)
        if instrument_count > 0:
            logger.info("📋 Processing instrument rules details:")
            for i, rule in enumerate(validated_response.instrument_rules[:5]):
                logger.info(f"  [{i+1}] instrument='{rule.instrument}', allowed={rule.allowed}, reason='{rule.reason[:100]}...'")
                data["notes"].append(
                    f"[DEBUG] Rule {i+1}: '{rule.instrument}' = {rule.allowed}"
                )
        
        # OCRD schema
        OCRD_SCHEMA = {
            "bond": ["covered_bond", "asset_backed_security", "mortgage_bond", "pfandbrief", "public_mortgage_bond", "convertible_bond_regular", "convertible_bond_coco", "reverse_convertible", "credit_linked_note", "commercial_paper", "genussscheine_bondlike", "inflation_linked", "participation_paper", "plain_vanilla_bond", "promissory_note", "warrant_linked_bond"],
            "certificate": ["bond_certificate", "commodity_certificate", "currency_certificate", "fund_certificate", "index_certificate", "stock_certificate"],
            "stock": ["common_stock", "depositary_receipt", "genussschein_stocklike", "partizipationsschein", "preferred_stock", "reit", "right"],
            "fund": ["alternative_investment_fund", "commodity_fund", "equity_fund", "fixed_income_fund", "mixed_allocation_fund", "moneymarket_fund", "private_equity_fund", "real_estate_fund", "speciality_fund"],
            "deposit": ["call_money", "cash", "time_deposit"],
            "future": ["bond_future", "commodity_future", "currency_future", "fund_future", "index_future", "single_stock_future"],
            "option": ["bond_future_option", "commodity_future_option", "commodity_option", "currency_future_option", "currency_option", "fund_future_option", "fund_option", "index_future_option", "index_option", "stock_option"],
            "warrant": ["commodity_warrant", "currency_warrant", "fund_warrant", "index_warrant", "stock_warrant"],
            "commodity": ["precious_metal"],
            "forex": ["forex_outright", "forex_spot"],
            "swap": ["credit_default_swap", "interest_swap", "total_return_swap"],
            "loan": [],
            "private_equity": [],
            "real_estate": [],
            "rights": ["subscription_rights"]
        }
        
        # Initialize sections
        for section, rows in OCRD_SCHEMA.items():
            data["sections"][section] = {}
            for r in rows:
                data["sections"][section][r] = {"allowed": False, "note": "", "evidence": {"page": None, "text": ""}}
            if section in ("stock", "fund", "bond", "certificate", "deposit", "future", "option", "warrant", "commodity", "forex", "swap", "loan", "private_equity", "real_estate", "rights"):
                data["sections"][section]["special_other_restrictions"] = []
        
        # Apply sector rules (using validated response)
        for rule in validated_response.sector_rules:
            sector = rule.sector.lower()
            allowed = rule.allowed
            reason = rule.reason
            
            # Map sectors to relevant instrument types
            sector_mapping = {
                "energy": ["bond", "stock", "fund"],
                "healthcare": ["bond", "stock", "fund"],
                "defense": ["bond", "stock", "fund"],
                "tobacco": ["bond", "stock", "fund"],
                "gambling": ["bond", "stock", "fund"],
                "weapons": ["bond", "stock", "fund"]
            }
            
            affected_sections = sector_mapping.get(sector, ["bond", "stock", "fund"])
            for section in affected_sections:
                if section in data["sections"]:
                    for key in data["sections"][section]:
                        if key != "special_other_restrictions":
                            data["sections"][section][key]["allowed"] = allowed
                            data["sections"][section][key]["note"] = f"Sector rule: {sector} - {reason}"
                            data["sections"][section][key]["evidence"] = {
                                "page": 1,
                                "text": reason
                            }
        
        # Apply country rules (using validated response)
        for rule in validated_response.country_rules:
            country = rule.country
            allowed = rule.allowed
            reason = rule.reason
            
            # Add to notes
            data["notes"].append(f"Country rule: {country} - {'Allowed' if allowed else 'Prohibited'} - {reason}")
        
        # Apply instrument rules using Excel mapping if available (using validated response)
        processed_instruments = set()  # Track which instruments we've processed
        instrument_rules = validated_response.instrument_rules
        
        if not instrument_rules:
            logger.warning("⚠️ No instrument_rules extracted from LLM! This is why allowed_count is 0.")
            logger.warning("⚠️ Check if LLM is returning instrument_rules in the response")
            data["notes"].append("[WARNING] No instrument rules extracted from PDF. LLM may not have found any investment instruments mentioned.")
        else:
            logger.info(f"✅ Processing {len(instrument_rules)} instrument rules from LLM")
            allowed_count_in_rules = sum(1 for r in instrument_rules if r.allowed is True)
            logger.info(f"✅ {allowed_count_in_rules}/{len(instrument_rules)} rules have allowed=True")
            # Log first few rules for debugging
            for i, rule in enumerate(instrument_rules[:5]):
                logger.info(f"  Rule {i+1}: '{rule.instrument}' = allowed={rule.allowed}")
        
        for rule in instrument_rules:
            instrument = rule.instrument.lower().strip()
            allowed = rule.allowed
            reason = rule.reason
            
            logger.info(f"🔍 Processing rule: instrument='{instrument}', allowed={allowed}, reason='{reason[:100]}...'")
            
            # Check for negative logic if Excel mapping is available
            excel_mapping_succeeded = False  # Track if Excel mapping actually updated OCRD structure
            if self.excel_mapping:
                # Use Excel mapping to find matching entries
                # Use full text context if available for better negative logic detection
                context_for_matching = full_text if full_text else reason
                matching_entries = self.excel_mapping.find_matching_entries(instrument, context=context_for_matching)
                
                logger.info(f"🔍 Excel mapping for '{instrument}': found {len(matching_entries)} entries")
                if matching_entries:
                    for i, entry in enumerate(matching_entries[:3]):
                        logger.info(f"  Match {i+1}: '{entry.get('instrument_category', 'unknown')}' → Type1={entry.get('asset_tree_type1')}, Type2={entry.get('asset_tree_type2')}")
                else:
                    # Log what's available in the lookup for debugging
                    if self.excel_mapping and hasattr(self.excel_mapping, 'instrument_lookup'):
                        sample_keys = list(self.excel_mapping.instrument_lookup.keys())[:5]
                        logger.warning(f"⚠️ No matches found. Sample available keys: {sample_keys}")
                
                # Only check negative logic if we have matching entries (more reliable)
                if matching_entries:
                    # Check for negative logic in the full text context (better detection)
                    is_negative, neg_explanation = self.excel_mapping.detect_negative_logic(context_for_matching, instrument)
                    if is_negative:
                        allowed = not allowed  # Flip the logic
                        reason = f"{reason} [Negative logic detected: {neg_explanation}]"
                        logger.info(f"EXCEL MAPPING: Negative logic detected for '{instrument}': {neg_explanation}")
                
                # Update Excel mapping entries AND populate OCRD structure using Asset Tree
                for entry in matching_entries:
                    self.excel_mapping.update_allowed_status(entry['row_id'], allowed, reason)
                    logger.debug(f"EXCEL MAPPING: Updated entry '{entry['instrument_category']}' (row {entry['row_id']}) to allowed={allowed}")
                    
                    # Use Asset Tree to populate OCRD structure directly
                    type1 = entry.get('asset_tree_type1', '').lower().strip() if entry.get('asset_tree_type1') else None
                    type2 = entry.get('asset_tree_type2', '').lower().strip() if entry.get('asset_tree_type2') else None
                    type3 = entry.get('asset_tree_type3', '').lower().strip() if entry.get('asset_tree_type3') else None
                    
                    if type1 and type1 in data["sections"]:
                        # Map type2 to specific instrument names in OCRD schema
                        # This mapping is generated from Investment_Mapping.xlsx
                        type2_to_key = {
                            # Bonds
                            "plain vanilla bond": "plain_vanilla_bond",
                            "covered bond": "covered_bond",
                            "asset backed security": "asset_backed_security",
                            "mortgage bond": "mortgage_bond",
                            "pfandbrief": "pfandbrief",
                            "public mortgage bond": "public_mortgage_bond",
                            "convertible bond": "convertible_bond_regular",
                            "commercial paper": "commercial_paper",
                            "inflation linked": "inflation_linked",
                            "promissory note": "promissory_note",
                            "credit linked note": "credit_linked_note",
                            "warrant linked bond": "warrant_linked_bond",
                            "participation paper": "participation_paper",
                            "reverse convertible": "reverse_convertible",
                            # Stocks
                            "common stock": "common_stock",
                            "preferred stock": "preferred_stock",
                            "depositary receipt": "depositary_receipt",
                            "right": "right",
                            "partizipationsschein": "partizipationsschein",
                            "reit": "reit",
                            # Funds
                            "equity fund": "equity_fund",
                            "fixed income fund": "fixed_income_fund",
                            "moneymarket fund": "moneymarket_fund",
                            "real estate fund": "real_estate_fund",
                            "real estate": "real_estate_fund",
                            "alternative investment fund": "alternative_investment_fund",
                            "private equity fund": "private_equity_fund",
                            # Deposits
                            "cash": "cash",
                            "call money": "call_money",
                            "time deposit": "time_deposit",
                            # Futures
                            "bond future": "bond_future",
                            "index future": "index_future",
                            "currency future": "currency_future",
                            # Options
                            "currency option": "currency_option",
                            "index option": "index_option",
                            "stock option": "stock_option",
                            # Forex
                            "forex outright": "forex_outright",
                            # Commodities
                            "precious metal": "precious_metal",
                        }
                        
                        # Try to find matching key in section
                        section = data["sections"][type1]
                        matched_keys = []  # Can match multiple keys (e.g., from Type3 comma-separated values)
                        
                        # First try type2 mapping
                        if type2 and type2 in type2_to_key:
                            key = type2_to_key[type2]
                            if key in section:
                                matched_keys.append(key)
                        
                        # Handle Type3 - can contain multiple comma-separated instrument names
                        if type3 and type3 != 'nan':
                            type3_parts = [p.strip().lower() for p in type3.split(',')]
                            for part in type3_parts:
                                # Try direct mapping first
                                if part in type2_to_key:
                                    key = type2_to_key[part]
                                    if key in section and key not in matched_keys:
                                        matched_keys.append(key)
                                else:
                                    # Try fuzzy matching
                                    for key in section.keys():
                                        if key != "special_other_restrictions":
                                            key_normalized = key.replace("_", " ").lower()
                                            if part in key_normalized or key_normalized in part:
                                                if key not in matched_keys:
                                                    matched_keys.append(key)
                                                break
                        
                        # If no match from type2/type3, try fuzzy matching on type2
                        if not matched_keys and type2:
                            for key in section.keys():
                                if key != "special_other_restrictions":
                                    key_normalized = key.replace("_", " ").lower()
                                    if type2 in key_normalized or key_normalized in type2:
                                        matched_keys.append(key)
                                        break
                        
                        # Apply to matched keys
                        if matched_keys:
                            for matched_key in matched_keys:
                                section[matched_key]["allowed"] = allowed
                                section[matched_key]["note"] = f"Excel mapping: {entry['instrument_category']} - {reason}"
                                section[matched_key]["evidence"] = {"page": 1, "text": reason}
                            excel_mapping_succeeded = True
                            logger.info(f"✅ EXCEL MAPPING: Mapped '{entry['instrument_category']}' → {type1}/{matched_keys} = {allowed}")
                        # If still no match but type1 matches, apply to all in section (generic)
                        elif not matched_keys:
                        
                            # Apply to all instruments in this section
                            for key in section.keys():
                                if key != "special_other_restrictions":
                                    section[key]["allowed"] = allowed
                                    section[key]["note"] = f"Excel mapping: {entry['instrument_category']} - {reason}"
                                    section[key]["evidence"] = {"page": 1, "text": reason}
                            excel_mapping_succeeded = True
                            logger.info(f"✅ EXCEL MAPPING: Applied '{entry['instrument_category']}' to all instruments in '{type1}' section (allowed={allowed})")
                    else:
                        # type1 doesn't match any OCRD section - log warning
                        logger.warning(f"⚠️ EXCEL MAPPING: type1 '{type1}' not found in OCRD sections for instrument '{instrument}'. Entry: {entry.get('instrument_category', 'unknown')}")
                        data["notes"].append(
                            f"[WARNING] Excel mapping found entry for '{instrument}' but type1 '{type1}' doesn't match OCRD sections. Will try fallback matching."
                        )
                
                # CRITICAL FIX: Only mark as processed if Excel mapping actually succeeded in updating OCRD structure
                if excel_mapping_succeeded:
                    processed_instruments.add(instrument)
                    logger.info(f"✅ Excel mapping successfully processed '{instrument}' - skipping fallback logic")
                elif matching_entries:
                    # Excel mapping found entries but couldn't update OCRD (e.g., type1 mismatch)
                    # Don't mark as processed - let fallback logic handle it
                    logger.warning(f"⚠️ Excel mapping found {len(matching_entries)} entries for '{instrument}' but failed to update OCRD structure. Will try fallback matching.")
                else:
                    # No matching entries found - will use fallback logic
                    logger.debug(f"Excel mapping found no matches for '{instrument}' - will use fallback logic")
            
            # Skip if already processed by Excel mapping
            if instrument in processed_instruments:
                logger.debug(f"Skipping '{instrument}' - already processed by Excel mapping")
                continue
            
            # Fallback logic: Use direct instrument matching (when Excel mapping didn't work or isn't available)
            logger.info(f"🔄 Using fallback matching for '{instrument}' (Excel mapping didn't process it)")
            
            # Normalize instrument name (handle underscores, spaces, hyphens)
            instrument_normalized = instrument.replace("_", " ").replace("-", " ")
            
            # Build comprehensive mapping of instruments to sections and specific instrument names
            instrument_mapping = {
                # Generic terms
                "bonds": "bond",
                "bond": "bond",
                "equities": "stock",
                "equity": "stock",
                "stocks": "stock",
                "stock": "stock",
                "funds": "fund",
                "fund": "fund",
                "derivatives": "future",
                "options": "option",
                "option": "option",
                "futures": "future",
                "future": "future",
                "warrants": "warrant",
                "warrant": "warrant",
                "commodities": "commodity",
                "commodity": "commodity",
                "forex": "forex",
                "swaps": "swap",
                "swap": "swap",
                # Specific bond types
                "covered bond": "bond",
                "covered_bond": "bond",
                "asset backed security": "bond",
                "asset_backed_security": "bond",
                "asset-backed security": "bond",
                "mortgage bond": "bond",
                "mortgage_bond": "bond",
                "mortgage-bond": "bond",
                "pfandbrief": "bond",
                "convertible bond": "bond",
                "convertible_bond": "bond",
                "commercial paper": "bond",
                "commercial_paper": "bond",
                # Specific stock types
                "common stock": "stock",
                "common_stock": "stock",
                "preferred stock": "stock",
                "preferred_stock": "stock",
                # Specific fund types
                "equity fund": "fund",
                "equity_fund": "fund",
                "fixed income fund": "fund",
                "fixed_income_fund": "fund",
                "money market fund": "fund",
                "moneymarket_fund": "fund",
            }
            
            # First try exact match
            section = instrument_mapping.get(instrument) or instrument_mapping.get(instrument_normalized)
            
            # If no exact match, try partial matching
            if not section:
                for key, value in instrument_mapping.items():
                    if key in instrument or instrument in key:
                        section = value
                        break
            
            # If still no match, try to infer from instrument name
            if not section:
                if "bond" in instrument_normalized:
                    section = "bond"
                elif "stock" in instrument_normalized or "equity" in instrument_normalized:
                    section = "stock"
                elif "fund" in instrument_normalized:
                    section = "fund"
                elif "option" in instrument_normalized:
                    section = "option"
                elif "future" in instrument_normalized:
                    section = "future"
                elif "warrant" in instrument_normalized:
                    section = "warrant"
                elif "swap" in instrument_normalized:
                    section = "swap"
                elif "commodity" in instrument_normalized:
                    section = "commodity"
                elif "forex" in instrument_normalized or "currency" in instrument_normalized:
                    section = "forex"
            
            if section and section in data["sections"]:
                # Try to match specific instrument names within the section
                instrument_found = False
                
                # Check if instrument name is generic (just "bond", "stock", "fund" without specificity)
                is_generic = instrument_normalized in ["bond", "bonds", "stock", "stocks", "equity", "equities", 
                                                       "fund", "funds", "derivative", "derivatives", "option", "options",
                                                       "future", "futures", "warrant", "warrants", "swap", "swaps",
                                                       "commodity", "commodities", "forex", "currency"]
                
                # Normalize instrument to word list for flexible matching
                instrument_words = set(instrument_normalized.split())
                
                for key in data["sections"][section]:
                    if key != "special_other_restrictions":
                        # Normalize key name
                        key_normalized = key.replace("_", " ").replace("-", " ")
                        key_words = set(key_normalized.split())
                        
                        # Smart matching function that handles variations
                        def matches_flexibly(instrument_str: str, instrument_word_set: set, key_str: str, key_word_set: set) -> bool:
                            """Check if instrument matches key with flexible word matching"""
                            # Exact match
                            if instrument_str == key_str:
                                return True
                            
                            # One contains the other (handles "commodity certificate" -> "commodity_certificate")
                            if instrument_str in key_str or key_str in instrument_str:
                                return True
                            
                            # Word-based matching: check if all significant words from instrument are in key
                            # Significant words are those with 3+ characters (skip "the", "a", "an", etc.)
                            significant_instrument_words = {w for w in instrument_word_set if len(w) >= 3}
                            significant_key_words = {w for w in key_word_set if len(w) >= 3}
                            
                            # If all significant instrument words are in key words, it's a match
                            # E.g., "commodity certificate" -> ["commodity", "certificate"] both in "commodity_certificate"
                            if significant_instrument_words and significant_instrument_words.issubset(significant_key_words):
                                return True
                            
                            # Reverse: if all significant key words are in instrument words
                            if significant_key_words and significant_key_words.issubset(significant_instrument_words):
                                return True
                            
                            # Partial overlap: if at least 2 significant words match (handles subcategories)
                            # E.g., "certificate" should match "commodity_certificate" if certificate is the main word
                            overlap = significant_instrument_words & significant_key_words
                            if len(overlap) >= min(2, len(significant_instrument_words), len(significant_key_words)):
                                return True
                            
                            return False
                        
                        # Check if instrument matches this key
                        if matches_flexibly(instrument_normalized, instrument_words, key_normalized, key_words):
                            # Found specific match - only update this one
                            data["sections"][section][key]["allowed"] = allowed
                            data["sections"][section][key]["note"] = f"Instrument rule: {instrument} - {reason}"
                            data["sections"][section][key]["evidence"] = {
                                "page": 1,
                                "text": reason
                            }
                            instrument_found = True
                            match_msg = f"[DEBUG] ✓ Matched '{instrument}' → '{key}' in '{section}' (allowed={allowed})"
                            logger.info(match_msg)  # Changed to info level for better visibility
                            data["notes"].append(match_msg)  # Add to notes for visibility
                            break  # Stop after first match to avoid duplicate matches
                
                # CRITICAL: For generic terms, apply to ALL instruments in that section
                if not instrument_found and is_generic:
                    logger.info(f"✅ Generic instrument term '{instrument}' found - applying to ALL instruments in '{section}' section (allowed={allowed})")
                    for key in data["sections"][section]:
                        if key != "special_other_restrictions":
                            data["sections"][section][key]["allowed"] = allowed
                            data["sections"][section][key]["note"] = f"Instrument rule: {instrument} - {reason}"
                            data["sections"][section][key]["evidence"] = {
                                "page": 1,
                                "text": reason
                            }
                    instrument_found = True
                    generic_msg = f"Generic instrument rule applied broadly: {instrument} = {'Allowed' if allowed else 'Not Allowed'}. Reason: {reason}"
                    logger.info(f"✅ {generic_msg}")
                    data["notes"].append(generic_msg)
                elif not instrument_found and section:
                    # Non-generic term but no match - apply to all instruments in section as fallback
                    logger.warning(f"⚠️ Could not match instrument '{instrument}' to specific instrument in '{section}', applying to ALL in section (allowed={allowed})")
                    for key in data["sections"][section]:
                        if key != "special_other_restrictions":
                            data["sections"][section][key]["allowed"] = allowed
                            data["sections"][section][key]["note"] = f"Instrument rule: {instrument} - {reason}"
                            data["sections"][section][key]["evidence"] = {
                                "page": 1,
                                "text": reason
                            }
                    unmatched_msg = f"Unmatched instrument rule applied broadly: {instrument} = {'Allowed' if allowed else 'Not Allowed'}. Reason: {reason}"
                    logger.info(f"✅ {unmatched_msg}")
                    data["notes"].append(unmatched_msg)
                elif not section:
                    # Couldn't even determine which section this belongs to
                    logger.error(f"Could not determine section for instrument '{instrument}'")
                    data["notes"].append(
                        f"ERROR: Unmatched instrument rule '{instrument}' = {'Allowed' if allowed else 'Not Allowed'}. "
                        f"Could not determine instrument category. Reason: {reason}"
                    )
        
        # Add conflicts to notes (using validated response)
        for conflict in validated_response.conflicts:
            data["notes"].append(f"Conflict: {conflict.category} - {conflict.detail}")
        
        # Final debug: Count how many instruments were actually set to allowed
        final_allowed_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and value.get("allowed") is True
        )
        
        # Count total instruments
        total_instruments_count = sum(
            1 for section in data["sections"].values()
            for key, value in section.items()
            if isinstance(value, dict) and "allowed" in value
        )
        
        final_debug = f"[DEBUG] After processing: {final_allowed_count}/{total_instruments_count} instruments set to allowed=True"
        data["notes"].append(final_debug)
        
        if final_allowed_count == 0:
            logger.warning(f"⚠️ {final_debug} - This might indicate a problem!")
            data["notes"].append(
                "[WARNING] No instruments were marked as allowed. Check logs for details about why rules weren't applied."
            )
        else:
            logger.info(f"✅ {final_debug}")
        
        return data

    def _calculate_metrics(self, data: Dict[str, Any]) -> tuple:
        """Calculate analysis metrics"""
        total_instruments = 0
        allowed_instruments = 0
        evidence_count = 0
        
        for section, items in data.get("sections", {}).items():
            for key, value in items.items():
                if isinstance(value, dict) and "allowed" in value:
                    total_instruments += 1
                    if value.get("allowed"):
                        allowed_instruments += 1
                        if value.get("evidence", {}).get("text"):
                            evidence_count += 1
        
        evidence_coverage = int((evidence_count / allowed_instruments * 100)) if allowed_instruments > 0 else 0
        
        return total_instruments, allowed_instruments, evidence_coverage
    
    def _calculate_confidence_score(self, data: Dict[str, Any], evidence_coverage: int, model: str, raw_analysis: Dict[str, Any]) -> int:
        """
        Calculate confidence score (0-100) based on:
        - Evidence quality and coverage
        - Model type (gpt-5 has higher base confidence)
        - Number of conflicts found
        - Evidence text quality (length, specificity)
        """
        base_score = 50  # Start with 50%
        
        # Model confidence boost
        model_confidence_boost = {
            "gpt-4o": 20,  # Highest quality model
            "gpt-4-turbo": 18,
            "gpt-4": 15,
            "gpt-4o-mini": 10,
            "gpt-3.5-turbo": 5
        }
        base_score += model_confidence_boost.get(model.lower(), 5)
        
        # Evidence coverage (0-25 points)
        evidence_score = (evidence_coverage / 100) * 25
        base_score += evidence_score
        
        # Evidence quality (0-15 points)
        evidence_quality_score = 0
        evidence_length_sum = 0
        evidence_count = 0
        
        for section, items in data.get("sections", {}).items():
            for key, value in items.items():
                if isinstance(value, dict) and value.get("allowed"):
                    evidence_text = value.get("evidence", {}).get("text", "")
                    if evidence_text:
                        evidence_length_sum += len(evidence_text)
                        evidence_count += 1
        
        if evidence_count > 0:
            avg_evidence_length = evidence_length_sum / evidence_count
            # Longer evidence texts (more specific) = higher confidence
            # 50 chars = 5 points, 100 chars = 10 points, 200+ chars = 15 points
            if avg_evidence_length >= 200:
                evidence_quality_score = 15
            elif avg_evidence_length >= 100:
                evidence_quality_score = 10
            elif avg_evidence_length >= 50:
                evidence_quality_score = 5
        
        base_score += evidence_quality_score
        
        # Conflicts penalty (0-10 points deduction)
        conflicts = raw_analysis.get("conflicts", [])
        conflicts_penalty = min(len(conflicts) * 2, 10)  # Max 10 point deduction
        base_score -= conflicts_penalty
        
        # Total rules found (0-10 points)
        # More rules extracted = better understanding
        sector_rules = len(raw_analysis.get("sector_rules", []))
        country_rules = len(raw_analysis.get("country_rules", []))
        instrument_rules = len(raw_analysis.get("instrument_rules", []))
        total_rules = sector_rules + country_rules + instrument_rules
        
        if total_rules >= 10:
            base_score += 10
        elif total_rules >= 5:
            base_score += 5
        elif total_rules >= 2:
            base_score += 2
        
        # Ensure score is between 0 and 100
        confidence_score = max(0, min(100, int(base_score)))
        
        return confidence_score
    
    async def create_excel_from_llm_response(self, llm_response: Dict[str, Any], filename: str = None) -> str:
        """Create Excel export from validated LLM response"""
        try:
            # Convert LLM response to OCRD format (includes validation)
            ocrd_data = self._convert_llm_response_to_ocrd_format(llm_response)
            
            # Create Excel export
            excel_path = await self.file_handler.create_excel_export(ocrd_data)
            
            return excel_path
            
        except Exception as e:
            raise Exception(f"Failed to create Excel from LLM response: {str(e)}")
    
    def validate_and_preview_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate LLM response and return preview for debugging"""
        try:
            # Validate the response (returns LLMResponse object)
            validated_response = self._validate_llm_response(llm_response)
            
            # Return preview using validated response
            preview = {
                "valid": True,
                "sector_rules_count": len(validated_response.sector_rules),
                "country_rules_count": len(validated_response.country_rules),
                "instrument_rules_count": len(validated_response.instrument_rules),
                "conflicts_count": len(validated_response.conflicts),
                "preview": {
                    "sector_rules": [r.model_dump() for r in validated_response.sector_rules[:3]],
                    "country_rules": [r.model_dump() for r in validated_response.country_rules[:3]],
                    "instrument_rules": [r.model_dump() for r in validated_response.instrument_rules[:3]],
                    "conflicts": [c.model_dump() for c in validated_response.conflicts[:3]]
                }
            }
            
            return preview
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "llm_response": llm_response
            }
