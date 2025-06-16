import os
import asyncio
import logging
import tempfile
import shutil
from pathlib import Path
from hydrogram import Client, filters
from hydrogram.types import Message
from dotenv import load_dotenv
import aiohttp
import aiofiles
import m3u8
import subprocess
import math
import re
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
CHUNK_SIZE = 1024 * 1024  # 1MB

# Initialize the bot
app = Client(
    "m3u8_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def parse_url_and_filename(text: str):
    """Parse URL and custom filename from user input"""
    if '|' in text:
        url, filename = text.split('|', 1)
        url = url.strip()
        filename = filename.strip()

        # Clean filename - remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

        # Ensure .mp4 extension
        if not filename.lower().endswith('.mp4'):
            filename += '.mp4'

        return url, filename
    else:
        # Generate filename from timestamp if no custom name provided
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return text.strip(), f"video_{timestamp}.mp4"

async def update_progress(message: Message, text: str):
    """Update progress message"""
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.warning(f"Failed to update progress: {e}")

async def download_m3u8_segments(url: str, temp_dir: str, session: aiohttp.ClientSession, progress_callback=None):
    """Download M3U8 playlist and all segments"""
    try:
        # Parse M3U8 playlist
        playlist = m3u8.load(url)
        if not playlist.segments:
            raise ValueError("No segments found in M3U8 playlist")

        total_segments = len(playlist.segments)
        downloaded_segments = []

        logger.info(f"Found {total_segments} segments to download")

        for i, segment in enumerate(playlist.segments):
            segment_url = segment.absolute_uri
            filename = f"segment_{i:04d}.ts"
            filepath = os.path.join(temp_dir, filename)

            # Download segment
            async with session.get(segment_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        await f.write(chunk)

            downloaded_segments.append(filepath)

            if progress_callback:
                progress = (i + 1) / total_segments * 100
                await progress_callback(f"Downloaded segment {i+1}/{total_segments} ({progress:.1f}%)")

        return downloaded_segments

    except Exception as e:
        logger.error(f"Error downloading M3U8: {e}")
        raise

async def merge_segments(segments: list, output_path: str, progress_callback=None):
    """Merge segments into MP4 using ffmpeg"""
    try:
        if progress_callback:
            await progress_callback("Preparing to merge segments...")

        # Create input file list for ffmpeg
        temp_dir = os.path.dirname(output_path)
        input_list_path = os.path.join(temp_dir, "input_list.txt")

        with open(input_list_path, 'w') as f:
            for segment in segments:
                f.write(f"file '{os.path.abspath(segment)}'\n")

        # FFmpeg command to merge segments
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', input_list_path,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',
            output_path
        ]

        if progress_callback:
            await progress_callback("Merging segments with ffmpeg...")

        # Run ffmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
            logger.error(f"FFmpeg error: {error_msg}")
            raise RuntimeError(f"FFmpeg failed: {error_msg}")

        if progress_callback:
            await progress_callback("Video merging completed!")

        return output_path

    except Exception as e:
        logger.error(f"Error merging segments: {e}")
        raise

async def split_large_file(file_path: str, base_filename: str, max_size: int = MAX_FILE_SIZE):
    """Split large file into smaller parts"""
    file_size = os.path.getsize(file_path)
    if file_size <= max_size:
        return [file_path]

    try:
        parts = []
        part_size = max_size - (10 * 1024 * 1024)  # Leave 10MB buffer
        num_parts = math.ceil(file_size / part_size)

        # Get video duration
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            file_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        try:
            total_duration = float(stdout.decode().strip())
        except:
            total_duration = 3600  # Default 1 hour

        part_duration = total_duration / num_parts
        base_name = os.path.splitext(base_filename)[0]
        temp_dir = os.path.dirname(file_path)

        for i in range(num_parts):
            start_time = i * part_duration
            part_filename = f"{base_name}_part{i+1:02d}.mp4"
            part_path = os.path.join(temp_dir, part_filename)

            cmd = [
                'ffmpeg',
                '-i', file_path,
                '-ss', str(start_time),
                '-t', str(part_duration),
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                part_path
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()
            if process.returncode == 0 and os.path.exists(part_path):
                parts.append(part_path)

        return parts

    except Exception as e:
        logger.error(f"Error splitting file: {e}")
        raise

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    logger.info(f"Received /start command from {message.from_user.id}")
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
    logger.info(f"Received /help command from {message.from_user.id}")
    await start_command(client, message)

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_url(client: Client, message: Message):
    """Handle M3U8 URL messages"""
    logger.info(f"Received message from {message.from_user.id}: {message.text[:50]}...")

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

    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp directory: {temp_dir}")

        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            # Download segments
            segments = await download_m3u8_segments(
                url, 
                temp_dir,
                session,
                lambda msg: update_progress(status_message, f"📥 {msg}\n📝 File: `{custom_filename}`")
            )

            # Merge segments
            output_path = os.path.join(temp_dir, custom_filename)
            await merge_segments(
                segments, 
                output_path,
                lambda msg: update_progress(status_message, f"🔧 {msg}\n📝 File: `{custom_filename}`")
            )

            # Check file size
            file_size = os.path.getsize(output_path)
            size_mb = file_size / (1024 * 1024)

            await update_progress(
                status_message, 
                f"📤 Preparing upload...\n📝 File: `{custom_filename}`\n📊 Size: {size_mb:.1f} MB"
            )

            if file_size > MAX_FILE_SIZE:
                # Split and upload parts
                await update_progress(
                    status_message, 
                    f"📤 File too large ({size_mb:.1f} MB), splitting into parts...\n📝 File: `{custom_filename}`"
                )

                parts = await split_large_file(output_path, custom_filename)

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
                    f"📤 Uploading video...\n📝 File: `{custom_filename}`\n📊 Size: {size_mb:.1f} MB"
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

    finally:
        # Cleanup temp directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temp directory: {e}")

async def main():
    """Main function to run the bot"""
    try:
        logger.info("Starting M3U8 Bot...")

        # Start the bot
        await app.start()
        logger.info("M3U8 Bot started successfully!")
        logger.info("Bot is ready to receive messages...")

        # Keep the bot running
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
    finally:
        await app.stop()
        logger.info("Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
