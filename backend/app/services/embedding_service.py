import os
from typing import List, Tuple, Optional
import numpy as np
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("⚠️ sentence-transformers not available. Install with: pip install sentence-transformers")

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("⚠️ rapidfuzz not available. Install with: pip install rapidfuzz")

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger.warning("⚠️ spacy not available. Install with: pip install spacy && python -m spacy download en_core_web_sm")


class EmbeddingService:
    """Service for embedding-based text matching"""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize embedding service
        
        Args:
            model_name: Name of the sentence transformer model to use
        """
        self.model_name = model_name
        self.model = None
        self.nlp = None
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize embedding and NLP models"""
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info(f"🔄 Loading embedding model: {self.model_name}")
                self.model = SentenceTransformer(self.model_name)
                logger.info("✅ Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"❌ Failed to load embedding model: {e}")
                self.model = None
        else:
            logger.warning("⚠️ sentence-transformers not available, embedding matching will be disabled")
        
        if SPACY_AVAILABLE:
            try:
                logger.info("🔄 Loading spaCy model...")
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("✅ spaCy model loaded successfully")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load spaCy model: {e}. Try: python -m spacy download en_core_web_sm")
                self.nlp = None
    
    def build_catalog_index(self, catalog_items: List[dict]) -> Tuple[List[str], List[str], Optional[np.ndarray]]:
        """
        Build embedding index from catalog items
        
        Args:
            catalog_items: List of dicts with 'id', 'texts' (list of strings), and 'item'
        
        Returns:
            Tuple of (texts, metadata_ids, embeddings)
        """
        if not self.model:
            logger.warning("⚠️ Embedding model not available, returning empty index")
            return [], [], None
        
        texts = []
        meta = []
        
        for item in catalog_items:
            for text in item["texts"]:
                texts.append(text)
                meta.append(item["id"])
        
        if not texts:
            return [], [], None
        
        try:
            embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            logger.info(f"✅ Built catalog index with {len(texts)} text entries")
            return texts, meta, embeddings
        except Exception as e:
            logger.error(f"❌ Failed to build catalog index: {e}")
            return texts, meta, None
    
    def extract_candidates(self, text: str) -> List[str]:
        """
        Extract candidate phrases from document text
        
        Args:
            text: Document text
        
        Returns:
            List of candidate phrases
        """
        candidates = set()
        
        # Method 1: Use spaCy noun chunks if available
        if self.nlp:
            try:
                doc = self.nlp(text)
                # Extract noun chunks of reasonable length
                for nc in doc.noun_chunks:
                    text_clean = nc.text.strip()
                    words = text_clean.split()
                    if 2 <= len(words) <= 6:
                        candidates.add(text_clean)
                
                # Extract single important tokens
                keywords = {
                    "gold", "silver", "platinum", "palladium", "etf", "unitranche", 
                    "mezzanine", "bullion", "private credit", "direct lending", 
                    "private debt", "commodity", "metals", "bonds", "stocks", 
                    "funds", "derivatives", "options", "futures", "swaps"
                }
                for token in doc:
                    if token.text.lower() in keywords:
                        candidates.add(token.text)
            except Exception as e:
                logger.warning(f"⚠️ spaCy processing failed: {e}")
        
        # Method 2: Extract title-like lines
        for line in text.splitlines():
            line = line.strip()
            words = line.split()
            if 3 <= len(words) <= 10 and len(line) > 10:
                candidates.add(line)
        
        # Method 3: Simple keyword-based extraction (fallback)
        if not candidates and not self.nlp:
            # Basic keyword matching
            keywords = [
                "gold", "silver", "platinum", "precious metals", "private credit",
                "direct lending", "mezzanine", "unitranche", "etf", "bullion"
            ]
            text_lower = text.lower()
            for keyword in keywords:
                if keyword in text_lower:
                    candidates.add(keyword)
        
        return list(candidates)
    
    def match_candidate(
        self, 
        phrase: str, 
        catalog_texts: List[str],
        catalog_meta: List[str],
        catalog_embeddings: Optional[np.ndarray],
        threshold: float = 0.68
    ) -> Tuple[Optional[str], float, float, float]:
        """
        Match a candidate phrase to catalog items
        
        Args:
            phrase: Candidate phrase to match
            catalog_texts: List of catalog text entries
            catalog_meta: List of catalog item IDs (parallel to texts)
            catalog_embeddings: Embedding vectors for catalog texts
            threshold: Minimum similarity threshold
        
        Returns:
            Tuple of (best_match_id, combined_score, embedding_score, fuzzy_score)
        """
        if catalog_embeddings is not None and self.model:
            # Use embedding similarity
            try:
                phrase_embedding = self.model.encode([phrase], normalize_embeddings=True)
                similarities = util.cos_sim(phrase_embedding, catalog_embeddings)[0].tolist()
                best_idx = max(range(len(similarities)), key=lambda i: similarities[i])
                embedding_score = similarities[best_idx]
            except Exception as e:
                logger.warning(f"⚠️ Embedding matching failed: {e}")
                embedding_score = 0.0
                best_idx = 0
        else:
            embedding_score = 0.0
            best_idx = 0
        
        # Backup fuzzy string similarity
        if RAPIDFUZZ_AVAILABLE:
            fuzzy_scores = [fuzz.partial_ratio(phrase.lower(), t.lower()) / 100.0 for t in catalog_texts]
            fuzzy_score = max(fuzzy_scores) if fuzzy_scores else 0.0
            best_fuzzy_idx = max(range(len(fuzzy_scores)), key=lambda i: fuzzy_scores[i])
        else:
            fuzzy_score = 0.0
            best_fuzzy_idx = 0
        
        # Combine scores (weighted average)
        combined_score = 0.7 * embedding_score + 0.3 * fuzzy_score
        
        # Use embedding match if available, otherwise fuzzy
        if catalog_embeddings is not None and self.model:
            best_id = catalog_meta[best_idx] if best_idx < len(catalog_meta) else None
        else:
            best_id = catalog_meta[best_fuzzy_idx] if best_fuzzy_idx < len(catalog_meta) else None
        
        return best_id, combined_score, embedding_score, fuzzy_score

