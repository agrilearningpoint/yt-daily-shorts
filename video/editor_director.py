"""Editor Director agent: a different, professional edit every day that keeps learning.

* plan()   picks today's "edit recipe" (colour palette, cut effects, motion, grade, ticker, bumper style)
           from a style space. Options that scored well before are picked more often (simple bandit),
           yesterday's look is never repeated, and the reviewer's notes are applied.
* review() a reviewer agent (Gemini vision) watches a contact sheet of the finished video like a senior
           TV news editor and scores it 1-10 with concrete notes. Scores + notes are stored in
           data/editor_memory.json (kept between runs by the Actions cache) and steer the next plan().
"""
from __future__ import annotations

import base64
import json
import logging
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("video.editor")
MEMORY = Path("data/editor_memory.json")

STYLE_SPACE: Dict[str, List[Any]] = {
    # accent, dark, highlight (lower-third / badge / ticker colours) - broadcast palettes
    "palette": [
        ["#E50914", "#0B0F1A", "#FFD60A"],   # red breaking
        ["#FF7A00", "#101828", "#FFFFFF"],   # saffron desk
        ["#00A3FF", "#04122B", "#FFE066"],   # blue studio
        ["#D62246", "#1B1B3A", "#F2C14E"],   # crimson gold
        ["#14B8A6", "#0A1F1C", "#FDE047"],   # teal prime-time
        ["#7C3AED", "#120B2E", "#FACC15"],   # violet night
    ],
    "cut_fx": [["flash", "punch", "glitch"], ["whip", "flash", "punch"], ["dip", "punch", "light"],
               ["glitch", "whip", "flash"], ["light", "punch", "whip"], ["punch", "flash", "dip"]],
    "motion": ["kenburns_in", "kenburns_mix", "parallax_pan", "slow_push"],
    "grade": ["news_crisp", "warm_film", "cool_studio", "punchy", "neutral"],
    "zoom": [1.10, 1.14, 1.18],
    "vignette": [True, False],
    "ticker": [True],
    "flash_color": ["white", "white", "#FFD60A"],
}

GRADES = {
    "news_crisp": "eq=contrast=1.08:saturation=1.12:brightness=0.01,unsharp=5:5:0.6",
    "warm_film": "colorbalance=rs=0.05:gs=0.01:bs=-0.05,eq=contrast=1.05:saturation=1.08",
    "cool_studio": "colorbalance=rs=-0.03:bs=0.05,eq=contrast=1.07:saturation=1.05",
    "punchy": "eq=contrast=1.15:saturation=1.25,unsharp=5:5:0.8",
    "neutral": "eq=contrast=1.03:saturation=1.04",
}


def _load() -> Dict[str, Any]:
    try:
        return json.loads(MEMORY.read_text())
    except Exception:
        return {"runs": [], "option_scores": {}, "notes": []}


def _save(mem: Dict[str, Any]) -> None:
    MEMORY.parent.mkdir(parents=True, exist_ok=True)
    mem["runs"] = mem.get("runs", [])[-60:]
    mem["notes"] = mem.get("notes", [])[-12:]
    MEMORY.write_text(json.dumps(mem, ensure_ascii=False, indent=1))


class EditorDirector:
    def __init__(self, gemini_key: str = "", models: Optional[List[str]] = None):
        self.key = gemini_key
        self.models = models or ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
        self.mem = _load()

    # ------------------------------------------------------------------ plan
    def plan(self, video_type: str = "news") -> Dict[str, Any]:
        scores = self.mem.get("option_scores", {})
        last = (self.mem.get("runs") or [{}])[-1].get("recipe", {})
        rng = random.Random(datetime.utcnow().strftime("%Y%m%d%H") + video_type)
        recipe: Dict[str, Any] = {}
        for key, options in STYLE_SPACE.items():
            weights = []
            for opt in options:
                s = scores.get(f"{key}={json.dumps(opt)}")
                w = (s["sum"] / s["n"]) if s and s.get("n") else 7.0   # unknown options get explored
                if opt == last.get(key) and len(options) > 1:
                    w *= 0.15                                         # never the same look two days running
                weights.append(max(w, 0.5) ** 2)
            recipe[key] = rng.choices(options, weights=weights, k=1)[0]
        recipe["notes"] = self.mem.get("notes", [])[-3:]
        logger.info("Editor recipe: palette=%s fx=%s motion=%s grade=%s", recipe["palette"][0],
                    recipe["cut_fx"], recipe["motion"], recipe["grade"])
        return recipe

    @staticmethod
    def theme(recipe: Dict[str, Any], base: Optional[dict] = None) -> dict:
        t = dict(base or {})
        acc, dark, hi = recipe["palette"]
        t.update({"primary_color": acc, "background_color": dark, "secondary_color": dark,
                  "caption_highlight": hi, "theme_name": f"editor-{acc}"})
        return t

    # ---------------------------------------------------------------- review
    def review(self, video_path: str, recipe: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {"score": None, "notes": []}
        sheet = str(Path(out_dir) / "editor_sheet.jpg")
        try:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", video_path, "-vf",
                            "fps=1/3,scale=200:-1,tile=8x5", "-frames:v", "1", sheet],
                           capture_output=True, timeout=120)
        except Exception:
            pass
        if self.key and Path(sheet).exists():
            prompt = ("You are the senior video editor of a top Indian TV news channel. This is a contact sheet "
                      "(one frame every 3 s) of today's vertical Hindi news Short. Judge it like a pro: "
                      "eye-catching? professional motion graphics? images relevant and varied? text readable? "
                      "boring or repetitive? Reply JSON only: {\"score\": 1-10, \"notes\": [3 short concrete "
                      "improvement instructions for tomorrow's edit]}")
            body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {
                "mime_type": "image/jpeg", "data": base64.b64encode(Path(sheet).read_bytes()).decode()}}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
            for m in self.models:
                try:
                    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                      params={"key": self.key}, json=body, timeout=60)
                    if r.status_code != 200:
                        continue
                    txt = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
                    data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
                    result = {"score": float(data.get("score", 0)) or None, "notes": data.get("notes", [])[:3]}
                    break
                except Exception as exc:
                    logger.debug("editor review %s failed: %s", m, exc)
        self._learn(recipe, result)
        logger.info("Editor review: score=%s notes=%s", result["score"], result["notes"])
        return result

    def _learn(self, recipe: Dict[str, Any], result: Dict[str, Any]) -> None:
        mem = self.mem
        clean = {k: v for k, v in recipe.items() if k in STYLE_SPACE}
        mem.setdefault("runs", []).append({"at": datetime.utcnow().isoformat(timespec="minutes"),
                                           "recipe": clean, "score": result.get("score")})
        if result.get("score"):
            for k, v in clean.items():
                s = mem.setdefault("option_scores", {}).setdefault(f"{k}={json.dumps(v)}", {"sum": 0.0, "n": 0})
                s["sum"] += result["score"]
                s["n"] += 1
        mem.setdefault("notes", []).extend(n for n in result.get("notes", []) if isinstance(n, str))
        _save(mem)
