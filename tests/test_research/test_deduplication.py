"""Unit tests for news deduplication."""

from __future__ import annotations

from datetime import datetime, timezone
from research.deduplication import deduplicate_articles, jaccard_similarity
from research.rss_reader import RawArticle


def test_jaccard_similarity():
    s1 = "भारत ने चंद्रमा पर चंद्रयान 3 सफलता पूर्वक उतारा"
    s2 = "चंद्रयान 3 मिशन भारत द्वारा चंद्रमा पर सफलता पूर्वक उतरा"
    sim = jaccard_similarity(s1, s2)
    assert sim > 0.3

    diff = "शेयर बाजार में आज भारी तेजी देखी गई"
    assert jaccard_similarity(s1, diff) < 0.1


def test_deduplicate_articles():
    now = datetime.now(timezone.utc)
    a1 = RawArticle("ISRO launches new rocket successfully", "https://isro.gov.in/1", "summary", now, "ISRO")
    a2 = RawArticle("ISRO launches new rocket successfully from Sriharikota", "https://thehindu.com/1", "summary", now, "The Hindu")
    a3 = RawArticle("Government introduces new semiconductor incentive policy", "https://pib.gov.in/2", "summary", now, "PIB")

    unique = deduplicate_articles([a1, a2, a3], threshold=0.4)
    assert len(unique) == 2
    assert unique[0].title == a1.title
    assert unique[1].title == a3.title
