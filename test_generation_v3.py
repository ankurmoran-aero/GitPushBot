import os
import requests
import json
import base64
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('API_KEY')
api_base = os.getenv('API_BASE', 'https://openrouter.ai/api/v1')
model_name = "google/gemini-3.1-flash-image-preview"

if not api_key:
    print("Error: API_KEY not found.")
    exit(1)

prompt = "A futuristic, professional 3D cyber-tech logo for a GitHub bot named 'GitPushBot'. Neon blue and purple colors, sleek lines, cinematic lighting, 8k resolution."

print(f"🚀 Attempting Image Generation with: {model_name}")

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
                {"role": "user", "content": f"Generate a high-quality image based on this description: {prompt}"}
            ]
        })
    )
    
    # Get raw text to find base64 even if JSON parsing is complex
    raw_text = response.text
    
    # Look for common base64 image pattern
    # Standard format: data:image/png;base64,iVBORw0...
    match = re.search(r'data:image/(?P<ext>png|jpeg|jpg);base64,(?P<data>[A-Za-z0-9+/=]+)', raw_text)
    
    if match:
        ext = match.group('ext')
        img_data = match.group('data')
        print(f"✅ Found image data! Extension: {ext}")
        
        filename = f"generated_bot_logo.{ext}"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(img_data))
        
        print(f"💾 Saved image to: {filename}")
    else:
        print("❌ Could not find base64 image data in response.")
        # Print a bit of the response for debugging
        print("\n--- Response Snippet ---")
        print(raw_text[:1000])

except Exception as e:
    print(f"Error: {e}")
