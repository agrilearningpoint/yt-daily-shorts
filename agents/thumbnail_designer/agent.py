"""Thumbnail Designer Agent — designs attractive high-contrast cover cards."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont
from agents.base_agent import AgentResult, BaseAgent


class ThumbnailDesignerAgent(BaseAgent):
    """Produces 1080x1920 thumbnail posters with prominent Hindi typography."""

    name = "thumbnail_designer"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        creative_brief = kwargs.get("creative_brief", {})
        video_id = kwargs.get("video_id", "daily_short")

        out_path = Path("output") / video_id / "thumbnail.jpg"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        title = script.get("title", "आज की बड़ी खबर")
        thumb_file = self._create_thumbnail(title, str(out_path))

        return AgentResult(
            success=Path(thumb_file).exists(),
            data={"thumbnail_path": thumb_file}
        )

    def _create_thumbnail(self, title: str, output_path: str) -> str:
        width, height = 1080, 1920
        img = Image.new("RGB", (width, height), (15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Draw bold header background box
        draw.rectangle([60, 400, 1020, 950], fill=(230, 57, 70))
        draw.rectangle([80, 420, 1000, 930], fill=(20, 20, 20))

        # Title text
        words = title.split()
        lines = []
        curr = []
        for w in words:
            curr.append(w)
            if len(" ".join(curr)) > 16:
                lines.append(" ".join(curr))
                curr = []
        if curr:
            lines.append(" ".join(curr))

        y = 520
        for l in lines[:3]:
            draw.text((120, y), l, fill=(255, 255, 255))
            y += 90

        # Draw Yellow hook sticker
        draw.rectangle([120, 1050, 960, 1180], fill=(255, 214, 10))
        draw.text((150, 1090), "⚡ 60 सेकंड में पूरा सच!", fill=(0, 0, 0))

        img.save(output_path, "JPEG", quality=95)
        return output_path
