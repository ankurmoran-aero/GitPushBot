import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('API_KEY')
api_base = os.getenv('API_BASE', 'https://openrouter.ai/api/v1')
model_name = "google/gemini-2.5-flash-image"

if not api_key:
    print("Error: API_KEY not found.")
    exit(1)

client = OpenAI(
    base_url=api_base,
    api_key=api_key,
)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

image_path = "GitPushBot/start.jpg"
if not os.path.exists(image_path):
    print(f"Error: {image_path} not found.")
    exit(1)

base64_image = encode_image(image_path)

print(f"🚀 Testing Image Model: {model_name}")
print(f"🖼 Analyzing: {image_path}...")

try:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image? Describe it professionally."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )
    print("\n--- AI Response ---")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
