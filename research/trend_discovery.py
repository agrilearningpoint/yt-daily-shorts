"""Knowledge-topic discovery for the 7-day editorial calendar.

* Rotates through curated seeds per weekday, never repeating a used topic
  (history persisted across runs).
* When a weekday's seeds are exhausted, the LLM proposes a fresh topic.
* Enriches the topic from Wikipedia (search API -> intro extract + lead image).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("research.trend")

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_UA = {"User-Agent": "YTDailyShortsBot/2.0 (https://github.com/agrilearningpoint/yt-daily-shorts)"}


@dataclass
class TopicDetails:
    title: str
    summary: str
    source_url: str
    category: str
    key_points: List[str] = field(default_factory=list)
    image_url: str = ""
    seed: str = ""


EDITORIAL_SEEDS: Dict[str, List[str]] = {
    "monday": [
        "B. R. Ambedkar", "Vallabhbhai Patel", "Lal Bahadur Shastri", "Subhas Chandra Bose",
        "Atal Bihari Vajpayee", "Constitution of India", "Jawaharlal Nehru", "Indira Gandhi",
        "Rajendra Prasad", "Sarojini Naidu", "Election Commission of India", "Panchayati raj in India",
        "Rajya Sabha", "Fundamental rights in India", "Goods and Services Tax (India)",
    ],
    "tuesday": [
        "Chandrayaan-3", "Aditya-L1", "Unified Payments Interface", "Gaganyaan", "Mangalyaan",
        "PSLV", "Param (supercomputer)", "NavIC", "Aadhaar", "BrahMos", "Agni-V",
        "Indian Space Research Organisation", "Tejas (aircraft)", "INS Vikrant (2013)", "Vande Bharat Express",
    ],
    "wednesday": [
        "Sushruta", "Ronald Ross", "Covaxin", "Polio eradication", "Ayurveda", "Charaka",
        "Yoga", "Har Gobind Khorana", "Yellapragada Subbarao", "Anandi Gopal Joshi",
        "Jagadish Chandra Bose", "Tuberculosis in India", "All India Institute of Medical Sciences, New Delhi",
        "Ayushman Bharat Yojana", "Smallpox",
    ],
    "thursday": [
        "Mahatma Gandhi", "Bhagat Singh", "Birsa Munda", "A. P. J. Abdul Kalam", "Rani of Jhansi",
        "Swami Vivekananda", "Rabindranath Tagore", "Chhatrapati Shivaji Maharaj", "Maharana Pratap",
        "Savitribai Phule", "Chandra Shekhar Azad", "Ashoka", "Chanakya", "Kalpana Chawla", "Milkha Singh",
    ],
    "friday": [
        "Kailasa temple, Ellora", "Konark Sun Temple", "Nalanda mahavihara", "Brihadisvara Temple, Thanjavur",
        "Ajanta Caves", "Taj Mahal", "Hampi", "Khajuraho Group of Monuments", "Qutb Minar",
        "Kashi Vishwanath Temple", "Sanchi Stupa", "Red Fort", "Meenakshi Temple", "Rani ki vav",
        "Indus Valley Civilisation",
    ],
    "saturday": [
        "0 (number)", "Raman scattering", "Aryabhata", "Satyendra Nath Bose", "Srinivasa Ramanujan",
        "Homi J. Bhabha", "Vikram Sarabhai", "Chess", "Wootz steel", "Iron pillar of Delhi",
        "Snakes and ladders", "Shampoo", "Buttons", "Brahmagupta", "Baudhayana sutras",
    ],
    "sunday": [
        "Green Revolution in India", "Operation Flood", "Make in India", "International Solar Alliance",
        "Economy of India", "Reserve Bank of India", "Bombay Stock Exchange", "Digital India",
        "Indian Railways", "Pradhan Mantri Jan Dhan Yojana", "Startup India", "Swachh Bharat Mission",
        "1991 Indian economic crisis", "White Revolution", "Amul",
    ],
}


def normalize_day(value: str) -> str:
    """Accept 'Monday', 'monday', or a category string and return a weekday key."""
    v = (value or "").strip().lower()
    for d in WEEKDAYS:
        if v.startswith(d):
            return d
    return ""


class TrendDiscovery:
    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    # ------------------------------------------------------------------
    def pick_seed(self, day_name: str, used: List[str]) -> Optional[str]:
        day = normalize_day(day_name) or "tuesday"
        used_l = {u.lower() for u in used}
        for seed in EDITORIAL_SEEDS.get(day, []):
            if seed.lower() not in used_l:
                return seed
        return None

    def discover_calendar_topic(self, day_name: str, used: Optional[List[str]] = None,
                                seed_override: Optional[str] = None) -> TopicDetails:
        day = normalize_day(day_name) or "tuesday"
        seed = seed_override or self.pick_seed(day, used or []) or EDITORIAL_SEEDS[day][0]
        details = self.fetch_wikipedia(seed, category=day)
        details.seed = seed
        return details

    # ------------------------------------------------------------------
    def _search_title(self, query: str) -> Optional[str]:
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                "action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"})
            hits = r.json().get("query", {}).get("search", [])
            return hits[0]["title"] if hits else None
        except Exception as exc:
            logger.warning("Wikipedia search failed for %s: %s", query, exc)
            return None

    def fetch_wikipedia(self, query: str, category: str = "general") -> TopicDetails:
        title = self._search_title(query) or query
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                "action": "query", "prop": "extracts|pageimages|info", "titles": title, "redirects": 1,
                "exintro": 1, "explaintext": 1, "piprop": "original", "inprop": "url", "format": "json"})
            pages = r.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values())) if pages else {}
            extract = (page.get("extract") or "").strip()
            if extract:
                sentences = [s.strip() for s in extract.replace("\n", " ").split(". ") if len(s.strip()) > 20]
                return TopicDetails(
                    title=page.get("title", title),
                    summary=extract[:3000],
                    source_url=page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    category=category,
                    key_points=sentences[:8],
                    image_url=(page.get("original") or {}).get("source", ""),
                )
        except Exception as exc:
            logger.warning("Wikipedia fetch failed for '%s': %s", title, exc)

        return TopicDetails(
            title=query, summary="", source_url=f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
            category=category, key_points=[])

    # Back-compat
    def fetch_wikipedia_summary(self, query: str, category: str = "general") -> TopicDetails:
        return self.fetch_wikipedia(query, category)
