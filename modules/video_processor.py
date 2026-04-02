"""
Video Download & Audio Extraction Module
Handles both YouTube URLs and uploaded video files
"""

import os
import sys
import yt_dlp
import subprocess
from pathlib import Path
from typing import Dict, Tuple
import logging
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, storage_dir: str = "./storage"):
        """
        Initialize video processor

        Args:
            storage_dir: Directory to store downloaded videos and audio
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir = self.storage_dir / "videos"
        self.audio_dir = self.storage_dir / "audio"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def download_youtube(self, youtube_url: str) -> Tuple[str, Dict]:
        """
        Download YouTube video

        Args:
            youtube_url: YouTube video URL

        Returns:
            Tuple of (video_file_path, metadata)
        """
        try:
            logger.info(f"Downloading YouTube video: {youtube_url}")

            # Extract video ID
            ydl = yt_dlp.YoutubeDL({'quiet': True})
            info = ydl.extract_info(youtube_url, download=False)
            video_id = info.get('id')

            # Check if already downloaded
            video_path = self.video_dir / f"youtube_{video_id}" / "video.mp4"
            if video_path.exists():
                logger.info(f"Video already exists: {video_path}")
                return str(video_path), self._get_metadata(info)

            # Setup download options
            output_dir = self.video_dir / f"youtube_{video_id}"
            output_dir.mkdir(parents=True, exist_ok=True)

            ydl_opts = {
                'format': 'best[ext=mp4]/best',  # Best MP4 quality
                'outtmpl': str(output_dir / 'video'),  # Will create video.mp4
                'quiet': False,
                'no_warnings': False,
            }

            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)

            # Find the actual downloaded file (it might not have .mp4 extension)
            video_files = list(output_dir.glob("video*"))
            if not video_files:
                raise Exception(f"No video file found in {output_dir}")

            video_path = video_files[0]
            logger.info(f"Downloaded YouTube video to: {video_path}")

            return str(video_path), self._get_metadata(info)

        except Exception as e:
            logger.error(f"Error downloading YouTube video: {str(e)}")
            raise

    def process_uploaded_video(self, video_file_path: str, user_id: str) -> Tuple[str, Dict]:
        """
        Process uploaded video file

        Args:
            video_file_path: Path to uploaded video
            user_id: User ID for organization

        Returns:
            Tuple of (video_file_path, metadata)
        """
        try:
            logger.info(f"Processing uploaded video: {video_file_path}")

            video_path = Path(video_file_path)

            # Generate file hash for deduplication
            file_hash = self._generate_file_hash(video_file_path)

            # Check if duplicate exists
            user_videos_dir = self.video_dir / f"uploaded_{user_id}"
            user_videos_dir.mkdir(parents=True, exist_ok=True)

            # Store in user directory
            final_path = user_videos_dir / video_path.name

            # Copy video to storage
            import shutil
            if not final_path.exists():
                shutil.copy2(video_file_path, final_path)
                logger.info(f"Stored video at: {final_path}")

            # Get video metadata
            metadata = self._get_video_metadata(str(final_path))
            metadata['file_hash'] = file_hash

            return str(final_path), metadata

        except Exception as e:
            logger.error(f"Error processing uploaded video: {str(e)}")
            raise

    def extract_audio(self, video_path: str) -> str:
        """
        Extract audio from video file

        Args:
            video_path: Path to video file

        Returns:
            Path to extracted audio file (MP3)
        """
        try:
            logger.info(f"Extracting audio from: {video_path}")

            video_path_obj = Path(video_path)
            video_name = video_path_obj.stem
            
            # If the video is named just "video" (default for youtube downloads), use the parent folder name
            if video_name.startswith('video') and video_path_obj.parent.name:
                video_name = f"{video_path_obj.parent.name}_audio"
            
            audio_output = self.audio_dir / f"{video_name}.mp3"

            # Check if audio already extracted
            if audio_output.exists():
                logger.info(f"Audio already exists: {audio_output}")
                return str(audio_output)

            # Ensure output directory exists
            self.audio_dir.mkdir(parents=True, exist_ok=True)

            # Convert paths to absolute paths for FFmpeg
            video_path_abs = str(Path(video_path).resolve())
            audio_output_abs = str(audio_output.resolve())

            # Extract audio using ffmpeg via subprocess
            # Command: ffmpeg -i input.mp4 -acodec libmp3lame -ab 192k -ar 16000 output.mp3
            cmd = [
                'ffmpeg',
                '-i', video_path_abs,           # Input file (absolute path)
                '-acodec', 'libmp3lame',        # Audio codec
                '-ab', '192k',                  # Audio bitrate
                '-ar', '16000',                 # Sample rate (16kHz for speech recognition)
                '-y',                           # Overwrite output file
                audio_output_abs                # Output file (absolute path)
            ]

            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")

            # Run ffmpeg with timeout for large files (1 hour)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=3600  # 1 hour timeout for large video files
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "Unknown FFmpeg error"
                logger.error(f"FFmpeg error: {error_msg}")
                if result.stdout:
                    logger.error(f"FFmpeg stdout: {result.stdout[:500]}")
                raise Exception(f"FFmpeg failed: {error_msg}")

            if not audio_output.exists():
                raise Exception(f"Audio file was not created at {audio_output}")

            # Verify extracted audio file size is reasonable
            audio_size_bytes = audio_output.stat().st_size
            audio_size_mb = audio_size_bytes / (1024 * 1024)

            # Rough estimate: 192kbps = 24KB/second, so multiply by video duration
            # We'll warn if file is suspiciously small (less than 1MB for videos > 1 min)
            if audio_size_mb < 1.0:
                logger.warning(f"Audio file is very small: {audio_size_mb:.2f} MB")
                logger.warning(f"Audio extraction might be incomplete!")

            logger.info(f"Audio extracted to: {audio_output_abs} ({audio_size_mb:.1f} MB)")
            return str(audio_output)

        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise

    def _generate_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """
        Generate SHA256 hash of file for deduplication

        Args:
            file_path: Path to file
            chunk_size: Size of chunks to read

        Returns:
            SHA256 hash string
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def _get_metadata(self, info: Dict) -> Dict:
        """
        Extract metadata from YouTube info
        """
        return {
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'upload_date': info.get('upload_date', ''),
            'channel': info.get('uploader', ''),
            'description': info.get('description', ''),
            'thumbnail': info.get('thumbnail', ''),
            'view_count': info.get('view_count', 0),
        }

    def _get_video_metadata(self, video_path: str) -> Dict:
        """
        Get metadata from video file using ffprobe
        """
        try:
            probe = ffmpeg.probe(video_path)
            video_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                None
            )

            duration = float(probe['format'].get('duration', 0))

            return {
                'title': Path(video_path).stem,
                'duration': duration,
                'width': video_stream.get('width') if video_stream else 0,
                'height': video_stream.get('height') if video_stream else 0,
                'format': probe['format'].get('format_name', 'unknown'),
            }
        except Exception as e:
            logger.warning(f"Could not get video metadata: {str(e)}")
            return {'title': Path(video_path).stem, 'duration': 0}
