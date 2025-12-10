"""
Conservative, Evidence-Based Classification Module
Implements strict sentence-level matching with specificity rules to prevent over-generalization.
"""
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

try:
    from ..utils.logger import setup_logger
    logger = setup_logger(__name__)
except:
    import logging
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

# Regex patterns for classification
NEGATORS = re.compile(r"\b(no|not|excluding|except|prohibited|forbidden|shall not|may not|restricted)\b", re.I)
CONDITIONAL = re.compile(r"\b(subject to|provided that|unless|up to|limit|capped at|conditional)\b", re.I)
ALLOW_MARKERS = re.compile(r"\b(eligible|permitted|allowed|investment universe includes|may invest in)\b", re.I)
PROHIBIT_SECTIONS = re.compile(r"(prohibited|restrictions|not permitted)", re.I)
ALLOW_SECTIONS = re.compile(r"(eligible|permitted|investment universe)", re.I)
DEFINITION_SECTIONS = re.compile(r"(definitions|glossary)", re.I)
ALL_QUANTIFIERS = re.compile(r"\b(all|any|in general|including but not limited to)\b", re.I)

# German mark patterns: X = allowed, - = prohibited
# These marks can appear in tables, lists, inline text, or any context - not just checkboxes
# Pattern matches standalone X or - marks in various contexts:
# - Tables: "Instrument Name    X" or "Instrument Name | X |"
# - Lists: "• FX Forwards X" or "- Bonds -"
# - Inline: "Derivatives (X)" or "Options: -"
# Note: We use word boundaries for X but need to avoid matching "FX" - so we check for X not preceded by F
GERMAN_MARK_X = re.compile(r'(?<![A-Za-z])X(?![A-Za-z])', re.I)  # Standalone X (not part of word like "FX")
GERMAN_MARK_DASH = re.compile(r'(?:^|\s|\(|\[|:|\|)(-)(?:\s|\)|\]|:|\||$)', re.I)  # Standalone dash/hyphen
GERMAN_JA = re.compile(r'\b(ja|erlaubt|zugelassen|berechtigt|darf)\b', re.I)
GERMAN_NEIN = re.compile(r'\b(nein|verboten|nicht erlaubt|ausgeschlossen|darf nicht)\b', re.I)


def section_weight(section_title: Optional[str]) -> int:
    """Calculate section weight for evidence scoring"""
    if not section_title:
        return 1
    
    section_lower = section_title.lower()
    if ALLOW_SECTIONS.search(section_lower):
        return 3
    if PROHIBIT_SECTIONS.search(section_lower):
        return 3
    if DEFINITION_SECTIONS.search(section_lower):
        return 0
    return 1


def classify_sentence(sentence: str, section_title: Optional[str] = None) -> Tuple[str, str]:
    """
    Classify a sentence as Allowed, Prohibited, Conditional, or Review.
    
    Args:
        sentence: The sentence text to classify
        section_title: Optional section title for context
        
    Returns:
        Tuple of (label, evidence_text)
    """
    s = sentence.strip()
    if not s:
        return "Review", ""
    
    # Check for German mark patterns first (highest priority for evidence)
    # In German documents: X = allowed, - = prohibited
    # These marks can appear in tables, lists, inline text, or any context
    has_mark_x = bool(GERMAN_MARK_X.search(s))
    has_mark_dash = bool(GERMAN_MARK_DASH.search(s))
    has_german_ja = bool(GERMAN_JA.search(s))
    has_german_nein = bool(GERMAN_NEIN.search(s))
    
    # Standard keyword patterns
    neg = bool(NEGATORS.search(s))
    cond = bool(CONDITIONAL.search(s))
    allow_kw = bool(ALLOW_MARKERS.search(s))
    prohibit_sec = bool(PROHIBIT_SECTIONS.search(section_title or "")) or ("not permitted" in s.lower())
    allow_sec = bool(ALLOW_SECTIONS.search(section_title or ""))
    
    # Precedence: Prohibited > Allowed > Conditional > Review
    # German patterns: dash/nein = prohibited, X/ja = allowed
    if prohibit_sec or neg or has_mark_dash or has_german_nein:
        return "Prohibited", s
    
    if allow_sec or allow_kw or has_mark_x or has_german_ja:
        return ("Conditional" if cond else "Allowed"), s
    
    return "Review", s


