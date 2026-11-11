"""The opening block of the daily bulletin: आज की तारीख, पंचांग, राशिफल, trading news.

Order the channel owner asked for (2026-11-11):

  1. आज की तारीख — अपने आप (timezone से, कोई API नहीं)
  2. आज का पर्व / महत्वपूर्ण दिन — Drik Panchang से, अपने आप
  3. आज का राशिफल — 12 राशियाँ, "किस राशि को फायदा" — Google News + LLM
  4. Trading news — share market / crypto / commodity / IPO / F&O, importance descending
  5. फिर बाकी देश-दुनिया की खबरें

Everything is best-effort: a dead feed or a missing key just drops that section
(the bulletin never fails because a horoscope page was down), and every fact is
labelled with where it came from so the fact-checker can verify it.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
import requests

logger = logging.getLogger("research.daily_context")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

HINDI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
                "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
HINDI_DAYS = {0: "सोमवार", 1: "मंगलवार", 2: "बुधवार", 3: "गुरुवार", 4: "शुक्रवार", 5: "शनिवार", 6: "रविवार"}

# Drik Panchang speaks English; the anchor speaks Hindi. Anything not in these maps is
# transliterated by the LLM beat instead (the fallback only needs to sound right).
HINDI_FESTIVALS = {
    "bhaiya dooj": "भैया दूज", "bhai dooj": "भाई दूज", "diwali": "दिवाली", "deepavali": "दीपावली",
    "dhanteras": "धनतेरस", "govardhan puja": "गोवर्धन पूजा", "chhath puja": "छठ पूजा",
    "holi": "होली", "holika dahan": "होलिका दहन", "raksha bandhan": "रक्षाबंधन",
    "janmashtami": "जन्माष्टमी", "karva chauth": "करवा चौथ", "navratri": "नवरात्रि",
    "dussehra": "दशहरा", "vijayadashami": "विजयादशमी", "ganesh chaturthi": "गणेश चतुर्थी",
    "makar sankranti": "मकर संक्रांति", "pongal": "पोंगल", "onam": "ओणम",
    "maha shivratri": "महाशिवरात्रि", "shivratri": "शिवरात्रि", "ram navami": "राम नवमी",
    "hanuman jayanti": "हनुमान जयंती", "guru purnima": "गुरु पूर्णिमा", "teej": "तीज",
    "akshaya tritiya": "अक्षय तृतीया", "vasant panchami": "वसंत पंचमी", "basant panchami": "बसंत पंचमी",
    "rath yatra": "रथ यात्रा", "guru nanak jayanti": "गुरु नानक जयंती", "buddha purnima": "बुद्ध पूर्णिमा",
    "mahavir jayanti": "महावीर जयंती", "ekakadashi": "एकादशी", "purnima": "पूर्णिमा",
}
HINDI_TITHI = {
    "prathama": "प्रतिपदा", "pratipada": "प्रतिपदा", "dwitiya": "द्वितीया", "tritiya": "तृतीया",
    "chaturthi": "चतुर्थी", "panchami": "पंचमी", "shashthi": "षष्ठी", "saptami": "सप्तमी",
    "ashtami": "अष्टमी", "navami": "नवमी", "dashami": "दशमी", "ekadashi": "एकादशी",
    "dwadashi": "द्वादशी", "trayodashi": "त्रयोदशी", "chaturdashi": "चतुर्दशी",
    "purnima": "पूर्णिमा", "amavasya": "अमावस्या", "shukla": "शुक्ल", "krishna": "कृष्ण",
    "paksha": "पक्ष",
}


def hindi_name(text: str) -> str:
    """'Bhaiya Dooj' -> 'भैया दूज'; 'Shukla Paksha, Dwitiya' -> 'शुक्ल पक्ष, द्वितीया'."""
    low = (text or "").strip().lower()
    if low in HINDI_FESTIVALS:
        return HINDI_FESTIVALS[low]
    words = []
    for w in re.split(r"([\s,]+)", low):
        words.append(HINDI_TITHI.get(w, w) if w.strip() else w)
    out = "".join(words)
    return out if out != low else text


RASHIS = ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]

# Trading vocabulary — these stories go FIRST inside the news block, highest impact first.
MARKET_TERMS = {
    "high": [  # index-level / policy events that move everything
        "सेंसेक्स", "निफ्टी", "sensex", "nifty", "बाज़ार", "बाजार", "शेयर बाजार", "stock market",
        "आरबीआई", "rbi", "रेपो रेट", "repo rate", "मुद्रास्फीति", "inflation", "जीडीपी", "gdp",
        "बजट", "budget", "फेड", "fed rate", "federal reserve", "ब्याज दर", "interest rate",
    ],
    "mid": [  # single large caps, sectors, commodities
        "शेयर", "share", "स्टॉक", "stock", "ipo", "आईपीओ", "f&o", "फ्यूचर एंड ऑप्शन", "डेरिवेटिव",
        "सोना", "gold", "चांदी", "silver", "क्रूड", "crude oil", "डॉलर", "rupee", "रुपया",
        "बिटकॉइन", "bitcoin", "क्रिप्टो", "crypto", "etherium", "ethereum", "म्यूचुअल फंड", "mutual fund",
        "damc", "sebi", "सेबी", "npci", "बैंक", "bank", "quarterly results", "नतीजे",
    ],
    "low": ["कंपनी", "company", "शेयरधारक", "dividend", "डिविडेंड", "बॉन्ड", "bond", "एफआईआई", "fii", "dii"],
}


@dataclass
class DayFacts:
    """What today IS: date, festival, and the panchang the anchor opens with."""
    date_hi: str = ""
    weekday_hi: str = ""
    tithi: str = ""
    paksha: str = ""
    nakshatra: str = ""
    samvat: str = ""
    festivals: List[str] = field(default_factory=list)
    special: str = ""            # one Hindi line: "आज भैया दूज है…"
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def date_label(tz: str = "Asia/Kolkata") -> tuple[str, str]:
    now = datetime.now(pytz.timezone(tz))
    return (f"{now.day} {HINDI_MONTHS[now.month - 1]} {now.year}", HINDI_DAYS[now.weekday()])


def fetch_panchang(tz: str = "Asia/Kolkata",
                   timeout: int = 15) -> DayFacts:
    """Drik Panchang's day page: tithi, paksha, nakshatra, samvat and today's festivals.

    One HTML GET, no key. If the page moves, we return whatever we got — the date
    line is computed locally and always present, so the intro never breaks.
    """
    date_hi, weekday_hi = date_label(tz)
    facts = DayFacts(date_hi=date_hi, weekday_hi=weekday_hi)
    now = datetime.now(pytz.timezone(tz))
    url = f"https://www.drikpanchang.com/panchang/day-panchang.html?date={now.month:02d}/{now.day:02d}/{now.year}"
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
        if r.status_code != 200:
            logger.warning("panchang HTTP %s", r.status_code)
            return facts
        h = r.text
        facts.source = url
        m = re.search(r'dpPHeaderLeftTitle">\s*([^<]{1,40})</div>\s*<div>\s*([^<]{1,60})</div>', h)
        if m:
            # "17, Kartika" / "Shukla Paksha, Dwitiya"
            facts.tithi = hindi_name(html.unescape(m.group(2)).strip())
        m2 = re.search(r'(\d{4})\s+(Siddharthi|Vikrama Samvata|Vikram Samvat)', h)
        if m2:
            facts.samvat = f"{m2.group(1)} {m2.group(2)}"
        # festival links carry the day's parv; keep only the ones named on this page body
        fest = []
        for href, name in re.findall(r'href="(/festivals/[^"]+)"[^>]*>\s*([^<]{3,60})<', h):
            name = html.unescape(name).strip(" .")
            name = hindi_name(name)
            if name and name.lower() not in ("festivals", "top 10 festivals", "hindu festivals",
                                             "vrat katha", "sankranti calendar", "tamil festivals",
                                             "malayalam festivals", "sankranti festivals", "diwali"):
                fest.append(name)
        facts.festivals = list(dict.fromkeys(fest))[:4]
    except Exception as exc:
        logger.warning("panchang fetch failed: %s", exc)
    return facts


def fetch_horoscope_news(timeout: int = 15, limit: int = 6) -> List[Dict[str, str]]:
    """Today's rashifal headlines (Hindi outlets) — source material for the astrology line."""
    out: List[Dict[str, str]] = []
    try:
        import feedparser
        url = ("https://news.google.com/rss/search?"
               "q=%E0%A4%86%E0%A4%9C+%E0%A4%95%E0%A4%BE+%E0%A4%B0%E0%A4%BE%E0%A4%B6%E0%A4%BF%E0%A4%AB%E0%A4%B2"
               "&hl=hi&gl=IN&ceid=IN:hi")
        r = requests.get(url, headers=_UA, timeout=timeout)
        parsed = feedparser.parse(r.content)
        for e in parsed.entries[:limit]:
            title = html.unescape(re.sub(r"<[^>]+>", " ", e.get("title", ""))).strip()
            pub = (e.get("source") or {}).get("title", "") if isinstance(e.get("source"), dict) else ""
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            if title:
                out.append({"title": title[:180], "source": pub or "Google News",
                            "url": e.get("link", "")})
    except Exception as exc:
        logger.warning("horoscope news failed: %s", exc)
    return out


