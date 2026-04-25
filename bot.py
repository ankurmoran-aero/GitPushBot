import os
import logging
import io
import re
import html
from github import Github, Auth, GithubException
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
AI_MODEL_NAME = get_config('API_MODEL', 'openai/gpt-4o')

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
    CREATING_PR_BODY,
    CREATING_REPO_NAME,
    CREATING_REPO_PRIVATE,
    CONFIRMING_DELETE_REPO
) = range(12)
# UI Constants
BANNER = (
    "<b>🚀 GitPushBot | Advanced Repository Manager</b>\n"
    "<i>High-performance GitHub integration via Telegram</i>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
)

# Initialize AI client with dynamic base URL
llm_client = AsyncOpenAI(
    base_url=AI_API_BASE,
    api_key=AI_API_KEY,
) if AI_API_KEY and AI_API_KEY not in ["YOUR_API_KEY_HERE", "PASTE_YOUR_API_KEY_HERE", ""] else None

def get_github_client(context: ContextTypes.DEFAULT_TYPE):
    """Get GitHub client for the current user."""
    token = context.user_data.get('github_token')
    if not token:
        return None
    return Github(auth=Auth.Token(token))

def get_repo_default_branch(repo):
    """Safely get the default branch of a repository."""
    try:
        return repo.default_branch
    except:
        return "main"

