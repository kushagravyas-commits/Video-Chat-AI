"""
Video Chunker Module — Keyframe Extraction for Visual Search
Extracts keyframes from video at regular intervals using ffmpeg.
Used by the visual embedding pipeline (NVIDIA Nemotron VL).
"""

import os
import subprocess
import logging
import json
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class VideoChunker:
    """Extract keyframes from video for visual embedding."""

    def __init__(self, chunk_duration: int = 30, output_dir: str = "./storage/visual_chunks"):
        """
        Args:
            chunk_duration: Seconds per chunk (1 keyframe extracted per chunk)
            output_dir: Directory to store extracted keyframe images
        """
        self.chunk_duration = chunk_duration
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def extract_keyframes(self, video_path: str, video_id: str) -> List[Dict]:
        """
        Extract 1 JPEG keyframe per chunk from the video.

        Args:
            video_path: Path to the video file
            video_id: Video identifier (for naming frames)

        Returns:
            List of dicts: [{chunk_index, start_time, end_time, frame_path}]
        """
        # Resolve video path
        video_path = self._resolve_video_path(video_path, video_id)
        if not video_path:
            logger.error(f"Video file not found for {video_id}")
            return []

        # Get video duration
        duration = self._get_duration(video_path)
        if duration <= 0:
            logger.error(f"Could not determine duration for {video_path}")
            return []

        logger.info(f"Extracting keyframes from {video_id}: {duration:.1f}s, "
                     f"chunk={self.chunk_duration}s")

        # Create output directory for this video
        frames_dir = os.path.join(self.output_dir, video_id)
        os.makedirs(frames_dir, exist_ok=True)

        frames = []
        chunk_index = 0
        start_time = 0.0

        while start_time < duration:
            end_time = min(start_time + self.chunk_duration, duration)
            mid_time = (start_time + end_time) / 2

            # Extract keyframe at the middle of the chunk
            frame_path = os.path.join(frames_dir, f"frame_{chunk_index:04d}.jpg")

            if self._extract_frame(video_path, mid_time, frame_path):
                frames.append({
                    'chunk_index': chunk_index,
                    'start_time': start_time,
                    'end_time': end_time,
                    'frame_path': frame_path,
                })
                chunk_index += 1
            else:
                logger.warning(f"Failed to extract frame at {mid_time:.1f}s")

            start_time += self.chunk_duration

        logger.info(f"Extracted {len(frames)} keyframes from {video_id}")
        return frames

    def _extract_frame(self, video_path: str, timestamp: float, output_path: str) -> bool:
        """Extract a single frame at the given timestamp as JPEG."""
        try:
            cmd = [
                'ffmpeg', '-ss', str(timestamp),
                '-i', video_path,
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                output_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.error(f"Frame extraction failed at {timestamp}s: {e}")
            return False

    def _get_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe."""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                video_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 0))
        except Exception as e:
            logger.error(f"ffprobe failed for {video_path}: {e}")
            return 0.0

    def _resolve_video_path(self, video_path: str, video_id: str) -> Optional[str]:
        """Resolve the actual video file path, trying multiple locations and extensions."""
        # Try the given path first
        if video_path and os.path.isfile(video_path):
            return video_path

        # Try common locations
        base_dir = Path("./storage/videos") / video_id
        if base_dir.exists():
            for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
                candidate = base_dir / f"video{ext}" if ext else base_dir / "video"
                if candidate.exists():
                    return str(candidate)

            # Try any video file in the directory
            for f in base_dir.iterdir():
                if f.is_file() and f.suffix.lower() in ('.mp4', '.mkv', '.avi', '.webm'):
                    return str(f)
                if f.is_file() and f.suffix == '' and f.stat().st_size > 1_000_000:
                    return str(f)

        logger.warning(f"Could not resolve video path for {video_id}")
        return None

    def cleanup(self, video_id: str):
        """Delete extracted keyframes after embedding to save disk space."""
        frames_dir = os.path.join(self.output_dir, video_id)
        if os.path.exists(frames_dir):
            import shutil
            shutil.rmtree(frames_dir)
            logger.info(f"Cleaned up keyframes for {video_id}")

    def is_still_frame(self, frame_paths: List[str], threshold: float = 0.95) -> bool:
        """
        Detect if frames are nearly identical (still/idle footage).
        Compares JPEG file sizes — if min/max ratio >= threshold, frames are identical.
        """
        if len(frame_paths) < 2:
            return False

        sizes = []
        for path in frame_paths:
            if os.path.exists(path):
                sizes.append(os.path.getsize(path))

        if len(sizes) < 2:
            return False

        ratio = min(sizes) / max(sizes) if max(sizes) > 0 else 0
        return ratio >= threshold
