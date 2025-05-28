from openai import AsyncOpenAI
import asyncio
import sys
import openai
import base64

# TODO: use parameters or env vars
base_url = "http://host.docker.internal:8080/v1"
model = "ggml_llava-v1.5-7b"
# model = "google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0"
# base_url = 'http://host.docker.internal:11434/v1'
# model = 'gemma3:27b-it-qat'

client = AsyncOpenAI(
    base_url = base_url,
    api_key = "llama.cpp" # required, but unused
)


async def image_query(image_b64: str|None, prompt: str = "describe the image"):
    if not image_b64: return

    global model, endpoint

    try:
        response = await client.chat.completions.create(
        # response = await client.completions.create(
            model=model,
            # prompt=f"You are a world class image analyzer. Follow the prompts given by the user: {prompt}",
            # temperature=0.5,
            max_tokens=512,
            messages=[
                {
                "role": "user",
                    "content": [
                        { "type": "text", "text": prompt},
                        { "type": "image_url", "image_url":
                            {
                                "url": f"data:image/png;base64,{image_b64}",
                            },
                        },
                        ],
                },
                # { "role": "system", "content": "You are a world class image analyzer." },
                # { "role": "user", "content": [
                #         {"type": "input_text", "text": prompt},
                #         {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                #     ],
                # }
            ],
        )
        return response
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
    description = asyncio.run(image_query(image_b64))
    print(description)
