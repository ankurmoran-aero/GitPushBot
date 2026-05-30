import os

# 🚀 GitPushBot Configuration
# 1. Fork this repository.
# 2. Paste your Telegram Bot Token from @BotFather below.
# 3. Add your OpenRouter API Key for AI Analysis features.

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "BOT_TOKEN")

# AI Analysis Configuration 
# Use your Own API & ITS key.
API_BASE = os.getenv("API_BASE_URL", "https://api.gptnix.online/v1")
API_MODEL = "zenith/gpt-4o"
API_KEY = os.getenv("API_KEY", "YOUR_API_KEY")

# Admin Configuration
ADMIN_IDS = "6049120581" # Comma-separated list of Telegram User IDs
