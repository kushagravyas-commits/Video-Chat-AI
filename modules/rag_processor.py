"""
RAG (Retrieval-Augmented Generation) Processing Module
Handles chunking, embedding generation, and vector storage
Embeddings are generated via OpenRouter (Qwen3-Embedding-8B)
"""

import os
from typing import Dict, List
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class RAGProcessor:
    def __init__(self, api_key: str = None):
        """
        Initialize RAG processor.
        Note: Embeddings are now handled by OpenRouterEmbedder (Qwen3-8B).
        This class handles chunking and transcript processing.
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')

    def process_transcript_for_rag(
        self,
        transcript_data: Dict,
        chunk_overlap: int = 50
    ) -> Dict:
        """
        Process transcript for RAG:
        1. Split into chunks
        2. Generate embeddings for each chunk
        3. Return augmented data

        Args:
            transcript_data: Transcript from Whisper
            chunk_overlap: Number of overlapping tokens

        Returns:
            Enhanced transcript with embeddings
        """

        try:
            logger.info("Starting RAG processing (chunking only — embeddings via OpenRouter)")

            # Create chunks from segments
            chunks = self._create_chunks(transcript_data['segments'], overlap=chunk_overlap)
            logger.info(f"Created {len(chunks)} chunks from segments")

            # Set placeholder embeddings (real embeddings done by OpenRouterEmbedder in v2 pipeline)
            for chunk in chunks:
                chunk['embedding'] = [0.0] * 384  # Placeholder for v1 compat

            rag_data = {
                'transcript_id': transcript_data['transcript_id'],
                'segments': transcript_data['segments'],
                'chunks': chunks,
                'metadata': {
                    **transcript_data['metadata'],
                    'rag_processed_at': datetime.now().isoformat(),
                    'total_chunks': len(chunks),
                    'embedding_model': 'qwen3-embedding-8b (via OpenRouter)',
                    'embedding_provider': 'openrouter',
                    'embedding_dimensions': 2048
                }
            }

            logger.info("RAG processing completed (chunks ready for OpenRouter embedding)")
            return rag_data

        except Exception as e:
            logger.error(f"Error processing transcript for RAG: {str(e)}")
            raise

    def generate_embedding(self, text: str) -> List[float]:
        """
        DEPRECATED: Returns zero vector. Use OpenRouterEmbedder.embed_text() instead.
        Kept for backward compatibility with code that calls this method.
        """
        return [0.0] * 384

    def _create_chunks(self, segments: List[Dict], overlap: int = 50) -> List[Dict]:
        """
        Create overlapping chunks from segments

        This allows for finer-grained RAG retrieval

        Args:
            segments: List of segments from transcript
            overlap: Number of words to overlap between chunks

        Returns:
            List of chunks
        """

        chunks = []
        chunk_id = 0

        # Group segments into chunks
        # Strategy: Create chunks from 2-3 consecutive segments
        for i in range(0, len(segments), max(1, len(segments) // 10)):
            # Take 2-3 segments per chunk
            chunk_segments = segments[i:i+2]

            if not chunk_segments:
                continue

            # Combine text from multiple segments
            chunk_text = " ".join([seg['text'] for seg in chunk_segments])

            # Get min/max timestamps
            start_time = chunk_segments[0]['start_time']
            end_time = chunk_segments[-1]['end_time']

            chunk = {
                'chunk_id': chunk_id,
                'text': chunk_text,
                'segment_ids': [seg['segment_id'] for seg in chunk_segments],
                'start_time': start_time,
                'end_time': end_time,
                'speakers': list(set([seg['speaker'] for seg in chunk_segments])),
                'embedding': None,  # Will be filled by generate_embedding
            }

            chunks.append(chunk)
            chunk_id += 1

        return chunks

    def get_relevant_segments(
        self,
        query: str,
        rag_data: Dict,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Retrieve relevant segments for a user query using semantic search

        Args:
            query: User query
            rag_data: RAG-processed transcript data
            top_k: Number of top results to return

        Returns:
            List of relevant segments with timestamps
        """

        try:
            logger.info(f"Retrieving relevant segments for query: {query}")

            # Generate embedding for query
            query_embedding = self.generate_embedding(query)

            # Calculate similarity between query and all chunks
            similarities = []

            for chunk in rag_data['chunks']:
                # Cosine similarity
                similarity = self._cosine_similarity(
                    query_embedding,
                    chunk['embedding']
                )

                similarities.append({
                    'chunk': chunk,
                    'similarity': similarity
                })

            # Sort by similarity and get top-k
            relevant = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:top_k]

            logger.info(f"Found {len(relevant)} relevant segments")

            # Return relevant chunks with their corresponding segments
            result = [item['chunk'] for item in relevant]

            return result

        except Exception as e:
            logger.error(f"Error retrieving relevant segments: {str(e)}")
            raise

    def reembed_transcript_for_v2(
        self,
        video_id: str,
        openrouter_embedder,
        chroma_store,
        title: str = "Unknown",
        channel: str = "",
        youtube_url: str = ""
    ) -> int:
        """
        Re-embed an existing transcript using Qwen3-Embedding-8B via OpenRouter
        and store in the v2 ChromaDB collection.

        Args:
            video_id: Video identifier (e.g., 'youtube_xxx')
            openrouter_embedder: OpenRouterEmbedder instance
            chroma_store: ChromaStore instance
            title: Video title
            channel: Channel name
            youtube_url: YouTube URL

        Returns:
            Number of chunks embedded and stored
        """
        # 1. Load transcript from JSON file
        base_vid = video_id
        transcript_path = f"./storage/transcripts/{base_vid}_transcript.json"

        if not os.path.exists(transcript_path):
            # Try without youtube_ prefix
            if base_vid.startswith("youtube_"):
                alt_path = f"./storage/transcripts/{base_vid[8:]}_transcript.json"
                if os.path.exists(alt_path):
                    transcript_path = alt_path

        if not os.path.exists(transcript_path):
            logger.error(f"Transcript not found: {transcript_path}")
            return 0

        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)

        segments = transcript_data.get('segments', [])
        if not segments:
            logger.warning(f"No segments found in transcript for {video_id}")
            return 0

        # 2. Create fine-grained chunks — embed EVERY 2-3 consecutive segments
        #    (NOT the default _create_chunks which skips 90% of segments)
        chunks = self._create_dense_chunks(segments)
        logger.info(f"Created {len(chunks)} dense chunks for v2 re-embedding of {video_id}")

        # 3. Batch embed all chunk texts via OpenRouter
        chunk_texts = [chunk['text'] for chunk in chunks]
        try:
            embeddings = openrouter_embedder.embed_batch_for_storage(chunk_texts)
        except Exception as e:
            logger.error(f"Failed to generate v2 embeddings: {e}")
            return 0

        # 4. Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding

        # 5. Store in v2 collection
        count = chroma_store.add_embeddings_v2(
            video_id=video_id,
            chunks=chunks,
            title=title,
            channel=channel,
            youtube_url=youtube_url
        )

        logger.info(f"Re-embedded {count} chunks for {video_id} into v2 collection")
        return count

    def _create_dense_chunks(self, segments: List[Dict], window_size: int = 3, step: int = 2) -> List[Dict]:
        """
        Create DENSE overlapping chunks from ALL segments using a sliding window.
        Unlike _create_chunks() which skips 90% of segments, this covers everything.

        With 131 segments, window=3, step=2 → ~65 chunks (full coverage with overlap)

        Args:
            segments: List of transcript segments
            window_size: Number of segments per chunk (default: 3)
            step: Slide step (default: 2 = 1 segment overlap between chunks)

        Returns:
            List of chunk dicts ready for embedding
        """
        chunks = []
        chunk_id = 0

        for i in range(0, len(segments), step):
            window = segments[i:i + window_size]
            if not window:
                continue

            chunk_text = " ".join([seg.get('text', '') for seg in window])
            if not chunk_text.strip():
                continue

            chunk = {
                'chunk_id': chunk_id,
                'text': chunk_text,
                'segment_ids': [seg.get('segment_id', i + j) for j, seg in enumerate(window)],
                'start_time': window[0].get('start_time', 0),
                'end_time': window[-1].get('end_time', 0),
                'speakers': list(set([seg.get('speaker', 'Unknown') for seg in window])),
                'embedding': None,
            }
            chunks.append(chunk)
            chunk_id += 1

        logger.info(f"Dense chunking: {len(segments)} segments -> {len(chunks)} chunks "
                     f"(window={window_size}, step={step})")
        return chunks

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors
        """
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0

        return dot_product / (magnitude1 * magnitude2)
