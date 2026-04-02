"""
SQLite Database Integration
Stores video metadata and file paths
"""

import sqlite3
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SQLiteStore:
    def __init__(self, db_path: str = "./storage/database.sqlite"):
        """Initialize SQLite database connection and create tables if needed"""
        self.db_path = db_path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        try:
            self._create_tables()
            logger.info(f"SQLite DB initialized at {db_path}")
        except Exception as e:
            logger.error(f"Error initializing SQLite DB: {e}")
            raise

    def get_connection(self):
        """Get a configured SQLite connection and cursor"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn

    def _create_tables(self):
        """Create necessary tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Videos Table
            # 1. Name (title)
            # 2. ID (video_id)
            # 3. Channel Name (channel)
            # 4. url (youtube_url)
            # 5. Date of video published (published_at)
            # 6. Date of video processed (processed_at)
            # 7. Transcript (transcript_path)
            # 8. Audio (audio_path)
            # 9. Video (video_path)
            # 10. is_deleted (soft delete flag)
            # 11. deleted_at (timestamp when deleted)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    channel TEXT,
                    url TEXT,
                    published_at TEXT,
                    processed_at TEXT,
                    transcript_path TEXT,
                    audio_path TEXT,
                    video_path TEXT,
                    is_deleted INTEGER DEFAULT 0,
                    deleted_at TEXT
                )
            ''')

            # Add soft-delete columns if they don't exist (migration for existing databases)
            try:
                cursor.execute("ALTER TABLE videos ADD COLUMN is_deleted INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE videos ADD COLUMN deleted_at TEXT")
                conn.commit()
                logger.info("Added soft-delete columns to videos table")
            except sqlite3.OperationalError:
                # Columns already exist, no action needed
                pass

    def upsert_video(self, video_data: Dict) -> str:
        """
        Insert or update a video record.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            video_id = video_data.get('id') or video_data.get('video_id')
            if not video_id:
                raise ValueError("Video ID is required")
                
            # Default values
            now = datetime.now().isoformat()
            
            # Extract fields safely
            title = video_data.get('title', 'Unknown Title')
            channel = video_data.get('channel', 'Unknown Channel')
            url = video_data.get('url') or video_data.get('youtube_url', '')
            published_at = video_data.get('published_at', '')
            processed_at = video_data.get('processed_at', now)
            transcript_path = video_data.get('transcript_path', '')
            audio_path = video_data.get('audio_path', '')
            video_path = video_data.get('video_path', '')
            
            cursor.execute('''
                INSERT INTO videos (
                    id, title, channel, url, published_at, processed_at, 
                    transcript_path, audio_path, video_path
                ) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    channel=excluded.channel,
                    url=excluded.url,
                    published_at=COALESCE(NULLIF(excluded.published_at, ''), videos.published_at),
                    processed_at=COALESCE(NULLIF(excluded.processed_at, ''), videos.processed_at),
                    transcript_path=COALESCE(NULLIF(excluded.transcript_path, ''), videos.transcript_path),
                    audio_path=COALESCE(NULLIF(excluded.audio_path, ''), videos.audio_path),
                    video_path=COALESCE(NULLIF(excluded.video_path, ''), videos.video_path)
            ''', (
                video_id, title, channel, url, published_at, processed_at,
                transcript_path, audio_path, video_path
            ))
            
            conn.commit()
            logger.info(f"Saved/Updated video in SQLite: {video_id}")
            return video_id

    def update_video_paths(self, video_id: str, transcript_path: str = None, 
                           audio_path: str = None, video_path: str = None):
        """Update specific file paths for an existing video"""
        updates = []
        params = []
        
        if transcript_path is not None:
            updates.append("transcript_path = ?")
            params.append(transcript_path)
            
        if audio_path is not None:
            updates.append("audio_path = ?")
            params.append(audio_path)
            
        if video_path is not None:
            updates.append("video_path = ?")
            params.append(video_path)
            
        if not updates:
            return
            
        params.append(video_id)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"UPDATE videos SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()

    def get_video(self, video_id: str) -> Optional[Dict]:
        """Get a single video by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None

    def get_all_videos(self) -> List[Dict]:
        """Get all videos (excluding deleted), ordered by processed_at descending"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE is_deleted = 0 ORDER BY processed_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def soft_delete_video(self, video_id: str) -> bool:
        """Soft delete a video (mark as deleted but keep data for recovery)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            deleted_at = datetime.now().isoformat()
            cursor.execute(
                "UPDATE videos SET is_deleted = 1, deleted_at = ? WHERE id = ?",
                (deleted_at, video_id)
            )
            conn.commit()
            logger.info(f"Soft deleted video: {video_id}")
            return cursor.rowcount > 0

    def recover_video(self, video_id: str) -> bool:
        """Recover a deleted video from trash"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE videos SET is_deleted = 0, deleted_at = NULL WHERE id = ?",
                (video_id,)
            )
            conn.commit()
            logger.info(f"Recovered video from trash: {video_id}")
            return cursor.rowcount > 0

    def get_trash_videos(self) -> List[Dict]:
        """Get all deleted videos (in trash), ordered by deleted_at descending"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE is_deleted = 1 ORDER BY deleted_at DESC")
            rows = cursor.fetchall()

            videos = []
            for row in rows:
                video_dict = dict(row)
                # Calculate days remaining
                if video_dict.get('deleted_at'):
                    deleted_at = datetime.fromisoformat(video_dict['deleted_at'])
                    now = datetime.now()
                    days_remaining = 10 - (now - deleted_at).days
                    video_dict['days_remaining'] = max(0, days_remaining)
                    video_dict['is_expired'] = days_remaining <= 0
                else:
                    video_dict['days_remaining'] = 10
                    video_dict['is_expired'] = False

                videos.append(video_dict)

            return videos

    def permanently_delete_video(self, video_id: str) -> bool:
        """Permanently delete a video from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
            conn.commit()
            logger.info(f"Permanently deleted video from database: {video_id}")
            return cursor.rowcount > 0