def decide(items_hits: Dict[str, List[Dict]], term_map: Dict[str, Dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Decide classification for each term based on evidence hits.
    
    Args:
        items_hits: Dict mapping term -> list of hits, where each hit is:
            {"sentence": str, "section": str, "page": int}
        term_map: Dict mapping term -> {"primary": bool, "specificity": int, "parent": str}
        
    Returns:
        Tuple of (decisions, evidence) where:
        - decisions: Dict[term] -> status ("Allowed", "Prohibited", "Conditional", "Review")
        - evidence: Dict[term] -> evidence text
    """
    decisions = {}
    evidence = {}
    
    # Step 1: Decide per term based on best evidence
    for term, hits in items_hits.items():
        if not hits:
            decisions[term] = "Review"
            evidence[term] = ""
            continue
        
        best = ("Review", -1, None)  # (label, score, evidence_text)
        
        for h in hits:
            label, evid = classify_sentence(h.get("sentence", ""), h.get("section"))
            weight = section_weight(h.get("section"))
            spec = term_map.get(term, {}).get("specificity", 1)
            
            # Score calculation: label priority * 10 + section weight * 2 + specificity
            label_score = {
                "Prohibited": 3,
                "Allowed": 2,
                "Conditional": 1,
                "Review": 0
            }.get(label, 0)
            
            score = label_score * 10 + weight * 2 + spec
            
            if score > best[1]:
                best = (label, score, evid)
        
        decisions[term] = best[0]
        evidence[term] = best[2] or ""
    
    # Step 2: Parent roll-up rules (e.g., "Bonds" from child terms)
    by_parent = defaultdict(list)
    for term in decisions:
        parent = term_map.get(term, {}).get("parent")
        if parent:
            by_parent[parent].append(term)
    
    for parent, children in by_parent.items():
        child_labels = [decisions.get(c, "Review") for c in children]
        
        # If any child is Prohibited, parent is Prohibited
        if "Prohibited" in child_labels:
            decisions[parent] = "Prohibited"
            prohibited_child = children[child_labels.index("Prohibited")]
            evidence[parent] = f"Child prohibited: {prohibited_child}"
            continue
        
        # Check for explicit "all/any" quantifier in parent hits
        parent_hits = items_hits.get(parent, [])
        explicit_all = False
        
        for h in parent_hits:
            sentence = h.get("sentence", "")
            if ALL_QUANTIFIERS.search(sentence):
                label, _ = classify_sentence(sentence, h.get("section"))
                if label == "Allowed":
                    explicit_all = True
                    evidence[parent] = f"Explicit 'all/any' allowance found: {sentence[:200]}"
                    break
        
        if explicit_all:
            decisions[parent] = "Allowed"
        else:
            # Coverage heuristic: >= 80% allowed and none prohibited
            allowed_count = sum(1 for l in child_labels if l == "Allowed")
            allowed_ratio = allowed_count / max(1, len(child_labels))
            
            if allowed_ratio >= 0.8 and "Prohibited" not in child_labels:
                decisions[parent] = "Conditional"  # Safer than Allowed for demo
                evidence[parent] = f"{int(allowed_ratio * 100)}% child coverage allowed; promoted to Conditional."
            # Otherwise, don't infer upwards (leave as Review or existing decision)
    
    return decisions, evidence


def extract_sentences(text: str) -> List[str]:
    """
    Extract sentences from text, handling bullet points and line breaks.
    
    Args:
        text: Full text to extract sentences from
        
    Returns:
        List of sentence strings
    """
    # Split on sentence endings, but preserve context
    sentences = re.split(r'[.!?]\s+', text)
    
    # Also split on line breaks that look like new sentences
    all_sentences = []
    for sent in sentences:
        # Split on double newlines (paragraph breaks)
        parts = re.split(r'\n\n+', sent)
        for part in parts:
            part = part.strip()
            if part and len(part) > 10:  # Only keep meaningful sentences
                all_sentences.append(part)
    
    return all_sentences


def build_items_hits(
    combined_context: str,
    term_map: Dict[str, Dict],
    section_titles: Optional[Dict[int, str]] = None
) -> Dict[str, List[Dict]]:
    """
    Build items_hits dictionary by scanning combined_context sentence-by-sentence.
    
    Args:
        combined_context: Full document text
        term_map: Dict mapping term -> metadata (must include "primary" and "specificity")
        section_titles: Optional dict mapping approximate position -> section title
        
    Returns:
        Dict mapping term -> list of hits, where each hit is:
        {"sentence": str, "section": str, "page": int}
    """
    items_hits = defaultdict(list)
    
    # Extract sentences
    sentences = extract_sentences(combined_context)
    
    # Build term lookup (normalize terms for matching)
    term_lookup = {}
    for term, metadata in term_map.items():
        term_normalized = term.lower().strip()
        term_lookup[term_normalized] = (term, metadata)
        
        # Also index by words for partial matching
        words = re.findall(r'\w+', term_normalized)
        for word in words:
            if len(word) > 3:
                if word not in term_lookup:
                    term_lookup[word] = (term, metadata)
    
    # Scan each sentence
    for sent_idx, sentence in enumerate(sentences):
        sent_lower = sentence.lower()
        
        # Find matching terms in this sentence
        for term_normalized, (original_term, metadata) in term_lookup.items():
            # Check if term appears in sentence (word boundary matching)
            term_match = re.search(r'\b' + re.escape(term_normalized) + r'\b', sentence, re.I)
            if term_match:
                # Determine section (simplified - could be enhanced with actual section detection)
                section = ""
                if section_titles:
                    # Find nearest section title (simplified)
                    section = section_titles.get(sent_idx, "")
                
                # Check if this looks like a pattern with German mark (X or -)
                # Extract context around the term (up to 100 chars after) for mark detection
                # Marks can appear in tables, lists, inline text, or any context
                term_pos = term_match.start()
                context_end = min(len(sentence), term_match.end() + 100)
                context_after = sentence[term_match.end():context_end]
                
                # If German mark (X or -) appears near the term, use focused context
                # Otherwise use full sentence
                has_german_mark = (GERMAN_MARK_X.search(context_after) or 
                                  GERMAN_MARK_DASH.search(context_after))
                
                if has_german_mark:
                    # Mark pattern (table/list/inline): use context around term + mark
                    context_start = max(0, term_pos - 50)
                    evidence_text = sentence[context_start:context_end]
                else:
                    # Regular sentence pattern: use full sentence
                    evidence_text = sentence
                
                hit = {
                    "sentence": evidence_text,
                    "section": section,
                    "page": 1  # Could be enhanced with actual page detection
                }
                items_hits[original_term].append(hit)
    
    return dict(items_hits)

