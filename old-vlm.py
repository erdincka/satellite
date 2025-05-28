import logging
import requests
from PIL import Image
from transformers import AutoProcessor, AutoModelForVisualQuestionAnswering
# FROM: https://discuss.streamlit.io/t/error-in-torch-with-streamlit/90908/3
import torch
torch.classes.__path__ = []

logger = logging.getLogger(__name__)

processor = AutoProcessor.from_pretrained("Salesforce/blip-vqa-base")
model = AutoModelForVisualQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")

#### SEND REQUESTS TO REAL AI MODEL ####

def image_to_text(image_url: str="", image_path: str="", question: str="Describe the image"):
    if not image_url and not image_path:
        return "Error: No image provided"

    try:
        raw_image = Image.open(requests.get(image_url, stream=True).raw).convert('RGB') if image_url else Image.open(image_path).convert('RGB') # pyright: ignore
    except Exception as e:
        logger.error(f"Error loading image: {e}")
        return "File not found, did you replicate the volume?"

    inputs = processor(raw_image, question, return_tensors="pt")

    try:
        out = model.generate(**inputs)
    except Exception as e:
        logger.error(f"Error generating answer: {e}")
        return "Error generating answer"

    return processor.decode(out[0], skip_special_tokens=True)
