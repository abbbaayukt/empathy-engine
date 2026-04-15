import os
import torch
from transformers import pipeline

# Suppress symlink warning on Windows if raised
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

class EmotionClassifier:
    def __init__(self, model_name="SamLowe/roberta-base-go_emotions"):
        """
        Initializes the EmotionClassifier by loading the roberta model.
        """
        # Load the model on GPU if available, else CPU
        device = 0 if torch.cuda.is_available() else -1
        self.classifier = pipeline(
            "text-classification",
            model=model_name,
            return_all_scores=True,
            device=device
        )

    def detect_emotion(self, text: str) -> tuple[str, float, list]:
        """
        Classifies the text and returns its top emotion label and confidence score.
        Returns:
            (top_label, top_score, all_scores)
        """
        if not text.strip():
            return "neutral", 1.0, []

        scores_list = self.classifier(text)[0]
        # Find the max score
        top_emotion = max(scores_list, key=lambda x: x['score'])
        
        return top_emotion['label'], top_emotion['score'], scores_list

# Singleton instance
classifier_instance = None

def get_classifier():
    global classifier_instance
    if classifier_instance is None:
        classifier_instance = EmotionClassifier()
    return classifier_instance

if __name__ == "__main__":
    clf = get_classifier()
    print(clf.detect_emotion("I am so excited and happy to be here today!"))
    print(clf.detect_emotion("This is absolutely terrifying. We need to leave."))
