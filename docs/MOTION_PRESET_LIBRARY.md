# 56 Broadcast Motion Presets Library — Technical Reference

## 1. Architecture & Design Principles

The Motion Presets Library (`video/motion_presets/`) provides 56 distinct, fully parameterizable motion presets engineered specifically for 1080x1920 9:16 vertical video production for **BHARAT KI SOCH**.

Location: `video/motion_presets/`  
Catalog Registry: `video/motion_presets/catalog.py`  
Data Models: `video/motion_presets/models.py`  
Unit Tests: `tests/test_video/test_motion_preset_catalog.py`

---

## 2. The 7 Preset Families (8 Presets Each = 56 Total)

### Family 1: Openers (`openers.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 01 | `opener_breaking_red_flash` | Breaking Red Flash | 1.5s | Urgent crimson strobe flash seizing attention in first 0.5s |
| 02 | `opener_headline_slam` | Headline Slam | 1.2s | Perspective zoom slam with simulated impact shake |
| 03 | `opener_date_flip` | Date & Panchang Flip | 2.0s | 3D card flip revealing date, weekday, and Tithi |
| 04 | `opener_light_sweep` | Broadcast Light Sweep | 1.8s | Diagonal specular sheen across glass news backdrop |
| 05 | `opener_radar_pulse` | Radar Geo Pulse | 2.2s | Concentric radar rings pulsing outward from map coordinate |
| 06 | `opener_split_screen` | Dynamic Split Screen Opener | 2.5s | Dual-feed top/bottom split revealing comparison angles |
| 07 | `opener_zoom_punch` | Kinetic Zoom Punch | 1.0s | Rapid in-out pulse synchronized with audio bass impact |
| 08 | `opener_cinematic_opener` | Cinematic Knowledge Opener | 2.5s | Anamorphic vignette and warm amber lighting for documentaries |

### Family 2: Headline Reveals (`headline_reveals.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 09 | `headline_bottom_up` | Bottom-Up Lower Third | 0.8s | Slide-up with subtle overshoot into reading position |
| 10 | `headline_left_right_strap` | Left-to-Right Strap Wipe | 0.9s | Saffron anchor bar extends from left unmasking Devanagari text |
| 11 | `headline_kinetic_word_pop` | Kinetic Word Pop | 1.4s | Words pop in succession synchronized with voice cadence |
| 12 | `headline_masked_wipe` | Masked Geometric Wipe | 0.7s | 45-degree angled chevron wipe revealing headline plate |
| 13 | `headline_double_chyron` | Double-Tier Broadcast Chyron | 1.0s | Two-layer strap: top topic tag, bottom wider headline |
| 14 | `headline_typewriter` | Devanagari Typewriter Unfold | 1.6s | Character sequential unfold with blinking cursor |
| 15 | `headline_category_badge` | Category Badge Flip-In | 0.6s | Pill badge scales and flips with 3D spring dynamics |
| 16 | `headline_story_counter` | Story Index Counter Tick | 0.5s | Digital story flip counter (e.g. 01/20) with border pulse |

### Family 3: Photo Motion (`photo_motion.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 17 | `photo_slow_push_in` | Slow Dramatic Push-In | 3.5s | High-precision center push zoom (1.00 -> 1.14) |
| 18 | `photo_smooth_pull_out` | Smooth Context Pull-Out | 3.5s | Starts on tight detail, pulls out (1.15 -> 1.00) revealing setting |
| 19 | `photo_diagonal_pan` | Diagonal Narrative Pan | 4.0s | Pan across documents, maps, or wide panoramic assemblies |
| 20 | `photo_horizontal_parallax` | Horizontal Parallax Glide | 3.5s | Simulated camera movement on a motorized slider |
| 21 | `photo_vertical_parallax` | Vertical Skyscraper Parallax | 3.5s | Vertical pedestal tilt upward along tall structures/figures |
| 22 | `photo_focus_crop` | Rule of Thirds Face Crop | 3.0s | Dynamic re-centering towards upper 1/3 eye line |
| 23 | `photo_depth_zoom` | 3D Depth Map Simulated Zoom | 3.5s | Foreground subject pushes forward faster than background |
| 24 | `photo_detail_to_wide` | Detail to Wide Context Snap | 3.5s | Holds on crucial detail for 1.2s then snaps to full scene |

