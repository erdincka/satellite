from nicegui import app
from openai import OpenAI
import sys
import openai
import base64
import logging

import settings

logger = logging.getLogger(__name__)

base_url = app.storage.general.get("AI_ENDPOINT", "http://localhost:8080/v1")
model = app.storage.general.get("AI_MODEL", "gpt-4-vision-preview")
# model = "google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0"
# base_url = 'http://host.docker.internal:11434/v1'
# model = 'gemma3:27b-it-qat'

client = OpenAI(
    base_url = base_url,
    api_key = "llama.cpp" # required, but unused
)


def image_query(image_b64: str|None, prompt: str = "describe the image"):
    if not image_b64: return

    global model

    logger.debug("Using VLM at %s", base_url)
    logger.debug("VLM Model: %s", model)

    try:

        response = client.chat.completions.create(
        # response = client.completions.create(
            model=model,
            # prompt=f"You are a world class image analyzer. Follow the prompts given by the user: {prompt}",
            # temperature=0.5,
            max_tokens=512,
            messages=[
                { "role": "system", "content": "You are a world class image analyzer." },
                { "role": "user", "content": [
                            { "type": "text", "text": prompt},
                            { "type": "image_url", "image_url": "data:image/png;base64," + image_b64},
                        ],
                }, # pyright: ignore
            ],
        )
        return response.choices[0].message.content

    except openai.APIConnectionError as e:
        print("The server could not be reached")
        print(e.__cause__)  # an underlying Exception, likely raised within httpx.
    except openai.RateLimitError as e:
        print("A 429 status code was received; we should back off a bit.")
    except openai.APIStatusError as e:
        print("Another non-200-range status code was received")
        print(e.status_code)
        print(e.response)



if __name__ in ["__main__", "__amain__"]:
    image_path = sys.argv[1]
    with open(image_path, "rb") as image_file:
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")
    description = image_query(image_b64)
    print(description)
