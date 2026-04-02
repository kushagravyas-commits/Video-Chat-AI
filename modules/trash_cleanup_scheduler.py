"""
Trash Cleanup Scheduler
Runs background tasks to automatically delete expired trash items (older than 10 days)
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TrashCleanupScheduler:
    """
    Simple scheduler for trash cleanup tasks
    Runs cleanup every 24 hours or at specified intervals
    """

    def __init__(self, cleanup_func: Callable, interval_hours: int = 24):
        """
        Initialize the scheduler
        Args:
            cleanup_func: Function to call for cleanup (should handle its own exceptions)
            interval_hours: How often to run cleanup (default: 24 hours)
        """
        self.cleanup_func = cleanup_func
        self.interval_seconds = interval_hours * 3600
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start the cleanup scheduler in background"""
        if self.running:
            logger.warning("Cleanup scheduler is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"Trash cleanup scheduler started (interval: {self.interval_seconds // 3600} hours)")

    def stop(self):
        """Stop the cleanup scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            logger.info("Trash cleanup scheduler stopped")

    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            try:
                time.sleep(self.interval_seconds)

                if self.running:  # Check again in case stop was called
                    logger.info("Running scheduled trash cleanup...")
                    self.cleanup_func()
                    logger.info("Trash cleanup completed")
            except Exception as e:
                logger.error(f"Error in trash cleanup scheduler: {e}")

    def run_now(self):
        """Run cleanup immediately (synchronously)"""
        try:
            logger.info("Running trash cleanup...")
            self.cleanup_func()
            logger.info("Trash cleanup completed")
        except Exception as e:
            logger.error(f"Error running trash cleanup: {e}")


def create_cleanup_function(sqlite_store, clip_trash_manager):
    """
    Factory function to create a cleanup function
    Returns a function that cleans up both videos and clips
    """

    def cleanup():
        try:
            from datetime import datetime, timedelta

            # Cleanup expired clips
            expired_clips_count = clip_trash_manager.auto_delete_expired_clips()

            # Cleanup expired videos
            expired_videos_count = 0
            trash_videos = sqlite_store.get_trash_videos()
            cutoff_date = (datetime.now() - timedelta(days=10)).isoformat()

            for video in trash_videos:
                if video.get('deleted_at') and video['deleted_at'] < cutoff_date:
                    if sqlite_store.permanently_delete_video(video['id']):
                        expired_videos_count += 1

            logger.info(
                f"Trash cleanup: deleted {expired_videos_count} videos and {expired_clips_count} clips"
            )
        except Exception as e:
            logger.error(f"Error in cleanup function: {e}")

    return cleanup
