import httpx
import json
import os
import time
from typing import Dict, List, Optional
from openai import AsyncOpenAI
import openai
from .interfaces.llm_provider_interface import LLMProviderInterface
from .providers.openai_provider import OpenAIProvider
from ..utils.trace_handler import TraceHandler
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# Robust system prompt for compliance analysis
SYSTEM_PROMPT = """You are a senior compliance analyst specializing in investment rules.

CRITICAL INSTRUCTIONS - READ CAREFULLY:

1. DEFAULT ASSUMPTION: If a rule is NOT explicitly stated, DO NOT mark it as "not allowed". Only mark as "not allowed" if the document EXPLICITLY prohibits or restricts it.

2. PRIORITIZE FINDING ALLOWED ITEMS: Actively search for and extract ALL items that are explicitly stated as ALLOWED, PERMITTED, or AUTHORIZED. These are just as important as prohibited items.

3. RECOGNIZE ALLOWED LANGUAGE (mark as allowed=true):
   - "permitted", "allowed", "authorized", "approved", "may invest", "can invest"
   - "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"
   - "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
   - Lists of permitted instruments, sectors, or countries
   - Positive statements like "investments in [X] are permitted"

4. RECOGNIZE PROHIBITED LANGUAGE (mark as allowed=false):
   - "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
   - "investments in X are not allowed", "prohibited from investing in..."

5. INSTRUMENT NAME VARIATIONS: Recognize that these refer to the SAME instrument type:
   - "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
   - "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
   - "derivatives" includes: options, futures, forwards, swaps, warrants
   - Extract the specific instrument name as stated in the document

6. EXTRACTION RULES:
   - Extract rules that are CLEARLY stated in the document (don't invent rules)
   - Look for buried rules in tables, footnotes, appendices - search the ENTIRE document
   - Extract rules even if stated indirectly (e.g., "prohibited from investing in tobacco" = tobacco sector not allowed)
   - Do NOT mix different rule categories (keep sectors, countries, instruments separate)
   - If text is unclear or contradictory, record it in conflicts section

7. CRITICAL: DO NOT OVER-GENERALIZE RULES
   - A rule about "securities with equity character are allowed" does NOT mean ALL bonds are allowed
   - A rule about "equity index options are allowed" does NOT mean ALL convertible bonds are allowed
   - A rule about "unlisted equities are allowed" does NOT mean ALL debt instruments are allowed
   - ONLY extract rules for instruments that are EXPLICITLY mentioned in the rule statement
   - Example: If document says "convertible bonds are allowed" → extract rule for "convertible bonds" specifically
   - Example: If document says "securities with equity character are allowed" → ONLY extract for instruments explicitly described as having equity character, NOT for regular bonds
   - DO NOT assume that a general rule applies to all similar instruments

8. CRITICAL: If the document explicitly states "FX Forwards are allowed" or "currency futures are permitted", you MUST extract this as an instrument rule with allowed=true. Do NOT miss these positive permission statements.

Your task: Systematically search through the ENTIRE document and extract ALL rules - prioritize finding what IS ALLOWED, then what is NOT ALLOWED. Extract every explicitly stated permission or prohibition.

Return ONLY valid JSON matching the required schema:
{
  "sector_rules": [
    {"sector": "string", "allowed": true/false, "reason": "string"}
  ],
  "country_rules": [
    {"country": "string", "allowed": true/false, "reason": "string"}
  ],
  "instrument_rules": [
    {"instrument": "string", "allowed": true/false, "reason": "string"}
  ],
  "conflicts": [
    {"category": "string", "detail": "string"}
  ]
}"""


