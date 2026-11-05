from agents.script_manager.agent import parse_script, resplit_parts
from video.media_collector import MediaAsset, MediaCollector


def test_parts_become_narration_and_keep_visuals():
    data = {"title": "t", "hook": "देखिए आज की खबरें", "scenes": [
        {"category": "खेल", "on_screen_text": "क्रिकेट", "src": 1, "parts": [
            {"say": "खेल में, भारत ने", "visual": "indian cricket team", "entity": "India national cricket team",
             "search": "cricket", "source": "entity"},
            {"say": "ऑस्ट्रेलिया को हराकर सीरीज़ जीती।", "visual": "trophy", "entity": "", "search": "trophy",
             "source": "stock"}]}]}
    items = [{"title": "India win", "source_url": "https://x.in/a", "source_name": "X"}]
    s = parse_script(data, "news", [], items)
    sc = s.scenes[0]
    assert sc.narration == "खेल में, भारत ने ऑस्ट्रेलिया को हराकर सीरीज़ जीती।"
    assert sc.category == "खेल" and len(sc.parts) == 2 and sc.sources == ["https://x.in/a"]
    assert sc.source_name == "X" and sc.headline == "India win"


def test_resplit_keeps_visual_count():
    parts = [{"say": "एक दो तीन", "visual": "a"}, {"say": "चार पांच छह", "visual": "b"}]
    out = resplit_parts(parts, "क ख ग घ ङ च छ ज")
    assert [p["visual"] for p in out] == ["a", "b"]
    assert " ".join(p["say"] for p in out) == "क ख ग घ ङ च छ ज"


def test_ai_hint_tries_ai_first(tmp_path, monkeypatch):
    mc = MediaCollector(cache_dir=str(tmp_path), agnes_key="k", pexels_key="p")
    calls = []
    monkeypatch.setattr(mc, "_agnes", lambda v, d, m="news": calls.append("ai") or MediaAsset(str(d), "ai"))
    monkeypatch.setattr(mc, "_pexels", lambda q, d: calls.append("pexels") or None)
    monkeypatch.setattr(mc, "_wikipedia_exact", lambda e, d: calls.append("entity") or None)
    a = mc.find_visual({"visual": "new chip", "search": "chip", "source": "ai"}, str(tmp_path / "x.jpg"))
    assert a.source == "ai" and calls == ["ai"]
