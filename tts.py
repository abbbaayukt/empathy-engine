import os
import re
import io
import wave
import hashlib
import pyttsx3
import asyncio
import edge_tts

AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), "audio_cache")
if not os.path.exists(AUDIO_CACHE_DIR):
    os.makedirs(AUDIO_CACHE_DIR)

# pyttsx3 kept as fallback for CLI
try:
    _pyttsx3_engine = pyttsx3.init()
except Exception as e:
    _pyttsx3_engine = None
    print(f"[WARN] pyttsx3 unavailable: {e}")

# ---------------------------------------------------------------------------
# Edge-TTS voice map (neural voices — very human sounding, free, no API key)
# ---------------------------------------------------------------------------
EDGE_VOICES = {
    "woman": ("en-US-JennyNeural",   0),   # (voice_name, semitone_offset)
    "man":   ("en-US-GuyNeural",     0),
    "girl":  ("en-US-JennyNeural",   5),   # Jenny + 5 semitones = energetic girl
    "boy":   ("en-US-AndrewNeural",  3),   # Andrew + 3 semitones = young boy
    "child": ("en-US-AnaNeural",     0),   # Ana is natively professional child voice
}

# ---------------------------------------------------------------------------
# Unit converters  (mapper units → edge-tts SSML units)
# ---------------------------------------------------------------------------

def _rate_to_pct(wpm: int, base: int = 140) -> str:
    """140 wpm base → '+0%'; 168 wpm → '+20%'"""
    pct = int((wpm - base) / base * 100)
    return f"+{pct}%" if pct >= 0 else f"{pct}%"

def _map_pitch(pitch_str: str, offset_st: int = 0) -> str:
    """'+2st' + 5st offset → '+7st' (Supported natively by Azure SSML)"""
    try:
        val = int(pitch_str.replace("st", ""))
    except ValueError:
        val = 0
    total = val + offset_st
    return f"+{total}st" if total >= 0 else f"{total}st"

def _db_to_pct(vol_str: str) -> str:
    """'+3dB' → '+21%' (7 % per dB, perceptual approximation)"""
    try:
        val = int(vol_str.replace("dB", ""))
    except ValueError:
        val = 0
    pct = val * 7
    return f"+{pct}%" if pct >= 0 else f"{pct}%"

def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

# ---------------------------------------------------------------------------
# Sentence segmentation
# ---------------------------------------------------------------------------

