"""The opening block: आज की तारीख/पर्व → राशिफल → trading news (descending impact)."""
from __future__ import annotations

from agents.script_manager.agent import parse_script
from core.duration import WORDS_PER_SEC
from research.daily_context import DayFacts, market_score, split_market


def test_market_score_ranks_index_above_single_stock():
    assert market_score("सेंसेक्स 800 अंक चढ़ा, निफ्टी रिकॉर्ड ऊंचाई पर") == 3
    assert market_score("सोने के दाम 2% बढ़े, चांदी भी मजबूत") == 2
    assert market_score("कंपनी का डिविडेंड घोषित") == 1
    assert market_score("बिहार में नई रेल परियोजना शुरू") == 0


def test_split_market_puts_trading_first_in_descending_order():
    items = [
        {"title": "कंपनी का डिविडेंड घोषित", "importance_score": 0.95},
        {"title": "सोने के दाम 2% बढ़े", "importance_score": 0.7},
        {"title": "सेंसेक्स 800 अंक चढ़ा", "importance_score": 0.6},
        {"title": "रेल परियोजना शुरू", "importance_score": 0.9},
    ]
    trading, rest = split_market(items)
    assert [t["market_score"] for t in trading] == [3, 2, 1]
    assert [r["title"] for r in rest] == ["रेल परियोजना शुरू"]


def test_today_block_is_parsed_first_and_kept_in_order():
    data = {
        "title": "t", "hook": "बाज़ार में बड़ा उछाल",
        "today": [
            {"kind": "today", "on_screen_text": "आज", "parts": [{"say": "आज बुधवार, 11 नवंबर 2026 है। आज भैया दूज है।",
                                                                 "visual": "diya and calendar", "search": "diwali diya"}]},
            {"kind": "rashifal", "on_screen_text": "राशिफल", "parts": [{"say": "राशिफल के अनुसार मकर और तुला के लिए दिन अच्छा है।",
                                                                        "visual": "zodiac wheel", "search": "zodiac wheel"}]},
            {"kind": "trading", "on_screen_text": "बाज़ार", "parts": [{"say": "सेंसेक्स 800 अंक चढ़कर बंद हुआ।",
                                                                      "visual": "stock screen", "search": "stock market"}]},
        ],
        "national": [{"src": None, "on_screen_text": "रेल", "parts": [
            {"say": "बिहार में नई रेल परियोजना शुरू हुई। इससे यात्रा आसान होगी।", "visual": "train", "search": "indian train"}]}],
        "international": [],
    }
    script = parse_script(data, "news", [], [])
    assert [s.section for s in script.scenes] == ["today", "today", "today", "national"]
    assert script.scenes[0].category == "आज"


def test_fallback_intro_always_has_the_date():
    import asyncio

    from research.daily_context import build_intro

    facts = DayFacts(date_hi="11 नवंबर 2026", weekday_hi="बुधवार", tithi="Shukla Paksha, Dwitiya",
                     festivals=["Bhaiya Dooj"])
    out = asyncio.run(build_intro(None, facts, [], [{"title": "सेंसेक्स 800 अंक चढ़ा", "market_score": 3}]))
    says = " ".join(p["say"] for b in out["beats"] for p in b["parts"])
    assert "11 नवंबर 2026" in says and "बुधवार" in says and "भैया दूज" in says
    assert out["beats"][-1]["kind"] == "trading" and "सेंसेक्स" in says


def test_voice_speed_is_the_configured_1_2x():
    assert WORDS_PER_SEC["news"] > 2.6      # 2.3 * 1.2
    assert WORDS_PER_SEC["knowledge"] > 2.8  # 2.4 * 1.2


def test_news_duration_budget_counts_the_faster_voice():
    """2.76 words/s at 1.2x: a 120 s bulletin needs more words than the old 2.3 estimate allowed."""
    from core.duration import estimate_seconds

    script = {"video_type": "news", "hook": "", "outro": "",
              "scenes": [{"narration": " ".join(["शब्द"] * 300)},
                         {"narration": " ".join(["शब्द"] * 31)}]}
    est = estimate_seconds(script)
    assert 118 <= est <= 122          # 331 / 2.76


def test_visual_quality_is_reported_for_every_render():
    from agents.video_producer.agent import VideoProducerAgent
    import inspect

    src = inspect.getsource(VideoProducerAgent.execute)
    assert '"visual_match": fig' in src and "avg_match" in src
