import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('API_KEY')
api_base = os.getenv('API_BASE', 'https://openrouter.ai/api/v1')
model_name = "google/gemini-3.1-flash-image-preview"

if not api_key:
    print("Error: API_KEY not found.")
    exit(1)

print(f"🚀 Attempting Image Generation with: {model_name}")

# OpenRouter typically uses the standard OpenAI-compatible completions/chat endpoint.
# For Image Generation (DALL-E style), they might have specific requirements 
# or it might be handled via a standard message with a prompt.
# However, "image-preview" models often support generating images via the chat API 
# by returning a URL or base64 if it's a multimodal-output model.

prompt = "A futuristic, professional 3D cyber-tech logo for a GitHub bot named 'GitPushBot'. Neon blue and purple colors, sleek lines, cinematic lighting, 8k resolution."

try:
    response = requests.post(
        url=f"{api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps({
            "model": model_name,
            "messages": [
                {"role": "user", "content": f"Generate a high-quality image based on this description: {prompt}. Return only the image data or a direct link if possible."}
            ],
            # Some generation models use specific parameters
        })
    )
    
    result = response.json()
    print("\n--- API Response ---")
    print(json.dumps(result, indent=2))
    
    # Check if an image was actually generated (Look for URLs or base64 in the response)
    # Different providers return generation results differently.
except Exception as e:
    print(f"Error: {e}")