def split_into_segments(text: str) -> list[str]:
    """Split into sentence/clause level segments for per-segment emotion."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    segments = []
    for sentence in raw:
        sentence = sentence.strip()
        if not sentence:
            continue
        clauses = re.split(r'(?<=,)\s+|(?<=;)\s+', sentence)
        for clause in clauses:
            clause = clause.strip().strip(',').strip()
            if len(clause.split()) >= 3:
                segments.append(clause)
            elif segments:
                segments[-1] += ' ' + clause
    return segments if segments else [text.strip()]

# ---------------------------------------------------------------------------
# Edge-TTS  (primary engine — neural, very human)
# ---------------------------------------------------------------------------

def _build_ssml(segment_meta: list[dict], voice_name: str, pitch_offset: int) -> str:
    """Build a MINIFIED Azure-compliant SSML document."""
    # Note: MINIFIED string starting with <speak is most robust for edge-tts.
    parts = [
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">',
        f'<voice name="{voice_name}">'
    ]
    for seg in segment_meta:
        rate  = _rate_to_pct(seg["rate"])
        pitch = _map_pitch(seg["pitch"], pitch_offset)
        vol   = _db_to_pct(seg["volume"])
        text  = _xml_escape(seg["text"])
        parts.append(f'<prosody rate="{rate}" pitch="{pitch}" volume="{vol}">{text}</prosody><break time="150ms"/>')
    parts.append('</voice></speak>')
    return "".join(parts).strip()


async def _edge_synth_async(ssml: str) -> bytes:
    """Async: stream audio from edge-tts and return raw MP3 bytes."""
    # When providing SSML, we DON'T pass the voice parameter to Communicate
    # as it's already defined inside the <voice> tag in the SSML.
    communicate = edge_tts.Communicate(ssml)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def synthesize_edge_segmented(
    full_text: str,
    voice_selection: str = "woman",
    force_recompute: bool = False,
) -> tuple[bytes, list[dict]]:
    """
    PRIMARY engine: segment text, classify emotion per segment,
    build SSML with per-segment prosody, synthesize with edge-tts neural voice.

    Returns (mp3_bytes, segment_meta_list)
    """
    from emotion_model import get_classifier
    from mapper import map_emotion_to_params

    voice_name, pitch_offset = EDGE_VOICES.get(voice_selection, EDGE_VOICES["woman"])

    # Cache (v2 signature to clear stale bugs)
    cache_key = hashlib.md5(
        f"{full_text}_{voice_selection}_edge_v2".encode()
    ).hexdigest()
    cache_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")

    # Segment + classify
    classifier = get_classifier()
    segments   = split_into_segments(full_text)
    segment_meta = []

    for seg_text in segments:
        emotion, conf, _ = classifier.detect_emotion(seg_text)
        rate, pitch, volume = map_emotion_to_params(emotion, conf)
        segment_meta.append({
            "text":       seg_text,
            "emotion":    emotion,
            "confidence": round(conf, 3),
            "rate":       rate,
            "pitch":      pitch,
            "volume":     volume,
        })
        print(f"[EDGE] '{seg_text[:45]}…' → {emotion} ({conf:.2f})")

    if not force_recompute and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read(), segment_meta

    # Build SSML + synthesize
    ssml = _build_ssml(segment_meta, voice_name, pitch_offset)
    audio_bytes = await _edge_synth_async(ssml)

    # Cache result
    with open(cache_path, "wb") as f:
        f.write(audio_bytes)

    return audio_bytes, segment_meta

# ---------------------------------------------------------------------------
# pyttsx3  (fallback / CLI — robotic but offline, no internet needed)
# ---------------------------------------------------------------------------

def _pyttsx3_voice_profile(voice_selection: str):
    if _pyttsx3_engine is None:
        return 0
    voices = _pyttsx3_engine.getProperty("voices")
    male   = next((v.id for v in voices if "david" in v.name.lower()), voices[0].id)
    female = next((v.id for v in voices if "zira"  in v.name.lower()), voices[0].id)
    mapping = {
        "man":   (male,   0),
        "woman": (female, 0),
        "boy":   (male,   8),
        "girl":  (female, 8),
        "child": (female, 10),
    }
    vid, pitch = mapping.get(voice_selection, (female, 0))
    _pyttsx3_engine.setProperty("voice", vid)
    return pitch


def synthesize_local(
    text: str,
    rate: int,
    volume: float,
    voice_selection: str = "woman",
    force_recompute: bool = False,
) -> bytes:
    """Fallback pyttsx3 synthesis (offline, used by CLI)."""
    if _pyttsx3_engine is None:
        raise RuntimeError("pyttsx3 engine not available.")

    h = hashlib.md5(f"{text}_{rate}_{volume}_{voice_selection}".encode()).hexdigest()
    path = os.path.join(AUDIO_CACHE_DIR, f"{h}.wav")

    if os.path.exists(path) and not force_recompute:
        with open(path, "rb") as f:
            return f.read()

    pitch_mod = _pyttsx3_voice_profile(voice_selection)
    _pyttsx3_engine.setProperty("rate", rate)
    _pyttsx3_engine.setProperty("volume", volume)
    sapi_text = f"<pitch absmiddle='{pitch_mod}'>{text}</pitch>" if pitch_mod else text
    _pyttsx3_engine.save_to_file(sapi_text, path)
    _pyttsx3_engine.runAndWait()

    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] pyttsx3 read failed: {e}")
        return b""


def synthesize_segmented(full_text: str, voice_selection: str = "woman",
                          force_recompute: bool = False) -> tuple[bytes, list[dict]]:
    """
    pyttsx3 segmented synthesis — kept for CLI fallback.
    Web API uses synthesize_edge_segmented (async) for neural quality.
    """
    from emotion_model import get_classifier
    from mapper import map_emotion_to_params, db_to_float_volume

    classifier = get_classifier()
    segments   = split_into_segments(full_text)
    segment_meta = []
    wav_paths  = []
    pitch_mod  = _pyttsx3_voice_profile(voice_selection)

    for seg_text in segments:
        emotion, conf, _ = classifier.detect_emotion(seg_text)
        rate, pitch, vol_str = map_emotion_to_params(emotion, conf)
        vol_f = db_to_float_volume(vol_str)

        h = hashlib.md5(f"{seg_text}_{rate}_{vol_f}_{voice_selection}".encode()).hexdigest()
        seg_path = os.path.join(AUDIO_CACHE_DIR, f"{h}_pyttsx3.wav")

        if not os.path.exists(seg_path) or force_recompute:
            if _pyttsx3_engine:
                sapi = f"<pitch absmiddle='{pitch_mod}'>{seg_text}</pitch>" if pitch_mod else seg_text
                _pyttsx3_engine.setProperty("rate", rate)
                _pyttsx3_engine.setProperty("volume", vol_f)
                _pyttsx3_engine.save_to_file(sapi, seg_path)
                _pyttsx3_engine.runAndWait()

        wav_paths.append(seg_path)
        segment_meta.append({
            "text": seg_text, "emotion": emotion, "confidence": round(conf, 3),
            "rate": rate, "pitch": pitch, "volume": vol_str,
        })

    # Concat WAVs
    buffers, params = [], None
    for p in wav_paths:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            continue
        try:
            with wave.open(p, "rb") as wf:
                if params is None:
                    params = wf.getparams()
                buffers.append(wf.readframes(wf.getnframes()))
        except Exception as e:
            print(f"[WARN] {p}: {e}")

    if not buffers or params is None:
        return b"", segment_meta

    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setparams(params)
        for buf in buffers:
            wf.writeframes(buf)

    return out.getvalue(), segment_meta


def get_available_voices():
    if not _pyttsx3_engine:
        return []
    return [{"id": v.id, "name": v.name} for v in _pyttsx3_engine.getProperty("voices")]
