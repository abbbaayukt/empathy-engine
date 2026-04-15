# Empathy Engine 🎙️

> **AI-powered Text-to-Speech that detects emotion in real time and modulates the voice accordingly — speaking joyfully when happy, slowly when sad, fast and loud when angry.**

---

## Project Description

The **Empathy Engine** is a Python-based service that reads input text, classifies its emotional tone using a state-of-the-art transformer model, and synthesizes speech with dynamically adjusted prosody (pitch, rate, and volume) to match that emotion.

Unlike standard TTS tools that speak every sentence identically, the Empathy Engine:

- **Splits** input text into individual sentences and clauses
- **Classifies** each segment independently into one of **28 nuanced emotions** (GoEmotions dataset: joy, grief, annoyance, admiration, curiosity, fear, disgust, and more)
- **Synthesizes** each segment with its own voice parameters using **Neural Microsoft Edge TTS** (high-quality, human-like) with automatic offline fallback to `pyttsx3`.
- **Supports File Inputs**: Directly upload `.txt`, `.pdf`, or `.docx` files for emotional narration.
- Exposes a **FastAPI REST endpoint**, a **CLI tool**, and a **premium animated Web UI** with drag-and-drop support.

---

## Repository Structure

```
empathy-engine/
├── app.py              # FastAPI server (REST API + UI host)
├── emotion_model.py    # Transformer-based emotion classifier
├── mapper.py           # Emotion → prosody mapping logic
├── tts.py              # TTS synthesis (Edge-TTS + pyttsx3 fallback)
├── file_reader.py      # PDF, DOCX, and TXT extraction logic
├── cli.py              # Command-line interface
├── test_mapping.py     # Mapping unit tests
├── test_emotions.txt   # Sample sentences covering all 28 emotions
├── requirements.txt    # Python dependencies
├── static/
│   ├── index.html      # Web UI
│   ├── style.css       # Glassmorphism dark theme
│   └── script.js       # Fetch API + per-segment breakdown rendering
├── audio_cache/        # Generated WAV files (auto-created)
└── README.md
```

---

## Setup Instructions

### Prerequisites

- **Python 3.10 or higher**
- Internet connection (required for **Neural voices** and first-run model download)
- Windows (Note: `pyttsx3` fallback uses SAPI5 voices native to Windows)

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/abbbaayukt/empathy-engine.git
cd empathy-engine
```

### Step 2 — Create a Virtual Environment (Recommended)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** On the very first run the application will automatically download the `SamLowe/roberta-base-go_emotions` model (~500 MB) from Hugging Face. This is a one-time download and will be cached locally.

---

### Step 4A — Run the Web UI (Recommended)

```bash
python app.py
```

Then open your browser and navigate to:

```
http://localhost:8000/ui
```

**Features of the Web UI:**
- **Two Input Modes**: ✏️ Type Text or 📄 Upload File (Drag & Drop)
- **Neural Voice Selection**: Human-like voices (Jenny, Guy, Ana, etc.)
- **Voice Profiles**: Woman / Man / Girl / Boy / Child
- **Live Metrics**: Animated emotion badge + confidence bar
- **Breakdown**: Per-segment breakdown panel showing each clause's detected emotion and parameters
- **Player**: Embedded HTML5 audio player (MP3/WAV)

---

### Step 4B — Run the CLI

```bash
python cli.py "I just got the promotion! But then I heard the terrible news."
```

Optional: save output to a specific file:

```bash
python cli.py "I am so excited about this!" --save output.wav
```

---

### Step 4C — Call the REST API Directly

```bash
curl -X POST http://localhost:8000/api/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "I am furious and I cannot believe this happened!", "voice": "man"}' \
  --output output.wav
```

**Available API endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/synthesize` | Synthesize text input |
| `POST` | `/api/synthesize-file` | Synthesize from uploaded file |
| `GET`  | `/api/voices` | List available neural voices |
| `GET`  | `/api/supported-formats` | List allowed file extensions |

**Request body:**
```json
{
  "text": "Your input text here",
  "voice": "woman",
  "force_recompute": false
}
```
- `voice`: one of `woman`, `man`, `girl`, `boy`, `child`
- `force_recompute`: bypass audio cache

**Response headers** (emotion metadata):
- `X-Detected-Emotion` — dominant segment's emotion label
- `X-Emotion-Confidence` — confidence score (0.0–1.0)
- `X-Prosody-Rate` — speech rate in WPM
- `X-Prosody-Pitch` — pitch shift in semitones
- `X-Prosody-Volume-db` — volume shift in dB
- `X-Segments` — JSON array of per-segment emotion details

---

### Step 5 — Run Emotion Mapping Tests

```bash
python test_mapping.py
```

