"""Typed data contracts for all pipeline agents and stages.

Provides validated dataclass structures for inputs, outputs, and shared production
context across the entire multi-agent YouTube Shorts generation system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class VideoFormat(str, Enum):
    NEWS = "news"
    KNOWLEDGE = "knowledge"


class VisualAssetType(str, Enum):
    PUBLISHER_PHOTO = "publisher_photo"
    WIKIPEDIA_PHOTO = "wikipedia_photo"
    COMMONS_PHOTO = "commons_photo"
    STOCK_PHOTO = "stock_photo"
    STOCK_VIDEO = "stock_video"
    DESIGNED_CARD = "designed_card"
    AI_ILLUSTRATION = "ai_illustration"


# ---------------------------------------------------------------------------
# Research & Fact Checking Contracts
# ---------------------------------------------------------------------------


@dataclass
class ResearchItem:
    title: str
    source_url: str
    source_name: str
    summary: str = ""
    image_url: str = ""
    region: str = "national"  # national | international | today
    seed: str = ""
    evidence: str = ""


@dataclass
class ResearchContext:
    video_type: str
    topic_category: str
    day_name: str
    items: List[ResearchItem] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    daily_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactVerificationReport:
    verdict: str  # pass | fixed | fail | skipped
    confidence: float
    issues: List[str] = field(default_factory=list)
    all_verified: bool = True
    verified_sources: List[str] = field(default_factory=list)
    dropped_scenes: List[int] = field(default_factory=list)
    corrected_scenes: Dict[int, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Creative & Hook Contracts
# ---------------------------------------------------------------------------


@dataclass
class CreativeBrief:
    theme_name: str
    primary_color: str
    secondary_color: str
    background_color: str
    caption_highlight: str
    transition_style: str
    music_mood: str
    font_name: str = "Mukta-ExtraBold"
    color_grade: str = "broadcast_crisp"
    editorial_tone: str = "authoritative_breaking"  # breaking | investigative | educational

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HookArchetype(str, Enum):
    CURIOSITY_GAP = "curiosity_gap"
    UNEXPECTED_FACT = "unexpected_fact"
    STRONG_STATEMENT = "strong_statement"
    DIRECT_IMPACT = "direct_impact"
    BREAKING_NEWS = "breaking_news"
    EMOTIONAL_INTRIGUE = "emotional_intrigue"


@dataclass
class HookCandidate:
    archetype: HookArchetype
    text: str
    impact_score: float  # 0-100: First-second attention grabbing
    curiosity_score: float  # 0-100: Compelling intrigue
    clarity_score: float  # 0-100: Clear, direct meaning
    factual_score: float  # 0-100: Strict adherence to research facts
    naturalness_score: float  # 0-100: Natural spoken Hindi phrasing
    visual_potential: float  # 0-100: Matches high-impact visual
    composite_score: float = 0.0
    visual_pairing: str = ""  # Subject/entity required for visual pairing


@dataclass
class ApprovedHook:
    text: str
    archetype: str
    composite_score: float
    visual_pairing_query: str
    headline_chip: str
    entity_hint: str = ""


# ---------------------------------------------------------------------------
# Script & Narration Contracts
# ---------------------------------------------------------------------------


@dataclass
class VisualBeatSpec:
    beat_index: int
    say_text: str
    entity: str = ""
    search_query: str = ""
    visual_type: VisualAssetType = VisualAssetType.WIKIPEDIA_PHOTO
    publisher_image: str = ""
    publisher_name: str = ""
    article_url: str = ""


@dataclass
class ScriptScene:
    scene_number: int
    narration: str
    on_screen_text: str
    visual_keywords: str
    image_query: str
    category: str
    headline: str
    section: str = "national"  # national | international | today
    sources: List[str] = field(default_factory=list)
    beats: List[VisualBeatSpec] = field(default_factory=list)


@dataclass
class ApprovedScript:
    title: str
    hook: ApprovedHook
    scenes: List[ScriptScene] = field(default_factory=list)
    outro: str = ""
    video_type: str = "news"
    total_words: int = 0
    estimated_duration: float = 0.0
    sources: List[str] = field(default_factory=list)

    def word_count(self) -> int:
        return (
            len(self.hook.text.split())
            + sum(len(s.narration.split()) for s in self.scenes)
            + len(self.outro.split())
        )


# ---------------------------------------------------------------------------
# Synchronization, VFX & Motion Graphics Contracts
# ---------------------------------------------------------------------------


@dataclass
class WordTimingItem:
    word: str
    start: float  # seconds from video start
    end: float  # seconds from video start


@dataclass
class TimelineSegmentContract:
    scene_id: str
    segment_id: str
    text: str
    audio_path: str
    audio_start: float
    audio_end: float
    measured_duration: float
    visual_id: str
    visual_path: str
    visual_start: float
    visual_end: float
    visual_source: str
    transition_effect: str
    camera_motion: str
    overlay_path: Optional[str] = None
    chip_path: Optional[str] = None
    sfx_cue: Optional[str] = None
    captions: List[WordTimingItem] = field(default_factory=list)
    motion_preset_id: Optional[str] = None
    is_video_asset: bool = False
    video_trim_start: float = 0.0
    video_trim_end: float = 0.0


@dataclass
class VFXPlanItem:
    scene_id: str
    transition_effect: str  # clean_cut, whip_pan, punch, flash, light_leak, dip
    camera_motion: str  # push_in, pull_out, pan_left, pan_right, subtle_drift
    color_grade: str
    intensity: float = 1.0
    sfx_type: Optional[str] = None
    motion_preset_id: Optional[str] = None


@dataclass
class MotionGraphicsPlanItem:
    scene_id: str
    overlay_path: str
    headline: str
    category_badge: str
    story_counter: str
    is_hook: bool = False
    progress_percent: float = 0.0
    motion_preset_id: Optional[str] = None


@dataclass
class MasterEditingTimeline:
    video_id: str
    total_duration: float
    segments: List[TimelineSegmentContract] = field(default_factory=list)
    master_audio_path: str = ""
    captions_ass_path: str = ""
    captions_srt_path: str = ""
    music_track_path: Optional[str] = None
    music_volume: float = 0.10
    color_grade_filter: str = ""
    audio_mix_plan: Optional[Any] = None
    opening_brief: Optional[Any] = None
    visual_assets: List[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Quality & Output Artifact Contracts
# ---------------------------------------------------------------------------


@dataclass
class QualityVerificationVerdict:
    approved: bool
    overall_score: float
    script_passed: bool
    voice_passed: bool
    visuals_passed: bool
    sync_passed: bool
    technical_passed: bool
    measured_duration: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class VisualAudioMatchResult:
    approved: bool
    overall_match_score: float
    pre_render_passed: bool
    post_render_passed: bool
    sync_drift_seconds: float
    av_alignment_score: float
    semantic_match_ratio: float
    checks: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ProductionArtifacts:
    video_id: str
    video_path: str
    thumbnail_path: str
    captions_srt_path: str
    captions_ass_path: str
    voiceover_path: str
    timings_json_path: str
    measured_duration: float
    youtube_id: str = ""
    youtube_url: str = ""
    telegram_delivered: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Long Video Intelligence & Shorts Repurposing Contracts
# ---------------------------------------------------------------------------


@dataclass
class SourceVideoManifest:
    video_id: str
    source_uri: str
    is_local_file: bool
    local_path: str
    sha256: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    audio_channels: int
    audio_sample_rate: int
    has_audio: bool
    detected_language: str = "hi"
    title: str = ""
    author: str = ""
    license: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WordTiming:
    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class SpeakerProfile:
    speaker_id: str
    display_name: str
    role: str = "speaker"  # anchor, guest, official, reporter, narrator
    speaking_duration: float = 0.0
    gender: str = "unknown"


@dataclass
class TranscriptSegment:
    segment_id: str
    speaker_id: str
    start: float
    end: float
    text: str
    confidence: float = 1.0
    words: List[WordTiming] = field(default_factory=list)
    language: str = "hi"


@dataclass
class VisualScene:
    scene_index: int
    start: float
    end: float
    keyframe_path: str
    scene_type: str = "studio_anchor"  # studio_anchor, split_interview, field_reporting, graphic_infographic, broll_footage
    chyron_text: str = ""
    has_person: bool = True
    vertical_crop_safe: bool = True
    speaker_position: str = "center"  # center, left, right, multi


@dataclass
class ExtractedStory:
    story_id: str
    title: str
    category: str  # politics, economy, science, national, international, sports
    start_time: float
    end_time: float
    key_facts: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    transcript_excerpt: str = ""
    completeness_score: float = 1.0
    lead_speaker: str = ""
    recommended_angle: str = ""


@dataclass
class EvidenceSource:
    name: str
    url: str
    reliability_score: float = 0.9
    is_government: bool = False
    published_date: str = ""


@dataclass
class EvidenceClaim:
    claim_id: str
    story_id: str
    claim_text: str
    status: str = "verified"  # verified, unverified, disputed, context_required
    confidence: float = 1.0
    explanation: str = ""
    sources: List[EvidenceSource] = field(default_factory=list)
    updated_context: str = ""


@dataclass
class StoryRanking:
    story_id: str
    composite_score: float  # 0-100
    factors: Dict[str, float] = field(default_factory=dict)
    recommended_duration: int = 60  # 30, 45, 60
    priority_flag: str = "top_pick"  # top_pick, viable, backlog, rejected
    selection_rationale: str = ""
    hook_angle: str = ""


@dataclass
class SelectedClip:
    clip_id: str
    story_id: str
    start_time: float
    end_time: float
    duration: float
    quote_text: str
    speaker_id: str
    audio_quality: str = "clean"  # clean, background_noise, overlap
    visual_quality: str = "high"  # high, medium, low
    crop_focus: str = "center"  # center, left, right
    is_hook_candidate: bool = False
    purpose: str = "soundbite"  # hook, core_statement, reaction, broll


@dataclass
class AdaptedShortScene:
    scene_index: int
    scene_type: str  # source_clip, photo_context, graphic_card, broll
    duration: float
    narration_hi: str
    source_clip_id: Optional[str] = None
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    visual_query: str = ""
    on_screen_text: str = ""
    headline_chip: str = ""
    camera_motion: str = "subtle_drift"
    transition: str = "clean_cut"


@dataclass
class AdaptedShortScript:
    short_id: str
    story_id: str
    title_hi: str
    hook_text_hi: str
    hook_archetype: str
    target_duration: int  # 30, 45, 60
    estimated_duration: float
    scenes: List[AdaptedShortScene] = field(default_factory=list)
    outro_hi: str = ""
    source_attributions: List[str] = field(default_factory=list)
    evidence_citations: List[str] = field(default_factory=list)
    category_badge: str = ""

    def to_script_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title_hi,
            "hook": self.hook_text_hi,
            "outro": self.outro_hi,
            "video_type": "repurposed_news",
            "scenes": [
                {
                    "scene_index": s.scene_index,
                    "scene_type": s.scene_type,
                    "duration": s.duration,
                    "narration": s.narration_hi,
                    "visual_keywords": s.visual_query,
                    "image_query": s.visual_query,
                    "on_screen_text": s.on_screen_text,
                    "headline": s.headline_chip,
                    "category": getattr(self, "category_badge", "राष्ट्रीय") or "राष्ट्रीय",
                    "camera_motion": s.camera_motion,
                    "transition_effect": s.transition,
                }
                for s in self.scenes
            ],
            "sources": self.source_attributions,
            "evidence": self.evidence_citations,
        }


@dataclass
class MediaRightsRecord:
    source_uri: str
    source_owner: str
    license_type: str = "fair_use_commentary"
    risk_level: str = "low"  # low, medium, high
    fair_use_score: float = 0.85
    max_clip_duration_seconds: float = 8.0
    mandatory_on_screen_credit: str = ""
    description_attribution_text: str = ""
    warnings: List[str] = field(default_factory=list)
    replacement_recommended: bool = False


@dataclass
class RepurposingJobResult:
    job_id: str
    source_manifest: SourceVideoManifest
    total_stories_extracted: int
    ranked_stories: List[StoryRanking] = field(default_factory=list)
    generated_shorts: List[AdaptedShortScript] = field(default_factory=list)
    rights_records: Dict[str, MediaRightsRecord] = field(default_factory=dict)
    status: str = "completed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Phase 2 — Daily Opening, Audio Sound Design & Visual Sourcing Contracts
# ---------------------------------------------------------------------------


@dataclass
class DailyOpeningBrief:
    date_iso: str
    date_hi: str
    weekday_hi: str
    panchang: Dict[str, Any] = field(default_factory=dict)
    festivals: List[str] = field(default_factory=list)
    national_observances: List[str] = field(default_factory=list)
    international_observances: List[str] = field(default_factory=list)
    on_this_day_events: List[str] = field(default_factory=list)
    selected_special_day: str = ""
    verified_facts: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    opening_hook_candidates: List[Dict[str, Any]] = field(default_factory=list)
    selected_hook: str = ""
    spoken_script: str = ""
    visual_beats: List[Dict[str, Any]] = field(default_factory=list)
    motion_preset_ids: List[str] = field(default_factory=list)
    sound_cue_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0
    verification_status: str = "verified"  # verified, partial, fallback
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SoundCueContract:
    cue_id: str
    scene_id: str
    sound_type: str  # sting, transition, whoosh, impact, bed, riser, click
    sound_path: str
    start_time: float
    end_time: float
    gain_db: float = -6.0
    fade_in: float = 0.05
    fade_out: float = 0.05
    ducking_priority: int = 1  # 0 = no ducking, 1 = normal, 2 = high priority (voice over it)
    trigger_type: str = "transition"  # transition, overlay, headline, hook, outro
    source_license: str = "cc0"
    attribution: str = ""
    required_or_optional: str = "optional"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AudioMixPlan:
    mix_id: str
    total_duration: float
    narration_audio_path: str
    background_bed_path: str
    bed_volume: float = 0.10
    ducked_volume: float = 0.03
    sound_cues: List[SoundCueContract] = field(default_factory=list)
    target_loudness_lufs: float = -14.0
    true_peak_limit_db: float = -1.0
    output_master_audio_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NewsVisualAsset:
    asset_id: str
    story_id: str
    asset_type: str  # photo, video_broll, graphic_chart, map
    local_path: str
    source_provider: str  # wikimedia, publisher, openverse, pexels, pixabay, official_gov
    original_source_url: str = ""
    source_page_url: str = ""
    creator: str = ""
    license_name: str = ""
    license_url: str = ""
    attribution_required: bool = False
    attribution_text: str = ""
    event_match_score: float = 1.0
    visual_description: str = ""
    actual_event_or_stock: str = (
        "actual_event"  # actual_event, institutional_broll, stock, illustrative_graphic
    )
    is_ai_generated: bool = False
    visual_confidence: float = 1.0
    quality_score: float = 1.0
    download_status: str = "ready"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Word-Level Visual Cuts Contracts
# ---------------------------------------------------------------------------


@dataclass
class WordCut:
    group_id: str
    start: float
    end: float
    text: str
    words: List[Any] = field(default_factory=list)
    visual_asset: str = ""
    motion_preset_id: str = "ken_burns_zoom_in"
    transition_effect: str = "none"
    vfx_cue: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WordCutPlan:
    video_id: str
    fps: int
    audio_path: str
    duration: float
    cuts: List[WordCut] = field(default_factory=list)
    captions: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

