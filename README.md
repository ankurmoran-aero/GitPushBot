# 🚀 GitPushBot - Your GitHub Manager on Telegram

**GitPushBot** is a high-performance, open-source Telegram bot designed to bridge the gap between your local files and GitHub repositories. It allows developers to manage their code directly from the Telegram interface with ease and security.

---

## 🧐 What It Does
GitPushBot provides a seamless mobile-first experience for GitHub management. 
- **📤 Instant Uploads:** Send any document (code, images, text) to the bot, and it will instantly upload or update it in your repository.
- **👁 File Viewing:** Read any file in your repo directly in Telegram with clean code formatting.
- **🧠 AI Analysis (Powered by Gemini 3.1):** Use AI to analyze individual files or entire folders. Identify bugs, architectural issues, and improvements with line-by-line precision.
- **🛠 Magic Fix:** AI detected an error? Fix it instantly with one click. The bot will rewrite and push the corrected code for you.
- **🔁 Pull Requests:** Create new Pull Requests directly from the bot.
- **📥 Repository Downloads:** Download specific files or generate a ZIP of your entire repository.
- **📂 Navigation:** Explore your repository structure through intuitive grid-style inline buttons.

## ⚙️ How It Works
1. **Authentication:** Uses your **GitHub Personal Access Token (PAT)**. This token is stored only within your Telegram session for maximum security.
2. **AI Integration:** Powered by **OpenRouter** and **Gemini 3.1 Flash Lite**, providing lightning-fast code reviews.
3. **Session Logic:** It utilizes a `ConversationHandler` to guide you through selecting a repo and performing actions.
4. **API Integration:** Powered by `PyGithub`, it interacts with the GitHub REST API.

---

## 👨‍💻 Developed By
**GitPushBot** was created with ❤️ by **Ankur** ([@Ankurslys](https://t.me/Ankurslys)).

---

## 🚀 Setup & Installation

### For Normal Users
1. **Clone the Repo:**
   ```bash
   git clone https://github.com/ankurmoran96-openai/GitPushBot.git
   cd GitPushBot
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure:**
   Update `config.py` with your Telegram Bot Token and OpenRouter API Key.
4. **Run:**
   ```bash
   python bot.py
   ```

## 📄 License
This project is licensed under the **MIT License**.
