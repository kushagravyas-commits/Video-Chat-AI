"""
Clip Generator Module
Creates short video clips from mention timestamps with configurable grouping
"""

import os
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import json
from openai import OpenAI

logger = logging.getLogger(__name__)


class ClipGenerator:
    """Generate video clips from mention timestamps"""

    def __init__(self, storage_dir: str = "./storage"):
        """
        Initialize clip generator

        Args:
            storage_dir: Directory to store clips
        """
        self.storage_dir = Path(storage_dir)
        self.clips_dir = self.storage_dir / "clips"
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir = self.clips_dir / "metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def create_clips_from_mentions(
        self,
        video_id: str,
        video_path: str,
        mentions: List[Dict],
        clip_duration_before: float = 2.0,
        clip_duration_after: float = 3.0,
        smart_grouping: bool = False,
        grouping_threshold_seconds: float = 7.0,
        expansion_mode: str = "default"
    ) -> Dict:
        """
        Create video clips from mention timestamps

        Args:
            video_id: Video ID for organization
            video_path: Path to the original video file
            mentions: List of mentions with start_time, end_time, text, etc.
            clip_duration_before: Seconds to include before mention starts
            clip_duration_after: Seconds to include after mention ends
            smart_grouping: Whether to group nearby mentions into single clips
            grouping_threshold_seconds: Seconds threshold for grouping mentions
            expansion_mode: 'default' or 'semantic' to expand timestamps to nearest sentence.

        Returns:
            {
                "status": "success",
                "video_id": str,
                "total_mentions": int,
                "clips_created": int,
                "clips": [
                    {
                        "clip_id": str,
                        "filename": str,
                        "start_time": float,
                        "end_time": float,
                        "duration": float,
                        "file_size_mb": float,
                        "mentions_included": int,
                        "mention_texts": [str]
                    }
                ],
                "statistics": {
                    "total_duration_seconds": float,
                    "average_clip_duration": float
                }
            }
        """
        try:
            logger.info(
                f"Creating clips from {len(mentions)} mentions "
                f"(grouping={smart_grouping}, threshold={grouping_threshold_seconds}s, expansion={expansion_mode})"
            )

            # Validate video file exists
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return {
                    "status": "error",
                    "message": f"Video file not found: {video_path}",
                    "video_id": video_id
                }

            # Phase 1: Group mentions if requested
            if smart_grouping and len(mentions) > 1:
                mention_groups = self._group_nearby_mentions(
                    mentions,
                    grouping_threshold_seconds
                )
                logger.info(f"Grouped {len(mentions)} mentions into {len(mention_groups)} groups")
            else:
                mention_groups = [[m] for m in mentions]

            # Phase 2: Create clips from mention groups
            clips = []
            for group_idx, group in enumerate(mention_groups):
                clip_result = self._create_clip_from_group(
                    video_id=video_id,
                    video_path=video_path,
                    mention_group=group,
                    group_index=group_idx,
                    clip_duration_before=clip_duration_before,
                    clip_duration_after=clip_duration_after,
                    expansion_mode=expansion_mode
                )

                if clip_result["status"] == "success":
                    clips.append(clip_result)
                else:
                    logger.warning(f"Failed to create clip for group {group_idx}: {clip_result['message']}")

            # Phase 3: Calculate statistics
            total_duration = sum(c.get("duration", 0) for c in clips)
            avg_duration = total_duration / len(clips) if clips else 0

            logger.info(f"Successfully created {len(clips)} clips from {len(mention_groups)} groups")

            return {
                "status": "success",
                "video_id": video_id,
                "total_mentions": len(mentions),
                "clips_created": len(clips),
                "grouping_applied": smart_grouping,
                "grouping_threshold": grouping_threshold_seconds,
                "clips": clips,
                "statistics": {
                    "total_duration_seconds": round(total_duration, 2),
                    "average_clip_duration": round(avg_duration, 2),
                    "mentions_per_clip": round(len(mentions) / len(clips), 2) if clips else 0
                }
            }

        except Exception as e:
            logger.error(f"Error creating clips: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "video_id": video_id
            }

    def _group_nearby_mentions(
        self,
        mentions: List[Dict],
        threshold_seconds: float
    ) -> List[List[Dict]]:
        """
        Group mentions that are close together in time

        Args:
            mentions: List of mentions (should already be sorted by start_time)
            threshold_seconds: Maximum gap between mentions to group them

        Returns:
            List of mention groups
        """
        if not mentions:
            return []

        # Sort by start_time
        sorted_mentions = sorted(mentions, key=lambda x: x.get("start_time", 0))

        groups = []
        current_group = [sorted_mentions[0]]

        for mention in sorted_mentions[1:]:
            current_end = current_group[-1].get("end_time", current_group[-1].get("start_time", 0))
            next_start = mention.get("start_time", 0)

            # If mention is within threshold of last mention in group, add to group
            if next_start - current_end <= threshold_seconds:
                current_group.append(mention)
            else:
                # Start new group
                groups.append(current_group)
                current_group = [mention]

        # Add last group
        groups.append(current_group)

        logger.info(f"Grouped {len(mentions)} mentions into {len(groups)} groups")
        return groups

    def _create_clip_from_group(
        self,
        video_id: str,
        video_path: str,
        mention_group: List[Dict],
        group_index: int,
        clip_duration_before: float,
        clip_duration_after: float,
        expansion_mode: str = "default"
    ) -> Dict:
        """
        Create a single clip from a group of mentions

        Args:
            video_id: Video ID
            video_path: Path to source video
            mention_group: List of mentions in this group
            group_index: Index of this group
            clip_duration_before: Seconds before first mention
            clip_duration_after: Seconds after last mention
            expansion_mode: 'default' or 'semantic'

        Returns:
            Clip metadata with success/error status
        """
        try:
            # Calculate clip boundaries
            first_mention = mention_group[0]
            last_mention = mention_group[-1]

            clip_start = max(0, first_mention.get("start_time", 0) - clip_duration_before)
            
            # Use max to prevent type errors if end_time is None
            last_start = last_mention.get("start_time", 0)
            last_end = last_mention.get("end_time")
            if last_end is None:
                last_end = last_start
            
            clip_end = last_end + clip_duration_after

            if expansion_mode == "semantic":
                clip_start, clip_end = self._expand_boundaries_semantically(video_id, clip_start, clip_end)
            elif expansion_mode == "ai_director":
                clip_start, clip_end = self._expand_boundaries_with_ai(video_id, clip_start, clip_end)

            # Enforce 20-second minimum duration for social media pacing
            if clip_end - clip_start < 20.0:
                shortfall = 20.0 - (clip_end - clip_start)
                # Distribute shortfall: 30% before, 70% after
                clip_start = max(0.0, clip_start - (shortfall * 0.3))
                clip_end = clip_end + (shortfall * 0.7)
                
                # If hit the start of the video, add the rest to the end
                if clip_start == 0.0:
                    clip_end = 20.0

            clip_duration = clip_end - clip_start

            # Generate clip filename
            clip_id = f"{video_id}_clip_{group_index:03d}"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clip_filename = f"{clip_id}_{timestamp}.mp4"
            clip_path = self.clips_dir / clip_filename

            # Create clip using FFmpeg
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(clip_start),
                "-to", str(clip_end),
                "-c:v", "libx264",  # Video codec
                "-crf", "18",  # Quality (18 is high quality, 28 is default)
                "-c:a", "aac",  # Audio codec
                "-b:a", "192k",  # Audio bitrate
                "-preset", "medium",  # Speed/quality tradeoff
                "-y",  # Overwrite output
                str(clip_path)
            ]

            logger.info(f"Creating clip: {clip_filename} (duration: {clip_duration:.2f}s)")

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per clip
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return {
                    "status": "error",
                    "message": f"FFmpeg error: {result.stderr}",
                    "clip_id": clip_id
                }

            # Check file exists and get size
            if not clip_path.exists():
                logger.error(f"Clip file was not created: {clip_path}")
                return {
                    "status": "error",
                    "message": "Clip file was not created",
                    "clip_id": clip_id
                }

            file_size_bytes = clip_path.stat().st_size
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Extract mention texts
            mention_texts = [m.get("text", "")[:100] for m in mention_group]  # First 100 chars

            clip_metadata = {
                "status": "success",
                "clip_id": clip_id,
                "filename": clip_filename,
                "clip_path": str(clip_path),
                "start_time": round(clip_start, 2),
                "end_time": round(clip_end, 2),
                "duration": round(clip_duration, 2),
                "file_size_mb": round(file_size_mb, 2),
                "mentions_included": len(mention_group),
                "mention_texts": mention_texts,
                "created_at": timestamp
            }

            # Save metadata
            self._save_clip_metadata(clip_id, clip_metadata)

            logger.info(f"Clip created successfully: {clip_filename} ({file_size_mb:.2f}MB)")
            return clip_metadata

        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for clip {group_index}")
            return {
                "status": "error",
                "message": "Clip creation timeout (video too long or system busy)",
                "clip_id": f"{video_id}_clip_{group_index:03d}"
            }
        except Exception as e:
            logger.error(f"Error creating clip: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "clip_id": f"{video_id}_clip_{group_index:03d}"
            }

    def _save_clip_metadata(self, clip_id: str, metadata: Dict):
        """
        Save clip metadata to JSON file

        Args:
            clip_id: Clip ID
            metadata: Metadata dictionary
        """
        try:
            metadata_path = self.metadata_dir / f"{clip_id}_metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Saved metadata for {clip_id}")
        except Exception as e:
            logger.error(f"Error saving metadata: {str(e)}")

    def _expand_boundaries_semantically(self, video_id: str, start_time: float, end_time: float) -> Tuple[float, float]:
        """Expands boundaries to nearest sentence/thought boundaries using the transcript"""
        try:
            # Handle normalized IDs
            base_vid = video_id
            if not base_vid.startswith('youtube_') and not base_vid.startswith('uploaded_'):
                base_vid = f"youtube_{base_vid}"
                
            transcript_path = self.storage_dir / "transcripts" / f"{base_vid}_transcript.json"
            if not transcript_path.exists():
                return start_time, end_time
                
            with open(transcript_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            segments = data.get('segments', [])
            if not segments:
                return start_time, end_time
                
            expanded_start = start_time
            expanded_end = end_time
            
            # Find the segment covering start_time
            start_idx = 0
            for i, seg in enumerate(segments):
                seg_start = seg.get('start_time', 0)
                seg_end = seg.get('end_time', seg_start)
                if seg_start <= start_time <= seg_end:
                    start_idx = i
                    break
                elif seg_start > start_time:
                    start_idx = max(0, i - 1)
                    break
                    
            # Go backwards to find punctuation or a long pause
            for i in range(start_idx, -1, -1):
                text = segments[i].get('text', '').strip()
                expanded_start = segments[i].get('start_time', 0)
                # If this segment ends with punctuation, the next segment is a good start
                if text.endswith(('.', '?', '!', '।', '|')):
                    if i < len(segments) - 1:
                        expanded_start = segments[i+1].get('start_time', 0)
                    break
                    
                # Or if gap between this and previous is > 1.5s
                if i > 0:
                    prev_end = segments[i-1].get('end_time', segments[i-1].get('start_time', 0))
                    if (segments[i].get('start_time', 0) - prev_end) > 1.5:
                        break
            
            # Find the segment covering end_time
            end_idx = len(segments) - 1
            for i, seg in enumerate(segments):
                seg_start = seg.get('start_time', 0)
                seg_end = seg.get('end_time', seg_start)
                if seg_start <= end_time <= seg_end:
                    end_idx = i
                    break
                elif seg_start > end_time:
                    end_idx = i
                    break
                    
            # Go forwards to find punctuation or a long pause
            for i in range(end_idx, len(segments)):
                text = segments[i].get('text', '').strip()
                expanded_end = segments[i].get('end_time', segments[i].get('start_time', 0))
                if text.endswith(('.', '?', '!', '।', '|')):
                    break
                if i < len(segments) - 1:
                    next_start = segments[i+1].get('start_time', expanded_end)
                    if (next_start - expanded_end) > 1.5:
                        break
                    
            return min(start_time, expanded_start), max(end_time, expanded_end)
            
        except Exception as e:
            logger.error(f"Semantic expansion failed: {e}")
            return start_time, end_time

    def _expand_boundaries_with_ai(self, video_id: str, start_time: float, end_time: float) -> Tuple[float, float]:
        """Uses an LLM to find the most engaging hook and logical conclusion around a mention"""
        try:
            # Handle normalized IDs
            base_vid = video_id
            if not base_vid.startswith('youtube_') and not base_vid.startswith('uploaded_'):
                base_vid = f"youtube_{base_vid}"
                
            transcript_path = self.storage_dir / "transcripts" / f"{base_vid}_transcript.json"
            if not transcript_path.exists():
                logger.warning("Transcript not found for AI director, falling back to semantic.")
                return self._expand_boundaries_semantically(video_id, start_time, end_time)
                
            with open(transcript_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            segments = data.get('segments', [])
            if not segments:
                return start_time, end_time
                
            # Get ~60 seconds of context before start and after end
            context_start = max(0, start_time - 60)
            context_end = end_time + 60
            
            context_text = []
            for seg in segments:
                seg_start = seg.get('start_time', 0)
                seg_end = seg.get('end_time', seg_start)
                if seg_start >= context_start and seg_end <= context_end:
                    context_text.append(f"[{seg_start:.2f}s - {seg_end:.2f}s] {seg.get('text', '').strip()}")
                    
            if not context_text:
                return self._expand_boundaries_semantically(video_id, start_time, end_time)

            formatted_context = "\\n".join(context_text)
            
            prompt = f"""You are a professional social media video editor (Viral AI Director).
Your job is to read transcript segments and find the absolute BEST start and end times to create a viral, highly engaging 15-60 second video clip for YouTube Shorts or Instagram Reels.

The user wants a clip that naturally includes the core mention between {start_time:.2f}s and {end_time:.2f}s.
You must expand these boundaries outwards to capture the full narrative hook leading up to it, and a satisfying conclusion after it.

TRANSCRIPT CONTEXT:
{formatted_context}

Respond ONLY with a valid JSON object containing exactly two keys: "start_time" (float) and "end_time" (float).
Example: {{"start_time": 12.5, "end_time": 45.3}}
"""
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                logger.warning("No OpenRouter API key found. Falling back to semantic boundaries.")
                return self._expand_boundaries_semantically(video_id, start_time, end_time)

            client = OpenAI(
                base_url="https://openrouter.io/api/v1",
                api_key=api_key,
            )
            
            response = client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                extra_headers={
                    "HTTP-Referer": "http://localhost:5000",
                    "X-OpenRouter-Title": "Video Chat AI Director"
                }
            )
            
            result_text = response.choices[0].message.content
            # Clean markdown code blocks if the LLM output them
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            result_json = json.loads(result_text.strip())
            
            ai_start = float(result_json.get("start_time", start_time))
            ai_end = float(result_json.get("end_time", end_time))
            
            if ai_end <= ai_start:
                logger.warning("AI returns invalid timestamps, falling back to semantic.")
                return self._expand_boundaries_semantically(video_id, start_time, end_time)

            # Ensure boundaries contain the core mention and aren't unreasonably long
            ai_start = min(start_time, ai_start)
            ai_end = max(end_time, ai_end)
            
            if ai_end - ai_start > 120:  # Cap at 2 mins just in case
                logger.warning("AI returns overly long clip (> 2 mins), falling back to semantic.")
                return self._expand_boundaries_semantically(video_id, start_time, end_time)
                
            # One more pass of semantic boundaries to ensure AI didn't cut off mid-word
            return self._expand_boundaries_semantically(video_id, ai_start, ai_end)
            
        except Exception as e:
            logger.error(f"AI Director expansion failed: {e}")
            return self._expand_boundaries_semantically(video_id, start_time, end_time)

    def list_clips(self, video_id: Optional[str] = None) -> List[Dict]:
        """
        List all clips or clips for specific video

        Args:
            video_id: Optional video ID to filter clips

        Returns:
            List of clip metadata
        """
        try:
            clips = []
            metadata_files = self.metadata_dir.glob("*_metadata.json")

            for metadata_file in metadata_files:
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)

                    # Filter by video_id if specified
                    if video_id:
                        clip_id = metadata.get("clip_id", "")
                        if not clip_id.startswith(video_id):
                            continue

                    # Check if file still exists
                    clip_path = metadata.get("clip_path", "")
                    if clip_path and os.path.exists(clip_path):
                        clips.append(metadata)
                    else:
                        logger.warning(f"Clip file missing: {clip_path}")

                except Exception as e:
                    logger.warning(f"Error reading metadata {metadata_file}: {str(e)}")

            return sorted(clips, key=lambda x: x.get("created_at", ""), reverse=True)

        except Exception as e:
            logger.error(f"Error listing clips: {str(e)}")
            return []

    def get_clip_info(self, clip_id: str) -> Dict:
        """
        Get information about a specific clip

        Args:
            clip_id: Clip ID

        Returns:
            Clip metadata or error
        """
        try:
            metadata_path = self.metadata_dir / f"{clip_id}_metadata.json"

            if not metadata_path.exists():
                logger.error(f"Metadata not found for clip: {clip_id}")
                return {
                    "status": "error",
                    "message": f"Clip {clip_id} not found"
                }

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            # Verify clip file exists
            clip_path = metadata.get("clip_path", "")
            if not os.path.exists(clip_path):
                logger.error(f"Clip file missing: {clip_path}")
                return {
                    "status": "error",
                    "message": f"Clip file missing: {clip_path}"
                }

            return metadata

        except Exception as e:
            logger.error(f"Error getting clip info: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

    def delete_clip(self, clip_id: str) -> Dict:
        """
        Delete a clip and its metadata (NOT USED - per user requirements to keep all clips)

        Args:
            clip_id: Clip ID to delete

        Returns:
            Success/error status
        """
        try:
            metadata_path = self.metadata_dir / f"{clip_id}_metadata.json"

            if not metadata_path.exists():
                return {
                    "status": "error",
                    "message": f"Metadata not found for clip: {clip_id}"
                }

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            clip_path = metadata.get("clip_path", "")

            # Delete clip file
            if clip_path and os.path.exists(clip_path):
                os.remove(clip_path)
                logger.info(f"Deleted clip file: {clip_path}")

            # Delete metadata
            metadata_path.unlink()
            logger.info(f"Deleted metadata for clip: {clip_id}")

            return {
                "status": "success",
                "message": f"Clip {clip_id} deleted",
                "clip_id": clip_id
            }

        except Exception as e:
            logger.error(f"Error deleting clip: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
