"""
Helper functions for the M3U8 Telegram Bot.
"""

import re
import logging
from datetime import datetime
from typing import Tuple
from hydrogram.types import Message

logger = logging.getLogger(__name__)


def parse_url_and_filename(text: str) -> Tuple[str, str]:
    """
    Parse URL and custom filename from user input.

    Args:
        text: Input text containing URL and optional filename

    Returns:
        Tuple of (url, filename)
    """
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


async def update_progress(message: Message, text: str) -> None:
    """
    Update progress message.

    Args:
        message: Telegram message to update
        text: New text content
    """
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.warning(f"Failed to update progress: {e}")


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def clean_filename(filename: str) -> str:
    """
    Clean filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Cleaned filename
    """
    # Remove invalid characters for most filesystems
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', filename)

    # Remove multiple consecutive underscores
    cleaned = re.sub(r'_{2,}', '_', cleaned)

    # Remove leading/trailing underscores and spaces
    cleaned = cleaned.strip('_ ')

    return cleaned if cleaned else "video"
