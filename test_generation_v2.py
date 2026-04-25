import os
import requests
import json
import base64
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
    
    result = response.json()
    
    # Check for image data in choices
    if "choices" in result and len(result["choices"]) > 0:
        message = result["choices"][0].get("message", {})
        
        # Look for multimodal content or base64 in the response
        # Gemini often returns images as parts of the message content in some APIs
        # In OpenRouter/Google AI Studio, it might be in 'content' as a string or a specific object.
        
        # Let's check the raw content first
        content = message.get("content")
        print("\n--- Content Type ---")
        print(type(content))
        
        # If content is None, look for 'parts' or other fields (Standard for some Google implementations)
        # Based on previous run, 'content' was null but 'usage' showed image_tokens.
        # This usually means the image was returned in a format standard OpenAI clients might miss 
        # but the JSON body contains.
        
        # Look for base64 strings in the entire result
        result_str = json.dumps(result)
        if "data:image" in result_str or "base64" in result_str:
            print("Found potential image data in JSON!")
            # Extract and save (simplified logic for test)
            # Typically looks like {"type": "image", "image_url": {"url": "data:image/png;base64,..."}}
            
    else:
        print("No choices in response.")
        print(json.dumps(result, indent=2))

except Exception as e:
    print(f"Error: {e}")
