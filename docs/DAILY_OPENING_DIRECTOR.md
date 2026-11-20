# Daily Opening Director Agent — Technical Documentation

## 1. Overview & Mission

`DailyOpeningDirectorAgent` is the opening creative and journalistic engine for **BHARAT KI SOCH** daily morning bulletins. It guarantees that every morning bulletin starts with culturally grounded, verified Indian context before diving into breaking news.

Location: `agents/daily_opening_director/agent.py`  
Contract: `DailyOpeningBrief` in `core/agent_contracts.py`  
Unit Tests: `tests/test_agents/test_daily_opening_director.py`

---

## 2. Core Functional Pillars

### 2.1 Hindu Panchang Computation
- Computes the Tithi (प्रतिपदा to पूर्णिमा/अमावस्या), Paksha (शुक्ल / कृष्ण), and Masa (चैत्र to फाल्गुन) in Devanagari.
- Formats dates authentically (e.g., `20 नवंबर 2026, शुक्रवार`).

### 2.2 Verified National & International Observances
- Evaluates fixed and dynamic observances:
  - United Nations International Days (e.g., Universal Children's Day, World Environment Day).
  - Indian National Days (e.g., National Science Day, Republic Day, Constitution Day).
  - Major festivals and historical anniversaries ("On This Day").
- Attaches verified facts and evidence sources (UN, PIB, Government Gazettes) to prevent hallucination.

### 2.3 Opening Hook Formulation
- Generates 5 distinct hook candidates across viral retention archetypes:
  1. Urgent Breaking (`urgency`)
  2. Question Hook (`question`)
  3. Statistic Impact (`stat`)
  4. Curiosity Gap (`curiosity`)
  5. Panchang & Culture (`panchang`)
- Selects the best candidate based on composite scoring and day significance.

### 2.4 Motion Preset & Sound Cue Association
- Associates visual opening beats with motion preset IDs:
  - `opener_breaking_red_flash`
  - `opener_headline_slam`
  - `opener_date_flip`
- Schedules initial sound cues (`cue_news_intro_sting`, `cue_bulletin_impact`).

---

## 3. Data Contract (`DailyOpeningBrief`)

```python
@dataclass
class DailyOpeningBrief:
    date_iso: str
    date_hi: str
    weekday_hi: str
    panchang: str
    festivals: List[str]
    national_observances: List[str]
    international_observances: List[str]
    on_this_day_events: List[str]
    selected_special_day: str
    verified_facts: List[str]
    evidence_sources: List[str]
    opening_hook_candidates: List[str]
    selected_hook: str
    spoken_script: str
    visual_beats: List[str]
    motion_preset_ids: List[str]
    sound_cue_ids: List[str]
    confidence: float
    verification_status: str
    warnings: List[str]
```
