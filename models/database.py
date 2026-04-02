"""
Database Models and Operations
Using MongoDB for flexible schema
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from typing import Dict, Optional, List
import logging
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, mongodb_uri: str = None):
        """Initialize MongoDB connection"""
        uri = mongodb_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017/videochat')
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.db = self.client['videochat']
            # Test connection
            self.client.admin.command('ismaster')
            self._create_indexes()
            logger.info("Connected to MongoDB successfully")
        except Exception as e:
            logger.warning(f"MongoDB connection warning: {str(e)}")
            logger.warning("Application will work with in-memory storage")
            self.db = None

    def _create_indexes(self):
        """Create necessary indexes"""
        if not self.db:
            return

        # Videos collection
        self.db.videos.create_index('video_id', unique=True)
        self.db.videos.create_index('youtube_id')
        self.db.videos.create_index('file_hash')

        # Transcripts collection
        self.db.transcripts.create_index('video_id')

        # Embeddings collection (for vector search)
        self.db.embeddings.create_index('video_id')
        self.db.embeddings.create_index('segment_id')

        logger.info("Database indexes created")

    # ============ VIDEO OPERATIONS ============

    def save_video(self, video_data: Dict) -> str:
        """
        Save or update video metadata

        Args:
            video_data: Video metadata

        Returns:
            video_id
        """
        try:
            if not self.db:
                logger.warning("MongoDB not available, skipping save_video")
                return video_data['video_id']

            result = self.db.videos.update_one(
                {'video_id': video_data['video_id']},
                {'$set': video_data},
                upsert=True
            )
            logger.info(f"Video saved: {video_data['video_id']}")
            return video_data['video_id']
        except Exception as e:
            logger.error(f"Error saving video: {str(e)}")
            raise

    def get_video(self, video_id: str) -> Optional[Dict]:
        """Get video metadata"""
        if not self.db:
            return None
        return self.db.videos.find_one({'video_id': video_id})

    def check_video_duplicate(self, file_hash: str = None, youtube_id: str = None) -> Optional[Dict]:
        """Check if video already exists (deduplication)"""
        if not self.db:
            return None

        if file_hash:
            return self.db.videos.find_one({'file_hash': file_hash})
        elif youtube_id:
            return self.db.videos.find_one({'youtube_id': youtube_id})
        return None

    def list_videos(self, user_id: str = None) -> List[Dict]:
        """List all videos or user's videos"""
        if not self.db:
            return []

        query = {} if not user_id else {'user_id': user_id}
        return list(self.db.videos.find(query).sort('created_at', DESCENDING))

    # ============ TRANSCRIPT OPERATIONS ============

    def save_transcript(self, video_id: str, transcript_data: Dict) -> str:
        """Save transcript"""
        try:
            if not self.db:
                logger.warning("MongoDB not available, skipping save_transcript")
                return video_id

            transcript_record = {
                'video_id': video_id,
                'transcript_id': transcript_data.get('transcript_id'),
                'full_text': transcript_data['full_text'],
                'language': transcript_data['language'],
                'duration': transcript_data['duration'],
                'segments': transcript_data['segments'],
                'metadata': transcript_data['metadata'],
                'created_at': datetime.now()
            }

            result = self.db.transcripts.update_one(
                {'video_id': video_id},
                {'$set': transcript_record},
                upsert=True
            )

            logger.info(f"Transcript saved for video: {video_id}")
            return video_id
        except Exception as e:
            logger.error(f"Error saving transcript: {str(e)}")
            raise

    def get_transcript(self, video_id: str) -> Optional[Dict]:
        """Get transcript for a video"""
        if not self.db:
            return None
        return self.db.transcripts.find_one({'video_id': video_id})

    # ============ EMBEDDING & RAG OPERATIONS ============

    def save_embeddings(self, video_id: str, chunks: List[Dict]):
        """Save chunk embeddings for vector search"""
        try:
            if not self.db:
                logger.warning("MongoDB not available, skipping save_embeddings")
                return len(chunks)

            embedding_docs = []

            for chunk in chunks:
                doc = {
                    'video_id': video_id,
                    'chunk_id': chunk['chunk_id'],
                    'text': chunk['text'],
                    'start_time': chunk['start_time'],
                    'end_time': chunk['end_time'],
                    'segment_ids': chunk['segment_ids'],
                    'speakers': chunk['speakers'],
                    'embedding': chunk['embedding'],  # Vector
                    'created_at': datetime.now()
                }
                embedding_docs.append(doc)

            # Delete existing embeddings for this video
            self.db.embeddings.delete_many({'video_id': video_id})

            # Insert new embeddings
            if embedding_docs:
                result = self.db.embeddings.insert_many(embedding_docs)
                logger.info(f"Saved {len(embedding_docs)} embeddings for video {video_id}")

            return len(embedding_docs)
        except Exception as e:
            logger.error(f"Error saving embeddings: {str(e)}")
            raise

    def search_embeddings(
        self,
        video_id: str,
        query_embedding: List[float],
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search for similar embeddings using vector similarity

        Note: This is a simple implementation.
        For production, use MongoDB Atlas Vector Search or Pinecone.
        """
        try:
            if not self.db:
                logger.warning("MongoDB not available, skipping search_embeddings")
                return []

            # Get all embeddings for this video
            embeddings = list(self.db.embeddings.find({'video_id': video_id}))

            # Calculate similarity for each
            from modules.rag_processor import RAGProcessor
            rag = RAGProcessor()

            similarities = []
            for emb in embeddings:
                similarity = rag._cosine_similarity(
                    query_embedding,
                    emb['embedding']
                )
                similarities.append({
                    'chunk': emb,
                    'similarity': similarity
                })

            # Sort and return top-k
            result = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:top_k]
            return [item['chunk'] for item in result]

        except Exception as e:
            logger.error(f"Error searching embeddings: {str(e)}")
            raise

    # ============ USER INTERACTIONS ============

    def save_user_interaction(
        self,
        user_id: str,
        video_id: str,
        query: str,
        response: str,
        relevant_chunks: List[Dict]
    ):
        """Save user chat interactions for analytics"""
        try:
            if not self.db:
                logger.warning("MongoDB not available, skipping save_user_interaction")
                return

            interaction = {
                'user_id': user_id,
                'video_id': video_id,
                'query': query,
                'response': response,
                'relevant_chunks_count': len(relevant_chunks),
                'timestamp': datetime.now()
            }

            self.db.interactions.insert_one(interaction)
            logger.info(f"Interaction saved for user: {user_id}")
        except Exception as e:
            logger.error(f"Error saving interaction: {str(e)}")

    # ============ UTILITY ============

    def clear_database(self):
        """Clear all collections (for testing)"""
        if not self.db:
            return

        self.db.videos.delete_many({})
        self.db.transcripts.delete_many({})
        self.db.embeddings.delete_many({})
        logger.warning("Database cleared")

    def get_stats(self) -> Dict:
        """Get database statistics"""
        if not self.db:
            return {
                'videos': 0,
                'transcripts': 0,
                'embeddings': 0,
                'interactions': 0,
                'status': 'MongoDB not available'
            }

        return {
            'videos': self.db.videos.count_documents({}),
            'transcripts': self.db.transcripts.count_documents({}),
            'embeddings': self.db.embeddings.count_documents({}),
            'interactions': self.db.interactions.count_documents({}),
            'status': 'Connected'
        }
