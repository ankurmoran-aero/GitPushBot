# 🚀 GitPushBot | Advanced Repository Manager

GitPushBot is a high-performance Telegram bot designed to turn your mobile device into a powerful development workstation. It bridges the gap between local files and GitHub repositories with zero friction, now enhanced with Google's **Gemini 3 Flash** for intelligent code insights.

## ✨ Features

*   **📤 Instant Synchronization:** Push or update files in your repository directly from Telegram.
*   **🔍 AI Summarization:** Get high-level, professional summaries of files or entire folders to understand code logic instantly.
*   **🧠 Deep AI Analysis:** Identify architectural issues, potential bugs, and logic errors with line-by-line feedback.
*   **🛠 Magic Fix:** Automatically resolve detected code issues with AI-driven patches pushed directly to your branch.
*   **📥 Archive Generation:** Download entire repositories as ZIP files or fetch specific assets on the go.
*   **🔁 Pull Request Management:** Create and submit Pull Requests without leaving the chat.
*   **🛡 Secure Sessions:** Uses GitHub PATs stored only in temporary session memory. Supports Fine-grained tokens for maximum security.
*   **📂 Professional UI:** A clean, grid-based interface with inline keyboards and path-shortening technology to handle deep directory structures.

## 🚀 Quick Start

1.  **Bot Token:** Obtain a bot token from [@BotFather](https://t.me/BotFather).
2.  **AI Power:** Get an API key from [OpenRouter](https://openrouter.ai/) (supports Gemini 3 Flash).
3.  **Environment:** Create a `.env` file or update `config.py` with your tokens.
4.  **Launch:**
    ```bash
    pip install -r requirements.txt
    python bot.py
    ```

## 🛠 Tech Stack

*   **Language:** Python 3.10+
*   **Framework:** `python-telegram-bot` (v21+)
*   **GitHub API:** `PyGithub`
*   **AI Integration:** `OpenAI` SDK (via OpenRouter)
*   **Process Management:** Recommended to run with `PM2`.

---
*Developed with ❤️ by Ankur. Bridging the gap between mobile and code.*