class LLMService:
    """Service for managing different LLM providers with fallback and validation"""
    
    def __init__(self):
        # Get API key - make it optional for graceful degradation
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Initialize client only if API key is available
        self.client = None
        if api_key:
            try:
                # Create a custom httpx client without proxies to avoid compatibility issues
                # This prevents the "unexpected keyword argument 'proxies'" error
                # Use connection pooling for faster requests (reuse connections)
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(60.0, connect=10.0),  # Longer timeout for large docs, fast connection
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    # Explicitly don't pass proxies parameter
                )
                
                # Initialize AsyncOpenAI client with custom http_client
                self.client = AsyncOpenAI(
                    api_key=api_key,
                    http_client=http_client
                )
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {str(e)}")
                logger.warning("OpenAI API key not found. Embedding generation will be disabled.")
                self.client = None
        else:
            logger.warning("OpenAI API key not found. Embedding generation will be disabled.")
        
        self.providers = {
            "openai": OpenAIProvider()
        }
        self.trace_handler = TraceHandler()
    
    def get_provider(self, provider_name: str) -> LLMProviderInterface:
        """Get LLM provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return self.providers[provider_name]
    
    async def analyze_text(self, prompt_text: str) -> dict:
        """Analyze text using the new OpenAI client with robust system prompt"""
        if not self.client:
            return {"error": "OpenAI client not initialized. Please set OPENAI_API_KEY environment variable."}
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_text}
                ]
            )
            raw = response.choices[0].message.content

            # try to parse JSON safely
            cleaned = raw.strip().strip("```json").strip("```")
            return json.loads(cleaned)

        except Exception as e:
            logger.error(f"LLM Error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def analyze_document(self, text: str, provider: str, model: str, trace_id: Optional[str] = None) -> Dict:
        """Analyze document using new OpenAI client with robust system prompt"""
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
        
        # Calculate safe text limit based on model
        # GPT-4: 8k tokens, GPT-4o/GPT-4o-mini: 128k tokens
        if model == "gpt-4":
            # GPT-4 has 8192 token limit: reserve ~1200 for enhanced prompts, ~2500 for completion
            max_text_length = 14000  # More conservative for GPT-4
        else:
            # Modern models (GPT-4o, GPT-4o-mini) have 128k context window
            max_text_length = 100000  # Full limit for comprehensive document analysis
        
        # Truncate only if text exceeds safe limit
        text_to_analyze = text if len(text) <= max_text_length else text[:max_text_length]
        if len(text) > max_text_length:
            logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for analysis")
        
        # Enhanced prompt that strongly emphasizes finding ALLOWED items
        user_prompt = f"""You are analyzing an investment policy document. Your PRIMARY goal is to find ALL items that are explicitly stated as ALLOWED or PERMITTED.

**STEP 1: SEARCH FOR ALLOWED ITEMS FIRST**
Actively search for and extract EVERY item explicitly stated as:
- "allowed", "permitted", "authorized", "approved", "may invest", "can invest"
- "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
- Lists of permitted instruments, sectors, or countries
- Any positive statement granting permission

**STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
Extract items explicitly stated as:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (use the exact name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants

**WHAT TO EXTRACT:**
- Sectors: Energy, Healthcare, Defense, Tobacco, Weapons, Technology, etc.
- Countries: USA, China, Russia, Europe, UK, etc.
- Instruments: Use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", etc.)

**CRITICAL RULES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "Document explicitly states FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "Document explicitly states currency futures are permitted"}}
3. DO NOT mark something as "not allowed" unless explicitly prohibited
4. Search ENTIRE document - rules can be in any section, table, footnote, or appendix

**Return JSON only:**
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

**Document text to analyze (search through ALL of it systematically):**
{text_to_analyze}"""

        if trace_id:
            prompt_data = {
                "model": model,
                "temperature": 0,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "provider": provider,
                "text_length": len(text),
                "text_preview": text[:500] + "..." if len(text) > 500 else text,
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": user_prompt
            }
            await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            # Use new OpenAI client approach with optimized settings for speed
            # GPT-4 has 8k context window, enhanced prompts are longer, so reduce max_tokens further
            # Reserve ~2500 tokens for completion to leave room for input (~5500 tokens with enhanced prompts)
            max_tokens = 2500 if model == "gpt-4" else 4000
            
            response = await self.client.chat.completions.create(
                model=model,
                temperature=0,  # Deterministic for faster processing
                max_tokens=max_tokens,  # Adjusted for GPT-4's 8k context limit
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw = response.choices[0].message.content

            # Save raw LLM response to trace file (before parsing to rule out parser errors)
            if trace_id:
                trace_dir = self.trace_handler.get_trace_dir(trace_id)
                os.makedirs(trace_dir, exist_ok=True)
                raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                with open(raw_response_path, 'w', encoding='utf-8') as f:
                    f.write(raw)

            # Parse JSON safely
            cleaned = raw.strip().strip("```json").strip("```")
            result = json.loads(cleaned)
            
            # Validate and return
            validated_result = self._validate_result(result)
            
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "result": validated_result,
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": True
                })
            
            return validated_result
            
        except Exception as e:
            err_msg = str(e).lower()
            
            # Handle model not available - try fallback models
            if "404" in err_msg or "does not exist" in err_msg:
                logger.warning(f"Model '{model}' unavailable. Falling back to 'gpt-4o-mini'")
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw = response.choices[0].message.content
                    
                    # Save raw LLM response to trace file (fallback model)
                    if trace_id:
                        trace_dir = self.trace_handler.get_trace_dir(trace_id)
                        os.makedirs(trace_dir, exist_ok=True)
                        raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                        with open(raw_response_path, 'w', encoding='utf-8') as f:
                            f.write(raw)
                    
                    cleaned = raw.strip().strip("```json").strip("```")
                    result = json.loads(cleaned)
                    return self._validate_result(result)
                except Exception as inner_e:
                    logger.warning("gpt-4o-mini also failed, falling back to 'gpt-3.5-turbo'")
                    response = await self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        temperature=0,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    raw = response.choices[0].message.content
                    
                    # Save raw LLM response to trace file (fallback model)
                    if trace_id:
                        trace_dir = self.trace_handler.get_trace_dir(trace_id)
                        os.makedirs(trace_dir, exist_ok=True)
                        raw_response_path = os.path.join(trace_dir, f"{trace_id}_llm_raw.txt")
                        with open(raw_response_path, 'w', encoding='utf-8') as f:
                            f.write(raw)
                    
                    cleaned = raw.strip().strip("```json").strip("```")
                    result = json.loads(cleaned)
                    return self._validate_result(result)
            
            if trace_id:
                await self.trace_handler.save_llm_response(trace_id, {
                    "provider": provider,
                    "model": model,
                    "error": str(e),
                    "timestamp": time.time(),
                    "trace_id": trace_id,
                    "success": False
                })
            
            raise e

    async def analyze_document_with_tracing(self, text: str, provider: str, model: str, trace_id: str) -> Dict:
        """Analyze document with forensic tracing and validation"""
        provider_instance = self.get_provider(provider)
        messages = await self._get_llm_messages(provider_instance, text, model)

        prompt_data = {
            "model": model,
            "temperature": 0.1,
            "timestamp": time.time(),
            "trace_id": trace_id,
            "provider": provider,
            "text_length": len(text),
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "messages": messages
        }
        await self.trace_handler.save_llm_prompt(trace_id, prompt_data)

        try:
            result = await provider_instance.analyze_document(text, model)
            validated = self._validate_result(result)
            await self.trace_handler.save_llm_response(trace_id, {
                "provider": provider,
                "model": model,
                "result": validated,
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": True
            })
            return validated

        except Exception as e:
            await self.trace_handler.save_llm_response(trace_id, {
                "provider": provider,
                "model": model,
                "error": str(e),
                "timestamp": time.time(),
                "trace_id": trace_id,
                "success": False
            })
            raise e
    
    def get_ollama_models(self) -> List[str]:
        """Get available Ollama models"""
        try:
            return self.providers["ollama"].get_available_models()
        except Exception:
            return []
    
    def get_openai_models(self) -> List[str]:
        """Get available OpenAI models"""
        return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

    def _validate_result(self, result: Dict) -> Dict:
        """Strictly validate the LLM output structure for compliance analysis"""
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM output: {result}")

        expected_keys = {"sector_rules", "country_rules", "instrument_rules", "conflicts"}
        missing = expected_keys - set(result.keys())
        if missing:
            raise ValueError(f"Missing expected keys in LLM output: {missing}")

        return result

    async def _get_llm_messages(self, provider_instance, text: str, model: str) -> List[Dict[str, str]]:
        """Extract the exact messages array that will be sent to the LLM"""
        if hasattr(provider_instance, 'api_key') and provider_instance.api_key:
            # Calculate safe text limit based on model
            # GPT-4: 8k tokens, GPT-4o/GPT-4o-mini: 128k tokens
            # Enhanced prompts are longer, so be more conservative for GPT-4
            if model == "gpt-4":
                max_text_length = 14000  # Conservative limit for GPT-4's 8k context
            else:
                max_text_length = 100000  # Full limit for modern models
            
            # Truncate only if text exceeds safe limit
            text_to_analyze = text if len(text) <= max_text_length else text[:max_text_length]
            if len(text) > max_text_length:
                logger.warning(f"Document is {len(text)} chars, truncating to {max_text_length} for analysis")
            
            prompt = f"""You are analyzing an official investment policy document. Your PRIMARY goal is to find ALL items that are explicitly stated as ALLOWED or PERMITTED.

**CRITICAL: You must carefully search through the ENTIRE document text provided below. Rules can appear anywhere - in the beginning, middle, end, in tables, footnotes, appendices, or any section.**

**STEP 1: SEARCH FOR ALLOWED ITEMS FIRST (PRIORITY)**
Actively search for and extract EVERY item explicitly stated as:
- "allowed", "permitted", "authorized", "approved", "may invest", "can invest"
- "FX Forwards are allowed", "currency futures are permitted", "forex is authorized"
- Lists of permitted instruments, sectors, or countries
- Any positive statement granting permission
- Phrases like: "investments are permitted in...", "the fund may invest in...", "investments in X are allowed"

**STEP 2: THEN SEARCH FOR PROHIBITED ITEMS**
Extract items explicitly stated as:
- "prohibited", "forbidden", "not allowed", "restricted", "excluded", "may not invest"
- "investments in X are not allowed", "prohibited from investing in..."

**INSTRUMENT NAME RECOGNITION:**
Recognize these as the SAME instrument types (use the exact name from document):
- "FX Forwards" = "forex forwards" = "foreign exchange forwards" = "FX" = "forex"
- "currency futures" = "FX futures" = "foreign exchange futures" = "forex futures"
- "derivatives" includes: options, futures, forwards, swaps, warrants

**CRITICAL RULES:**
1. If document says "FX Forwards are allowed" → extract: {{"instrument": "FX Forwards", "allowed": true, "reason": "Document explicitly states FX Forwards are allowed"}}
2. If document says "currency futures are permitted" → extract: {{"instrument": "currency futures", "allowed": true, "reason": "Document explicitly states currency futures are permitted"}}
3. DO NOT mark something as "not allowed" unless explicitly prohibited
4. Search ENTIRE document - rules can be in any section, table, footnote, or appendix

**DO NOT OVER-GENERALIZE:**
- If document says "securities with equity character are allowed" → this ONLY applies to instruments explicitly described as having equity character, NOT to all bonds
- If document says "equity index options are allowed" → this ONLY applies to equity index options, NOT to all convertible bonds or structured products
- If document says "unlisted equities are allowed" → this ONLY applies to unlisted equities, NOT to debt instruments like bonds
- ONLY extract rules when the SPECIFIC instrument type is mentioned in the rule statement
- DO NOT assume a general rule applies to all similar instruments

Your task:
1. Systematically identify EVERY rule related to:
   - Investment sectors (e.g., Energy, Healthcare, Defense, Technology, Tobacco, Weapons, etc.)
   - Countries or regions (e.g., USA, China, Russia, Europe, etc.)
   - Financial instruments - use EXACT names from document (e.g., "FX Forwards", "currency futures", "covered bonds", "common stock", etc.). If the document mentions generic terms like "bonds" or "stocks", use those terms.
2. For each rule you find, determine:
   - Whether it indicates investments are **allowed** (permitted/authorized) or **not allowed** (prohibited/restricted)
   - A short **reason or quote** from the policy text supporting your conclusion
3. Search through ALL sections of the document - rules may be stated in multiple places.
4. Extract rules even if they're stated indirectly (e.g., "investments in tobacco companies are prohibited" means "tobacco sector: not allowed")
5. If conflicting or unclear information appears, record it in a "conflicts" section.

Return only structured JSON, matching this schema exactly:
{{
  "sector_rules": [{{"sector": "string", "allowed": true/false, "reason": "string"}}],
  "country_rules": [{{"country": "string", "allowed": true/false, "reason": "string"}}],
  "instrument_rules": [{{"instrument": "string", "allowed": true/false, "reason": "string"}}],
  "conflicts": [{{"category": "string", "detail": "string"}}]
}}

**Document text to analyze (search through all of it carefully):**
{text_to_analyze}"""
            
            return [
                {
                    "role": "system",
                    "content": """You are a senior compliance analyst specializing in investment restrictions.

CRITICAL INSTRUCTIONS:
- Extract ONLY explicit rules from the provided text
- Do NOT summarize, interpret, or infer beyond what is explicitly stated
- Do NOT mix different rule categories (keep sectors, countries, instruments separate)
- Do NOT drift into general policy discussion
- Focus on specific "allowed" vs "not allowed" statements
- Look for buried restrictions in tables, footnotes, and appendices
- If text is unclear or contradictory, record it in conflicts section

Your task: Extract exact factual rules about where investments are permitted or prohibited.

Return ONLY valid JSON matching the required schema."""
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ]
        else:
            return [
                {
                    "role": "system",
                    "content": "You are a senior compliance analyst specializing in investment restrictions."
                },
                {
                    "role": "user",
                    "content": f"Extract explicit investment rules from this document. Search through the entire document carefully. Document text: {text[:50000] if len(text) > 50000 else text}..."
                }
            ]