def _stem(word: str) -> str:
    """Hindi inflections: सोना/सोने -> सोन, चांदी/चांदी -> चांद. Latin words lose a plural s."""
    w = word.lower().strip()
    if re.fullmatch(r"[\u0900-\u097F]+", w or ""):
        return re.sub(r"[\u093e\u093f\u0940\u0941\u0942\u0943\u0947\u0948\u094b\u094c\u0902\u0903\u0901]+$", "", w)
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _stems(text: str) -> str:
    toks = re.findall(r"[\u0900-\u097F]+|[a-z&]+", (text or "").lower())
    return " " + " ".join(_stem(t) for t in toks) + " "


def market_score(title: str, summary: str = "") -> int:
    """0 = not a market story, 1..3 = impact tier (higher = runs earlier)."""
    text = f"{title} {summary}".lower()
    stems = _stems(text)
    for tier, weight in (("high", 3), ("mid", 2), ("low", 1)):
        for term in MARKET_TERMS[tier]:
            t = term.lower()
            if t in text:                       # exact / multi-word / English
                return weight
            if any(_stem(part) in stems.split() for part in t.split() if len(part) > 2):
                return weight
    return 0


def split_market(items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split collected news into (trading, everything else), trading sorted by impact."""
    trading, rest = [], []
    for it in items:
        score = market_score(str(it.get("title", "")), str(it.get("summary", "")))
        if score:
            it = {**it, "market_score": score}
            trading.append(it)
        else:
            rest.append(it)
    trading.sort(key=lambda i: (-int(i.get("market_score", 0)), -float(i.get("importance_score", 0))))
    return trading, rest


PROMPT = """You write the first 45 seconds of a Hindi daily bulletin Short (Devanagari).

TODAY: {date_hi}, {weekday_hi}
PANCHANG: {panchang}
TODAY'S FESTIVALS / SPECIAL DAY (from Drik Panchang, use only these): {festivals}
TODAY'S RASHIFAL HEADLINES (from Hindi news outlets, headline text only):
{rashifal}
TRADING NEWS of the day, already sorted by impact (index/policy first):
{trading}

TASK — write exactly four beats, in this order:
1. "date_line": the date + weekday + the festival/special day in ONE warm Hindi sentence, 12–20 words.
   If there is a festival or vrat today, name it and say in one clause why it matters.
2. "rashifal": 15–30 words. Say today's date's moon/star hint if the panchang gives one, then name the
   2–3 rashis that look best today and one that needs care. Astrology is belief, not fact: phrase it as
   "राशिफल के अनुसार…" — never as a promise of money or health.
3. "trading": 15–30 words naming the single biggest market story and its number (index level, rate, %),
   then one line on what it means for a normal viewer. Copy numbers ONLY from the trading headlines.
4. Follow with the rest of the news (handled elsewhere) — do NOT invent other news here.

RULES: no greeting, no channel name, no "नमस्कार". Numbers exactly as written in the sources.
Each beat is spoken by one anchor; give a matching screen description in "visual" (English, what the
camera shows) and "search" (2–4 English stock words). Never put a real politician's name in "visual".

Return JSON:
{{"date_line": {{"say": "...", "visual": "...", "search": "..."}},
  "rashifal":  {{"say": "...", "visual": "...", "search": "..."}},
  "trading":   {{"say": "...", "visual": "...", "search": "..."}},
  "best_rashis": ["मेष", "वृषभ"], "care_rashi": "मीन"}}"""


async def build_intro(llm, facts: DayFacts, rashifal: List[Dict[str, str]],
                      trading: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The three opening beats as ready-to-render parts (say/visual/search)."""
    trading_lines = "\n".join(
        f"- [{i.get('market_score', 1)}] {i.get('title', '')} — {str(i.get('summary', ''))[:110]}"
        for i in trading[:6]) or "- (no market story in the last 24h)"
    rash_lines = "\n".join(f"- {h['title']}" for h in rashifal[:6]) or "- (no rashifal headline today)"
    panchang = " ".join(x for x in [facts.paksha, facts.tithi, facts.nakshatra, facts.samvat] if x)
    prompt = PROMPT.format(date_hi=facts.date_hi, weekday_hi=facts.weekday_hi,
                           panchang=panchang or "(unavailable)",
                           festivals=", ".join(facts.festivals) or "(none listed)",
                           rashifal=rash_lines, trading=trading_lines)
    fallback = _fallback_intro(facts, trading)
    if llm is None:
        return fallback
    try:
        data = await llm.generate_json(prompt, tier="quality")
    except Exception as exc:
        logger.warning("intro LLM failed (%s) — deterministic intro", exc)
        return fallback

    def part(key: str) -> Optional[Dict[str, str]]:
        v = data.get(key)
        if isinstance(v, dict) and str(v.get("say", "")).strip():
            return {k: str(v.get(k, "") or "").strip()[:200]
                    for k in ("say", "visual", "entity", "search", "source")}
        if isinstance(v, str) and v.strip():
            return {"say": v.strip()[:400], "visual": "", "entity": "", "search": "", "source": ""}
        return None

    out = {"beats": [], "best_rashis": data.get("best_rashis") or [],
           "care_rashi": data.get("care_rashi") or "", "source": "llm"}
    for key, label in (("date_line", "आज की तारीख"), ("rashifal", "आज का राशिफल"),
                       ("trading", "बाज़ार")):
        p = part(key)
        if p:
            p.setdefault("entity", "")
            out["beats"].append({"kind": key, "chip": label, "parts": [p]})
    return out if out["beats"] else fallback


def _fallback_intro(facts: DayFacts, trading: List[Dict[str, Any]]) -> Dict[str, Any]:
    """No LLM: still open with the date, the parv and the top market line."""
    fest_names = [hindi_name(f) for f in facts.festivals[:2]]
    fest = f" आज {' और '.join(fest_names)} है।" if fest_names else ""
    date_say = f"आज {facts.weekday_hi}, {facts.date_hi} है।{fest}"
    beats = [{"kind": "date_line", "chip": "आज की तारीख",
              "parts": [{"say": date_say, "visual": "Hindu temple bells and a calendar page turning at sunrise",
                         "entity": "", "search": "hindu temple sunrise bells", "source": "stock"}]}]
    if facts.tithi:
        beats[0]["parts"].append(
            {"say": f"पंचांग के अनुसार आज {hindi_name(facts.tithi)} है।",
             "visual": "traditional Hindu panchang almanac open on a wooden table",
             "entity": "", "search": "hindu panchang almanac", "source": "stock"})
    if trading:
        t = trading[0]
        beats.append({"kind": "trading", "chip": "बाज़ार",
                      "parts": [{"say": f"बाज़ार की सबसे बड़ी खबर: {str(t.get('title', ''))[:120]}।",
                                 "visual": "stock market screen with rising green graph, Indian rupee notes",
                                 "entity": "", "search": "stock market graph india", "source": "stock"}]})
    return {"beats": beats, "best_rashis": [], "care_rashi": "", "source": "fallback"}


def gather(tz: str = "Asia/Kolkata") -> Dict[str, Any]:
    """Everything the intro needs, fetched once (sync; call from a thread if needed)."""
    facts = fetch_panchang(tz)
    facts.special = " और ".join(facts.festivals[:2])
    return {"facts": facts.to_dict(), "rashifal": fetch_horoscope_news()}