### Family 4: Video Reframe (`video_reframe.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 25 | `video_speaker_focus_reframe` | Speaker Focus Center Reframe | 3.5s | 16:9 source centered with blurred ambient mirror pillars |
| 26 | `video_face_follow_vertical_crop` | Face-Follow Vertical Dynamic Crop | 4.0s | Direct 9:16 crop tracked to human face coordinates |
| 27 | `video_reporter_split_screen` | Anchor & Ground Reporter Split | 4.5s | Dual feed stack: studio anchor top, ground reporter bottom |
| 28 | `video_pip_headline` | Picture-in-Picture News Box | 3.0s | Floating rounded PiP video window with drop shadow |
| 29 | `video_two_source_comparison` | Two-Source Claim Comparison | 4.0s | Stacked split comparing claims vs evidence |
| 30 | `video_dynamic_montage` | Dynamic Fast-Cut B-Roll Montage | 3.0s | Rapid 0.6s–1.2s b-roll rhythm with alternating zoom directions |
| 31 | `video_to_headline_transition` | Video Push to Headline Strap | 2.0s | Live video shrinks upward while bottom expands for facts |
| 32 | `video_vertical_subject_tracking` | Vertical Moving Subject Tracking | 4.0s | Interpolated pan window following moving delegates/vehicles |

### Family 5: Data Graphics (`data_graphics.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 33 | `data_map_zoom` | Geographic Region Map Zoom | 3.0s | Pushes from all-India down to specific state/district |
| 34 | `data_location_pin` | Animated Location Pin Drop | 1.2s | 3D location marker drops with spring bounce and ripple ring |
| 35 | `data_route_line_draw` | Animated Transit Route Line | 2.5s | Glowing corridor line draws across map between stations |
| 36 | `data_number_count_up` | Economic Metric Count-Up | 1.8s | Numbers rapidly tick up from zero to target value (e.g. ₹5 Trillion) |
| 37 | `data_statistics_bar` | Comparative Bar Graph Growth | 2.0s | Horizontal comparison bars expand smoothly |
| 38 | `data_timeline_progress` | Historical Milestones Timeline | 3.0s | Milestone nodes illuminate sequentially along progress axis |
| 39 | `data_quote_highlight` | Key Statement Quote Card | 3.5s | Typographic statement card with animated quotation marks |
| 40 | `data_chart_draw_on` | Interactive Line Chart Unfold | 2.4s | Market index or trend curve draws from left to right |

### Family 6: Transitions (`transitions.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 41 | `transition_fast_whip` | Fast Camera Whip Pan | 0.35s | High-velocity directional whip pan with horizontal blur |
| 42 | `transition_luma_dissolve` | Luma Contrast Dissolve | 0.5s | Smooth luminance-weighted dissolve through highlights |
| 43 | `transition_diagonal_wipe` | 45-Degree High-Contrast Wipe | 0.4s | 45-degree blade wipe with saffron edge highlight |
| 44 | `transition_light_sweep` | Specular Light Beam Transition | 0.45s | Gold/white streak blinding the cut between topics |
| 45 | `transition_rgb_glitch` | Limited Tech RGB Glitch Cut | 0.25s | 3-frame chromatic aberration split for breaking alerts |
| 46 | `transition_smooth_blur_swipe` | Smooth Directional Blur Swipe | 0.45s | Gentle push-swipe with directional gaussian blur |
| 47 | `transition_impact_flash` | Impact Flash Cut | 0.2s | Instantaneous 2-frame flash matched to audio impact |
| 48 | `transition_clean_cut` | Broadcast Clean Straight Cut | 0.05s | Zero-dissolve standard newsroom cut between related beats |

### Family 7: Brand & Outros (`brand_outros.py`)
| Index | Preset ID | Name | Duration | Description |
| :--- | :--- | :--- | :--- | :--- |
| 49 | `brand_national_bumper` | National News Segment Bumper | 1.5s | Saffron/navy bumper introducing domestic coverage |
| 50 | `brand_international_bumper` | Global Affairs Segment Bumper | 1.5s | Cobalt blue globe rotation bumper for geopolitics |
| 51 | `brand_economy_bumper` | Business & Markets Bumper | 1.5s | Emerald green financial ticker card |
| 52 | `brand_calendar_reveal` | Editorial Calendar Observance Card | 2.5s | Elegant card highlighting UN/National observances |
| 53 | `brand_ticker_transition` | Breaking News Ticker Slide-In | 1.0s | Bottom ticker banner sliding up with glowing live tag |
| 54 | `brand_attribution_card` | Legal Attribution Bug | 2.5s | Semi-transparent source watermark card |
| 55 | `brand_outro_subscribe` | Channel Identity & Follow Callout | 2.5s | BHARAT KI SOCH logo with animated subscribe bell |
| 56 | `brand_short_loop_ending` | Seamless Shorts Loop Matcher | 0.8s | Visual alignment matching starting frame for endless loop |