This prints each sample sentence from `test_emotions.txt` with its detected emotion and mapped prosody parameters.

---

## Design Choices & Emotion-to-Voice Mapping Logic

### Emotion Model

We use **`SamLowe/roberta-base-go_emotions`** — a RoBERTa model fine-tuned on Google's [GoEmotions](https://github.com/google-research/google-research/tree/master/goemotions) dataset (58k Reddit comments, 28 emotion labels). This was chosen over simpler 6-class models because:

- It covers nuanced emotions like `remorse`, `admiration`, `nervousness`, `realization`
- It achieves strong benchmark accuracy on the 28-class problem
- The `transformers` pipeline makes it plug-and-play

### Per-Sentence Segmentation

Rather than classifying the whole input at once, the engine:
1. Splits on sentence terminals (`.`, `!`, `?`) first
2. Sub-splits long sentences on comma/semicolon clause boundaries
3. Classifies **each clause independently**
4. Builds an **SSML document** with per-segment `<prosody>` tags
5. Synthesizes via **Microsoft Edge Neural TTS** (or concatenates WAVs for fallback)

This means a single input like:
> *"I just won the lottery! But I'm devastated about losing my best friend."*

…will speak the first clause **faster and higher pitched** (joy) and the second **slower and softer** (sadness).

### Emotion → Prosody Mapping

The base speech rate is **140 WPM** (chosen to be natural and clear). All parameters are **linearly scaled by the confidence score** so that a high-confidence (0.95) joy is much more exuberant than a low-confidence (0.45) joy.

The 28 GoEmotions labels are first grouped into 6 prosodic archetypes:

| Group | GoEmotions Labels | Rate | Pitch | Volume |
|-------|------------------|------|-------|--------|
| **Joy** | joy, excitement, amusement, optimism | +30% max | +3 st max | +3 dB max |
| **Love** | love, caring, admiration, approval, pride, gratitude, relief | +30% max | +3 st max | +3 dB max |
| **Sadness** | sadness, disappointment, embarrassment, grief, remorse | −15% max | −3 st max | −3 dB max |
| **Anger** | anger, annoyance, disapproval, disgust | +50% max | 0 st (flat) | +5 dB max |
| **Fear** | fear, nervousness | +20% max | +2 st max | −2 dB max |
| **Surprise** | surprise, realization, confusion, curiosity, desire | +30% max | +4 st max | +2 dB max |
| **Neutral** | neutral | 0% | 0 st | 0 dB |

**Example (confidence = 0.85):**
- Input: *"Get out of my house!"* → `anger (0.91)` → Rate = 140 × 1.455 = **204 WPM**, Volume = **+4 dB**
- Input: *"Are you okay?"* → `nervousness (0.72)` → Rate = 140 × 1.144 = **160 WPM**, Volume = **−1 dB**

We now primarily use **Edge-TTS Neural Voices** for professional, human-like quality. `pyttsx3` is kept as a local fallback.

| Profile | Neural Voice | SAPI5 (Fallback) |
|---------|--------------|------------------|
| Woman | en-US-JennyNeural | Zira (female) |
| Man | en-US-GuyNeural | David (male) |
| Girl | en-US-JennyNeural (+60Hz) | Zira (+8st) |
| Boy | en-US-AndrewNeural (+30Hz) | David (+8st) |
| Child | en-US-AnaNeural (Genuine) | Zira (+10st) |

### Caching

Every synthesized segment is cached as a WAV file named after an MD5 hash of `(text + rate + volume + voice)`. Repeated requests with identical parameters return instantly from disk.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `transformers` | Hugging Face model inference |
| `torch` | PyTorch backend for transformer |
| `edge-tts` | Neural human-like speech engine |
| `pyttsx3` | Local offline TTS fallback |
| `PyPDF2` | PDF text extraction |
| `python-docx` | DOCX text extraction |
| `pydub` | Advanced audio processing |
| `pydantic` | Data validation |

---

## Bonus Features Implemented

- ✅ **Human-like Neural Voices** — Professional speech quality via Edge-TTS
- ✅ **28 granular emotion categories** (GoEmotions, far beyond 3-class)
- ✅ **PDF & DOCX Support** — Extract and narrate entire documents
- ✅ **Intensity scaling** — confidence score linearly modulates all parameters
- ✅ **Per-sentence emotion detection** — different prosody within a single input
- ✅ **Tabbed UI with Drag & Drop** — premium glassmorphism dark theme
- ✅ **Automatic Fallback** — works offline via pyttsx3 if internet is unavailable
- ✅ **Audio caching** — MD5-based disk cache for both MP3 and WAV
- ✅ **CLI + REST API** — both interfaces fully functional
