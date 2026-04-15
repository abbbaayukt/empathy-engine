import edge_tts
import asyncio

async def test():
    # Attempt 1: The current structure in tts.py
    # (Checking if startswith("<speak") is True)
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">\n'
        '  <voice name="en-US-JennyNeural">\n'
        '    <prosody rate="+14%" pitch="+1st" volume="+7%">i won the lottery</prosody>\n'
        '  </voice>\n'
        '</speak>'
    )
    
    print(f"Starts with <speak: {ssml.startswith('<speak')}")
    print(f"First 10 chars: {repr(ssml[:10])}")
    
    # If it starts with <speak, edge-tts SHOULD parse it.
    # If it's still reading it as text, maybe the parser is failing INTERNALLY.
    
    communicate = edge_tts.Communicate(ssml)
    # Check if edge-tts internally detected it as SSML?
    # edge-tts doesn't expose a 'is_ssml' flag easily, but we can verify by the audio.
    # However, I can't hear the audio.
    
    # Let's try MINIFIED SSML (no newlines)
    min_ssml = ssml.replace("\n", "").replace("  ", "")
    print(f"Minified starts with <speak: {min_ssml.startswith('<speak')}")
    
    await communicate.save("scratch/debug_current.mp3")
    
    c2 = edge_tts.Communicate(min_ssml)
    await c2.save("scratch/debug_minified.mp3")
    print("Files saved to scratch/")

if __name__ == "__main__":
    asyncio.run(test())
