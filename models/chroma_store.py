"""
Chroma DB Vector Store Integration
Handles vector embeddings storage and retrieval
"""

import os
from typing import Dict, List, Optional
import logging
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


def _chroma_corruption_remediation_hint(exc: BaseException) -> str:
    """Detect known Chroma on-disk schema skew / corruption and point to recovery."""
    msg = str(exc).lower()
    if "mismatched types" in msg and "blob" in msg:
        return (
            " Chroma persist data is incompatible or corrupt. Stop the server, run: "
            "python scripts/reset_chroma_data.py -y   "
            "then restart and re-run embeddings / RAG for your videos."
        )
    if "metadata segment" in msg and "compaction" in msg:
        return (
            " Chroma compaction failed on local data. If this persists after restart, "
            "run: python scripts/reset_chroma_data.py -y"
        )
    return ""


# Collection constants
VIDEO_TRANSCRIPTS_V1 = "video_transcripts"          # Legacy: all-minilm-l6-v2, 384-dim
VIDEO_TRANSCRIPTS_V2 = "video_transcripts_v2"        # Upgraded: qwen3-embedding-8b, 2048-dim
VIDEO_VISUAL_EMBEDDINGS = "video_visual_embeddings"   # Visual: nvidia-nemotron-vl, 2048-dim


