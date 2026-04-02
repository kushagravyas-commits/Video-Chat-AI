"""
Move ./chroma_data aside so ChromaDB can create a fresh on-disk store.

Use when logs show compaction / metadata errors such as:
  mismatched types; Rust type `u64` ... is not compatible with SQL type `BLOB`

After running: restart the backend and re-run RAG / embedding for your videos.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup and remove local Chroma persist directory")
    parser.add_argument(
        "--dir",
        default="chroma_data",
        help="Path to Chroma persist directory (default: chroma_data)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Do not prompt for confirmation",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    persist = (root / args.dir).resolve()

    if not persist.exists():
        print(f"Nothing to do: {persist} does not exist.")
        return

    if not args.yes:
        print(f"This will move:\n  {persist}\nto a timestamped backup folder.")
        reply = input("Continue? [y/N]: ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted.")
            return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = persist.parent / f"{persist.name}.bak_{stamp}"
    shutil.move(str(persist), str(backup))
    persist.mkdir(parents=True, exist_ok=True)
    print(f"Moved store to:\n  {backup}\nCreated empty:\n  {persist}\nRestart the backend and re-embed your videos.")


if __name__ == "__main__":
    main()
