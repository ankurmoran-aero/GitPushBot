# GitPushBot

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-22c55e?style=for-the-badge)]()

**GitPushBot** is a Telegram bot that provides direct GitHub repository management from any chat interface. Push, pull, update files, create pull requests, and get AI-powered code analysis — all without opening a browser.

---

## Features

| Feature | Description |
|---------|-------------|
| **Instant Sync** | Push, pull, or update files in any GitHub repository directly from Telegram |
| **AI Code Insights** | GPT-4o-powered professional code summaries and architectural analysis |
| **Magic Fix** | AI-generated bug patches pushed directly to your repository |
| **PR Management** | Create and manage Pull Requests entirely through the bot |
| **Secure PAT Handling** | GitHub Personal Access Tokens managed securely, optimized for low-bandwidth environments |

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/ankurmoran-aero/GitPushBot.git
cd GitPushBot
pip install -r requirements.txt
```

### 2. Configure Environment

Update `config.py` or create a `.env` file:

```env
BOT_TOKEN=your_telegram_bot_token
API_KEY=your_openai_api_key
```

### 3. Run

```bash
# With PM2 (recommended for production)
pm2 start bot.py --name GitPushBot

# Or directly
python3 bot.py
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.10+ |
| Telegram API | `python-telegram-bot` |
| GitHub Interface | `PyGithub` |
| AI Integration | OpenAI SDK |

---

## Project Structure

```
GitPushBot/
├── bot.py              # Main bot logic & command handlers
├── config.py           # Configuration & credentials
├── fetch_models.py     # AI model management
└── requirements.txt
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
