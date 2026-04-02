import os
from models.chroma_store import ChromaStore
from pathlib import Path

def diagnose():
    print("--- ChromaDB Diagnosis ---")
    try:
        store = ChromaStore(persist_dir="./chroma_data")
        collections = store.list_collections()
        print(f"Collections: {collections}")
        
        for coll_name in collections:
            count = store.get_collection_info(coll_name)['count']
            print(f"Collection '{coll_name}': {count} items")
            if count > 0:
                videos = store.get_all_videos(coll_name)
                print(f"Videos in '{coll_name}': {videos}")
    except Exception as e:
        print(f"ChromaDB Error: {e}")

    print("\n--- Storage Diagnosis ---")
    storage_path = Path("./storage")
    if storage_path.exists():
        for sub in storage_path.iterdir():
            if sub.is_dir():
                items = list(sub.iterdir())
                print(f"Directory '{sub.name}': {len(items)} items")
    else:
        print("Storage directory not found!")

if __name__ == "__main__":
    diagnose()
