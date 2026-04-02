import os
import json
from pathlib import Path
from models.sqlite_store import SQLiteStore
from models.chroma_store import ChromaStore

def sync_transcripts_to_db():
    sqlite_store = SQLiteStore(db_path="./storage/database.sqlite")
    chroma_store = ChromaStore(persist_dir="./chroma_data")
    
    transcripts_dir = Path("./storage/transcripts")
    if not transcripts_dir.exists():
        print("No transcripts directory found.")
        return

    # Try to grab metadata from chroma if available because transcripts don't always have title/channel
    # get_all_videos from chroma_store
    chroma_videos = chroma_store.get_all_videos('video_transcripts')
    chroma_meta_map = {v['video_id']: v for v in chroma_videos}

    count = 0
    for filename in os.listdir(transcripts_dir):
        if filename.endswith("_transcript.json"):
            video_id = filename.replace("_transcript.json", "")
            file_path = transcripts_dir / filename
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract basic info
            metadata = data.get("metadata", {})
            transcribed_at = metadata.get("transcribed_at", "")
            
            # Merge with chroma info if we have it
            c_meta = chroma_meta_map.get(video_id, {})
            title = c_meta.get("title", f"Video {video_id}")
            channel = c_meta.get("channel", "")
            url = c_meta.get("youtube_url", "")
            
            video_data = {
                'id': video_id,
                'title': title,
                'channel': channel,
                'url': url,
                'published_at': '', # We don't have this in transcript usually
                'processed_at': transcribed_at,
                'transcript_path': str(file_path),
                'audio_path': f"./storage/audio/{video_id}.mp3", # Guessing
                'video_path': f"./storage/videos/{video_id}" # Guessing
            }
            
            try:
                sqlite_store.upsert_video(video_data)
                print(f"Synced {video_id} to database.")
                count += 1
            except Exception as e:
                print(f"Error syncing {video_id}: {e}")

    print(f"Successfully synced {count} videos into the database.")

if __name__ == "__main__":
    sync_transcripts_to_db()
