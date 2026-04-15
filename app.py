import io
import json
import os
import logging

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from emotion_model import get_classifier
from mapper import map_emotion_to_params, db_to_float_volume
from tts import synthesize_edge_segmented, synthesize_segmented, get_available_voices
from file_reader import extract_text_from_bytes, SUPPORTED_EXTENSIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Empathy Engine", description="Text to Emotionally Modulated Speech")

static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)

app.mount("/ui", StaticFiles(directory=static_path, html=True), name="static")


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "woman"
    force_recompute: bool = False


# ---------------------------------------------------------------------------
# Shared response builder  (async — uses neural Edge-TTS)
# ---------------------------------------------------------------------------

async def _build_response(text: str, voice: str, force: bool) -> StreamingResponse:
    """Run edge-tts segmented synthesis and pack result as a StreamingResponse."""
    try:
        from tts import _build_ssml, split_into_segments, EDGE_VOICES, _edge_synth_async
        from emotion_model import get_classifier
        from mapper import map_emotion_to_params

        # We manually build segment meta here to log the SSML before synthesis
        voice_name, pitch_offset = EDGE_VOICES.get(voice, EDGE_VOICES["woman"])
        classifier = get_classifier()
        segments = split_into_segments(text)
        segment_meta = []
        for s in segments:
            emotion, conf, _ = classifier.detect_emotion(s)
            r, p, v = map_emotion_to_params(emotion, conf)
            segment_meta.append({"text": s, "emotion": emotion, "confidence": conf, "rate": r, "pitch": p, "volume": v})

        ssml = _build_ssml(segment_meta, voice_name, pitch_offset)
        logger.info(f"Generated SSML for synthesis:\n{ssml[:500]}...")

        # Actual synthesis (we use the internal async runner since we already have the SSML)
        # We pass voice_name to 'prime' the engine for SSML
        audio_bytes = await _edge_synth_async(ssml, voice_name)
    except Exception as e:
        logger.error(f"Edge-TTS failed, attempting pyttsx3 fallback: {e}")
        # Build segment_meta again for fallback (unlikely path but safe)
        from tts import synthesize_segmented
        audio_bytes, segment_meta = synthesize_segmented(text, voice_selection=voice, force_recompute=force)

    if not audio_bytes:
        raise HTTPException(status_code=500, detail="TTS Engine produced no audio.")

    dominant = segment_meta[0] if segment_meta else {
        "emotion": "neutral", "confidence": 1.0,
        "rate": 140, "pitch": "0st", "volume": "+0dB",
    }

    headers = {
        "X-Detected-Emotion":    dominant["emotion"],
        "X-Emotion-Confidence":  str(dominant["confidence"]),
        "X-Prosody-Rate":        str(dominant["rate"]),
        "X-Prosody-Pitch":       dominant["pitch"],
        "X-Prosody-Volume-db":   dominant["volume"],
        "X-Segments":            json.dumps(segment_meta),
        "Access-Control-Expose-Headers": (
            "X-Detected-Emotion,X-Emotion-Confidence,"
            "X-Prosody-Rate,X-Prosody-Pitch,"
            "X-Prosody-Volume-db,X-Segments"
        ),
    }

    # Edge-TTS outputs MP3; pyttsx3 fallback outputs WAV
    media = "audio/mpeg" if audio_bytes[:3] == b"\xff\xfb" or audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xf3" else "audio/wav"
    # Simpler: always check for ID3/MPEG header
    is_mp3 = audio_bytes[:3] in (b"ID3",) or (len(audio_bytes) > 1 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0)
    media = "audio/mpeg" if is_mp3 else "audio/wav"

    return StreamingResponse(io.BytesIO(audio_bytes), media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    logger.info(f"POST /api/synthesize | voice={req.voice} | {len(req.text)} chars")
    try:
        return await _build_response(req.text, req.voice, req.force_recompute)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/synthesize-file")
async def synthesize_file_endpoint(
    file: UploadFile = File(...),
    voice: str = Form(default="woman"),
    force_recompute: bool = Form(default=False),
):
    filename = file.filename or ""
    _, ext = os.path.splitext(filename)
    if ext.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    try:
        contents = await file.read()
        text = extract_text_from_bytes(filename, contents)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not extract text: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="File contains no readable text.")

    logger.info(f"POST /api/synthesize-file | '{filename}' | {len(text)} chars | voice={voice}")

    try:
        return await _build_response(text, voice, force_recompute)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voices")
def get_voices():
    from tts import EDGE_VOICES
    edge = [{"id": k, "name": f"{k.capitalize()} (Neural – {v[0]})"} for k, v in EDGE_VOICES.items()]
    return JSONResponse(content={"voices": edge})


@app.get("/api/supported-formats")
def supported_formats():
    return JSONResponse(content={"formats": sorted(SUPPORTED_EXTENSIONS)})


@app.get("/")
def redirect_to_ui():
    return RedirectResponse(url="/ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
