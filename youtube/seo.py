"""YouTube SEO formatting for titles and descriptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FormattedSEO:
    title: str
    description: str
    tags: List[str]
    category_id: str = "27"


class YouTubeSEOFormatter:
    @staticmethod
    def format_title(raw_title: str, max_length: int = 100) -> str:
        clean = " ".join(raw_title.replace("<", "").replace(">", "").split())
        if "#shorts" not in clean.lower():
            clean = f"{clean} #shorts"
        if len(clean) > max_length:
            clean = clean[: max_length - 11].rstrip() + "… #shorts"
        return clean

    @staticmethod
    def format_description(summary_hook: str, source_urls: List[str], hashtags: List[str],
                           channel_name: str = "BHARAT KI SOCH",
                           media_credits: Optional[List[str]] = None, max_length: int = 5000,
                           story_lines: Optional[List[str]] = None, sources_title: str = "") -> str:
        sources = f"📌 {sources_title or 'स्रोत / Sources'}:\n"
        if story_lines:
            sources += "".join(f"{line}\n" for line in story_lines)
        elif source_urls:
            sources += "".join(f"{i}. {u}\n" for i, u in enumerate(source_urls, 1))
        else:
            sources += "1. Official public sources\n"
        credits = ""
        if media_credits:
            credits = ("\n🖼️ तस्वीरें कहाँ से / Image credits:\n"
                       + "".join(f"• {c}\n" for c in list(dict.fromkeys(media_credits))[:25])
                       + "• जिन दृश्यों पर 'सांकेतिक चित्र (AI)' लिखा है, वे AI से बनाए गए हैं।\n")
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in hashtags)
        desc = (f"{summary_hook}\n\n{sources}{credits}\n"
                f"🔔 रोज़ ऐसी जानकारी के लिए {channel_name} को सब्सक्राइब करें!\n\n"
                "ℹ️ यह वीडियो AI की मदद से (स्क्रिप्ट व आवाज़) सार्वजनिक स्रोतों के आधार पर बनाया गया है। "
                "This video was produced with AI assistance from the public sources listed above.\n\n"
                f"{tags}")
        desc = desc.replace("<", "").replace(">", "")
        return desc[:max_length].strip()
