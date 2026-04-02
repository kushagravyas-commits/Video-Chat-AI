"""
Clip Trash Manager
Handles soft-delete operations for video clips
Stores deleted clip metadata in a JSON file for recovery within 10 days
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ClipTrashManager:
    def __init__(self, storage_dir: str = "./storage"):
        """Initialize clip trash manager"""
        self.storage_dir = Path(storage_dir)
        self.clips_dir = self.storage_dir / "clips"
        self.trash_dir = self.storage_dir / "trash"
        self.trash_metadata_file = self.trash_dir / "deleted_clips.json"

        # Create trash directory if it doesn't exist
        self.trash_dir.mkdir(parents=True, exist_ok=True)

        # Initialize trash metadata file if it doesn't exist
        if not self.trash_metadata_file.exists():
            self.trash_metadata_file.write_text(json.dumps({"clips": {}, "videos": {}}, indent=2))

    def _load_trash_metadata(self) -> Dict:
        """Load trash metadata from JSON file"""
        try:
            if self.trash_metadata_file.exists():
                with open(self.trash_metadata_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading trash metadata: {e}")
        return {"clips": {}, "videos": {}}

    def _save_trash_metadata(self, data: Dict):
        """Save trash metadata to JSON file"""
        try:
            with open(self.trash_metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trash metadata: {e}")

    def soft_delete_clip(self, clip_filename: str, clip_path: Optional[Path] = None) -> bool:
        """
        Soft delete a clip by moving to trash directory
        Args:
            clip_filename: Name of the clip file (e.g., "highlight_1.mp4")
            clip_path: Optional full path to the clip
        """
        try:
            # If no path provided, construct it
            if clip_path is None:
                clip_path = self.clips_dir / clip_filename
            else:
                clip_path = Path(clip_path)

            if not clip_path.exists():
                logger.warning(f"Clip file not found: {clip_path}")
                return False

            # Move clip to trash
            trash_clip_path = self.trash_dir / clip_filename
            clip_path.rename(trash_clip_path)

            # Also move metadata file if it exists
            clip_id = clip_path.stem
            metadata_file = self.clips_dir / "metadata" / f"{clip_id}_metadata.json"
            if metadata_file.exists():
                trash_metadata_file = self.trash_dir / f"{clip_id}_metadata.json"
                metadata_file.rename(trash_metadata_file)

            # Record deletion in trash metadata
            trash_data = self._load_trash_metadata()
            trash_data["clips"][clip_filename] = {
                "deleted_at": datetime.now().isoformat(),
                "original_path": str(clip_path),
                "clip_id": clip_id
            }
            self._save_trash_metadata(trash_data)

            logger.info(f"Soft deleted clip: {clip_filename}")
            return True
        except Exception as e:
            logger.error(f"Error soft deleting clip: {e}")
            return False

    def recover_clip(self, clip_filename: str) -> bool:
        """Recover a clip from trash"""
        try:
            trash_clip_path = self.trash_dir / clip_filename
            if not trash_clip_path.exists():
                logger.warning(f"Clip not found in trash: {clip_filename}")
                return False

            # Move clip back to clips directory
            original_clip_path = self.clips_dir / clip_filename
            trash_clip_path.rename(original_clip_path)

            # Also move metadata file if it exists
            clip_id = Path(clip_filename).stem
            trash_metadata_file = self.trash_dir / f"{clip_id}_metadata.json"
            if trash_metadata_file.exists():
                metadata_file = self.clips_dir / "metadata" / f"{clip_id}_metadata.json"
                metadata_file.parent.mkdir(parents=True, exist_ok=True)
                trash_metadata_file.rename(metadata_file)

            # Remove from trash metadata
            trash_data = self._load_trash_metadata()
            if clip_filename in trash_data["clips"]:
                del trash_data["clips"][clip_filename]
                self._save_trash_metadata(trash_data)

            logger.info(f"Recovered clip from trash: {clip_filename}")
            return True
        except Exception as e:
            logger.error(f"Error recovering clip: {e}")
            return False

    def get_trash_clips(self) -> List[Dict]:
        """Get all deleted clips in trash with metadata"""
        trash_clips = []
        trash_data = self._load_trash_metadata()

        try:
            # Iterate over clips in metadata
            for clip_filename, info in trash_data["clips"].items():
                clip_path = self.trash_dir / clip_filename
                if clip_path.exists():
                    stat = clip_path.stat()
                    deleted_at = datetime.fromisoformat(info["deleted_at"])
                    now = datetime.now()
                    days_remaining = 10 - (now - deleted_at).days

                    trash_clips.append({
                        "filename": clip_filename,
                        "clip_id": info.get("clip_id", Path(clip_filename).stem),
                        "deleted_at": info["deleted_at"],
                        "days_remaining": max(0, days_remaining),
                        "file_size": stat.st_size,
                        "is_expired": days_remaining <= 0
                    })
        except Exception as e:
            logger.error(f"Error getting trash clips: {e}")

        return sorted(trash_clips, key=lambda x: x["deleted_at"], reverse=True)

    def permanently_delete_clip(self, clip_filename: str) -> bool:
        """Permanently delete a clip from trash"""
        try:
            trash_clip_path = self.trash_dir / clip_filename
            if trash_clip_path.exists():
                trash_clip_path.unlink()

            # Also delete metadata
            clip_id = Path(clip_filename).stem
            trash_metadata_file = self.trash_dir / f"{clip_id}_metadata.json"
            if trash_metadata_file.exists():
                trash_metadata_file.unlink()

            # Remove from trash metadata
            trash_data = self._load_trash_metadata()
            if clip_filename in trash_data["clips"]:
                del trash_data["clips"][clip_filename]
                self._save_trash_metadata(trash_data)

            logger.info(f"Permanently deleted clip: {clip_filename}")
            return True
        except Exception as e:
            logger.error(f"Error permanently deleting clip: {e}")
            return False

    def auto_delete_expired_clips(self) -> int:
        """
        Automatically delete clips that have been in trash for more than 10 days
        Returns count of deleted clips
        """
        deleted_count = 0
        trash_clips = self.get_trash_clips()

        for clip_info in trash_clips:
            if clip_info["is_expired"]:
                if self.permanently_delete_clip(clip_info["filename"]):
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Auto-deleted {deleted_count} expired clips from trash")

        return deleted_count
