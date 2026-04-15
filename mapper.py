"""
Emotion to Prosody Mapping Logic
"""

BASE_RATE = 140      # Words per minute (slower for better audibility)
BASE_VOLUME = 1.0    # Float 0.0 to 1.0

def map_emotion_to_params(emotion: str, score: float) -> tuple[int, str, str]:
    """
    Given an emotion label and a confidence score, return TTS parameters:
    (rate, pitch_str, volume_str)
    
    Returns:
        rate: Integer words per minute
        pitch_str: String format (e.g. '+2st', '-1st')
        volume_str: String format (e.g. '+3dB', '-2dB') for cloud or relative volume mapped for local.
    """
    
    rate = BASE_RATE
    pitch = "0st"
    volume = "+0dB"
    
    # Scale changes by score. If score is high (e.g. 0.9), impact is high.
    
    # 28 GoEmotions categories grouped by broad characteristics
    joy_group = {"joy", "excitement", "amusement", "optimism"}
    love_group = {"love", "caring", "admiration", "approval", "pride", "gratitude", "relief"}
    sadness_group = {"sadness", "disappointment", "embarrassment", "grief", "remorse"}
    anger_group = {"anger", "annoyance", "disapproval", "disgust"}
    fear_group = {"fear", "nervousness"}
    surprise_group = {"surprise", "realization", "confusion", "curiosity", "desire"}

    if emotion in joy_group or emotion in love_group:
        # Joy/Love: Faster, higher pitch, louder
        rate_mult = 1 + (0.3 * score)
        rate = int(BASE_RATE * rate_mult)
        pitch = f"+{int(3 * score)}st"
        volume = f"+{int(3 * score)}dB"
        
    elif emotion in sadness_group:
        # Sadness: Slightly slower, lower pitch, softer
        # Max -15% rate (reduced from -30% for better audibility)
        rate_mult = 1 - (0.15 * score)
        rate = int(BASE_RATE * rate_mult)
        pitch = f"-{int(3 * score)}st"
        volume = f"-{int(3 * score)}dB"
        
    elif emotion in anger_group:
        # Anger: Much faster, flat/zero pitch shift natively, much louder
        rate_mult = 1 + (0.5 * score)
        rate = int(BASE_RATE * rate_mult)
        pitch = "0st"
        volume = f"+{int(5 * score)}dB"
        
    elif emotion in surprise_group:
        # Surprise: Faster, much higher pitch
        rate_mult = 1 + (0.3 * score)
        rate = int(BASE_RATE * rate_mult)
        pitch = f"+{int(4 * score)}st"
        volume = f"+{int(2 * score)}dB"
        
    elif emotion in fear_group:
        # Fear: Faster, slightly higher pitch, softer
        rate_mult = 1 + (0.2 * score)
        rate = int(BASE_RATE * rate_mult)
        pitch = f"+{int(2 * score)}st"
        volume = f"-{int(2 * score)}dB"
        
    else:
        # Default / Neutral
        rate = BASE_RATE
        pitch = "0st"
        volume = "+0dB"

    return rate, pitch, volume

def db_to_float_volume(db_str: str) -> float:
    """
    Helper to convert dB string (e.g. "+3dB") to a float for pyttsx3 volume proxy.
    pyttsx3 expects volume between 0.0 and 1.0. 
    We will just treat base volume as 0.7, and scale roughly.
    """
    base_pyttsx3_vol = 0.7
    
    try:
        db_val = int(db_str.replace('+', '').replace('dB', ''))
    except ValueError:
        db_val = 0
        
    # Roughly every 3dB is doubling/halving, but we'll use a simpler linear mapping
    # +5dB -> +0.3
    # -3dB -> -0.2
    shift = db_val * 0.05
    
    final_vol = base_pyttsx3_vol + shift
    # Clamp between 0.1 and 1.0
    return max(0.1, min(1.0, final_vol))
