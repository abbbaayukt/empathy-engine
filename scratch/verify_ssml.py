import asyncio
import edge_tts
import os

async def test_parsing():
    # Attempt 1: WITH declaration (Hypothesis: this FAILS and reads tags)
    ssml_decl = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        '<voice name="en-US-JennyNeural">Testing declaration. If you hear this but NOT the words "XML Version", it worked.</voice>'
        '</speak>'
    )
    
    # Attempt 2: WITHOUT declaration (Hypothesis: this WORKS)
    ssml_no_decl = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        '<voice name="en-US-JennyNeural">Testing no declaration.</voice>'
        '</speak>'
    )
    
    os.makedirs("scratch", exist_ok=True)
    
    print("Testing SSML WITH declaration...")
    c1 = edge_tts.Communicate(ssml_decl)
    # The library has a property .text, we can see if it was altered?
    # Actually we just save it.
    await c1.save("scratch/test_decl_fail.mp3")
    
    print("Testing SSML WITHOUT declaration...")
    c2 = edge_tts.Communicate(ssml_no_decl)
    await c2.save("scratch/test_no_decl_pass.mp3")
    
    print("Generated files in scratch/")

if __name__ == "__main__":
    asyncio.run(test_parsing())
