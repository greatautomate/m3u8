import os
import asyncio
import logging
from pathlib import Path
from hydrogram import Client, filters
from hydrogram.types import Message
from dotenv import load_dotenv

from config.settings import Config
from utils.downloader import M3U8Downloader
from utils.video_processor import VideoProcessor
from utils.helpers import parse_url_and_filename, update_progress, format_file_size

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize the bot
app = Client(
    "m3u8_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    welcome_text = """
🎥 **M3U8 Video Downloader Bot**

Send me an M3U8 playlist URL and I'll:
• Download all video segments
• Merge them into a single MP4 file
• Upload the result to this chat

**Usage:**
Just send me a valid M3U8 URL:
`https://example.com/playlist.m3u8`

**Custom File Naming:**
Add a custom filename after a pipe `|` character:
`https://example.com/playlist.m3u8|My Custom Video.mp4`

**Features:**
✅ Works in private chats, groups, and channels
✅ Progress updates during processing
✅ Automatic file splitting for large videos (>2GB)
✅ Custom file naming support
✅ Error handling and user-friendly messages

**Commands:**
/start - Show this help message
/help - Show this help message

Made with ❤️ using Hydrogram
    """
    await message.reply_text(welcome_text)


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    await start_command(client, message)


@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_url(client: Client, message: Message):
    """Handle M3U8 URL messages"""
    text = message.text.strip()

    # Parse URL and filename
    url, custom_filename = parse_url_and_filename(text)

    # Validate URL
    if not url.startswith(('http://', 'https://')):
        await message.reply_text("❌ Please send a valid HTTP/HTTPS URL")
        return

    if not url.endswith('.m3u8') and 'm3u8' not in url:
        await message.reply_text("❌ Please send a valid M3U8 playlist URL")
        return

    # Start processing
    status_message = await message.reply_text(
        f"🔄 Starting download process...\n📝 File will be named: `{custom_filename}`"
    )

    try:
        # Initialize processors
        downloader = M3U8Downloader()
        video_processor = VideoProcessor()

        async with downloader:
            # Download segments
            segments = await downloader.download_m3u8(
                url, 
                lambda msg: update_progress(status_message, f"📥 {msg}\n📝 File: `{custom_filename}`")
            )

            # Merge segments
            output_path = await video_processor.merge_segments(
                segments, 
                custom_filename,
                lambda msg: update_progress(status_message, f"🔧 {msg}\n📝 File: `{custom_filename}`")
            )

            # Check file size and handle upload
            file_size = os.path.getsize(output_path)
            size_str = format_file_size(file_size)

            await update_progress(
                status_message, 
                f"📤 Preparing upload...\n📝 File: `{custom_filename}`\n📊 Size: {size_str}"
            )

            if file_size > Config.MAX_FILE_SIZE:
                # Split and upload parts
                await update_progress(
                    status_message, 
                    f"📤 File too large ({size_str}), splitting into parts...\n📝 File: `{custom_filename}`"
                )

                parts = await video_processor.split_large_file(output_path, custom_filename)

                for i, part in enumerate(parts):
                    part_name = os.path.basename(part)
                    await update_progress(
                        status_message, 
                        f"📤 Uploading part {i+1}/{len(parts)}...\n📝 File: `{part_name}`"
                    )
                    await client.send_document(
                        message.chat.id,
                        part,
                        caption=f"Part {i+1}/{len(parts)} - {custom_filename}"
                    )
            else:
                # Upload single file
                await update_progress(
                    status_message, 
                    f"📤 Uploading video...\n📝 File: `{custom_filename}`\n📊 Size: {size_str}"
                )
                await client.send_document(
                    message.chat.id,
                    output_path,
                    caption=f"✅ Downloaded and merged: {custom_filename}"
                )

            await status_message.delete()
            await message.reply_text(f"✅ Video processing completed successfully!\n🎥 File: `{custom_filename}`")

    except Exception as e:
        error_msg = f"❌ Error processing video: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await update_progress(status_message, error_msg)


async def main():
    """Main function to run the bot"""
    try:
        # Start the Telegram bot
        await app.start()
        logger.info("M3U8 Bot started successfully!")

        # Keep the bot running
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
