import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('API_KEY')
api_base = os.getenv('API_BASE', 'https://openrouter.ai/api/v1')

if not api_key or api_key == "YOUR_API_KEY_HERE":
    print("Error: API_KEY not found in .env file.")
    exit(1)

client = OpenAI(
    base_url=api_base,
    api_key=api_key,
)

try:
    models = client.models.list()
    google_models = [m.id for m in models.data if 'google' in m.id.lower()]
    
    print(f"--- Available Google Models on {api_base} ---")
    if not google_models:
        print("No Google models found.")
    for model in sorted(google_models):
        print(f"✅ {model}")
except Exception as e:
    print(f"Error fetching models: {e}")