def store_path(path: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Store a path and return a short ID to fit in Telegram's 64-byte callback_data limit."""
    if 'path_map' not in context.user_data:
        context.user_data['path_map'] = {}

    # Use a simple hash or index for the path
    import hashlib
    path_hash = hashlib.md5(path.encode()).hexdigest()[:10]
    context.user_data['path_map'][path_hash] = path
    return path_hash

def resolve_path(path_hash: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Resolve a short ID back to the full path."""
    return context.user_data.get('path_map', {}).get(path_hash, path_hash)

def clean_ai_html(text):
    """Sanitize AI output for Telegram HTML parse mode."""
    if not text: return ""
    
    # Strip wrapping markdown code blocks if the AI includes them
    text = text.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n?```$', '', text)
    text = text.strip()
    
    # Standard HTML tags allowed by Telegram: <b>, <i>, <u>, <s>, <a>, <code>, <pre>
    # First, escape everything to avoid breaking parse mode with rogue < or >
    text = html.escape(text)
    # Then restore specific allowed tags if they were intended as HTML
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    text = text.replace("&lt;u&gt;", "<u>").replace("&lt;/u&gt;", "</u>")
    text = text.replace("&lt;s&gt;", "<s>").replace("&lt;/s&gt;", "</s>")
    text = text.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    text = text.replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")
    
    # Handle common markdown formatting if AI didn't follow HTML instructions
    if "<b>" not in text and "**" in text:
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    if "<code>" not in text and "`" in text:
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
    return text

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
            f"Welcome, <b>{first_name}</b>! 👋\n\n"
            "This bot turns your mobile device into a powerful development workstation, bridging the gap between local files and remote repositories with zero friction.\n\n"
            "<b>🛡 Security First:</b>\n"
            "Your <b>GitHub PAT</b> is stored only within your encrypted session. We recommend <b>Fine-grained tokens</b>.\n\n"
            "<b>✨ Professional Features:</b>\n"
            "• <b>Push & Update:</b> Instant file synchronization.\n"
            "• <b>Archives:</b> One-tap repository downloads.\n"
            "• <b>Management:</b> PR creation and file deletion.\n"
            "• <b>✨ AI:</b> <i>Online & Active (GPT-4o)</i>\n\n"
            "🔑 <b>Please provide your GitHub PAT to begin:</b>"
        )
        keyboard = [
            [InlineKeyboardButton("📖 Documentation", callback_data="how_to_use")],
            [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/Ankurslys"), InlineKeyboardButton("🛡 Support", url="https://t.me/BrahMosAI")]
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
        g = Github(auth=Auth.Token(token))
        user = g.get_user()
        username = html.escape(user.login)
        
        context.user_data['github_token'] = token
        context.user_data['github_username'] = username
        
        await update.message.reply_html(f"✅ <b>Token Verified!</b>\nWelcome, <code>{username}</code>. Fetching your repositories...")
        return await list_repos(update, context)
    except GithubException as e:
        logger.error(f"GitHub Error during token validation: {e.status} {getattr(e, 'data', str(e))}")
        if e.status == 401:
            await update.message.reply_html("❌ <b>Invalid Token</b>.\nThe GitHub PAT provided is incorrect or expired. Please send a valid one.")
        else:
            error_msg = getattr(e, 'data', {}).get('message', 'Unknown error') if hasattr(e, 'data') and isinstance(e.data, dict) else 'Unknown error'
            await update.message.reply_html(f"❌ <b>GitHub Error</b>.\nConnection failed: {error_msg}\nPlease try again.")
        return SETTING_TOKEN
    except Exception as e:
        logger.error(f"Unexpected token validation failed: {e}")
        await update.message.reply_html("❌ <b>Technical Error</b>.\nFailed to validate token. Please try again later.")
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
        
        keyboard = [
            [InlineKeyboardButton("➕ Create New Repository", callback_data="create_repo_start")]
        ]
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
        [InlineKeyboardButton("📤 Upload File", callback_data="initiate")],
        [InlineKeyboardButton("🔍 Summarize", callback_data="list_contents_summarize"), InlineKeyboardButton("🧠 Analyze", callback_data="list_contents_analyze")],
        [InlineKeyboardButton("👁 View", callback_data="list_contents_view"), InlineKeyboardButton("📥 Download", callback_data="list_contents_download")],
        [InlineKeyboardButton("🗑 Delete Repo", callback_data="list_contents_delete_repo"), InlineKeyboardButton("🔁 Pull Request", callback_data="create_pr_start")],
        [InlineKeyboardButton("🔙 Switch Repository", callback_data="back_to_repos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = (
        f"{BANNER}"
        f"📍 <b>Repository:</b> <code>{html.escape(repo_name)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select an action to perform on this repository:"
    )
    
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
    
    mapping = {
        "list_contents_delete": "delete",
        "list_contents_download": "download",
        "list_contents_view": "view",
        "list_contents_analyze": "analyze",
        "list_contents_summarize": "summarize"
    }
    
    if query.data in mapping:
        context.user_data['action_type'] = mapping[query.data]
        context.user_data['current_path'] = ""

    return await render_contents(update, context)

async def handle_cd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # Get hash and resolve to full path
    path_hash = query.data.split(":", 1)[1]
    path = resolve_path(path_hash, context)
    context.user_data['current_path'] = path
    return await render_contents(update, context)

async def render_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    repo_name = context.user_data.get('repo_name')
    if not repo_name:
        await query.edit_message_text("⚠️ Repo context lost. Please select a repo again.")
        return SELECTING_REPO

    path = context.user_data.get('current_path', "")
    action = context.user_data.get('action_type', "delete")
    g = get_github_client(context)
    if not g:
        await query.edit_message_text("⚠️ GitHub session expired. Please /start.")
        return ConversationHandler.END

    repo = g.get_user().get_repo(repo_name)
    
    try:
        contents = repo.get_contents(path)
        keyboard = []
        
        if path:
            parent_path = "/".join(path.split("/")[:-1])
            p_hash = store_path(parent_path, context)
            keyboard.append([InlineKeyboardButton("🔙 .. (Parent)", callback_data=f"cd:{p_hash}")])

        if action in ["analyze", "summarize"]:
            f_hash = store_path(path, context)
            label = "🧠 Analyze Folder" if action == "analyze" else "🔍 Summarize Folder"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"{action}_folder:{f_hash}")])

        current_row = []
        for content in contents:
            content_path_hash = store_path(content.path, context)
            if content.type == "dir":
                btn = InlineKeyboardButton(f"📁 {content.name}", callback_data=f"cd:{content_path_hash}")
            else:
                icon_map = {
                    "delete": "🗑",
                    "download": "📥",
                    "view": "👁",
                    "analyze": "🧠",
                    "summarize": "🔍"
                }
                prefix = icon_map.get(action, "📄")
                callback_prefix = f"{action}_file" if action != "download" else "download_file"

                btn = InlineKeyboardButton(f"{prefix} {content.name}", callback_data=f"{callback_prefix}:{content_path_hash}")
            
            current_row.append(btn)
            if len(current_row) == 2:
                keyboard.append(current_row)
                current_row = []
                
        if current_row:
            keyboard.append(current_row)
        
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        display_path = html.escape(path) if path else "Root"
        mode_text = action.capitalize()
        await query.edit_message_text(
            f"{BANNER}"
            f"📂 <b>{mode_text} Mode</b>\n"
            f"📍 <b>Path:</b> <code>{html.escape(repo_name)}/{display_path}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Select a file or folder to continue:</i>", 
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
    
    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data.get('repo_name')
    g = get_github_client(context)
    if not g:
        await query.edit_message_text("⚠️ Session expired.")
        return ConversationHandler.END

    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    try:
        contents = repo.get_contents(file_path, ref=def_branch)
        repo.delete_file(contents.path, f"Deleted {file_path} via Bot", contents.sha, branch=def_branch)
        await query.edit_message_text(f"✅ <b>Successfully Deleted:</b>\n<code>{html.escape(file_path)}</code>", parse_mode=ParseMode.HTML)
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        await query.edit_message_text(f"❌ <b>Deletion Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def download_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data.get('repo_name')
    g = get_github_client(context)
    if not g: return ConversationHandler.END
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)

    await query.edit_message_text(f"⏳ <b>Downloading</b> <code>{html.escape(file_path)}</code>...", parse_mode=ParseMode.HTML)

    try:
        contents = repo.get_contents(file_path, ref=def_branch)
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

    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    if not g: return ConversationHandler.END
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)

    try:
        contents = repo.get_contents(file_path, ref=def_branch)
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
async def summarize_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data['repo_name']
    
    if not llm_client:
        await query.edit_message_text("❌ AI client not configured. Check your API key.")
        return SELECTING_ACTION

    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    await query.edit_message_text(f"⏳ <b>AI is summarizing:</b> <code>{html.escape(file_path)}</code>...", parse_mode=ParseMode.HTML)
    
    try:
        content_file = repo.get_contents(file_path, ref=def_branch)
        decoded_content = content_file.decoded_content.decode('utf-8')
        
        prompt = f"You are a Senior Code Reviewer and Expert Software Engineer explaining to a developer on Telegram. Summarize the following file contents concisely, accurately, and professionally. Use ONLY valid Telegram HTML tags (<b>, <i>, <code>, <pre>, <u>, <s>) for formatting. Do NOT use standard markdown like ** or `.\n\nPath: {file_path}\n\nContent:\n{decoded_content}"
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800
        )
        
        summary = response.choices[0].message.content
        formatted_summary = f"{BANNER}🔍 <b>AI Summary:</b> <code>{html.escape(file_path)}</code>\n\n{clean_ai_html(summary)}"
        
        if len(formatted_summary) > 4000:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_summary, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(formatted_summary, parse_mode=ParseMode.HTML)
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"AI Summary Error: {e}")
        await query.edit_message_text(f"❌ <b>AI Summary Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def summarize_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    path_hash = query.data.split(":", 1)[1]
    folder_path = resolve_path(path_hash, context)
    repo_name = context.user_data['repo_name']
    
    if not llm_client:
        await query.edit_message_text("❌ AI client not configured. Check your API key.")
        return SELECTING_ACTION

    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    await query.edit_message_text(f"⏳ <b>AI is summarizing folder:</b> <code>{html.escape(folder_path or 'root')}</code>...", parse_mode=ParseMode.HTML)
    
    try:
        contents = repo.get_contents(folder_path, ref=def_branch)
        file_structure = []
        for c in contents:
            file_structure.append(f"{'[DIR] ' if c.type == 'dir' else ''}{c.name}")
        
        structure_str = "\n".join(file_structure)
        prompt = (
            f"You are a Senior Code Reviewer and Expert Software Engineer explaining to a developer on Telegram.\n"
            f"Summarize the purpose and structure of this folder accurately.\n\nFolder: {folder_path or 'root'}\n\nContents:\n{structure_str}\n\n"
            "TASK: Provide a detailed, highly accurate summary. You MUST include:\n"
            "1. 🚀 What this project/folder ACTUALLY does, its core focus, and its goal.\n"
            "2. ✨ Core project features.\n"
            "3. 📊 Estimated Language Breakdown (e.g., 'Python 90%, Shell 10%').\n"
            "4. 🏅 Code Review & Judgment: Tell me how impressive or garbage the project looks, and how useful it actually is.\n\n"
            "STRICT FORMATTING: You are answering on Telegram. Use ONLY valid Telegram HTML tags (<b>, <i>, <code>, <pre>, <u>, <s>) for formatting. Do NOT use markdown like ** or `. Do NOT generate full HTML web pages or DOCTYPEs."
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800
        )
        
        summary = response.choices[0].message.content
        formatted_summary = f"{BANNER}🔍 <b>Folder Summary:</b> <code>{html.escape(folder_path or 'root')}</code>\n\n{clean_ai_html(summary)}"
        
        if len(formatted_summary) > 4000:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_summary, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(formatted_summary, parse_mode=ParseMode.HTML)
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"AI Folder Summary Error: {e}")
        await query.edit_message_text(f"❌ <b>Folder Summary Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def analyze_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data['repo_name']
    
    if not llm_client:
        await query.edit_message_text("❌ AI client not configured. Check your API key.")
        return SELECTING_ACTION

    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    await query.edit_message_text(f"⏳ <b>AI is analyzing:</b> <code>{html.escape(file_path)}</code>...", parse_mode=ParseMode.HTML)
    
    try:
        content_file = repo.get_contents(file_path, ref=def_branch)
        decoded_content = content_file.decoded_content.decode('utf-8')
            
        prompt = (
            f"Provide a deep analysis for this file.\n\nFile: {file_path}\n\nContent:\n{decoded_content}\n\n"
            "TASK: Perform a deep code analysis. You MUST ONLY report on:\n"
            "1. 🐛 Detect any bugs, critical errors, or security vulnerabilities and report them clearly.\n\n"
            "FORMATTING: Use ** ** for bold text and emojis. Do not use ANY HTML tags whatsoever. Provide a clean, well-formatted bug & error report."
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500
        )
        
        analysis = response.choices[0].message.content
        formatted_analysis = f"{BANNER}🧠 <b>AI Deep Analysis:</b> <code>{html.escape(file_path)}</code>\n\n{clean_ai_html(analysis)}"
        
        if len(formatted_analysis) > 4000:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_analysis, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(formatted_analysis, parse_mode=ParseMode.HTML)
            
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"AI Analysis Error: {e}")
        await query.edit_message_text(f"❌ <b>AI Analysis Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def fix_error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    path_hash = query.data.split(":", 1)[1]
    file_path = resolve_path(path_hash, context)
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)

    if not llm_client:
        await query.edit_message_text("❌ AI client not configured.")
        return SELECTING_ACTION

    await query.edit_message_text(f"🛠 <b>Fixing</b> <code>{html.escape(file_path)}</code> with AI...", parse_mode=ParseMode.HTML)

    try:
        contents = repo.get_contents(file_path, ref=def_branch)
        decoded_content = contents.decoded_content.decode('utf-8')

        prompt = (
            f"Fix the bugs/errors in this code from {file_path}. "
            "IMPORTANT: Return ONLY the fully corrected raw code. "
            "Do not include any explanations, comments outside the code, or markdown formatting blocks."
            f"\n\n{decoded_content}"
        )

        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4000
        )

        fixed_code = response.choices[0].message.content.strip()
        # More robust stripping of markdown blocks
        if fixed_code.startswith("```"):
            fixed_code = re.sub(r"^```[a-zA-Z0-9]*\n", "", fixed_code)
            fixed_code = re.sub(r"```$", "", fixed_code).strip()

        if not fixed_code or len(fixed_code) < 10:
             raise ValueError("AI returned invalid or empty code.")

        repo.update_file(contents.path, f"AI Fix {file_path}", fixed_code.encode('utf-8'), contents.sha, branch=def_branch)

        await query.edit_message_text(f"✅ <b>Successfully fixed and pushed:</b> <code>{html.escape(file_path)}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error fixing file: {e}")
        await query.edit_message_text(f"❌ <b>Fix Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def analyze_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    path_hash = query.data.split(":", 1)[1]
    folder_path = resolve_path(path_hash, context)
    repo_name = context.user_data.get('repo_name')
    g = get_github_client(context)
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    if not llm_client:
        await query.edit_message_text("❌ AI client not configured.")
        return SELECTING_ACTION

    await query.edit_message_text(f"🧠 <b>Analyzing folder</b> <code>{html.escape(folder_path or 'root')}</code> with AI...", parse_mode=ParseMode.HTML)
    
    try:
        def get_all_files(repo, path, branch, limit=40):
            files = []
            try:
                contents = repo.get_contents(path, ref=branch)
                for content in contents:
                    if len(files) >= limit: break
                    if content.type == "dir":
                        files.extend(get_all_files(repo, content.path, branch, limit - len(files)))
                    else:
                        if not any(content.name.lower().endswith(ext) for ext in ['.jpg', '.png', '.jpeg', '.gif', '.zip', '.tar', '.gz', '.mp4', '.mp3', '.pdf', '.exe', '.dll', '.so', '.pyc']):
                            files.append(content)
            except: pass
            return files
            
        files_to_analyze = get_all_files(repo, folder_path, branch=def_branch)
        
        file_contents_list = []
        for f in files_to_analyze:
            try:
                file_obj = repo.get_contents(f.path, ref=def_branch)
                decoded = file_obj.decoded_content.decode('utf-8')
                file_contents_list.append(f"--- FILE: {f.path} ---\n{decoded}")
            except Exception:
                pass
                
        all_code = "\n\n".join(file_contents_list)
        
        prompt = (
            f"You are a Senior Code Reviewer and Expert Software Engineer explaining to a developer on Telegram.\n"
            f"Analyze the entire codebase of the folder '{folder_path}' to detect and fix errors.\n\n"
            f"Repository Files & Code:\n{all_code}\n\n"
            "TASK: Provide a comprehensive and highly accurate deep technical analysis. You MUST include:\n"
            "1. 🚀 What this specific repository/folder ACTUALLY does, its core focus, and its goal.\n"
            "2. 🐛 <b>Bug Detection & Fixes</b>: Explicitly detect critical errors, bugs, or bad practices across all files. Provide exact fixes and corrected code snippets.\n"
            "3. 🏗 <b>Architecture Analysis</b>: Evaluate the design pattern and structure.\n"
            "4. 🏅 <b>Code Review & Judgment</b>: Give your honest opinion on how impressive or garbage the project looks, and how useful it is.\n\n"
            "STRICT FORMATTING: You are answering on Telegram. Use ONLY valid Telegram HTML tags (<b>, <i>, <code>, <pre>, <u>, <s>). Do NOT use markdown like ** or `. Do NOT generate full HTML web pages or DOCTYPEs."
        )
        
        response = await llm_client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        
        analysis = response.choices[0].message.content
        formatted_analysis = f"{BANNER}🧠 <b>Folder Analysis:</b> <code>{html.escape(folder_path or 'root')}</code>\n\n{clean_ai_html(analysis)}"
        
        if len(formatted_analysis) > 4000:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_analysis, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(formatted_analysis, parse_mode=ParseMode.HTML)
            
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error analyzing folder: {e}")
        await query.edit_message_text(f"❌ <b>Analysis Failed:</b>\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        return SELECTING_ACTION

async def initiate_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    repo_name = context.user_data.get('repo_name')
    g = get_github_client(context)
    if not g: return ConversationHandler.END
    repo = g.get_user().get_repo(repo_name)
    def_branch = get_repo_default_branch(repo)
    
    await query.edit_message_text(
        f"{BANNER}"
        f"📤 <b>Send the file</b> you want to upload to the <code>{html.escape(def_branch)}</code> branch.",
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
        if not g: return ConversationHandler.END
        repo = g.get_user().get_repo(repo_name)
        def_branch = get_repo_default_branch(repo)
        
        try:
            contents = repo.get_contents(file_name, ref=def_branch)
            repo.update_file(contents.path, f"Update {file_name} via Bot", bytes(file_bytes), contents.sha, branch=def_branch)
            await status_msg.edit_text(f"✅ <b>Updated:</b> <code>{html.escape(file_name)}</code>", parse_mode=ParseMode.HTML)
        except:
            repo.create_file(file_name, f"Upload {file_name} via Bot", bytes(file_bytes), branch=def_branch)
            await status_msg.edit_text(f"✅ <b>Uploaded:</b> <code>{html.escape(file_name)}</code>", parse_mode=ParseMode.HTML)
            
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        await update.message.reply_html(f"❌ <b>Upload Failed:</b>\n{html.escape(str(e))}")
        return SELECTING_ACTION

async def create_pr_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    body = update.message.text.strip()
    repo_name = context.user_data.get('repo_name')
    head = context.user_data.get('pr_head')
    base = context.user_data.get('pr_base')
    title = context.user_data.get('pr_title')

    status_msg = await update.message.reply_html(f"🔄 <b>Creating PR:</b> <code>{html.escape(title)}</code>...")

    try:
        g = get_github_client(context)
        if not g: return ConversationHandler.END
        repo = g.get_user().get_repo(repo_name)
        
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        await status_msg.edit_text(f"✅ <b>PR Created:</b> <a href='{pr.html_url}'>#{pr.number}</a>", parse_mode=ParseMode.HTML)
        return await show_action_menu(update, context)
    except Exception as e:
        logger.error(f"PR creation error: {e}")
        await update.message.reply_html(f"❌ <b>PR Failed:</b>\n{html.escape(str(e))}")
        return SELECTING_ACTION

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await show_action_menu(update, context)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_html("👋 <b>Logged Out.</b> Your session has been cleared.")
    return ConversationHandler.END

# --- Repo Management Functions ---
async def create_repo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"{BANNER}➕ <b>Create New Repository</b>\n\n"
        "Please send the <b>name</b> for your new repository:\n"
        "<i>(e.g., my-awesome-project)</i>",
        parse_mode=ParseMode.HTML
    )
    return CREATING_REPO_NAME

async def create_repo_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    repo_name = update.message.text.strip()
    context.user_data['new_repo_name'] = repo_name
    
    keyboard = [
        [InlineKeyboardButton("🌍 Public", callback_data="public"), InlineKeyboardButton("🔒 Private", callback_data="private")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        f"{BANNER}Visibility for <b>{html.escape(repo_name)}</b>:",
        reply_markup=reply_markup
    )
    return CREATING_REPO_PRIVATE

async def create_repo_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    is_private = query.data == "private"
    repo_name = context.user_data.get('new_repo_name')
    g = get_github_client(context)
    
    try:
        user = g.get_user()
        user.create_repo(repo_name, private=is_private)
        await query.edit_message_text(f"✅ <b>Success!</b> Repository <code>{html.escape(repo_name)}</code> has been created.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.edit_message_text(f"❌ <b>Error:</b> Could not create repository.\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
    
    return await list_repos(update, context)

async def list_contents_delete_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    repo_name = context.user_data['repo_name']
    
    keyboard = [
        [InlineKeyboardButton("⚠️ YES, DELETE IT", callback_data="confirm_delete_repo")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_delete_repo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{BANNER}⚠️ <b>DANGER ZONE</b> ⚠️\n\n"
        f"Are you absolutely sure you want to <b>permanently delete</b> the repository <code>{html.escape(repo_name)}</code>?\n\n"
        "<i>This action cannot be undone.</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    return CONFIRMING_DELETE_REPO

async def delete_repo_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_delete_repo":
        return await show_action_menu(update, context)
        
    repo_name = context.user_data['repo_name']
    g = get_github_client(context)
    
    try:
        user = g.get_user()
        repo = user.get_repo(repo_name)
        repo.delete()
        await query.edit_message_text(f"✅ <b>Deleted.</b> Repository <code>{html.escape(repo_name)}</code> has been permanently removed.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.edit_message_text(f"❌ <b>Error:</b> Could not delete repository. (You may need the 'delete_repo' scope in your token).\n<code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)
        
    return await list_repos(update, context)

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
            SELECTING_REPO: [
                CallbackQueryHandler(repo_choice, pattern="^repo:"),
                CallbackQueryHandler(create_repo_start, pattern="^create_repo_start$")
            ],
            SELECTING_ACTION: [
                CallbackQueryHandler(initiate_prompt, pattern="^initiate$"),
                CallbackQueryHandler(download_menu_prompt, pattern="^download_menu$"),
                CallbackQueryHandler(list_contents_delete_repo, pattern="^list_contents_delete_repo$"),
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
                CallbackQueryHandler(summarize_file_callback, pattern="^summarize_file:"),
                CallbackQueryHandler(summarize_folder_callback, pattern="^summarize_folder:"),
                CallbackQueryHandler(fix_error_callback, pattern="^fix_error:"),
                CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
            ],
            CREATING_PR_HEAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_head)],
            CREATING_PR_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_base)],
            CREATING_PR_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_title)],
            CREATING_PR_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pr_submit)],
            CREATING_REPO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_repo_name)],
            CREATING_REPO_PRIVATE: [CallbackQueryHandler(create_repo_private, pattern="^(public|private)$")],
            CONFIRMING_DELETE_REPO: [CallbackQueryHandler(delete_repo_execute, pattern="^(confirm_delete_repo|cancel_delete_repo)$")]
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

