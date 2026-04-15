import argparse
import sys
from emotion_model import get_classifier
from mapper import map_emotion_to_params, db_to_float_volume
from tts import synthesize_local

def main():
    parser = argparse.ArgumentParser(description="Empathy Engine CLI - Text to Emotional Speech")
    parser.add_argument("text", type=str, help="The text to synthesize")
    parser.add_argument("--save", type=str, default=None, help="Optional specific path to save the output WAV, otherwise relies on cache.")
    
    args = parser.parse_args()
    
    print("\n--- Empathy Engine ---")
    print(f"Input Text: '{args.text}'")
    
    print("\n1. Analyzing emotion...")
    classifier = get_classifier()
    emotion, conf, _ = classifier.detect_emotion(args.text)
    print(f"-> Detected Emotion: '{emotion}' with confidence {conf:.2f}")
    
    print("\n2. Mapping to prosody features...")
    rate, pitch, vol = map_emotion_to_params(emotion, conf)
    print(f"-> Selected Parameters | Rate: {rate} wpm, Pitch: {pitch}, Volume: {vol}")
    
    vol_float = db_to_float_volume(vol)
    
    print("\n3. Synthesizing audio...")
    audio_bytes = synthesize_local(args.text, rate, vol_float, force_recompute=True)
    
    if not audio_bytes:
        print("[!] Synthesis failed.")
        sys.exit(1)
        
    if args.save:
        try:
            with open(args.save, "wb") as f:
                f.write(audio_bytes)
            print(f"[+] Saved successfully to {args.save}")
        except Exception as e:
            print(f"[!] Could not save file: {e}")
    else:
        print("[+] Synthesis complete. Audio saved in local cache directory.")

if __name__ == "__main__":
    main()
