import os
import json
from pathlib import Path
from models.sqlite_store import SQLiteStore
from models.chroma_store import ChromaStore

def sync_data():
    sqlite_store = SQLiteStore()
    chroma_store = ChromaStore()

    print("Fetching videos from ChromaDB...")
    chroma_videos = chroma_store.get_all_videos('video_transcripts')
    video_dict = {v['video_id']: v for v in chroma_videos}

    print("Scanning storage directories...")
    videos_dir = Path('./storage/videos')
    if videos_dir.exists():
        for video_folder in videos_dir.iterdir():
            if video_folder.is_dir():
                vid = video_folder.name
                if vid not in video_dict:
                    video_dict[vid] = {
                        'video_id': vid,
                        'title': vid,
                        'channel': 'Local Storage',
                        'youtube_url': ''
                    }

    print(f"Found {len(video_dict)} unique videos. Syncing to SQLite...")
    
    for vid, meta in video_dict.items():
        # Deduce paths
        video_dir = videos_dir / vid
        if not video_dir.exists() and vid.startswith('youtube_'):
            video_dir_no_prefix = videos_dir / vid.replace('youtube_', '')
            if video_dir_no_prefix.exists():
                video_dir = video_dir_no_prefix

        # Video path
        video_path = ""
        for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
            v_file = video_dir / f"video{ext}" if ext else video_dir / "video"
            if v_file.exists():
                video_path = str(v_file)
                break

        # Audio path
        audio_path = f"./storage/audio/{vid}_audio.mp3"
        if not Path(audio_path).exists():
            # Check without youtube_ prefix
            no_prefix = vid.replace('youtube_', '')
            alt_audio = f"./storage/audio/{no_prefix}_audio.mp3"
            if Path(alt_audio).exists():
                audio_path = alt_audio
            else:
                audio_path = ""
                
        # Transcript path
        transcript_path = f"./storage/transcripts/{vid}_transcript.json"
        if not Path(transcript_path).exists():
            no_prefix = vid.replace('youtube_', '')
            alt_transcript = f"./storage/transcripts/{no_prefix}_transcript.json"
            if Path(alt_transcript).exists():
                transcript_path = alt_transcript
            else:
                # Also check 'video_transcript.json' which is a known bug
                if Path('./storage/transcripts/video_transcript.json').exists():
                    # We can't guarantee it belongs to this video, but leave it empty
                    pass
                transcript_path = ""
        
        # Publish date
        pub_date = meta.get('upload_date', '')
        if pub_date and len(pub_date) == 8:
            pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:]}"
        
        # Processed date (use folder modification time)
        processed_at = ""
        try:
            if video_dir.exists():
                from datetime import datetime
                mtime = video_dir.stat().st_mtime
                processed_at = datetime.fromtimestamp(mtime).isoformat()
        except:
            pass

        sqlite_store.upsert_video({
            'id': vid,
            'title': meta.get('title', 'Unknown'),
            'channel': meta.get('channel', ''),
            'url': meta.get('youtube_url', ''),
            'published_at': pub_date,
            'processed_at': processed_at,
            'video_path': video_path,
            'audio_path': audio_path,
            'transcript_path': transcript_path
        })

    print("Sync complete.")

if __name__ == "__main__":
    sync_data()
