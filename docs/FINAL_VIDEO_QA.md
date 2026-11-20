# Final Video Quality Assurance & Verification Standards

## 1. Overview & Quality Mandate

Quality Assurance across **BHARAT KI SOCH** operates on a zero-tolerance policy for audio-visual defects:
- No audio-video drift exceeding 0.05 seconds.
- No stretched, squashed, or incorrectly oriented visuals.
- No unverified or synthetic claims presented as authentic news.
- Strict YouTube Shorts vertical duration compliance (15.0s to 59.0s).

---

## 2. Multi-Tier Verification Gates

### Gate 1: Pre-Render Media & Font Audit (`VisualAudioMatchQAAgent`)
- Inspects every segment in `MasterEditingTimeline`.
- Asserts that all assigned visual assets (`.jpg`, `.png`, `.mp4`) exist on disk and exceed 100 bytes.
- Verifies that required typography fonts (`Mukta-Bold.ttf`, `Mukta-Regular.ttf`) are present in `assets/fonts/`.
- Validates semantic keyword presence between narration text and image subject metadata.

### Gate 2: FFmpeg Stream Inspection (`VideoQAInspector`)
- Container: MP4 (ISO Media / QuickTime).
- Resolution: Strictly 1080x1920 (9:16 vertical orientation).
- Video Codec: H.264 (AVC1), High profile, 30 FPS.
- Audio Codec: AAC, stereo or dual-mono, 44,100 Hz, $\ge 192$ kbps.
- Loudness: Broadcast integrated loudness normalized to -14.0 LUFS ($\pm 1.0$ LUFS), True Peak $\le -1.0$ dBFS.
- Black frames / freeze frame detection: Video is rejected if frozen frames exceed 1.5 seconds.

### Gate 3: Auto-Repair Mechanism
- If a rendered video slightly exceeds the YouTube Shorts hard duration ceiling (59.0s) due to audio tail decay, `VideoQAInspector.auto_repair_video` performs a safe, frame-accurate re-trim with an audio exponential crossfade to preserve Shorts status.

---

## 3. Verification Artifacts Produced in Phase 2

All test proofs are stored in `output/proofs/`:

1. `output/proofs/motion_presets_contact_sheet.png`: Complete visual contact sheet detailing all 56 motion presets across 7 categories.
2. `output/proofs/daily_bulletin_opening_sample.mp4`: Verified 1080x1920 30 FPS MP4 demonstrating opening red flash, Panchang card, Devanagari lower third, and news intro sting.
3. `output/proofs/news_short_sample.mp4`: Verified 1080x1920 30 FPS MP4 demonstrating Ken Burns photo motion, category badge, and background bed mixing.
4. `output/proofs/repurposed_short_sample.mp4`: Verified 1080x1920 30 FPS MP4 demonstrating 16:9 to 9:16 vertical re-framing with blurred ambient pillars and transition whoosh.
