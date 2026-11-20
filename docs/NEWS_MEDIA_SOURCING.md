# News Visual Sourcing Agent — Technical Documentation

## 1. Overview & Mission

`NewsVisualSourcingAgent` manages authentic visual media acquisition for **BHARAT KI SOCH**. It prioritizes authentic editorial photos, historical public domain images, and Creative Commons media over synthetic AI generation, ensuring high journalistic credibility.

Location: `agents/news_visual_sourcing/agent.py`  
Contract: `NewsVisualAsset` in `core/agent_contracts.py`  
Unit Tests: `tests/test_agents/test_news_visual_sourcing.py`

---

## 2. Priority Waterfall Strategy

The agent queries visual sources in strict order of journalistic authority:

1. **Publisher News Editorial Photos**: High-resolution press images embedded in source news articles.
2. **Wikipedia Lead Images**: Authoritative biographical and institutional photographs.
3. **Wikimedia Commons**: Free and Creative Commons images with documented licensing.
4. **Pexels & Pixabay (Free Tier)**: High-quality b-roll stock photos and video clips.
5. **Designed News Cards (Pillow Fallback)**: Typographic 1080x1920 news graphic cards (deep slate, saffron/ruby straps) if no suitable photo meets the quality threshold.

---

## 3. Provenance & Legal Verification

Every sourced asset creates a `NewsVisualAsset` record documenting:
- `asset_id`: Unique tracking identifier.
- `story_id`: Associated news story or beat.
- `local_path`: Cached file path on disk.
- `source_provider`: Source repository (`publisher`, `wikipedia`, `wikimedia`, `pexels`, `pixabay`, `designed_card`).
- `license_name`: Explicit license (e.g., `Public Domain`, `CC BY-SA 4.0`, `Editorial Fair Use`).
- `attribution_required`: Boolean flag.
- `attribution_text`: Exact legal attribution string for YouTube description.
- `actual_event_or_stock`: Classification (`actual_event` vs `stock_representative`).
- `is_ai_generated`: Truthful flag (false for real photos; labeled `सांकेतिक चित्र (AI)` if AI).
