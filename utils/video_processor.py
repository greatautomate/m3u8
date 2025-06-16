"""
Video processing module for merging and splitting video files.
"""

import os
import subprocess
import asyncio
import tempfile
import math
import logging
from typing import List, Callable, Optional
from pathlib import Path

from config.settings import Config

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles video merging and splitting operations."""

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    def __del__(self):
        """Cleanup temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    async def merge_segments(
        self, 
        segments: List[str], 
        output_filename: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Merge video segments into a single MP4 file.

        Args:
            segments: List of segment file paths
            output_filename: Name for output file
            progress_callback: Optional callback for progress updates

        Returns:
            Path to merged video file

        Raises:
            RuntimeError: If ffmpeg fails
            Exception: For other merge errors
        """
        try:
            if progress_callback:
                await progress_callback("Preparing to merge segments...")

            output_path = os.path.join(self.temp_dir, output_filename)

            # Create input file list for ffmpeg
            input_list_path = os.path.join(self.temp_dir, "input_list.txt")
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
                '-bsf:a', 'aac_adtstoasc',  # Fix AAC issues
                '-y',  # Overwrite output file
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

            logger.info(f"Successfully merged video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error merging segments: {e}")
            raise

    async def split_large_file(
        self, 
        file_path: str, 
        base_filename: str,
        max_size: int = None
    ) -> List[str]:
        """
        Split large video file into smaller parts.

        Args:
            file_path: Path to video file to split
            base_filename: Base name for split parts
            max_size: Maximum size per part (defaults to Config.MAX_FILE_SIZE)

        Returns:
            List of split file paths

        Raises:
            Exception: For splitting errors
        """
        if max_size is None:
            max_size = Config.MAX_FILE_SIZE

        file_size = os.path.getsize(file_path)
        if file_size <= max_size:
            return [file_path]

        try:
            parts = []
            part_size = max_size - (10 * 1024 * 1024)  # Leave 10MB buffer
            num_parts = math.ceil(file_size / part_size)

            # Get video duration first
            duration = await self._get_video_duration(file_path)
            part_duration = duration / num_parts

            base_name = os.path.splitext(base_filename)[0]

            for i in range(num_parts):
                start_time = i * part_duration
                part_filename = f"{base_name}_part{i+1:02d}.mp4"
                part_path = os.path.join(self.temp_dir, part_filename)

                # Use ffmpeg to split the file
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
                    logger.info(f"Created part {i+1}/{num_parts}: {part_filename}")

            return parts

        except Exception as e:
            logger.error(f"Error splitting file: {e}")
            raise

    async def _get_video_duration(self, file_path: str) -> float:
        """
        Get video duration using ffprobe.

        Args:
            file_path: Path to video file

        Returns:
            Duration in seconds
        """
        try:
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

            if process.returncode == 0:
                return float(stdout.decode().strip())
            else:
                logger.warning("Could not get video duration, using default")
                return 3600.0  # Default 1 hour

        except Exception as e:
            logger.warning(f"Error getting video duration: {e}")
            return 3600.0  # Default 1 hour
