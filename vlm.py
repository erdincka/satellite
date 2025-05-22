import logging
import os
import requests
from PIL import Image
# from transformers import BlipProcessor, BlipForQuestionAnswering
# Load model directly
from transformers import AutoProcessor, AutoModelForVisualQuestionAnswering

# FROM: https://discuss.streamlit.io/t/error-in-torch-with-streamlit/90908/3
import torch
torch.classes.__path__ = []


processor = AutoProcessor.from_pretrained("Salesforce/blip-vqa-base")
model = AutoModelForVisualQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")

logger = logging.getLogger(__name__)

# processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
# model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")

def image_to_text(image_url: str="", image_path: str="", question: str="Describe the image"):

    if not image_url and not image_path:
        return "Error: No image provided"

    if image_url:
        raw_image = Image.open(requests.get(image_url, stream=True).raw).convert('RGB') # pyright: ignore
    else:
        if os.path.exists(image_path):
            raw_image = Image.open(image_path).convert('RGB')
        else:
            return "File not found, did you replicate the volume?"

    inputs = processor(raw_image, question, return_tensors="pt")

    try:
        out = model.generate(**inputs)
    except Exception as e:
        logger.error(e)
        return "Error generating answer"
    return processor.decode(out[0], skip_special_tokens=True)
