from emotion_model import get_classifier
from mapper import map_emotion_to_params

test_cases = [
    "I got a promotion! I am so happy right now!",
    "I'm really worried about you. Are you safe?",
    "The cake is good, I suppose.",
    "Get out of my house immediately!",
    "Wow, I can't believe this is happening!",
    "My dog passed away yesterday, I feel broken."
]

def run_tests():
    print("--- Emotion and Prosody Mapping Tests ---")
    classifier = get_classifier()
    
    for text in test_cases:
        print(f"\nText: \"{text}\"")
        emotion, conf, _ = classifier.detect_emotion(text)
        print(f"Detected: {emotion} (conf: {conf:.2f})")
        
        rate, pitch, vol = map_emotion_to_params(emotion, conf)
        print(f"Mapped Props: Rate={rate} wpm | Pitch={pitch} | Vol={vol}")

if __name__ == "__main__":
    run_tests()
