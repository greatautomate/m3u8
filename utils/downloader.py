"""
M3U8 downloader module for handling playlist downloads.
"""

import os
import tempfile
import shutil
import logging
import asyncio
from typing import List, Callable, Optional
import aiohttp
import aiofiles
import m3u8
from pathlib import Path

from config.settings import Config

logger = logging.getLogger(__name__)


class M3U8Downloader:
    """Handles M3U8 playlist downloading and segment management."""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.temp_dir: Optional[str] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.temp_dir = tempfile.mkdtemp()
        timeout = aiohttp.ClientTimeout(total=Config.DOWNLOAD_TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    async def download_m3u8(
        self, 
        url: str, 
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[str]:
        """
        Download M3U8 playlist and all segments.

        Args:
            url: M3U8 playlist URL
            progress_callback: Optional callback for progress updates

        Returns:
            List of downloaded segment file paths

        Raises:
            ValueError: If no segments found in playlist
            Exception: For download errors
        """
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
                filepath = os.path.join(self.temp_dir, filename)

                await self._download_segment(segment_url, filepath)
                downloaded_segments.append(filepath)

                if progress_callback:
                    progress = (i + 1) / total_segments * 100
                    await progress_callback(f"Downloaded segment {i+1}/{total_segments} ({progress:.1f}%)")

            logger.info(f"Successfully downloaded {len(downloaded_segments)} segments")
            return downloaded_segments

        except Exception as e:
            logger.error(f"Error downloading M3U8: {e}")
            raise

    async def _download_segment(self, url: str, filepath: str) -> None:
        """
        Download a single segment.

        Args:
            url: Segment URL
            filepath: Local file path to save segment

        Raises:
            Exception: For download errors
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                timeout = aiohttp.ClientTimeout(total=Config.SEGMENT_TIMEOUT)
                async with self.session.get(url, timeout=timeout) as response:
                    response.raise_for_status()
                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                            await f.write(chunk)
                return  # Success, exit retry loop

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Failed to download segment {url} after {max_retries} retries: {e}")
                    raise
                else:
                    logger.warning(f"Retry {retry_count}/{max_retries} for segment {url}: {e}")
                    await asyncio.sleep(1)  # Wait before retry
