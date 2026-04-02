"""
Video Editing Tools Module
Provides trim, clip, and highlight extraction using ffmpeg
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
import shutil
import re

logger = logging.getLogger(__name__)


class VideoTools:
    """Video editing tools for trimming, clipping, and creating highlights"""

    def __init__(self, output_dir: str = "./storage/clips", storage_root: str = "./storage/videos"):
        """
        Initialize video tools

        Args:
            output_dir: Directory to save output clips
            storage_root: Root directory where processed videos are stored
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage_root = Path(storage_root)

    def _resolve_video_path(self, video_path: str) -> str:
        """
        Attempt to resolve a video path, filename, or video_id to a real file on disk.
        """
        path_obj = Path(video_path)
        
        # 1. Try as-is
        if path_obj.exists() and path_obj.is_file():
            return str(path_obj.resolve())

        # 2. Check if it's just a video_id (e.g. youtube_FX3x-k7vM7Y)
        # Processed videos are in storage/videos/video_id/video.mp4 or similar
        potential_dir = self.storage_root / video_path
        if potential_dir.exists() and potential_dir.is_dir():
            # Strategy A: Check for file named 'video' (no extension)
            base_video = potential_dir / "video"
            if base_video.exists() and base_video.is_file():
                return str(base_video.resolve())

            # Strategy B: Check common extensions
            for ext in ['.mp4', '.mkv', '.avi', '.webm']:
                v_file = potential_dir / f"video{ext}"
                if v_file.exists():
                    return str(v_file.resolve())
                
                # Strategy C: Any video file in that dir
                for f in potential_dir.glob(f"*{ext}"):
                    if f.is_file():
                        return str(f.resolve())

        # 3. Check if it's a filename in any subdirectory of storage_root
        if self.storage_root.exists():
            for f in self.storage_root.rglob(video_path):
                if f.is_file():
                    return str(f.resolve())

        # 4. Extract video_id from filename (if it looks like youtube_ID.mp4)
        match = re.search(r'(youtube_[A-Za-z0-9_-]{11})', video_path)
        if match:
            return self._resolve_video_path(match.group(1))

        return video_path # Return as-is if nothing found (will fail later with clear error)

    def trim_video(
        self,
        video_path: str,
        start_seconds: float,
        end_seconds: float,
        output_name: str = None
    ) -> str:
        """
        Trim a video to a specific time range
        """
        try:
            # Resolve the path (could be a video_id or partial path)
            resolved_path = self._resolve_video_path(video_path)
            logger.info(f"Resolved video path: '{video_path}' -> '{resolved_path}'")
            
            video_path = str(Path(resolved_path).resolve())
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video not found: {video_path}")

            duration = end_seconds - start_seconds
            if duration <= 0:
                raise ValueError("End time must be greater than start time")

            # Generate output path
            if not output_name:
                stem = Path(video_path).stem
                output_name = f"{stem}_trim_{int(start_seconds)}s_to_{int(end_seconds)}s.mp4"

            output_path = str((self.output_dir / output_name).resolve())

            # Build ffmpeg command
            cmd = [
                'ffmpeg',
                '-ss', str(start_seconds),
                '-i', video_path,
                '-t', str(duration),
                '-c', 'copy',       # Stream copy (fast, no re-encoding)
                '-avoid_negative_ts', 'make_zero',
                '-y',               # Overwrite
                output_path
            ]

            logger.info(f"Running FFmpeg trim: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                # Retry with re-encoding if stream copy fails
                logger.warning(f"Stream copy failed (code {result.returncode}), retrying with re-encoding...")
                cmd = [
                    'ffmpeg',
                    '-ss', str(start_seconds),
                    '-i', video_path,
                    '-t', str(duration),
                    '-c:v', 'libx264', '-c:a', 'aac',
                    '-y',
                    output_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise Exception(f"FFmpeg trim failed (code {result.returncode}): {result.stderr}")

            logger.info(f"Trimmed video saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error trimming video: {e}")
            raise

    def create_highlight_clip(
        self,
        video_path: str,
        segments: List[Dict],
        output_name: str = None
    ) -> str:
        """
        Create a highlight reel from multiple video segments
        """
        try:
            # Resolve the path (could be a video_id or partial path)
            resolved_path = self._resolve_video_path(video_path)
            logger.info(f"Resolved video path: '{video_path}' -> '{resolved_path}'")
            
            video_path = str(Path(resolved_path).resolve())
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video not found: {video_path}")

            if not segments:
                raise ValueError("No segments provided for highlight clip")

            # Sort segments by start time
            segments = sorted(segments, key=lambda s: s['start_seconds'])

            # Create temp directory for segment clips
            temp_dir = self.output_dir / "_temp_highlights"
            temp_dir.mkdir(parents=True, exist_ok=True)

            segment_files = []
            try:
                # Step 1: Extract each segment
                for i, seg in enumerate(segments):
                    start = seg['start_seconds']
                    end = seg['end_seconds']
                    duration = end - start

                    if duration <= 0:
                        logger.warning(f"Skipping invalid segment {i}: {start}s to {end}s")
                        continue

                    seg_path = str((temp_dir / f"seg_{i:03d}.mp4").resolve())
                    cmd = [
                        'ffmpeg',
                        '-ss', str(start),
                        '-i', video_path,
                        '-t', str(duration),
                        '-c:v', 'libx264', '-c:a', 'aac',
                        '-y',
                        seg_path
                    ]

                    logger.debug(f"Extracting segment {i}: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        logger.warning(f"Failed to extract segment {i}: {result.stderr}")
                        continue

                    segment_files.append(seg_path)

                if not segment_files:
                    raise Exception("No segments were successfully extracted")

                # Step 2: Create concat file
                concat_file = str((temp_dir / "concat_list.txt").resolve())
                with open(concat_file, 'w') as f:
                    for seg_file in segment_files:
                        f.write(f"file '{seg_file}'\n")

                # Step 3: Concatenate segments
                if not output_name:
                    stem = Path(video_path).stem
                    output_name = f"{stem}_highlights.mp4"
                else:
                    # Ensure .mp4 extension is present
                    if not output_name.lower().endswith('.mp4'):
                        output_name = f"{output_name}.mp4"

                output_path = str((self.output_dir / output_name).resolve())

                cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',
                    '-y',
                    output_path
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise Exception(f"FFmpeg concat failed: {result.stderr}")

                logger.info(f"Highlight clip saved to: {output_path}")
                return output_path

            finally:
                # Clean up temp files
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug("Cleaned up temp highlight files")

        except Exception as e:
            logger.error(f"Error creating highlight clip: {e}")
            raise

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Format seconds as HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
