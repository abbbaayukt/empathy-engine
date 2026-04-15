import edge_tts
import asyncio
import os

async def reproduce():
    # The EXACT string from the user's log
    ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US"><voice name="en-US-JennyNeural"><prosody rate="+27%" pitch="+2st" volume="+14%">nice try</prosody><break time="150ms"/></voice></speak>'
    
    print(f"Testing SSML: {ssml}")
    
    # Attempt 1: Just SSML
    c1 = edge_tts.Communicate(ssml)
    await c1.save("scratch/rep_1.mp3")
    
    # Attempt 2: SSML with voice arg
    # (Maybe this forces the parser?)
    c2 = edge_tts.Communicate(ssml, voice="en-US-JennyNeural")
    await c2.save("scratch/rep_2.mp3")
    
    print("Files saved. Check if they have audio or tags.")

if __name__ == "__main__":
    asyncio.run(reproduce())
