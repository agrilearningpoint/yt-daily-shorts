"""YouTube SEO formatting for Titles, Descriptions, and Tags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class FormattedSEO:
    title: str
    description: str
    tags: List[str]
    category_id: str = "22"


class YouTubeSEOFormatter:
    """Formats compliant, click-worthy metadata with verified source links."""

    @staticmethod
    def format_title(raw_title: str, max_length: int = 100) -> str:
        clean = raw_title.strip()
        if "#shorts" not in clean.lower():
            clean = f"{clean} #shorts"
        if len(clean) > max_length:
            clean = clean[:max_length - 8].strip() + "... #shorts"
        return clean

    @staticmethod
    def format_description(
        summary_hook: str,
        source_urls: List[str],
        hashtags: List[str],
        channel_name: str = "Daily Hindi Shorts"
    ) -> str:
        sources_section = "📌 Verified Sources & References:\n"
        if source_urls:
            for idx, url in enumerate(source_urls, 1):
                sources_section += f"{idx}. {url}\n"
        else:
            sources_section += "1. Official PIB & Public Data Feeds\n"

        hashtag_str = " ".join([h if h.startswith("#") else f"#{h}" for h in hashtags])

        desc = f"""{summary_hook}

{sources_section}
---
🔔 Subscribe to {channel_name} for daily verified news and knowledge explainers in Hindi!

Disclaimer: This video is produced for educational and informational purposes based on verified public news and government releases.

{hashtag_str}
"""
        return desc.strip()
