"""Dynamic topic and trend discovery for the 7-day editorial calendar."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
import requests

logger = logging.getLogger("research.trend")


@dataclass
class TopicDetails:
    title: str
    summary: str
    source_url: str
    category: str
    key_points: List[str]


# Curated high-impact topics for 7-day calendar rotation as seeds
EDITORIAL_SEEDS: Dict[str, List[str]] = {
    "monday": [
        "Dr. B. R. Ambedkar and Constitution of India",
        "Sardar Vallabhbhai Patel and Integration of India",
        "Lal Bahadur Shastri and Jai Jawan Jai Kisan",
        "Netaji Subhash Chandra Bose and Azad Hind Fauj",
        "Atal Bihari Vajpayee and Golden Quadrilateral"
    ],
    "tuesday": [
        "Chandrayaan-3 and India's Moon Landing",
        "Aditya-L1 India's Solar Mission",
        "India's UPI and Digital Public Infrastructure",
        "Param Supercomputers and India's AI Mission",
        "Gaganyaan India's Manned Spaceflight Mission"
    ],
    "wednesday": [
        "Ayurveda and Modern Medical Validation",
        "Discovery of Malaria transmission in India by Ronald Ross",
        "India's Indigenous Covid Vaccine Covaxin",
        "Sushruta - Ancient Indian Father of Surgery",
        "Eradication of Polio in India"
    ],
    "thursday": [
        "Mahatma Gandhi and Non-Violent Satyagraha",
        "Bhagat Singh and the Revolutionary Spirit",
        "Birsa Munda and Tribal Freedom Struggle",
        "A. P. J. Abdul Kalam - The Missile Man of India",
        "Rani Lakshmibai and 1857 Revolt"
    ],
    "friday": [
        "Kailasa Temple Ellora - Monolithic Wonder",
        "Konark Sun Temple Architectural Marvel",
        "Nalanda University - Ancient Global Seat of Learning",
        "Brihadisvara Temple Thanjavur Living Chola Architecture",
        "Ajanta and Ellora Caves Heritage"
    ],
    "saturday": [
        "Invention of Zero by Ancient Indian Mathematician Aryabhata",
        "Raman Effect - Sir C. V. Raman Nobel Prize",
        "Jagadish Chandra Bose and Discovery of Plant Response and Radio Waves",
        "Bose-Einstein Condensate - Satyendra Nath Bose",
        "Srinivasa Ramanujan - The Mathematical Genius"
    ],
    "sunday": [
        "India's Green Revolution and Food Security",
        "White Revolution - Dr. Verghese Kurien and Amul",
        "India's Transition to 5 Trillion Dollar Economy",
        "India's Renewable Energy Push and Solar Alliance",
        "Make in India and Semiconductor Manufacturing Hub"
    ]
}


class TrendDiscovery:
    """Discovers verified topics from Wikipedia API and editorial rotation."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def discover_calendar_topic(self, day_name: str, seed_index: int = 0) -> TopicDetails:
        day_key = day_name.lower().strip()
        candidates = EDITORIAL_SEEDS.get(day_key, EDITORIAL_SEEDS["tuesday"])
        chosen_topic = candidates[seed_index % len(candidates)]
        
        # Enrich via Wikipedia API
        return self.fetch_wikipedia_summary(chosen_topic, category=day_key)

    def fetch_wikipedia_summary(self, query: str, category: str = "general") -> TopicDetails:
        """Fetch summary and official link from Wikipedia REST API."""
        encoded_query = query.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
        headers = {"User-Agent": "YTDailyShortsBot/1.0 (educational-automation)"}

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", query)
                extract = data.get("extract", "")
                page_url = data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{encoded_query}")
                
                # Split extract into key points
                sentences = [s.strip() for s in extract.split(". ") if len(s.strip()) > 15]
                return TopicDetails(
                    title=title,
                    summary=extract,
                    source_url=page_url,
                    category=category,
                    key_points=sentences[:4]
                )
        except Exception as exc:
            logger.warning("Wikipedia fetch failed for '%s': %s", query, exc)

        return TopicDetails(
            title=query,
            summary=f"{query} is a historically and culturally significant subject in India.",
            source_url="https://en.wikipedia.org",
            category=category,
            key_points=[f"{query} has a deep legacy and major impact."]
        )
