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
import config
from dotenv import load_dotenv

# Load environment variables from .env if it exists
load_dotenv()

# Priority: 1. Environment Variable, 2. config.py
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or getattr(config, 'TELEGRAM_BOT_TOKEN', "YOUR_BOT_TOKEN_HERE")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
SETTING_TOKEN, SELECTING_REPO, SELECTING_ACTION, LISTING_CONTENTS, SELECTING_DOWNLOAD_TYPE = range(5)

# UI Constant
BANNER = "<b>🚀 GitPushBot | GitHub Manager</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"

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
            "• <b>Seamless UI:</b> Explore folders using interactive menus.\n\n"
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
        "5) <b>Manage Assets:</b> Use the 'Delete' menu to browse and remove files, or use the 'Download' menu to get single files or the entire repo as a ZIP.\n\n"
        "6) <b>Clean Session:</b> Use /logout anytime to wipe your token from the bot's temporary memory."
    )
    keyboard = [[InlineKeyboardButton("🔙 Back to Start", callback_data="back_to_start")]]
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

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
        loading_msg = await update.callback_query.edit_message_text("🔄 <b>Fetching repositories...</b>", parse_mode=ParseMode.HTML)
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
        [InlineKeyboardButton("🗑 Delete File", callback_data="list_contents_delete")],
        [InlineKeyboardButton("🔙 Back to Repos", callback_data="back_to_repos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = f"{BANNER}📍 <b>Repo:</b> <code>{html.escape(repo_name)}</code>\nWhat would you like to do?"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(msg_text, reply_markup=reply_markup)
    return SELECTING_ACTION

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

        for content in contents:
            content_path = html.escape(content.path)
            if content.type == "dir":
                keyboard.append([InlineKeyboardButton(f"📁 {content.name}", callback_data=f"cd:{content.path}")])
            else:
                prefix = "🗑" if action == "delete" else "📥"
                callback_prefix = "delete" if action == "delete" else "download_file"
                keyboard.append([InlineKeyboardButton(f"{prefix} {content.name}", callback_data=f"{callback_prefix}:{content.path}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        display_path = html.escape(path) if path else "Root"
        mode_text = "DELETE" if action == "delete" else "DOWNLOAD"
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
                CallbackQueryHandler(list_repos, pattern="^back_to_repos$"),
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
                CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"),
            ],
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
