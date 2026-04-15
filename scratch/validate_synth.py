import asyncio
import edge_tts
import sys
import os

# Add parent dir to path to import tts
sys.path.append(os.getcwd())
from tts import _build_ssml, _edge_synth_async

async def validate():
    print("Testing SSML generation and synthesis...")
    
    # Mock segment data
    segment_meta = [
        {
            "text": "I am so happy to see you!",
            "emotion": "joy",
            "confidence": 0.9,
            "rate": 182,
            "pitch": "+3st",
            "volume": "+3dB"
        },
        {
            "text": "But I am also a bit nervous.",
            "emotion": "nervousness",
            "confidence": 0.5,
            "rate": 140,
            "pitch": "+0st",
            "volume": "-1dB"
        }
    ]
    
    voice_name = "en-US-JennyNeural"
    pitch_offset = 0
    
    ssml = _build_ssml(segment_meta, voice_name, pitch_offset)
    print("\n--- GENERATED SSML ---")
    print(ssml)
    print("----------------------\n")
    
    # Check for critical components
    assert "<voice" in ssml, "Missing <voice> tag!"
    assert 'name="en-US-JennyNeural"' in ssml, "Incorrect voice name!"
    assert 'pitch="+3st"' in ssml or 'pitch="+2st"' in ssml, "Pitch semitones missing/wrong!"
    assert 'rate="+30%"' in ssml, "Rate percentage missing/wrong!"
    
    print("SSML Validation Passed. Attempting synthesis...")
    
    try:
        audio_bytes = await _edge_synth_async(ssml)
        if len(audio_bytes) > 1000:
            print(f"SUCCESS: Generated {len(audio_bytes)} bytes of audio.")
            # Save for manual check if needed
            os.makedirs("scratch", exist_ok=True)
            with open("scratch/verified_audio.mp3", "wb") as f:
                f.write(audio_bytes)
            print("Saved to scratch/verified_audio.mp3")
        else:
            print("FAILURE: Audio too short or empty.")
    except Exception as e:
        print(f"SYNTHESIS ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(validate())
