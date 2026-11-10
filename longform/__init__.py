"""Long-form (documentary) pipeline: 20-25 min videos, 16:9, unlisted by default.

Design goals
------------
* **Chapters, not one giant render.** Each chapter is scripted, voiced, illustrated
  and rendered independently, so a failure costs one chapter instead of the film.
* **Free at the edges.** edge-tts for narration (no Gemini quota burn), Wikimedia
  Commons for most visuals, AI images only as a last resort.
* **Resumable.** Every chapter writes its own JSON + media into `output/long/<id>/`
  and is skipped on the next run if already complete.
"""

__all__ = ["script", "media", "render", "pipeline"]