class ChromaStore:
    """Chroma DB vector store for embeddings"""

    def __init__(self, persist_dir: str = "./chroma_data"):
        """
        Initialize Chroma DB with new client API

        Args:
            persist_dir: Directory to persist Chroma DB data
        """
        self.persist_dir = persist_dir

        try:
            # Create directory if it doesn't exist
            os.makedirs(persist_dir, exist_ok=True)

            # Initialize Chroma with new persistent client API
            self.client = chromadb.PersistentClient(path=persist_dir)
            logger.info(
                f"Chroma DB initialized (chromadb {chromadb.__version__}) at {persist_dir}"
            )

        except Exception as e:
            logger.error(f"Error initializing Chroma DB: {str(e)}")
            raise

    def create_collection(self, collection_name: str, metadata: Dict = None) -> any:
        """
        Create or get a collection

        Args:
            collection_name: Name of the collection
            metadata: Optional metadata for the collection

        Returns:
            Chroma collection
        """
        try:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata=metadata or {"description": f"Collection for {collection_name}"}
            )
            # Fix ChromaDB 0.5.23 empty config bug
            self._fix_collection_config(collection_name, "l2")
            logger.info(f"Collection '{collection_name}' ready for use")
            return collection

        except Exception as e:
            logger.error(f"Error creating collection: {str(e)}")
            raise

    def add_embeddings(
        self,
        collection_name: str,
        video_id: str,
        chunks: List[Dict],
        title: str = "Unknown",
        channel: str = "",
        youtube_url: str = ""
    ) -> int:
        """
        Add embeddings to collection

        Args:
            collection_name: Name of the collection
            video_id: Video ID for organization
            chunks: List of chunks with embeddings
            title: Video title
            channel: Channel/uploader name
            youtube_url: YouTube URL for the video

        Args:
            chunks format: [
                {
                    'chunk_id': 0,
                    'text': 'chunk text',
                    'embedding': [0.1, 0.2, ...],
                    'start_time': 0.5,
                    'end_time': 12.3,
                    'speakers': ['Speaker_1']
                }
            ]

        Returns:
            Number of embeddings added
        """
        try:
            collection = self.create_collection(collection_name)

            # Prepare data for Chroma
            ids = []
            embeddings = []
            metadatas = []
            documents = []

            for chunk in chunks:
                # Create unique ID combining video_id and chunk_id
                chunk_id = f"{video_id}_chunk_{chunk['chunk_id']}"
                ids.append(chunk_id)

                # Add embedding
                embeddings.append(chunk['embedding'])

                # Add metadata
                metadata = {
                    'video_id': video_id,
                    'title': title,
                    'channel': channel,
                    'youtube_url': youtube_url,
                    'chunk_id': str(chunk['chunk_id']),
                    'start_time': str(chunk.get('start_time', 0)),
                    'end_time': str(chunk.get('end_time', 0)),
                    'speakers': ','.join(chunk.get('speakers', [])),
                }
                metadatas.append(metadata)

                # Add document text
                documents.append(chunk['text'])

            # Add to Chroma
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )

            logger.info(f"Added {len(chunks)} embeddings to collection '{collection_name}'")
            return len(chunks)

        except Exception as e:
            logger.error(
                f"Error adding embeddings: {str(e)}{_chroma_corruption_remediation_hint(e)}"
            )
            raise

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        video_id: str = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search for similar embeddings

        Args:
            collection_name: Name of the collection
            query_embedding: Query embedding vector
            video_id: Optional video ID to filter results
            top_k: Number of results to return

        Returns:
            List of search results with metadata and text
        """
        try:
            collection = self.client.get_collection(name=collection_name)

            # Prepare where filter if video_id provided
            where_filter = None
            if video_id:
                where_filter = {"video_id": {"$eq": video_id}}

            # Query Chroma
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["embeddings", "metadatas", "documents", "distances"]
            )

            # Format results
            formatted_results = []

            if results['ids'] and len(results['ids']) > 0:
                for i, chunk_id in enumerate(results['ids'][0]):
                    result = {
                        'chunk_id': chunk_id,
                        'text': results['documents'][0][i],
                        'distance': results['distances'][0][i],
                        'similarity': 1 - results['distances'][0][i],  # Convert distance to similarity
                        'metadata': results['metadatas'][0][i]
                    }
                    formatted_results.append(result)

            logger.info(f"Found {len(formatted_results)} results for query")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching embeddings: {str(e)}")
            raise

    def delete_collection(self, collection_name: str):
        """
        Delete a collection

        Args:
            collection_name: Name of the collection to delete
        """
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Collection '{collection_name}' deleted")

        except Exception as e:
            logger.error(f"Error deleting collection: {str(e)}")
            raise

    def get_collection_info(self, collection_name: str) -> Dict:
        """
        Get information about a collection

        Args:
            collection_name: Name of the collection

        Returns:
            Collection information
        """
        try:
            collection = self.client.get_collection(name=collection_name)
            count = collection.count()

            logger.info(f"Collection '{collection_name}' has {count} embeddings")

            return {
                'name': collection_name,
                'count': count,
                'metadata': collection.metadata
            }

        except Exception as e:
            logger.error(f"Error getting collection info: {str(e)}")
            raise

    def clear_collection(self, collection_name: str):
        """
        Clear all embeddings from a collection (keep the collection)

        Args:
            collection_name: Name of the collection
        """
        try:
            collection = self.client.get_collection(name=collection_name)

            # Get all IDs
            all_data = collection.get()
            if all_data['ids']:
                collection.delete(ids=all_data['ids'])
                logger.info(f"Cleared {len(all_data['ids'])} embeddings from '{collection_name}'")

        except Exception as e:
            logger.error(f"Error clearing collection: {str(e)}")
            raise

    def persist(self):
        """
        Persist Chroma data to disk
        (PersistentClient automatically persists, so this is a no-op)
        """
        try:
            # PersistentClient automatically persists to disk
            # No explicit persist() call needed
            logger.info("Chroma DB is using PersistentClient (auto-persisted)")

        except Exception as e:
            logger.error(f"Error persisting Chroma: {str(e)}")
            raise

    def check_video_exists(self, video_id: str, collection_name: str = 'video_transcripts') -> Dict:
        """
        Check if a video's embeddings already exist in ChromaDB

        Args:
            video_id: Video identifier to check
            collection_name: Collection to search in

        Returns:
            Dict with 'exists' (bool) and 'count' (int) of chunks found
        """
        try:
            collection = self.client.get_collection(name=collection_name)
            results = collection.get(
                where={"video_id": video_id},
                limit=1
            )
            count = len(results['ids']) if results['ids'] else 0
            
            # Get full count if exists
            if count > 0:
                all_results = collection.get(
                    where={"video_id": video_id}
                )
                count = len(all_results['ids'])
            
            return {'exists': count > 0, 'count': count, 'video_id': video_id}
        except Exception as e:
            logger.debug(f"Collection '{collection_name}' not found or error: {e}")
            return {'exists': False, 'count': 0, 'video_id': video_id}

    def list_collections(self) -> List[str]:
        """
        List all collections

        Returns:
            List of collection names
        """
        try:
            collections = self.client.list_collections()
            # ChromaDB 0.6+ returns strings directly, 0.5.x returned objects with .name
            collection_names = [c if isinstance(c, str) else c.name for c in collections]
            logger.info(f"Found {len(collection_names)} collections")
            return collection_names

        except Exception as e:
            logger.error(f"Error listing collections: {str(e)}")
            raise

    def get_all_videos(self, collection_name: str = 'video_transcripts') -> List[Dict]:
        """
        Get all unique videos in a collection with full metadata.
        Normalizes video_ids to always have 'youtube_' prefix and deduplicates.

        Returns:
            List of dicts with 'video_id', 'title', 'channel', and 'youtube_url'
        """
        try:
            collection = self.client.get_collection(name=collection_name)
            # Get all metadata
            results = collection.get(include=['metadatas'])

            if not results['metadatas']:
                return []

            videos = {}
            for meta in results['metadatas']:
                raw_vid = meta.get('video_id', '')
                # Normalize: ensure video_id has 'youtube_' prefix
                if raw_vid and not raw_vid.startswith('youtube_') and not raw_vid.startswith('uploaded_'):
                    vid = f'youtube_{raw_vid}'
                else:
                    vid = raw_vid

                # Only add once per normalized video_id (deduplication)
                # Prefer entries that have real title over 'Unknown'
                title = meta.get('title', 'Unknown')
                if vid not in videos or (videos[vid]['title'] == 'Unknown' and title != 'Unknown'):
                    videos[vid] = {
                        'video_id': vid,
                        'title': title,
                        'channel': meta.get('channel', ''),
                        'youtube_url': meta.get('youtube_url', '')
                    }

            return list(videos.values())
        except Exception as e:
            logger.error(
                f"Error getting all videos: {e}{_chroma_corruption_remediation_hint(e)}"
            )
            return []

    def search_flexible(
        self,
        collection_name: str,
        query_embedding: List[float],
        video_ids: List[str] = None,
        threshold: float = 0.7,
        top_k: int = 20
    ) -> List[Dict]:
        """
        Flexible search across multiple videos with threshold filtering

        Args:
            collection_name: Collection to search in
            query_embedding: Query embedding vector
            video_ids: List of video IDs to search (None = all)
            threshold: Minimum similarity threshold (0.0-1.0)
            top_k: Results per video

        Returns:
            List of matching chunks sorted by similarity
        """
        try:
            collection = self.client.get_collection(name=collection_name)
            all_results = []

            # If specific videos requested, search each one
            if video_ids and len(video_ids) > 0:
                for vid in video_ids:
                    # Try with 'youtube_' prefix first
                    for video_id in [vid, vid.replace('youtube_', '') if vid.startswith('youtube_') else f'youtube_{vid}']:
                        try:
                            existing = collection.get(
                                where={"video_id": {"$eq": video_id}},
                                include=[],
                            )
                            available = len(existing.get('ids', []))
                            if available == 0:
                                continue

                            results = collection.query(
                                query_embeddings=[query_embedding],
                                n_results=min(top_k, available),
                                where={"video_id": {"$eq": video_id}},
                                include=["embeddings", "metadatas", "documents", "distances"]
                            )
                        except Exception as e:
                            logger.debug(f"Flexible search query failed for {video_id}: {e}")
                            continue

                        if results['ids'] and len(results['ids']) > 0:
                            for i, chunk_id in enumerate(results['ids'][0]):
                                similarity = 1 - results['distances'][0][i]
                                if similarity >= threshold:
                                    all_results.append({
                                        'chunk_id': chunk_id,
                                        'text': results['documents'][0][i],
                                        'similarity': similarity,
                                        'metadata': results['metadatas'][0][i]
                                    })
                            break  # Found results for this video
            else:
                # Search all videos
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["embeddings", "metadatas", "documents", "distances"]
                )

                if results['ids'] and len(results['ids']) > 0:
                    for i, chunk_id in enumerate(results['ids'][0]):
                        similarity = 1 - results['distances'][0][i]
                        if similarity >= threshold:
                            all_results.append({
                                'chunk_id': chunk_id,
                                'text': results['documents'][0][i],
                                'similarity': similarity,
                                'metadata': results['metadatas'][0][i]
                            })

            # Sort by similarity
            all_results = sorted(all_results, key=lambda x: x.get('similarity', 0), reverse=True)

            logger.info(f"Flexible search: Found {len(all_results)} results above {threshold} threshold")
            return all_results

        except Exception as e:
            logger.error(
                f"Error in flexible search: {str(e)}{_chroma_corruption_remediation_hint(e)}"
            )
            return []

    def get_segments_by_time_range(
        self,
        collection_name: str,
        video_id: str,
        start_time: float,
        end_time: float
    ) -> List[Dict]:
        """
        Get all transcript segments for a video within a time range

        Args:
            collection_name: Collection to search in
            video_id: Video ID
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            List of segments within the time range
        """
        try:
            collection = self.client.get_collection(name=collection_name)

            # Get all segments for this video
            results = collection.get(
                where={"video_id": video_id},
                include=['metadatas', 'documents']
            )

            segments = []
            if results['ids']:
                for i, chunk_id in enumerate(results['ids']):
                    metadata = results['metadatas'][i]
                    try:
                        seg_start = float(metadata.get('start_time', 0))
                        seg_end = float(metadata.get('end_time', 0))

                        # Check if segment overlaps with time range
                        if seg_start < end_time and seg_end > start_time:
                            segments.append({
                                'chunk_id': chunk_id,
                                'text': results['documents'][i],
                                'start_time': seg_start,
                                'end_time': seg_end,
                                'metadata': metadata
                            })
                    except (ValueError, TypeError):
                        continue

            return sorted(segments, key=lambda x: x['start_time'])

        except Exception as e:
            logger.error(f"Error getting segments by time range: {str(e)}")
            return []

    # ─── V2 TEXT EMBEDDINGS (Qwen3-Embedding-8B, 2048-dim) ──────────────

    def _get_or_create_cosine_collection(self, collection_name: str):
        """Get or create a collection with cosine distance metric."""
        collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        # Fix ChromaDB 0.5.23 bug: patch empty config_json_str to prevent _type KeyError
        self._fix_collection_config(collection_name, "cosine")
        return collection

    def _fix_collection_config(self, collection_name: str, space: str = "cosine"):
        """Patch empty config_json_str in ChromaDB SQLite to prevent _type KeyError."""
        try:
            import sqlite3, json
            db_path = os.path.join(self.persist_dir, "chroma.sqlite3")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT config_json_str FROM collections WHERE name = ?", (collection_name,))
            row = cursor.fetchone()
            if row and (not row[0] or row[0] == '{}'):
                config = json.dumps({
                    "hnsw_configuration": {
                        "space": space, "ef_construction": 100, "ef_search": 10,
                        "num_threads": 8, "M": 16, "resize_factor": 1.2,
                        "batch_size": 100, "sync_threshold": 1000,
                        "_type": "HNSWConfigurationInternal"
                    },
                    "_type": "CollectionConfigurationInternal"
                })
                cursor.execute("UPDATE collections SET config_json_str = ? WHERE name = ?", (config, collection_name))
                conn.commit()
                logger.info(f"Fixed empty config for collection '{collection_name}'")
            conn.close()
        except Exception as e:
            logger.debug(f"Config fix skipped for {collection_name}: {e}")

    def add_embeddings_v2(
        self,
        video_id: str,
        chunks: List[Dict],
        title: str = "Unknown",
        channel: str = "",
        youtube_url: str = ""
    ) -> int:
        """
        Add Qwen3-based embeddings to the v2 collection (cosine distance).
        Same interface as add_embeddings() but targets VIDEO_TRANSCRIPTS_V2.
        """
        try:
            collection = self._get_or_create_cosine_collection(VIDEO_TRANSCRIPTS_V2)

            ids = []
            embeddings = []
            metadatas = []
            documents = []

            for chunk in chunks:
                chunk_id = f"{video_id}_chunk_{chunk['chunk_id']}"
                ids.append(chunk_id)
                embeddings.append(chunk['embedding'])
                metadatas.append({
                    'video_id': video_id,
                    'title': title,
                    'channel': channel,
                    'youtube_url': youtube_url,
                    'chunk_id': str(chunk['chunk_id']),
                    'start_time': str(chunk.get('start_time', 0)),
                    'end_time': str(chunk.get('end_time', 0)),
                    'speakers': ','.join(chunk.get('speakers', [])),
                })
                documents.append(chunk['text'])

            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )

            logger.info(f"Added {len(chunks)} v2 embeddings for video '{video_id}'")
            return len(chunks)

        except Exception as e:
            logger.error(f"Error adding v2 embeddings: {e}")
            raise

    def search_v2(
        self,
        query_embedding: List[float],
        video_ids: List[str] = None,
        threshold: float = 0.3,
        top_k: int = 200
    ) -> List[Dict]:
        """
        Semantic search in v2 collection (Qwen3 embeddings, cosine distance).
        Lower default threshold (0.3) and higher top_k (200) for mention counting.
        """
        return self._search_cosine_collection(
            collection_name=VIDEO_TRANSCRIPTS_V2,
            query_embedding=query_embedding,
            video_ids=video_ids,
            threshold=threshold,
            top_k=top_k
        )

    def check_video_exists_v2(self, video_id: str) -> Dict:
        """Check if a video has been indexed in the v2 collection."""
        return self.check_video_exists(video_id, collection_name=VIDEO_TRANSCRIPTS_V2)

    def _search_cosine_collection(
        self,
        collection_name: str,
        query_embedding: List[float],
        video_ids: List[str] = None,
        threshold: float = 0.3,
        top_k: int = 200
    ) -> List[Dict]:
        """
        Search a collection that uses cosine distance metric.
        For cosine distance, ChromaDB returns distances in [0, 2] range.
        Similarity = 1 - distance (range [-1, 1]).
        """
        try:
            collection = self.client.get_collection(name=collection_name)
            all_results = []

            if video_ids and len(video_ids) > 0:
                for vid in video_ids:
                    for video_id in [vid, vid.replace('youtube_', '') if vid.startswith('youtube_') else f'youtube_{vid}']:
                        try:
                            existing = collection.get(
                                where={"video_id": {"$eq": video_id}},
                                include=[],
                            )
                            available = len(existing.get('ids', []))
                            if available == 0:
                                continue

                            results = collection.query(
                                query_embeddings=[query_embedding],
                                n_results=min(top_k, available),
                                where={"video_id": {"$eq": video_id}},
                                include=["metadatas", "documents", "distances"]
                            )

                            if results['ids'] and len(results['ids']) > 0:
                                # DEBUG: Log raw distances to diagnose L2 vs cosine
                                if results['distances'][0]:
                                    raw_dists = results['distances'][0][:3]
                                    raw_sims = [1 - d for d in raw_dists]
                                    logger.info(f"[DEBUG] {collection_name} raw distances: {raw_dists}, sims: {raw_sims}")

                                for i, chunk_id in enumerate(results['ids'][0]):
                                    similarity = 1 - results['distances'][0][i]
                                    if similarity >= threshold:
                                        all_results.append({
                                            'chunk_id': chunk_id,
                                            'text': results['documents'][0][i],
                                            'similarity': similarity,
                                            'metadata': results['metadatas'][0][i]
                                        })
                                break
                        except Exception as e:
                            logger.error(
                                f"Cosine query FAILED for {video_id} in '{collection_name}': {e}"
                            )
                            continue
            else:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(top_k, collection.count()),
                    include=["metadatas", "documents", "distances"]
                )

                if results['ids'] and len(results['ids']) > 0:
                    for i, chunk_id in enumerate(results['ids'][0]):
                        similarity = 1 - results['distances'][0][i]
                        if similarity >= threshold:
                            all_results.append({
                                'chunk_id': chunk_id,
                                'text': results['documents'][0][i],
                                'similarity': similarity,
                                'metadata': results['metadatas'][0][i]
                            })

            all_results = sorted(all_results, key=lambda x: x.get('similarity', 0), reverse=True)
            logger.info(f"Cosine search in '{collection_name}': {len(all_results)} results above {threshold}")
            return all_results

        except Exception as e:
            logger.error(f"Error in cosine search: {e}")
            return []

    # ─── VISUAL EMBEDDINGS (NVIDIA Nemotron VL, 2048-dim) ───────────────

    def add_visual_embeddings(
        self,
        video_id: str,
        frames: List[Dict],
        title: str = "Unknown",
        channel: str = "",
        youtube_url: str = ""
    ) -> int:
        """
        Add visual frame embeddings to the visual collection.

        Args:
            video_id: Video identifier
            frames: List of frame dicts with keys:
                - chunk_index: int
                - start_time: float
                - end_time: float
                - embedding: List[float] (2048-dim)
            title: Video title
            channel: Channel name
            youtube_url: YouTube URL

        Returns:
            Number of embeddings added
        """
        try:
            collection = self._get_or_create_cosine_collection(VIDEO_VISUAL_EMBEDDINGS)

            ids = []
            embeddings = []
            metadatas = []
            documents = []

            for frame in frames:
                frame_id = f"{video_id}_frame_{frame['chunk_index']}"
                ids.append(frame_id)
                embeddings.append(frame['embedding'])
                metadatas.append({
                    'video_id': video_id,
                    'title': title,
                    'channel': channel,
                    'youtube_url': youtube_url,
                    'chunk_index': str(frame['chunk_index']),
                    'start_time': str(frame.get('start_time', 0)),
                    'end_time': str(frame.get('end_time', 0)),
                    'source_type': 'visual',
                })
                # Document text = AI-generated description of the frame (for RAG context)
                description = frame.get('description',
                    f"Visual frame {frame['chunk_index']}: "
                    f"{frame.get('start_time', 0):.1f}s - {frame.get('end_time', 0):.1f}s"
                )
                documents.append(description)

            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )

            logger.info(f"Added {len(frames)} visual embeddings for video '{video_id}'")
            return len(frames)

        except Exception as e:
            logger.error(f"Error adding visual embeddings: {e}")
            raise

    def search_visual(
        self,
        query_embedding: List[float],
        video_ids: List[str] = None,
        threshold: float = 0.4,
        top_k: int = 10
    ) -> List[Dict]:
        """
        Search visual embeddings collection (cosine distance).

        Args:
            query_embedding: Text query embedded with NVIDIA Nemotron VL (2048-dim)
            video_ids: Optional video IDs to filter
            threshold: Minimum similarity threshold
            top_k: Number of results

        Returns:
            List of matching visual frames sorted by similarity
        """
        return self._search_cosine_collection(
            collection_name=VIDEO_VISUAL_EMBEDDINGS,
            query_embedding=query_embedding,
            video_ids=video_ids,
            threshold=threshold,
            top_k=top_k
        )

    def check_visual_index_exists(self, video_id: str) -> bool:
        """Check if a video has been visually indexed."""
        result = self.check_video_exists(video_id, collection_name=VIDEO_VISUAL_EMBEDDINGS)
        return result.get('exists', False)
