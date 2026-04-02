import os
import logging
import io
import re
import html
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables from .env if it exists
load_dotenv()

# Centralized Configuration: Priority 1: .env -> Priority 2: config.py
try:
    import config
except ImportError:
    config = None

def get_config(key, default=None):
    return os.getenv(key) or (getattr(config, key, default) if config else default)

TELEGRAM_BOT_TOKEN = get_config('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
AI_API_KEY = get_config('API_KEY', 'YOUR_API_KEY_HERE')
AI_API_BASE = get_config('API_BASE', 'https://openrouter.ai/api/v1')
AI_MODEL_NAME = get_config('API_MODEL', 'google/gemini-3.1-flash-lite-preview')

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
(
    SETTING_TOKEN, 
    SELECTING_REPO, 
    SELECTING_ACTION, 
    LISTING_CONTENTS, 
    SELECTING_DOWNLOAD_TYPE,
    CREATING_PR_HEAD,
    CREATING_PR_BASE,
    CREATING_PR_TITLE,
    CREATING_PR_BODY
) = range(9)

# UI Constant
BANNER = "<b>🚀 GitPushBot | GitHub Manager</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"

# Initialize AI client with dynamic base URL
llm_client = AsyncOpenAI(
    base_url=AI_API_BASE,
    api_key=AI_API_KEY,
) if AI_API_KEY and AI_API_KEY != "YOUR_API_KEY_HERE" else None

def get_github_client(context: ContextTypes.DEFAULT_TYPE):
    """Get GitHub client for the current user."""
    token = context.user_data.get('github_token')
    if not token:
        return None
    return Github(token)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        error_msg = f"❌ <b>Technical Error:</b>\n<code>{html.escape(str(context.error))}</code>"
        try:
            await update.effective_message.reply_html(error_msg)
        except:
            await update.effective_message.reply_text(f"❌ Technical Error: {str(context.error)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bot and check for GitHub token."""
    user = update.effective_user
    first_name = html.escape(user.first_name) if user.first_name else "User"
    
    if 'github_token' not in context.user_data:
        welcome_text = (
            f"{BANNER}"
            f"Hello, <b>{first_name}</b>! 👋\n\n"
            "Welcome to <b>GitPushBot</b>, your high-performance GitHub partner on Telegram. This bot turns your mobile device into a powerful development workstation, bridging the gap between local files and remote repositories with zero friction.\n\n"
            "🛡 <b>Identity & Security</b>\n"
            "We prioritize your safety. Your <b>GitHub PAT</b> is stored only within your encrypted session and is never shared. We recommend <b>Fine-grained tokens</b> for maximum security.\n\n"
            "🚀 <b>Key Features</b>\n"
            "• <b>Instant Uploads:</b> Push files to your repo immediately.\n"
            "• <b>Smart Deletion:</b> Remove obsolete files with a single click.\n"
            "• <b>Archive Gen:</b> Download repos as ZIP files for offline access.\n"
            "• <b>Seamless UI:</b> Explore folders using interactive menus.\n"
            "• <b>AI Analysis:</b> Analyze code with AI via OpenRouter.\n"
            "• <b>Pull Requests:</b> Create PRs directly from Telegram.\n\n"
            "🔑 <b>To begin, please provide your GitHub PAT.</b>"
        )
        keyboard = [
            [InlineKeyboardButton("👨‍💻 Dev", url="https://t.me/Ankurslys")],
            [InlineKeyboardButton("🛡 Support", url="https://t.me/BrahMosAI")],
            [InlineKeyboardButton("📖 How To Use", callback_data="how_to_use")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        banner_path = os.path.join(os.path.dirname(__file__), "start.jpg")
        
        if os.path.exists(banner_path):
            with open(banner_path, 'rb') as banner:
                if update.message:
                    await update.message.reply_photo(photo=banner, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                else:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=banner, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            if update.message:
                await update.message.reply_html(welcome_text, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return SETTING_TOKEN
    
    return await list_repos(update, context)

async def how_to_use_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains how to use the bot."""
    query = update.callback_query
    await query.answer()
    
    help_text = (
        f"{BANNER}"
        "<b>How To Use GitPushBot</b>\n\n"
        "1) <b>Generate a Token:</b> Go to GitHub Settings > Developer Settings > Personal Access Tokens. We recommend <b>Fine-grained</b> tokens for better security control.\n\n"
        "2) <b>Authenticate:</b> Paste your token here. The bot will verify it and fetch your repository list automatically.\n\n"
        "3) <b>Select Repository:</b> Click on any folder icon to enter a repo. All subsequent actions will happen inside this specific repository until you go back.\n\n"
        "4) <b>Push Files:</b> Once inside a repo, click 'Initiate' then simply send a file to this chat. The bot will upload it to the 'main' branch by default.\n\n"
        "5) <b>Manage Assets:</b> Use the menus to View, Analyze, Download or Delete files. Create PRs with ease.\n\n"
        "6) <b>Clean Session:</b> Use /logout anytime to wipe your token from the bot's temporary memory."
    )
    keyboard = [[InlineKeyboardButton("🔙 Back to Start", callback_data="back_to_start")]]
    
    try:
        await query.edit_message_caption(caption=help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    except Exception:
        # Fallback if the message doesn't have a caption (unlikely here but safe)
        await query.edit_message_text(text=help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Delete the message with buttons so start() can send a NEW message (with photo)
    await query.delete_message()
    return await start(update, context)

async def receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and store the user's GitHub token."""
    token = update.message.text.strip()
    
    try:
        g = Github(token)
        user = g.get_user()
        username = html.escape(user.login)
        
        context.user_data['github_token'] = token
        context.user_data['github_username'] = username
        
        await update.message.reply_html(f"✅ <b>Token Verified!</b>\nWelcome, <code>{username}</code>. Fetching your repositories...")
        return await list_repos(update, context)
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        await update.message.reply_html("❌ <b>Invalid Token</b> or connection error.\nPlease send a valid GitHub PAT.")
        return SETTING_TOKEN

async def list_repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List repositories for the user."""
    g = get_github_client(context)
    if not g:
        await update.effective_message.reply_html("⚠️ <b>Session Expired.</b> Please use /start.")
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()
        try:
            loading_msg = await update.callback_query.edit_message_text("🔄 <b>Fetching repositories...</b>", parse_mode=ParseMode.HTML)
        except Exception:
            loading_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="🔄 <b>Fetching repositories...</b>", parse_mode=ParseMode.HTML)
    else:
        loading_msg = await update.effective_message.reply_html("🔄 <b>Fetching repositories...</b>")
    
    try:
        user_gh = g.get_user()
        repos = user_gh.get_repos()
        
        keyboard = []
        for repo in repos:
            repo_name = html.escape(repo.name)
            keyboard.append([InlineKeyboardButton(f"📁 {repo_name}", callback_data=f"repo:{repo.name}")])
        
        if not keyboard:
            await loading_msg.edit_text("❌ No repositories found.")
            return ConversationHandler.END

        reply_markup = InlineKeyboardMarkup(keyboard)
        await loading_msg.edit_text(f"{BANNER}<b>Select a Repository:</b>", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return SELECTING_REPO
    except Exception as e:
        logger.error(f"Error fetching repos: {e}")
        await loading_msg.edit_text("❌ Failed to fetch repositories. Use /logout and try again.")
        return ConversationHandler.END

async def repo_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split(":")
    repo_name = data_parts[1]
    
    context.user_data['repo_name'] = repo_name
    context.user_data['current_path'] = ""
    
    return await show_action_menu(update, context)

async def show_action_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    repo_name = context.user_data['repo_name']
    keyboard = [
        [InlineKeyboardButton("📤 Initiate (Upload)", callback_data="initiate")],
        [InlineKeyboardButton("📥 Download (Get File)", callback_data="download_menu")],
        [InlineKeyboardButton("👁 View File", callback_data="list_contents_view")],
        [InlineKeyboardButton("🧠 Analyze File", callback_data="list_contents_analyze")],
        [InlineKeyboardButton("🗑 Delete File", callback_data="list_contents_delete")],
        [InlineKeyboardButton("🔁 Create PR", callback_data="create_pr_start")],
        [InlineKeyboardButton("🔙 Back to Repos", callback_data="back_to_repos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = f"{BANNER}📍 <b>Repo:</b> <code>{html.escape(repo_name)}</code>\nWhat would you like to do?"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(msg_text, reply_markup=reply_markup)
    return SELECTING_ACTION

# --- PR Flow Functions ---
async def create_pr_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"{BANNER}🔁 <b>Create Pull Request</b>\n\n"
        "Please type the name of the <b>HEAD branch</b> (the branch containing your changes):",
        parse_mode=ParseMode.HTML
    )
    return CREATING_PR_HEAD

async def create_pr_head(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pr_head'] = update.message.text.strip()
    await update.message.reply_html(
        "Please type the name of the <b>BASE branch</b> (the branch you want to merge into, e.g., main):"
    )
    return CREATING_PR_BASE

async def create_pr_base(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pr_base'] = update.message.text.strip()
    await update.message.reply_html("Please type the <b>Title</b> for the Pull Request:")
    return CREATING_PR_TITLE

async def create_pr_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pr_title'] = update.message.text.strip()
    await update.message.reply_html("Please type the <b>Body/Description</b> for the Pull Request:")
    return CREATING_PR_BODY

async def create_pr_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    body = update.message.text.strip()
    repo_name = context.user_data['repo_name']
    head = context.user_data['pr_head']
    base = context.user_data['pr_base']
    title = context.user_data['pr_title']
    
    status_msg = await update.message.reply_html("⏳ <b>Creating Pull Request...</b>")
    g = get_github_client(context)
    try:
        repo = g.get_user().get_repo(repo_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        await status_msg.edit_text(f"✅ <b>Pull Request Created!</b>\n<a href='{pr.html_url}'>{html.escape(title)}</a>", parse_mode=ParseMode.HTML)
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Error creating PR: {e}")
        await status_msg.edit_text(f"❌ <b>PR Creation Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION
# -------------------------

async def download_menu_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    repo_name = context.user_data['repo_name']
    
    keyboard = [
        [InlineKeyboardButton("📦 Full Repo (ZIP)", callback_data="download_zip")],
        [InlineKeyboardButton("📄 Specific File", callback_data="list_contents_download")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"{BANNER}📥 <b>Download:</b> <code>{html.escape(repo_name)}</code>\n"
        "Do you want the entire repository as a ZIP or select a single file?",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    return SELECTING_DOWNLOAD_TYPE

async def download_zip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)

    await query.edit_message_text(f"⏳ <b>Preparing ZIP for</b> <code>{html.escape(repo_name)}</code>...", parse_mode=ParseMode.HTML)
    
    try:
        archive_url = repo.get_archive_link("zipball")
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=archive_url,
            filename=f"{repo_name}_main.zip",
            caption=f"📦 <b>Archive for</b> <code>{html.escape(repo_name)}</code> (main branch)",
            parse_mode=ParseMode.HTML
        )
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"ZIP error: {e}")
        await query.edit_message_text(f"❌ <b>ZIP Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def list_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "list_contents_delete":
        context.user_data['action_type'] = "delete"
        context.user_data['current_path'] = ""
    elif query.data == "list_contents_download":
        context.user_data['action_type'] = "download"
        context.user_data['current_path'] = ""
    elif query.data == "list_contents_view":
        context.user_data['action_type'] = "view"
        context.user_data['current_path'] = ""
    elif query.data == "list_contents_analyze":
        context.user_data['action_type'] = "analyze"
        context.user_data['current_path'] = ""

    return await render_contents(update, context)

async def handle_cd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    path = query.data.split(":", 1)[1]
    context.user_data['current_path'] = path
    return await render_contents(update, context)

async def render_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    repo_name = context.user_data['repo_name']
    path = context.user_data.get('current_path', "")
    action = context.user_data.get('action_type', "delete")
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    try:
        contents = repo.get_contents(path)
        keyboard = []
        
        if path:
            parent_path = "/".join(path.split("/")[:-1])
            keyboard.append([InlineKeyboardButton("📁 .. (Parent)", callback_data=f"cd:{parent_path}")])

        if action == "analyze":
            keyboard.append([InlineKeyboardButton("🧠 Analyze Entire Folder", callback_data=f"analyze_folder:{path}")])

        current_row = []
        for content in contents:
            content_path = html.escape(content.path)
            if content.type == "dir":
                btn = InlineKeyboardButton(f"📁 {content.name}", callback_data=f"cd:{content.path}")
            else:
                if action == "delete":
                    prefix = "🗑"
                    callback_prefix = "delete"
                elif action == "download":
                    prefix = "📥"
                    callback_prefix = "download_file"
                elif action == "view":
                    prefix = "👁"
                    callback_prefix = "view_file"
                else: # analyze
                    prefix = "🧠"
                    callback_prefix = "analyze_file"

                btn = InlineKeyboardButton(f"{prefix} {content.name}", callback_data=f"{callback_prefix}:{content.path}")
            
            current_row.append(btn)
            if len(current_row) == 2:
                keyboard.append(current_row)
                current_row = []
                
        if current_row:
            keyboard.append(current_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        display_path = html.escape(path) if path else "Root"
        mode_text = action.upper()
        await query.edit_message_text(
            f"{BANNER}📂 <b>{mode_text} Path:</b> <code>{html.escape(repo_name)}/{display_path}</code>\n\n"
            "<i>Select a file or folder.</i>", 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return LISTING_CONTENTS
    except Exception as e:
        logger.error(f"Error listing contents: {e}")
        await query.edit_message_text(f"❌ Error listing contents: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def delete_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    file_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    try:
        contents = repo.get_contents(file_path)
        repo.delete_file(contents.path, f"Deleted {file_path} via Bot", contents.sha, branch="main")
        await query.edit_message_text(f"✅ <b>Successfully Deleted:</b>\n<code>{html.escape(file_path)}</code>", parse_mode=ParseMode.HTML)
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        await query.edit_message_text(f"❌ <b>Deletion Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def download_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    file_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    await query.edit_message_text(f"⏳ <b>Downloading</b> <code>{html.escape(file_path)}</code>...", parse_mode=ParseMode.HTML)
    
    try:
        contents = repo.get_contents(file_path)
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=contents.download_url,
            filename=contents.name,
            caption=f"📥 <b>File:</b> <code>{html.escape(file_path)}</code>",
            parse_mode=ParseMode.HTML
        )
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Download file error: {e}")
        await query.edit_message_text(f"❌ <b>Download Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def view_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    file_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    try:
        contents = repo.get_contents(file_path)
        try:
            decoded_content = contents.decoded_content.decode('utf-8')
        except UnicodeDecodeError:
            decoded_content = "Binary or unsupported file format."

        safe_content = html.escape(decoded_content)
        if len(safe_content) > 3800:
            safe_content = safe_content[:3800] + "\n...[Content Truncated]..."
        
        msg = f"👁 <b>File:</b> <code>{html.escape(file_path)}</code>\n<pre><code>{safe_content}</code></pre>"
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Repo", callback_data="back_to_menu")]]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Actions:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error viewing file: {e}")
        await query.edit_message_text(f"❌ <b>View Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def analyze_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    file_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    await query.edit_message_text(f"🧠 <b>Analyzing</b> <code>{html.escape(file_path)}</code> with LLM...", parse_mode=ParseMode.HTML)
    
    try:
        contents = repo.get_contents(file_path)
        try:
            decoded_content = contents.decoded_content.decode('utf-8')
        except UnicodeDecodeError:
            decoded_content = "Cannot analyze binary files."

        # Format code with line numbers to help AI
        lines = decoded_content.split('\n')
        numbered_code = '\n'.join([f"{i+1} | {line}" for i, line in enumerate(lines)])
        
        prompt = (
            f"Analyze the following code from {file_path}. "
            "Identify any potential errors, bugs, or improvements. \n"
            "IMPORTANT RULES:\n"
            "- Always mention the exact line number where the issue is found.\n"
            "- Ignore 'hardcoded credentials' warnings for config files (like config.py or .env).\n"
            "CRITICAL FORMATTING RULES:\n"
            "1. Format strictly using HTML tags: <b>, <i>, <pre>, <code>.\n"
            "2. DO NOT use markdown like ** or ### or ```.\n"
            "3. Escape < and > inside code blocks as &lt; and &gt;.\n"
            "4. If you detect ANY error (critical OR minor) that needs fixing, end your response with exactly: [ERROR_DETECTED].\n\n"
            f"CODE WITH LINE NUMBERS:\n{numbered_code[:6000]}" # Limit context
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME, 
            messages=[
                {"role": "system", "content": "You are an expert code reviewer and debugger."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800
        )
        
        raw_analysis = response.choices[0].message.content
        if len(raw_analysis) > 3800:
            raw_analysis = raw_analysis[:3800] + "..."
            
        keyboard = [[InlineKeyboardButton("🔙 Back to Repo", callback_data="back_to_menu")]]
        
        if "[ERROR_DETECTED]" in raw_analysis:
            raw_analysis = raw_analysis.replace("[ERROR_DETECTED]", "")
            # Give users a clear, optional button to trigger an AI fix
            keyboard.insert(0, [InlineKeyboardButton("🛠 Magic Fix (Auto-Resolve)", callback_data=f"fix_error:{file_path}")])
            
        msg = f"🧠 <b>Analysis for</b> <code>{html.escape(file_path)}</code>:\n\n{raw_analysis}"
        
        try:
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"HTML Parse Error: {e}, falling back to plain text.")
            clean_msg = re.sub(r'<[^>]+>', '', msg)
            await query.edit_message_text(clean_msg)
            
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Actions:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error analyzing file: {e}")
        await query.edit_message_text(f"❌ <b>Analysis Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION


async def fix_error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    file_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    await query.edit_message_text(f"🛠 <b>Fixing</b> <code>{html.escape(file_path)}</code> with AI...", parse_mode=ParseMode.HTML)
    
    try:
        contents = repo.get_contents(file_path)
        decoded_content = contents.decoded_content.decode('utf-8')
        
        prompt = (
            f"Fix the errors in the following code from {file_path}. "
            "Return ONLY the fully corrected raw code. Do not include any explanations, markdown formatting (like ```python), or HTML tags. "
            "The output must be strictly the raw code that can be saved directly to the file.\n\n"
            f"{decoded_content}"
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an expert code fixer. Provide only raw fixed code."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        fixed_code = response.choices[0].message.content.strip()
        fixed_code = re.sub(r"^```[a-zA-Z0-9]*\n", "", fixed_code)
        fixed_code = re.sub(r"```$", "", fixed_code).strip()
        
        repo.update_file(contents.path, f"AI Fix {file_path}", bytes(fixed_code, 'utf-8'), contents.sha, branch="main")
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Repo", callback_data="back_to_menu")]]
        await query.edit_message_text(f"✅ <b>Successfully fixed and pushed:</b> <code>{html.escape(file_path)}</code>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error fixing file: {e}")
        await query.edit_message_text(f"❌ <b>Fix Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION


async def analyze_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    folder_path = query.data.split(":", 1)[1]
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    
    display_path = html.escape(folder_path) if folder_path else "Root"
    await query.edit_message_text(f"🧠 <b>Analyzing folder</b> <code>{display_path}</code> with AI...\n<i>This might take a minute depending on folder size.</i>", parse_mode=ParseMode.HTML)
    
    try:
        def get_all_files(repo, path, limit=15):
            files = []
            try:
                contents = repo.get_contents(path)
                for content in contents:
                    if len(files) >= limit: break
                    if content.type == "dir":
                        files.extend(get_all_files(repo, content.path, limit - len(files)))
                    elif content.name.endswith(('.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.toml', '.txt')):
                        files.append(content)
            except: pass
            return files
            
        files_to_analyze = get_all_files(repo, folder_path)
        
        combined_content = ""
        for f in files_to_analyze:
            try:
                decoded = f.decoded_content.decode('utf-8')
                combined_content += f"\n\n--- FILE: {f.path} ---\n{decoded[:1000]}"
            except: pass
                
        prompt = (
            f"Analyze the following files from the folder '{folder_path}'. "
            "Identify architectural issues, potential errors, or bugs. "
            "Keep the response concise.\n"
            "CRITICAL FORMATTING RULES:\n"
            "1. Format strictly using HTML tags: <b>, <i>, <pre>, <code>.\n"
            "2. DO NOT use markdown like ** or ### or ```.\n"
            "3. Escape < and > inside code blocks as &lt; and &gt;.\n\n"
            f"CODE:\n{combined_content[:15000]}"
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "system", "content": "You are an expert software architect."}, {"role": "user", "content": prompt}],
            max_tokens=800
        )
        
        raw_analysis = response.choices[0].message.content
        if len(raw_analysis) > 3800: raw_analysis = raw_analysis[:3800] + "..."
            
        keyboard = [[InlineKeyboardButton("🔙 Back to Repo", callback_data="back_to_menu")]]
        msg = f"🧠 <b>Analysis for Folder</b> <code>{display_path}</code>:\n\n{raw_analysis}"
        
        try:
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        except Exception:
            clean_msg = re.sub(r'<[^>]+>', '', msg)
            await query.edit_message_text(clean_msg)
            
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Actions:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error analyzing folder: {e}")
        await query.edit_message_text(f"❌ <b>Analysis Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def initiate_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"{BANNER}"
        "📤 <b>Send the file</b> you want to upload to the <code>main</code> branch.",
        parse_mode=ParseMode.HTML
    )
    return SELECTING_ACTION

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    repo_name = context.user_data.get('repo_name')
    if not repo_name:
        await update.message.reply_html("⚠️ <b>Select a repository first!</b>")
        return ConversationHandler.END
        
    document = update.message.document
    file_name = document.file_name
    
    status_msg = await update.message.reply_html(f"🔄 <b>Uploading</b> <code>{html.escape(file_name)}</code>...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        
        g = get_github_client(context)
        repo = g.get_user().get_repo(repo_name)
        
        try:
            contents = repo.get_contents(file_name, ref="main")
            repo.update_file(contents.path, f"Update {file_name} via Bot", bytes(file_bytes), contents.sha, branch="main")
            await status_msg.edit_text(f"✅ <b>Updated:</b> <code>{html.escape(file_name)}</code>", parse_mode=ParseMode.HTML)
        except:
            repo.create_file(file_name, f"Upload {file_name} via Bot", bytes(file_bytes), branch="main")
            await status_msg.edit_text(f"✅ <b>Uploaded:</b> <code>{html.escape(file_name)}</code>", parse_mode=ParseMode.HTML)
            
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        await update.message.reply_html(f"❌ <b>Upload Failed:</b>\n{html.escape(str(e))}")
        return SELECTING_ACTION

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await show_action_menu(update, context)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_html("👋 <b>Logged Out.</b> Your session has been cleared.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_html("❌ <b>Operation Cancelled.</b>")
    return ConversationHandler.END

async def set_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_html("🔑 <b>Please send your NEW GitHub PAT:</b>")
    return SETTING_TOKEN

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("🏓 <b>Pong!</b> Bot is active.")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("ping", ping))
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("set_token", set_token_command)
        ],
        states={
            SETTING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token)],
            SELECTING_REPO: [CallbackQueryHandler(repo_choice, pattern="^repo:")],
            SELECTING_ACTION: [
                CallbackQueryHandler(initiate_prompt, pattern="^initiate$"),
                CallbackQueryHandler(download_menu_prompt, pattern="^download_menu$"),
                CallbackQueryHandler(list_contents, pattern="^list_contents_"),
                CallbackQueryHandler(create_pr_start, pattern="^create_pr_start$"),
                CallbackQueryHandler(list_repos, pattern="^back_to_repos$"),
                CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
                MessageHandler(filters.Document.ALL, handle_document),
            ],
            SELECTING_DOWNLOAD_TYPE: [
                CallbackQueryHandler(download_zip_callback, pattern="^download_zip$"),
                CallbackQueryHandler(list_contents, pattern="^list_contents_download$"),
                CallbackQueryHandler(show_action_menu, pattern="^back_to_menu$"),
            ],
            LISTING_CONTENTS: [
                CallbackQueryHandler(handle_cd, pattern="^cd:"),
                CallbackQueryHandler(delete_file_callback, pattern="^delete:"),
                CallbackQueryHandler(download_file_callback, pattern="^download_file:"),
                CallbackQueryHandler(view_file_callback, pattern="^view_file:"),
                CallbackQueryHandler(analyze_file_callback, pattern="^analyze_file:"),
                CallbackQueryHandler(analyze_folder_callback, pattern="^analyze_folder:"),
                CallbackQueryHandler(fix_error_callback, pattern="^fix_error:"),
                CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
            ],
            CREATING_PR_HEAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_head)],
            CREATING_PR_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_base)],
            CREATING_PR_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_title)],
            CREATING_PR_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_submit)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel), 
            CommandHandler("logout", logout), 
            CommandHandler("start", start),
            CallbackQueryHandler(how_to_use_callback, pattern="^how_to_use$"),
            CallbackQueryHandler(back_to_start, pattern="^back_to_start$")
        ],
    )

    application.add_error_handler(error_handler)
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_document))

    logger.info("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
