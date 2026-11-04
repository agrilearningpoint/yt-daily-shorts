"""Deduplication and clustering of news stories across multiple sources."""

from __future__ import annotations

import re
from typing import List, Set
from research.rss_reader import RawArticle


def _tokenize(text: str) -> Set[str]:
    """Tokenize Hindi and English text into words."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    words = [w for w in cleaned.split() if len(w) > 2]
    # Simple common stop words
    stopwords = {"and", "the", "for", "with", "this", "that", "aur", "hai", "koi", "nahi", "liye", "gaya", "mein", "se", "ko"}
    return {w for w in words if w not in stopwords}


def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    return intersection / union if union > 0 else 0.0


def deduplicate_articles(articles: List[RawArticle], threshold: float = 0.35) -> List[RawArticle]:
    """Remove duplicate and highly overlapping stories, prioritizing earlier/higher reliability ones."""
    unique: List[RawArticle] = []
    for art in articles:
        is_dup = False
        for kept in unique:
            sim = jaccard_similarity(art.title, kept.title)
            if sim >= threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(art)
    return unique
