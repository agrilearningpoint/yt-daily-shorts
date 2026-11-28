from agents.script_manager.agent import parse_script, resplit_parts
from video.media_collector import MediaAsset, MediaCollector


def test_parts_become_narration_and_keep_visuals():
    data = {
        "title": "t",
        "hook": "देखिए आज की खबरें",
        "scenes": [
            {
                "category": "खेल",
                "on_screen_text": "क्रिकेट",
                "src": 1,
                "parts": [
                    {
                        "say": "खेल में, भारत ने",
                        "visual": "indian cricket team",
                        "entity": "India national cricket team",
                        "search": "cricket",
                        "source": "entity",
                    },
                    {
                        "say": "ऑस्ट्रेलिया को हराकर सीरीज़ जीती।",
                        "visual": "trophy",
                        "entity": "",
                        "search": "trophy",
                        "source": "stock",
                    },
                ],
            }
        ],
    }
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
    monkeypatch.setattr(
        mc, "_agnes", lambda v, d, m="news": calls.append("ai") or MediaAsset(str(d), "ai")
    )
    monkeypatch.setattr(mc, "_pexels", lambda q, d: calls.append("pexels") or None)
    monkeypatch.setattr(mc, "_wikipedia_exact", lambda e, d: calls.append("entity") or None)
    a = mc.find_visual(
        {"visual": "new chip", "search": "chip", "source": "ai"}, str(tmp_path / "x.jpg")
    )
    assert a.source == "ai" and calls == ["ai"]


def test_blank_and_logo_images_rejected():
    from PIL import Image, ImageDraw
    from video.media_collector import MediaCollector

    white = Image.new("RGB", (800, 800), "white")
    logo = white.copy()
    ImageDraw.Draw(logo).ellipse((350, 350, 450, 450), fill="navy")
    import random

    random.seed(1)
    photo = Image.new("RGB", (64, 64))
    photo.putdata([(random.randint(40, 220),) * 3 for _ in range(64 * 64)])
    assert MediaCollector._looks_blank(white)
    assert MediaCollector._looks_blank(logo)
    assert not MediaCollector._looks_blank(photo)


def test_resplit_never_cuts_a_phrase_in_half():
    """Regression: cuts used to be made by word count, so one picture got 'बिसलेरी के' and the
    next 'पानी के सैंपल में कोलीफॉर्म' — an image cannot illustrate half a noun phrase."""
    from agents.script_manager.agent import resplit_parts

    parts = [{"say": "old", "visual": "a"}, {"say": "old", "visual": "b"}]
    text = "जलपाईगुड़ी में बिसलेरी के पानी के सैंपल में बैक्टीरिया पाए गए। जाँच शुरू हो गई है।"
    out = resplit_parts(parts, text)
    assert len(out) == 2
    assert " ".join(p["say"] for p in out) == text  # not one word lost
    # each beat is a complete sentence, and none starts on a dangling function word
    assert out[0]["say"].endswith("।") and out[1]["say"].endswith("।")
    assert not out[1]["say"].split()[0] in {"के", "का", "की", "में", "से", "ने"}


def test_fragment_parts_are_merged_not_dropped():
    from agents.script_manager.agent import merge_fragment_parts

    fragments = [
        {"say": "रांची में पुलिस और एनसीबी", "visual": "ncB"},
        {"say": "ने संयुक्त कार्रवाई", "visual": "x"},
        {"say": "करते हुए दो क्विंटल गांजा", "visual": "y"},
        {"say": "जब्त किया है।", "visual": "z"},
    ]
    merged = merge_fragment_parts([dict(f) for f in fragments])
    assert len(merged) < len(fragments)
    assert " ".join(m["say"] for m in merged) == " ".join(f["say"] for f in fragments)
    # a complete two-beat story must survive untouched
    fine = [{"say": "खेल में, भारत ने", "visual": "a"}, {"say": "सीरीज़ जीती।", "visual": "b"}]
    assert len(merge_fragment_parts([dict(f) for f in fine])) == 2
