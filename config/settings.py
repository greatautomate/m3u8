"""
Configuration settings for the M3U8 Telegram Bot.
"""

import os
from typing import Optional


class Config:
    """Configuration class for bot settings."""

    # Telegram Bot Configuration
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # File Processing Configuration
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "2147483648"))  # 2GB
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1048576"))  # 1MB

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Timeouts (in seconds)
    DOWNLOAD_TIMEOUT: int = int(os.getenv("DOWNLOAD_TIMEOUT", "300"))  # 5 minutes
    SEGMENT_TIMEOUT: int = int(os.getenv("SEGMENT_TIMEOUT", "30"))  # 30 seconds

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration parameters."""
        required_fields = ['API_ID', 'API_HASH', 'BOT_TOKEN']
        missing_fields = []

        for field in required_fields:
            value = getattr(cls, field)
            if not value or (isinstance(value, int) and value == 0):
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")

        return True
