"""
RAG (Retrieval-Augmented Generation) Processing Module
Handles chunking, embedding generation, and vector storage
Uses Open Router for embeddings
"""

import os
from typing import Dict, List
import logging
import json
from datetime import datetime
import requests

# Try to import sentence-transformers for local embeddings
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available. Using numpy-based embeddings instead.")

logger = logging.getLogger(__name__)

class RAGProcessor:
    def __init__(self, api_key: str = None):
        """
        Initialize RAG processor with local embeddings (no API calls needed!)

        Args:
            api_key: Open Router API key (for LLM only, not embeddings)
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.io/api/v1"

        # Use local sentence-transformers for embeddings (free, fast, 768-dim)
        self.embedding_model = "all-minilm-l6-v2"
        self.embedding_provider = "local"

        # Initialize embedding model if available
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info("Loading local embedding model: all-minilm-l6-v2")
                self.model = SentenceTransformer('sentence-transformers/all-minilm-l6-v2')
                logger.info("Embedding model loaded successfully (NO API KEY NEEDED!)")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
                self.model = None
        else:
            logger.warning("sentence-transformers not available. Install with: pip install sentence-transformers")
            self.model = None

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set. LLM features will fail, but embeddings still work.")

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
            logger.info("Starting RAG processing with Open Router embeddings")

            # Step 1: Create chunks from segments (for more granular RAG)
            chunks = self._create_chunks(transcript_data['segments'], overlap=chunk_overlap)
            logger.info(f"Created {len(chunks)} chunks from segments")

            # Step 2: Generate embeddings for each chunk using Open Router
            logger.info(f"Generating embeddings for {len(chunks)} chunks using Open Router")

            for chunk in chunks:
                embedding = self.generate_embedding(chunk['text'])
                chunk['embedding'] = embedding
                logger.debug(f"Generated embedding for chunk {chunk['chunk_id']}")

            # Step 3: Also generate segment embeddings
            logger.info(f"Generating embeddings for {len(transcript_data['segments'])} segments")
            for segment in transcript_data['segments']:
                embedding = self.generate_embedding(segment['text'])
                segment['embedding'] = embedding

            # Return enhanced data with both segment and chunk embeddings
            rag_data = {
                'transcript_id': transcript_data['transcript_id'],
                'segments': transcript_data['segments'],
                'chunks': chunks,
                'metadata': {
                    **transcript_data['metadata'],
                    'rag_processed_at': datetime.now().isoformat(),
                    'total_chunks': len(chunks),
                    'embedding_model': self.embedding_model,
                    'embedding_provider': 'local-sentencetransformers',
                    'embedding_dimensions': 384
                }
            }

            logger.info("RAG processing completed with Open Router embeddings")

            return rag_data

        except Exception as e:
            logger.error(f"Error processing transcript for RAG: {str(e)}")
            raise

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using local sentence-transformers model
        NO API CALLS NEEDED - completely free!

        Args:
            text: Text to embed

        Returns:
            Embedding vector (list of floats)
        """
        try:
            # Clean up text
            text = text.replace("\n", " ").strip()

            if not text:
                logger.debug("Empty text for embedding, returning zeros")
                return [0.0] * 384  # all-minilm-l6-v2 uses 384 dimensions

            # Use local embedding model (NO API CALL!)
            if self.model is not None:
                embedding = self.model.encode(text, convert_to_tensor=False)
                # Convert numpy array to list
                embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                logger.debug(f"Generated local embedding with dimension {len(embedding_list)}")
                return embedding_list
            else:
                logger.warning("Embedding model not available, using zero vector")
                return [0.0] * 384

        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

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
