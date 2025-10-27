import time
from typing import Dict, Any, Optional
from datetime import datetime
from .llm_service import LLMService
from ..models.analysis_models import AnalysisResult, AnalysisMethod, LLMProvider
from ..utils.trace_handler import TraceHandler

class AnalysisService:
    """Core analysis service that orchestrates document analysis"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.trace_handler = TraceHandler()
    
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
        
        # COMMENTED OUT: Only using OpenAI API for now
        # if analysis_method == AnalysisMethod.KEYWORDS:
        #     # Use fast keyword analysis
        #     result = self._analyze_with_keywords(data, text)
        #     analysis_method_used = "keywords"
        #     
        # elif analysis_method == AnalysisMethod.LLM:
        #     # Use LLM analysis only
        #     result = await self._analyze_with_llm(data, text, llm_provider, model)
        #     analysis_method_used = f"llm_{llm_provider.value}"
        #     
        # elif analysis_method == AnalysisMethod.LLM_WITH_FALLBACK:
        #     # Try LLM first, fallback to keywords
        #     try:
        #         result = await self._analyze_with_llm(data, text, llm_provider, model)
        #         analysis_method_used = f"llm_{llm_provider.value}"
        #     except Exception as e:
        #         print(f"LLM failed ({e}), using keyword fallback")
        #         result = self._analyze_with_keywords(data, text)
        #         analysis_method_used = "keywords_fallback"
        
        # ONLY USING OPENAI API - All requests go through OpenAI
        if trace_id:
            result = await self._analyze_with_llm_traced(data, text, llm_provider, model, trace_id)
        else:
            result = await self._analyze_with_llm(data, text, llm_provider, model)
        analysis_method_used = f"llm_{llm_provider.value}"
        
        processing_time = time.time() - start_time
        
        # Calculate metrics
        total_instruments, allowed_instruments, evidence_coverage = self._calculate_metrics(result)
        
        return {
            "fund_id": fund_id,
            "analysis_method": analysis_method_used,
            "llm_provider": llm_provider.value,
            "model": model,
            "total_instruments": total_instruments,
            "allowed_instruments": allowed_instruments,
            "evidence_coverage": evidence_coverage,
            "sections": result["sections"],
            "processing_time": round(processing_time, 2),
            "created_at": datetime.now().isoformat()
        }
    
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
    
    async def _analyze_with_llm(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str) -> Dict[str, Any]:
        """LLM-based analysis"""
        try:
            # Get LLM analysis
            analysis = await self.llm_service.analyze_document(text, llm_provider.value, model)
            
            # Apply LLM results to data structure
            if analysis.get("bonds", {}).get("allowed"):
                evidence_text = analysis.get("bonds", {}).get("evidence", "")
                for key in data["sections"]["bond"]:
                    if key != "special_other_restrictions":
                        data["sections"]["bond"][key]["allowed"] = True
                        data["sections"]["bond"][key]["note"] = f"LLM ({llm_provider.value}): Bonds allowed"
                        data["sections"]["bond"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates bonds are permitted"
                        }
            
            if analysis.get("stocks", {}).get("allowed"):
                evidence_text = analysis.get("stocks", {}).get("evidence", "")
                for key in data["sections"]["stock"]:
                    if key != "special_other_restrictions":
                        data["sections"]["stock"][key]["allowed"] = True
                        data["sections"]["stock"][key]["note"] = f"LLM ({llm_provider.value}): Stocks allowed"
                        data["sections"]["stock"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates stocks are permitted"
                        }
            
            if analysis.get("funds", {}).get("allowed"):
                evidence_text = analysis.get("funds", {}).get("evidence", "")
                for key in data["sections"]["fund"]:
                    if key != "special_other_restrictions":
                        data["sections"]["fund"][key]["allowed"] = True
                        data["sections"]["fund"][key]["note"] = f"LLM ({llm_provider.value}): Funds allowed"
                        data["sections"]["fund"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates funds are permitted"
                        }
            
            if analysis.get("derivatives", {}).get("allowed"):
                evidence_text = analysis.get("derivatives", {}).get("evidence", "")
                for key in data["sections"]["future"]:
                    if key != "special_other_restrictions":
                        data["sections"]["future"][key]["allowed"] = True
                        data["sections"]["future"][key]["note"] = f"LLM ({llm_provider.value}): Derivatives allowed"
                        data["sections"]["future"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
                for key in data["sections"]["option"]:
                    if key != "special_other_restrictions":
                        data["sections"]["option"][key]["allowed"] = True
                        data["sections"]["option"][key]["note"] = f"LLM ({llm_provider.value}): Derivatives allowed"
                        data["sections"]["option"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
            
            return data
            
        except Exception as e:
            raise Exception(f"LLM analysis failed: {str(e)}")
    
    async def _analyze_with_llm_traced(self, data: Dict[str, Any], text: str, llm_provider: LLMProvider, model: str, trace_id: str) -> Dict[str, Any]:
        """LLM-based analysis with forensic tracing"""
        try:
            # Get LLM analysis with tracing
            analysis = await self.llm_service.analyze_document_with_tracing(text, llm_provider.value, model, trace_id)
            
            # Apply LLM results to data structure
            if analysis.get("bonds", {}).get("allowed"):
                evidence_text = analysis.get("bonds", {}).get("evidence", "")
                for key in data["sections"]["bond"]:
                    if key != "special_other_restrictions":
                        data["sections"]["bond"][key]["allowed"] = True
                        data["sections"]["bond"][key]["note"] = f"LLM ({llm_provider.value}): Bonds allowed"
                        data["sections"]["bond"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates bonds are permitted"
                        }
            
            if analysis.get("stocks", {}).get("allowed"):
                evidence_text = analysis.get("stocks", {}).get("evidence", "")
                for key in data["sections"]["stock"]:
                    if key != "special_other_restrictions":
                        data["sections"]["stock"][key]["allowed"] = True
                        data["sections"]["stock"][key]["note"] = f"LLM ({llm_provider.value}): Stocks allowed"
                        data["sections"]["stock"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates stocks are permitted"
                        }
            
            if analysis.get("funds", {}).get("allowed"):
                evidence_text = analysis.get("funds", {}).get("evidence", "")
                for key in data["sections"]["fund"]:
                    if key != "special_other_restrictions":
                        data["sections"]["fund"][key]["allowed"] = True
                        data["sections"]["fund"][key]["note"] = f"LLM ({llm_provider.value}): Funds allowed"
                        data["sections"]["fund"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates funds are permitted"
                        }
            
            if analysis.get("derivatives", {}).get("allowed"):
                evidence_text = analysis.get("derivatives", {}).get("evidence", "")
                for key in data["sections"]["future"]:
                    if key != "special_other_restrictions":
                        data["sections"]["future"][key]["allowed"] = True
                        data["sections"]["future"][key]["note"] = f"LLM ({llm_provider.value}): Derivatives allowed"
                        data["sections"]["future"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
                for key in data["sections"]["option"]:
                    if key != "special_other_restrictions":
                        data["sections"]["option"][key]["allowed"] = True
                        data["sections"]["option"][key]["note"] = f"LLM ({llm_provider.value}): Derivatives allowed"
                        data["sections"]["option"][key]["evidence"] = {
                            "page": 1,
                            "text": evidence_text if evidence_text else "LLM analysis indicates derivatives are permitted"
                        }
            
            return data
            
        except Exception as e:
            raise Exception(f"LLM analysis failed: {str(e)}")
    
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
