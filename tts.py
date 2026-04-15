import os
import re
import io
import wave
import hashlib
import asyncio
import edge_tts
from typing import AsyncGenerator
import pyttsx3

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
    """'+2st' + 5st offset → '+42%' (Relative percentages are most robust for Edge/Azure Neural)"""
    try:
        val = int(pitch_str.replace("st", ""))
    except ValueError:
        val = 0
    total_st = val + offset_st
    pct = total_st * 6 # Approx 6% frequency change per semitone
    return f"+{pct}%" if pct >= 0 else f"{pct}%"

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


class SSMLCommunicate(edge_tts.Communicate):
    """
    Subclass of edge_tts.Communicate that allows sending RAW SSML.
    Bypasses the library's internal escaping and wrapping.
    """
    def __init__(self, ssml: str, **kwargs):
        # We pass a placeholder because we will override the transmission anyway.
        super().__init__("placeholder", **kwargs)
        self.ssml = ssml

    async def stream(self) -> AsyncGenerator[edge_tts.typing.TTSChunk, None]:
        """Override stream to send our raw SSML directly."""
        if self.state["stream_was_called"]:
            raise RuntimeError("stream can only be called once.")
        self.state["stream_was_called"] = True

        from edge_tts.communicate import (
            connect_id, date_to_string, ssml_headers_plus_data, 
            WSS_URL, WSS_HEADERS, SEC_MS_GEC_VERSION, DRM, _SSL_CTX, 
            get_headers_and_data, UnexpectedResponse, UnknownResponse, WebSocketError
        )
        import aiohttp
        import json

        async def send_command_request():
            await websocket.send_str(
                f"X-Timestamp:{date_to_string()}\r\n"
                "Content-Type:application/json; charset=utf-8\r\n"
                "Path:speech.config\r\n\r\n"
                '{"context":{"synthesis":{"audio":{"metadataoptions":{'
                '"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"'
                "},"
                '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"'
                "}}}}\r\n"
            )

        async def send_ssml_request():
            # THIS IS THE FIX: We send self.ssml DIRECTLY, bypassing mkssml()
            await websocket.send_str(
                ssml_headers_plus_data(connect_id(), date_to_string(), self.ssml)
            )

        audio_was_received = False
        async with aiohttp.ClientSession(
            trust_env=True, timeout=self.session_timeout
        ) as session, session.ws_connect(
            f"{WSS_URL}&ConnectionId={connect_id()}"
            f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
            f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}",
            compress=15, headers=DRM.headers_with_muid(WSS_HEADERS), ssl=_SSL_CTX
        ) as websocket:
            await send_command_request()
            await send_ssml_request()

            async for received in websocket:
                if received.type == aiohttp.WSMsgType.TEXT:
                    encoded_data = received.data.encode("utf-8")
                    parameters, data = get_headers_and_data(encoded_data, encoded_data.find(b"\r\n\r\n"))
                    path = parameters.get(b"Path")
                    if path == b"turn.end": break
                    elif path == b"audio.metadata": pass # ignored for now
                elif received.type == aiohttp.WSMsgType.BINARY:
                    header_length = int.from_bytes(received.data[:2], "big")
                    parameters, data = get_headers_and_data(received.data, header_length)
                    if parameters.get(b"Path") == b"audio":
                        audio_was_received = True
                        yield {"type": "audio", "data": data}

        if not audio_was_received:
            raise RuntimeError("No audio received from Edge TTS.")

async def _edge_synth_async(ssml: str, voice: str) -> bytes:
    """Async: stream audio using OUR CUSTOM SSMLCommunicate."""
    communicate = SSMLCommunicate(ssml, voice=voice)
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

    # Cache (v4 signature to clear stale bugs - BYPASSING LOGIC)
    cache_key = hashlib.md5(
        f"{full_text}_{voice_selection}_edge_v4".encode()
    ).hexdigest()
    cache_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.mp3")

    if not force_recompute and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read(), [] # simplified return for this loop

    # Build SSML + synthesize
    ssml = _build_ssml(segment_meta, voice_name, pitch_offset)
    audio_bytes = await _edge_synth_async(ssml, voice_name)

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
