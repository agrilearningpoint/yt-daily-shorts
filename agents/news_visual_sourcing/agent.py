"""News Visual Sourcing Agent.

Coordinates multi-source visual discovery (actual news photos, Wikimedia Commons,
Wikipedia entity photos, Openverse, Pexels, Pixabay, and labelled AI illustrations)
with strict priority for authentic event media and comprehensive license provenance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import NewsVisualAsset
from core.configuration import AppConfig
from core.state_manager import StateManager
from video.media_collector import MediaAsset, MediaCollector
from video.semantic_matcher import extract_entity_from_hindi


def calculate_keyword_match(text: str, labels: str) -> float:
    """Calculate lexical keyword overlap score between narration and asset labels."""
    import re

    t_words = set(re.findall(r"\w+", text.lower()))
    l_words = set(re.findall(r"\w+", labels.lower()))
    if not t_words or not l_words:
        return 0.50
    intersect = t_words.intersection(l_words)
    return min(1.0, max(0.20, len(intersect) / max(1, min(len(t_words), len(l_words)))))


class NewsVisualSourcingAgent(BaseAgent):
    """Sourcing, validation, and provenance tracking for news visual assets."""

    name: str = "NewsVisualSourcingAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        mcfg = config.media
        self.collector = MediaCollector(
            pexels_key=getattr(mcfg, "pexels_api_key", ""),
            pixabay_key=getattr(mcfg, "pixabay_api_key", ""),
            cache_dir=getattr(mcfg, "cache_dir", "data/media_cache"),
            use_wikimedia=getattr(mcfg, "use_wikimedia", True),
            use_openverse=getattr(mcfg, "use_openverse", True),
            use_publisher_images=getattr(mcfg, "use_publisher_images", True),
            use_news_photos=getattr(mcfg, "use_news_photos", True),
        )
        self.min_confidence = getattr(mcfg, "min_visual_confidence", 0.40)

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify scenes or script or stories are provided."""
        return bool(kwargs.get("scenes") or kwargs.get("script") or kwargs.get("stories"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute visual sourcing across all designated scenes or stories."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No scenes, script, or stories provided to NewsVisualSourcingAgent."],
            )

        video_id = kwargs.get("video_id", "sourcing_unk")
        script = kwargs.get("script", {})
        scenes = kwargs.get("scenes") or script.get("scenes", [])
        stories = kwargs.get("stories", [])
        research = kwargs.get("research_data", {}) or {}
        research_items = kwargs.get("research_items") or (
            research.get("items", []) if isinstance(research, dict) else []
        )
        out_dir = Path(kwargs.get("out_dir", f"output/{video_id}/visuals"))
        out_dir.mkdir(parents=True, exist_ok=True)

        assets_by_scene: Dict[str, NewsVisualAsset] = {}
        all_candidates: List[NewsVisualAsset] = []

        # 1. Process each scene
        for idx, sc in enumerate(scenes):
            scene_id = f"scene_{idx:03d}"
            say_text = sc.get("narration") or sc.get("narration_hi") or sc.get("text", "")
            query = sc.get("visual_keywords") or sc.get("visual_query") or sc.get("image_query", "")
            entity = (
                sc.get("entity")
                or extract_entity_from_hindi(say_text)
                or extract_entity_from_hindi(query)
            )

            # Try to match research item for authentic publisher photo
            matching_item = next(
                (
                    it
                    for it in research_items
                    if entity and entity.lower() in str(it.get("title", "")).lower()
                ),
                None,
            )
            if not matching_item and idx < len(research_items):
                matching_item = research_items[idx]

            dest_file = out_dir / f"{scene_id}.jpg"
            asset = self._source_scene_visual(
                scene_id=scene_id,
                query=query,
                entity=entity,
                say_text=say_text,
                dest_path=dest_file,
                research_item=matching_item,
                prefer_video=bool(idx % 4 == 1),  # B-roll preference for dynamic edits
            )

            if asset:
                assets_by_scene[scene_id] = asset
                all_candidates.append(asset)

        # 2. Process extracted stories if provided
        for st in stories:
            s_id = getattr(st, "story_id", "story_001")
            s_title = getattr(st, "title", "")
            s_entities = getattr(st, "entities", [])
            ent = s_entities[0] if s_entities else extract_entity_from_hindi(s_title)

            dest_file = out_dir / f"{s_id}.jpg"
            asset = self._source_scene_visual(
                scene_id=s_id,
                query=s_title,
                entity=ent,
                say_text=s_title,
                dest_path=dest_file,
                research_item=None,
            )
            if asset:
                all_candidates.append(asset)

        result_data = {
            "visual_assets": assets_by_scene,
            "candidate_pool": all_candidates,
            "total_sourced": len(assets_by_scene),
            "authentic_events_count": sum(
                1 for a in assets_by_scene.values() if a.actual_event_or_stock == "actual_event"
            ),
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "sourced_count": len(assets_by_scene)},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _source_scene_visual(
        self,
        scene_id: str,
        query: str,
        entity: str,
        say_text: str,
        dest_path: Path,
        research_item: Optional[Dict[str, Any]] = None,
        prefer_video: bool = False,
    ) -> Optional[NewsVisualAsset]:
        """Source a visual asset following strict news visual priority."""
        effective_query = query or entity or say_text[:60]
        media_asset: Optional[MediaAsset] = None
        actual_or_stock = "stock"
        source_provider = "unknown"

        # Priority 1: Publisher / News authentic event photo if available
        if research_item and (research_item.get("image_url") or research_item.get("source_url")):
            try:
                img_url = research_item.get("image_url") or research_item.get("source_url")
                media_asset = self.collector.article_image(img_url, dest_path)
                if media_asset:
                    actual_or_stock = "actual_event"
                    source_provider = media_asset.source or "publisher_news"
            except Exception as exc:
                self.logger.warning(
                    "Publisher image lookup failed (%s). Continuing hierarchy.", exc
                )

        # Priority 2: Stock or Sourced photography / visuals via Collector
        if not media_asset:
            try:
                pref_url = research_item.get("image_url", "") if research_item else ""
                art_url = research_item.get("source_url", "") if research_item else ""
                media_asset = self.collector.find_image(
                    keywords=effective_query,
                    dest_path=str(dest_path),
                    preferred_url=pref_url,
                    entity=entity or "",
                    article_url=art_url,
                )
                if media_asset:
                    actual_or_stock = "stock"
                    source_provider = media_asset.source or "stock_photo"
            except Exception as exc:
                self.logger.debug("find_image lookup error: %s", exc)

        # Priority 2b: B-roll Video if preferred and image not found
        if prefer_video and not media_asset:
            try:
                spec = {"say": say_text, "search": effective_query, "entity": entity, "video": True}
                media_asset = self.collector.find_visual(
                    spec, dest_path=str(dest_path), mode="news"
                )
                if media_asset:
                    source_provider = media_asset.source or "video_stock"
            except Exception as exc:
                self.logger.debug("find_visual video failed: %s", exc)

        # If nothing found, synthesize local placeholder image so pipeline never halts
        if not media_asset:
            if not dest_path.exists():
                self._create_solid_fallback(dest_path, entity or effective_query[:30])
            media_asset = MediaAsset(
                path=str(dest_path),
                source="designed_graphic",
                credit="BHARAT KI SOCH Graphics",
                labels=effective_query,
            )
            actual_or_stock = "illustrative_graphic"
            source_provider = "designed_card"

        # Calculate semantic match score against narration
        match_score = calculate_keyword_match(say_text, media_asset.labels or effective_query)
        is_ai = media_asset.source == "ai"

        # Determine real license provenance
        if media_asset.source == "publisher":
            license_name = "News Publisher Editorial Media (Reporting of Current Events)"
            license_url = research_item.get("source_url", "") if research_item else ""
        elif "wikimedia" in source_provider or media_asset.source == "wikipedia":
            license_name = "Creative Commons Attribution-ShareAlike (CC BY-SA)"
            license_url = "https://creativecommons.org/licenses/by-sa/4.0/"
        elif "pexels" in source_provider:
            license_name = "Pexels Free Commercial License"
            license_url = "https://www.pexels.com/license/"
        elif "pixabay" in source_provider:
            license_name = "Pixabay Content License"
            license_url = "https://pixabay.com/service/license-summary/"
        elif media_asset.source == "ai":
            license_name = "AI Generated Visual"
            license_url = ""
        else:
            license_name = "Original Broadcast Graphic"
            license_url = ""

        return NewsVisualAsset(
            asset_id=f"vis_{scene_id}",
            story_id=scene_id,
            asset_type="video_broll" if getattr(media_asset, "video", "") else "photo",
            local_path=media_asset.path,
            source_provider=source_provider,
            original_source_url=getattr(media_asset, "page_url", ""),
            source_page_url=getattr(media_asset, "page_url", ""),
            creator=media_asset.credit,
            license_name=license_name,
            license_url=license_url,
            attribution_required=bool(media_asset.credit),
            attribution_text=media_asset.credit,
            event_match_score=round(match_score, 2),
            visual_description=media_asset.labels or effective_query,
            actual_event_or_stock=actual_or_stock,
            is_ai_generated=is_ai,
            visual_confidence=0.95 if actual_or_stock == "actual_event" else 0.75,
            quality_score=0.90,
            download_status="ready",
        )

    def _create_solid_fallback(self, path: Path, label: str) -> None:
        """Create high-contrast broadcast news graphic card."""
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (1080, 1920), color=(18, 22, 34))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(40, 40), (1040, 1880)], outline=(220, 50, 40), width=6)
        draw.text((100, 900), label[:40], fill=(240, 240, 240))
        img.save(path, format="JPEG", quality=85)
