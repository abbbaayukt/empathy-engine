import asyncio
import edge_tts
import sys
import os

# Add parent dir to path to import tts
sys.path.append(os.getcwd())
from tts import _build_ssml, _edge_synth_async

async def final_check():
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        '<voice name="en-US-JennyNeural">'
        '<prosody rate="+14%" pitch="+6%" volume="+7%">I am finally expressing emotion without reading tags.</prosody>'
        '</voice>'
        '</speak>'
    )
    
    print("Testing SSML-Bypass Synthesis...")
    try:
        audio_bytes = await _edge_synth_async(ssml, "en-US-JennyNeural")
        print(f"SUCCESS: Generated {len(audio_bytes)} bytes of audio.")
        os.makedirs("scratch", exist_ok=True)
        with open("scratch/verified_bypass.mp3", "wb") as f:
            f.write(audio_bytes)
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(final_check())
