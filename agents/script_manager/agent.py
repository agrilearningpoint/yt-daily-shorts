"""Script Manager Agent — generates and validates structured Hindi scripts."""

from __future__ import annotations

import re

from core.duration import WORDS_PER_SEC, bounds, estimate_seconds
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
SYSTEM_PROMPT = (
    "You write accurate, engaging Hindi (Devanagari) scripts for YouTube Shorts. "
    "You never invent facts. You always answer with a single valid JSON object."
)


@dataclass
class Scene:
    scene_number: int = 0
    narration: str = ""
    on_screen_text: str = ""
    visual_keywords: str = ""
    image_query: str = ""
    sources: List[str] = field(default_factory=list)
    category: str = ""            # news section, e.g. "रक्षा", "खेल"
    headline: str = ""            # source headline (for the description)
    source_name: str = ""
    # Small visual beats: each part = a few spoken words + exactly what the screen shows meanwhile.
    parts: List[Dict[str, str]] = field(default_factory=list)
    section: str = ""             # news: "national" | "international"


@dataclass
class Script:
    title: str = ""
    hook: str = ""
    scenes: List[Scene] = field(default_factory=list)
    total_duration: float = 0.0
    language: str = "hi"
    video_type: str = ""
    sources: List[str] = field(default_factory=list)
    outro: str = ""

    def word_count(self) -> int:
        return (len(self.hook.split()) + sum(len(s.narration.split()) for s in self.scenes)
                + len(self.outro.split()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title, "hook": self.hook, "scenes": [vars(s) for s in self.scenes],
            "total_duration": self.total_duration, "language": self.language,
            "video_type": self.video_type, "sources": self.sources, "word_count": self.word_count(),
            "outro": self.outro,
        }


def resplit_parts(parts: List[Dict[str, str]], text: str) -> List[Dict[str, str]]:
    """Re-distribute corrected narration over the existing visual beats (by word share)."""
    words = text.split()
    if not parts or not words:
        return parts
    sizes = [max(1, len(p.get("say", "").split())) for p in parts]
    total, out, i = sum(sizes), [], 0
    for k, (p, sz) in enumerate(zip(parts, sizes)):
        take = len(words) - i if k == len(parts) - 1 else max(1, round(len(words) * sz / total))
        chunk = words[i:i + take]
        i += take
        if chunk:
            out.append({**p, "say": " ".join(chunk)})
    return out or parts


def parse_script(data: Dict[str, Any], video_type: str, fallback_sources: List[str],
                 items: List[Dict[str, Any]] = None) -> Script:
    items = items or []
    sources = [s for s in (data.get("sources") or []) if isinstance(s, str) and s.startswith("http")]
    if video_type != "news":  # knowledge: always credit every page the research actually read
        sources = list(dict.fromkeys(sources + [s for s in fallback_sources if isinstance(s, str) and s.startswith("http")]))
    scenes = []
    raw_scenes = data.get("scenes") or []
    if video_type == "news" and (data.get("national") or data.get("international")):
        raw_scenes = ([{**s, "section": "national"} for s in (data.get("national") or []) if isinstance(s, dict)]
                      + [{**s, "section": "international"} for s in (data.get("international") or [])
                         if isinstance(s, dict)])
    for idx, sc in enumerate(raw_scenes, 1):
        if not isinstance(sc, dict):
            continue
        parts = []
        for pt in sc.get("parts") or []:
            if isinstance(pt, dict) and str(pt.get("say", "")).strip():
                parts.append({k: str(pt.get(k, "") or "").strip()[:200]
                              for k in ("say", "visual", "entity", "search", "source")})
        narration = " ".join(p["say"] for p in parts) if parts else str(sc.get("narration", "")).strip()
        if not narration:
            continue
        if not parts:
            parts = [{"say": narration, "visual": str(sc.get("visual_keywords", "")),
                      "entity": str(sc.get("image_query", "")), "search": str(sc.get("visual_keywords", "")),
                      "source": "entity" if sc.get("image_query") else "stock"}]
        item = {}
        category = str(sc.get("category", "")).strip()[:20]
        section = str(sc.get("section", "")).strip()
        if video_type == "news" and section:
            category = "अंतरराष्ट्रीय" if section == "international" else "राष्ट्रीय"
        sc_sources = [s for s in (sc.get("sources") or []) if isinstance(s, str) and s.startswith("http")]
        src = sc.get("src")
        try:
            if src is not None and 1 <= int(str(src).strip("[] ")) <= len(items):
                item = items[int(str(src).strip("[] ")) - 1]
                sc_sources = [item.get("source_url", "")] + sc_sources
        except ValueError:
            pass
        if not sc_sources and video_type != "news":
            sc_sources = list(sources)
        scenes.append(Scene(
            scene_number=idx,
            narration=narration,
            on_screen_text=str(sc.get("on_screen_text", "")).strip()[:40],
            visual_keywords=str(sc.get("visual_keywords") or sc.get("visual_instructions") or "").strip()[:80],
            image_query=str(sc.get("image_query", "") or parts[0].get("entity", "")).strip()[:80],
            sources=[u for u in dict.fromkeys(sc_sources) if u],
            category=category,
            headline=str(item.get("title", "")).strip()[:160],
            source_name=str(item.get("source_name", "")).strip(),
            parts=parts,
            section=section,
        ))
    all_sources = list(dict.fromkeys(sources + [u for s in scenes for u in s.sources]))
    return Script(title=str(data.get("title", "")).strip(), hook=str(data.get("hook", "")).strip(),
                  scenes=scenes, video_type=video_type, sources=all_sources,
                  outro=str(data.get("outro", "")).strip())


class ScriptManagerAgent(BaseAgent):
    name = "script_manager"

    def __init__(self, config, state_manager, llm=None):
        super().__init__(config, state_manager)
        self.llm = llm

    def _targets(self) -> dict:
        t = getattr(self, "targets", None)
        if t:
            return t
        v = self.config.video
        return {"national": v.news_national_count, "international": v.news_international_count,
                "min_national": v.news_national_count - 6, "min_international": min(5, v.news_international_count)}

    def fit_news(self, script: Script, max_w: int) -> None:
        """LLMs overshoot length: drop the longest/extra stories (keeping section minimums) instead of failing."""
        t = self._targets()
        need = {"national": t["min_national"], "international": t["min_international"]}
        sec = lambda s: "international" if s.section == "international" else "national"
        # very long stories first, then trailing ones, while words exceed the budget
        while script.word_count() > max_w:
            counts = {k: sum(1 for s in script.scenes if sec(s) == k) for k in need}
            cand = [s for s in script.scenes if counts[sec(s)] > need[sec(s)]]
            if not cand:
                break
            victim = max(cand, key=lambda s: (len(s.narration.split()) > 14, sec(s) == "national",
                                              len(s.narration.split()), s.scene_number))
            script.scenes.remove(victim)
        for i, s in enumerate(script.scenes, 1):
            s.scene_number = i

    def validate(self, script: Script, min_w: int, max_w: int) -> List[str]:
        problems = []
        if script.video_type == "news":
            t = self._targets()
            nat = [s for s in script.scenes if s.section != "international"]
            intl = [s for s in script.scenes if s.section == "international"]
            if len(nat) < t["min_national"]:
                problems.append(f"only {len(nat)} national stories, need {t['national']}")
            if len(intl) < t["min_international"]:
                problems.append(f"only {len(intl)} international stories, need {t['international']}")
            short_lines = [s.scene_number for s in script.scenes if len(s.narration.split()) < 9]
            long_lines = [s.scene_number for s in script.scenes if len(s.narration.split()) > 22]
            if len(short_lines) > 3:
                problems.append(f"stories {short_lines[:6]} are meaningless fragments: each must be a complete "
                                f"13-17 word story in 2 sentences (what happened + result)")
            if len(long_lines) > 6:
                problems.append(f"stories {long_lines[:5]} too long: keep each story 13-17 words")
            labelled = [s.scene_number for s in script.scenes
                        if re.match(r"^\s*[^\s,]{2,14}\s*(में|मोर्चे पर|जगत में)?\s*[,:]", s.narration)]
            if len(labelled) > 3:
                problems.append(f"stories {labelled[:5]} start with a topic label like 'खेल में,': remove labels, "
                                f"just say the news")
            crime = [s.scene_number for s in script.scenes if "अपराध" in s.category or "क्राइम" in s.category]
            if crime:
                problems.append(f"stories {crime} are crime news: replace them with other important stories")
            no_cat = [s.scene_number for s in script.scenes if not s.category]
            if len(no_cat) > 2:
                problems.append(f"stories {no_cat[:5]} missing \"category\" (Hindi section name)")
        few_parts = [s.scene_number for s in script.scenes if len(s.parts) < 2]
        if script.video_type != "news" and len(few_parts) > max(1, len(script.scenes) // 4):
            problems.append(f"scenes {few_parts[:6]} need 2-3 \"parts\" (small visual beats), each with its own visual")
        lim = 12 if script.video_type == "news" else 11
        long_parts = [s.scene_number for s in script.scenes if any(len(p["say"].split()) > lim for p in s.parts)]
        if len(long_parts) > max(1, len(script.scenes) // 4):
            problems.append(f"scenes {long_parts[:6]} have parts longer than 10 words: split into smaller parts")
        if not script.title:
            problems.append("missing title")
        if len(script.hook.split()) < 4:
            problems.append("hook too short")
        if len(script.scenes) < 2:
            problems.append("fewer than 2 scenes")
        text = script.hook + " ".join(s.narration for s in script.scenes)
        if len(_DEVANAGARI.findall(text)) < len(text) * 0.4:
            problems.append("narration is not in Hindi (Devanagari)")
        wc = script.word_count()
        if wc < min_w * 0.8:
            problems.append(f"too short: {wc} words, need {min_w}-{max_w}")
        if wc > max_w * (1.25 if script.video_type == "news" else 1.1):
            problems.append(f"too long: {wc} words, need {min_w}-{max_w}")
        est = wc / WORDS_PER_SEC.get(script.video_type or "knowledge", 2.4)
        lo, hi = bounds(self.config.video, script.video_type or "knowledge", getattr(self, "targets", None))
        if est > hi:
            problems.append(f"too long: about {est:.0f}s spoken, must be under {hi:.0f}s - shorten")
        elif est < lo:
            problems.append(f"too short: about {est:.0f}s spoken, must be at least {lo:.0f}s")
        if not script.sources:
            problems.append("no sources")
        return problems

    async def execute(self, **kwargs: Any) -> AgentResult:
        research_data = kwargs.get("research_data", {}) or {}
        prompt = kwargs.get("prompt_instructions", "")
        video_type = kwargs.get("video_type", "news")
        min_w = int(kwargs.get("min_words", 110))
        max_w = int(kwargs.get("max_words", 135))
        fallback_sources = research_data.get("sources", [])
        self.targets = kwargs.get("targets") or None

        if self.llm is None:
            return AgentResult(success=False, errors=["No LLM configured"])

        attempt_prompt = prompt
        last_problems: List[str] = []
        script = None
        for attempt in range(3):
            try:
                data = await self.llm.generate_json(attempt_prompt, SYSTEM_PROMPT)
            except Exception as exc:
                self.logger.error("Script generation failed: %s", exc)
                return AgentResult(success=False, errors=[str(exc)])
            script = parse_script(data, video_type, fallback_sources, research_data.get("items", []))
            if video_type == "news":  # trim to the quality-gate limit before judging (saves LLM retries)
                self.fit_news(script, int(bounds(self.config.video, "news", self.targets)[1] * WORDS_PER_SEC["news"]))
            last_problems = self.validate(script, min_w, max_w)
            if not last_problems:
                break
            self.logger.warning("Script attempt %d rejected: %s", attempt + 1, last_problems)
            attempt_prompt = (prompt + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED because: "
                              + "; ".join(last_problems) + ". Fix these and return the full JSON again.")

        if script is not None and video_type == "news":
            # last resort: trim to the SAME limit the Quality Manager enforces
            lo, hi = bounds(self.config.video, "news", self.targets)
            self.fit_news(script, int(hi * WORDS_PER_SEC["news"]))
        hard = [p for p in last_problems if not p.startswith("too ")]
        if script is not None:
            est = estimate_seconds(self._as_dict(script, video_type))
            lo, hi = bounds(self.config.video, video_type, self.targets)
            if not lo <= est <= hi:  # same rule the Quality Manager applies
                hard.append(f"estimated {est:.0f}s outside {lo:.0f}-{hi:.0f}s")
        if script is None or hard or last_problems:
            if script is None or hard:
                return AgentResult(success=False, errors=hard or last_problems or ["no script"])
            self.logger.warning("Accepting script with soft issues: %s", last_problems)

        data = self._as_dict(script, video_type)
        script.total_duration = round(estimate_seconds(data), 1)
        data = self._as_dict(script, video_type)
        if video_type == "news":
            await self._best_hook(data)
        return AgentResult(success=True, data={"script": data, "llm": getattr(self.llm, "last_used", "")},
                           metadata={"video_type": video_type})

    async def _best_hook(self, data: dict) -> None:
        """Hook Agent: write 4 scroll-stopping hooks from the top stories, keep the best factual one."""
        scenes = data.get("scenes", [])[:5]
        if not scenes or self.llm is None:
            return
        lines = "\n".join(f"{i + 1}. {s.get('narration', '')}" for i, s in enumerate(scenes))
        prompt = ("You write the first 2 seconds of a Hindi TV-news YouTube Short. Stories (story 1 opens the video):\n"
                  f"{lines}\n\nWrite 4 different Hindi hooks, 6-10 words each, about STORY 1 (or the most shocking of "
                  "these), as a punchy claim or curiosity question. Use only facts written above. No greeting, no "
                  "channel name, no 'आज की खबरें'. Then pick the best for curiosity + accuracy.\n"
                  'Return JSON: {"hooks": ["...", "...", "...", "..."], "best": 0}')
        try:
            res = await self.llm.generate_json(prompt)
            hooks = [h.strip() for h in (res.get("hooks") or []) if isinstance(h, str) and h.strip()]
            best = int(res.get("best", 0) or 0)
            order = ([hooks[best]] if 0 <= best < len(hooks) else []) + hooks
            for h in order:
                n = len(h.split())
                if 5 <= n <= 12 and not re.search(r"नमस्कार|नमस्ते|स्वागत", h):
                    self.logger.info("Hook Agent picked: %s (from %d)", h, len(hooks))
                    data["hook"] = h
                    return
        except Exception as exc:
            self.logger.warning("Hook Agent skipped: %s", exc)

    def _as_dict(self, script: Script, video_type: str) -> dict:
        d = script.to_dict()
        d.setdefault("video_type", video_type)
        if video_type == "news" and self.targets:
            d["news_targets"] = self.targets
        return d
