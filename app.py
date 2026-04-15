import io
import json
import os
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from emotion_model import get_classifier
from mapper import map_emotion_to_params, db_to_float_volume
from tts import synthesize_segmented, synthesize_local, get_available_voices

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Empathy Engine", description="Text to Emotionally Modulated Speech")

# Mount static folder for the frontend UI
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)

app.mount("/ui", StaticFiles(directory=static_path, html=True), name="static")


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "woman"
    force_recompute: bool = False


@app.post("/api/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        logger.info(f"Synthesizing (segmented): voice={req.voice}")

        # --- Segmented synthesis: each sentence gets its own emotion + params ---
        audio_bytes, segment_meta = synthesize_segmented(
            req.text,
            voice_selection=req.voice,
            force_recompute=req.force_recompute,
        )

        if not audio_bytes:
            raise HTTPException(status_code=500, detail="TTS Engine produced no audio.")

        # Use the dominant (first) segment's emotion for top-level headers
        dominant = segment_meta[0] if segment_meta else {
            "emotion": "neutral", "confidence": 1.0,
            "rate": 140, "pitch": "0st", "volume": "+0dB"
        }

        headers = {
            "X-Detected-Emotion":    dominant["emotion"],
            "X-Emotion-Confidence":  str(dominant["confidence"]),
            "X-Prosody-Rate":        str(dominant["rate"]),
            "X-Prosody-Pitch":       dominant["pitch"],
            "X-Prosody-Volume-db":   dominant["volume"],
            # Full segment breakdown as JSON string (URL-safe via base64 is overkill; keep it simple)
            "X-Segments":            json.dumps(segment_meta),
            "Access-Control-Expose-Headers": (
                "X-Detected-Emotion,X-Emotion-Confidence,"
                "X-Prosody-Rate,X-Prosody-Pitch,"
                "X-Prosody-Volume-db,X-Segments"
            ),
        }

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers=headers,
        )

    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voices")
def get_voices():
    voices = get_available_voices()
    return JSONResponse(content={"voices": voices})


@app.get("/")
def redirect_to_ui():
    return RedirectResponse(url="/ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
