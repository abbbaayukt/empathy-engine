import os
import re
import io
import wave
import hashlib
import tempfile
import pyttsx3

AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), "audio_cache")
if not os.path.exists(AUDIO_CACHE_DIR):
    os.makedirs(AUDIO_CACHE_DIR)

try:
    engine = pyttsx3.init()
except Exception as e:
    engine = None
    print(f"Failed to initialize pyttsx3: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_voice_ids():
    """Return (male_id, female_id) from installed SAPI5 voices."""
    voices = engine.getProperty('voices')
    male_id   = next((v.id for v in voices if 'david' in v.name.lower() or 'male' in v.name.lower()), voices[0].id)
    female_id = next((v.id for v in voices if 'zira'  in v.name.lower() or 'female' in v.name.lower()), voices[0].id)
    return male_id, female_id


def _apply_voice_profile(voice_selection: str):
    """Set engine voice property and return SAPI5 pitch offset for the profile."""
    male_id, female_id = _get_voice_ids()
    pitch_mod = 0

    mapping = {
        "man":   (male_id,   0),
        "woman": (female_id, 0),
        "boy":   (male_id,   8),
        "girl":  (female_id, 8),
        "child": (female_id, 10),
    }
    voice_id, pitch_mod = mapping.get(voice_selection, (female_id, 0))
    engine.setProperty('voice', voice_id)
    return pitch_mod


def _synthesize_one_segment(text: str, rate: int, vol: float,
                             pitch_mod: int, out_path: str):
    """Synthesize a single text chunk and save to out_path (WAV)."""
    engine.setProperty('rate', rate)
    engine.setProperty('volume', vol)

    # SAPI5 XML pitch tag for child/boy/girl voices
    sapi_text = f"<pitch absmiddle='{pitch_mod}'>{text}</pitch>" if pitch_mod else text

    engine.save_to_file(sapi_text, out_path)
    engine.runAndWait()


def _concat_wavs(wav_paths: list[str]) -> bytes:
    """Concatenate multiple WAV files (same params) into one bytes object."""
    buffers = []
    params = None

    for path in wav_paths:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            continue
        try:
            with wave.open(path, 'rb') as wf:
                if params is None:
                    params = wf.getparams()
                buffers.append(wf.readframes(wf.getnframes()))
        except Exception as e:
            print(f"[WARN] Could not read {path}: {e}")

    if not buffers or params is None:
        return b""

    out_buf = io.BytesIO()
    with wave.open(out_buf, 'wb') as out_wf:
        out_wf.setparams(params)
        for buf in buffers:
            out_wf.writeframes(buf)

    return out_buf.getvalue()


# ---------------------------------------------------------------------------
# Sentence segmentation
# ---------------------------------------------------------------------------

def split_into_segments(text: str) -> list[str]:
    """
    Split text into clause-level segments for per-segment emotion detection.
    Splits on  .  !  ?  and also on  ,  when the clause is long enough
    to carry its own emotional tone (≥5 words).
    """
    # First split on strong sentence boundaries
    raw = re.split(r'(?<=[.!?])\s+', text.strip())

    segments = []
    for sentence in raw:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Further split long sentences on commas/semicolons
        clauses = re.split(r'(?<=,)\s+|(?<=;)\s+', sentence)
        for clause in clauses:
            clause = clause.strip().strip(',').strip()
            if len(clause.split()) >= 3:   # ignore tiny fragments
                segments.append(clause)
            elif segments:                  # append tiny bits to previous
                segments[-1] += ' ' + clause

    return segments if segments else [text.strip()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize_segmented(full_text: str,
                          voice_selection: str = "woman",
                          force_recompute: bool = False
                          ) -> tuple[bytes, list[dict]]:
    """
    Split full_text into sentences/clauses, detect emotion per segment,
    synthesize each separately, then concatenate into one WAV.

    Returns:
        (audio_bytes, segment_metadata_list)
        segment_metadata_list = [
            {"text": ..., "emotion": ..., "confidence": ...,
             "rate": ..., "pitch": ..., "volume": ...}, ...
        ]
    """
    if engine is None:
        raise RuntimeError("TTS Engine is not initialized.")

    # Lazy import to avoid circular deps
    from emotion_model import get_classifier
    from mapper import map_emotion_to_params, db_to_float_volume

    classifier = get_classifier()
    segments   = split_into_segments(full_text)

    # Cache key covers entire request
    cache_key  = hashlib.md5(
        f"{full_text}_{voice_selection}".encode()
    ).hexdigest()
    final_cache = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}_merged.wav")

    segment_meta = []
    wav_paths    = []

    pitch_mod = _apply_voice_profile(voice_selection)

    for idx, seg_text in enumerate(segments):
        # Per-segment emotion
        emotion, confidence, _ = classifier.detect_emotion(seg_text)
        rate, pitch_str, vol_str = map_emotion_to_params(emotion, confidence)
        vol_float = db_to_float_volume(vol_str)

        seg_hash = hashlib.md5(
            f"{seg_text}_{rate}_{vol_float}_{voice_selection}".encode()
        ).hexdigest()
        seg_path = os.path.join(AUDIO_CACHE_DIR, f"{seg_hash}_seg.wav")

        if not os.path.exists(seg_path) or force_recompute:
            try:
                _synthesize_one_segment(seg_text, rate, vol_float, pitch_mod, seg_path)
            except Exception as e:
                print(f"[ERROR] Segment {idx} synthesis failed: {e}")
                continue

        wav_paths.append(seg_path)
        segment_meta.append({
            "text":       seg_text,
            "emotion":    emotion,
            "confidence": round(confidence, 3),
            "rate":       rate,
            "pitch":      pitch_str,
            "volume":     vol_str,
        })

        print(f"[SEG {idx+1}/{len(segments)}] '{seg_text[:40]}…'  "
              f"→ {emotion} ({confidence:.2f}) | rate={rate} pitch={pitch_str}")

    # Concatenate all segment WAVs
    audio_bytes = _concat_wavs(wav_paths)
    return audio_bytes, segment_meta


def synthesize_local(text: str, rate: int, pyttsx3_vol: float,
                     voice_selection: str = "woman",
                     force_recompute: bool = False) -> bytes:
    """
    Single-emotion synthesis (kept for CLI / fallback).
    """
    if engine is None:
        raise RuntimeError("TTS Engine is not initialized.")

    hash_str = hashlib.md5(
        f"{text}_{rate}_{pyttsx3_vol}_{voice_selection}".encode()
    ).hexdigest()
    output_filepath = os.path.join(AUDIO_CACHE_DIR, f"{hash_str}.wav")

    if os.path.exists(output_filepath) and not force_recompute:
        with open(output_filepath, "rb") as f:
            return f.read()

    pitch_mod = _apply_voice_profile(voice_selection)
    _synthesize_one_segment(text, rate, pyttsx3_vol, pitch_mod, output_filepath)

    try:
        with open(output_filepath, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading generated audio: {e}")
        return b""


def get_available_voices():
    """Returns a list of local voices."""
    if not engine:
        return []
    voices = engine.getProperty('voices')
    return [{"id": v.id, "name": v.name} for v in voices]
