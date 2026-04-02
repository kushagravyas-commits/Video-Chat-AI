"""
OpenRouter Embedding Client
Provides text embeddings via qwen/qwen3-embedding-8b and
visual embeddings via nvidia/llama-nemotron-embed-vl-1b-v2 through OpenRouter API.
"""

import os
import time
import base64
import logging
import requests
from typing import List, Optional, Dict

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Model constants
TEXT_MODEL = "qwen/qwen3-embedding-8b"
VISUAL_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
TEXT_DIMENSIONS = 2048  # Matryoshka truncation from 4096
VISUAL_DIMENSIONS = 2048  # Fixed


class OpenRouterEmbedder:
    """
    Unified embedding client for OpenRouter.
    - Text embeddings: qwen/qwen3-embedding-8b (2048-dim via Matryoshka)
    - Visual embeddings: nvidia/llama-nemotron-embed-vl-1b-v2 (2048-dim, free)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        text_model: str = TEXT_MODEL,
        visual_model: str = VISUAL_MODEL,
        text_dimensions: int = TEXT_DIMENSIONS,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment or constructor")

        self.text_model = text_model
        self.visual_model = visual_model
        self.text_dimensions = text_dimensions

        # OpenAI-compatible client for text embeddings
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
        )

        # Base URL for raw requests (visual embeddings)
        self.base_url = "https://openrouter.ai/api/v1/embeddings"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            f"OpenRouterEmbedder initialized: text={text_model} ({text_dimensions}d), "
            f"visual={visual_model} ({VISUAL_DIMENSIONS}d)"
        )

    # ─── TEXT EMBEDDINGS (Qwen3-Embedding-8B) ────────────────────────────

    def embed_text(self, text: str, instruction: str = None) -> List[float]:
        """
        Embed a single text string using Qwen3-Embedding-8B.

        Args:
            text: Text to embed
            instruction: Optional task instruction for better retrieval
                        (Qwen3 is instruction-aware)

        Returns:
            List of floats (2048 dimensions)
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding, returning zero vector")
            return [0.0] * self.text_dimensions

        # Qwen3 supports instruction-aware embeddings
        if instruction:
            input_text = f"Instruct: {instruction}\nQuery: {text}"
        else:
            input_text = text

        try:
            response = self.client.embeddings.create(
                model=self.text_model,
                input=input_text,
                encoding_format="float",
                dimensions=self.text_dimensions,
            )
            embedding = response.data[0].embedding
            logger.debug(f"Text embedding generated: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Text embedding failed: {e}")
            raise

    def embed_text_for_retrieval(self, query: str) -> List[float]:
        """Embed a search query with retrieval-optimized instruction."""
        return self.embed_text(
            query,
            instruction="Given a video transcript, retrieve relevant passages that match the query"
        )

    def embed_text_for_storage(self, text: str) -> List[float]:
        """Embed a transcript chunk for storage (no instruction prefix)."""
        return self.embed_text(text)

    def embed_batch(self, texts: List[str], instruction: str = None) -> List[List[float]]:
        """
        Batch embed multiple texts in a single API call.

        Args:
            texts: List of text strings
            instruction: Optional task instruction

        Returns:
            List of embeddings (each 2048 dimensions)
        """
        if not texts:
            return []

        # Apply instruction prefix if provided
        if instruction:
            input_texts = [f"Instruct: {instruction}\nQuery: {t}" for t in texts]
        else:
            input_texts = texts

        try:
            response = self.client.embeddings.create(
                model=self.text_model,
                input=input_texts,
                encoding_format="float",
                dimensions=self.text_dimensions,
            )
            embeddings = [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
            logger.info(f"Batch embedded {len(embeddings)} texts ({len(embeddings[0])} dims each)")
            return embeddings

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise

    def embed_batch_for_storage(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """
        Embed texts for storage in batches to avoid API limits.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts per API call

        Returns:
            List of embeddings
        """
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embed_batch(batch)
            all_embeddings.extend(embeddings)
            if i + batch_size < len(texts):
                time.sleep(0.5)  # Rate limiting between batches
        return all_embeddings

    # ─── VISUAL EMBEDDINGS (NVIDIA Nemotron VL) ─────────────────────────

    def embed_image(self, image_path: str) -> List[float]:
        """
        Embed an image file using NVIDIA Nemotron VL (free, multimodal).

        Args:
            image_path: Path to JPEG/PNG image file

        Returns:
            List of floats (2048 dimensions)
        """
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        # Detect MIME type
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={
                    "model": self.visual_model,
                    "input": [
                        {
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{b64}"
                                    },
                                }
                            ]
                        }
                    ],
                    "encoding_format": "float",
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            logger.debug(f"Image embedding generated: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Image embedding failed for {image_path}: {e}")
            raise

    def embed_visual_query(self, query: str) -> List[float]:
        """
        Embed a text query into the VISUAL vector space (NVIDIA model).

        CRITICAL: This must use the NVIDIA model (not Qwen3) so that
        text queries and image embeddings share the same vector space.

        Args:
            query: Text description of visual content to search for

        Returns:
            List of floats (2048 dimensions)
        """
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={
                    "model": self.visual_model,
                    "input": query,
                    "encoding_format": "float",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            logger.debug(f"Visual query embedding generated: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Visual query embedding failed: {e}")
            raise

    def embed_image_batch(
        self, image_paths: List[str], rate_limit_delay: float = 3.0
    ) -> List[List[float]]:
        """
        Embed multiple images with rate limiting (free tier: 20 req/min).

        Args:
            image_paths: List of image file paths
            rate_limit_delay: Seconds between requests (3.0 = 20 req/min safe)

        Returns:
            List of embeddings (2048-dim each)
        """
        embeddings = []
        for i, path in enumerate(image_paths):
            try:
                emb = self.embed_image(path)
                embeddings.append(emb)
                logger.info(f"Embedded image {i + 1}/{len(image_paths)}: {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"Failed to embed {path}: {e}")
                embeddings.append([0.0] * VISUAL_DIMENSIONS)

            # Rate limiting for free tier
            if i < len(image_paths) - 1:
                time.sleep(rate_limit_delay)

        return embeddings

    # ─── UTILITIES ───────────────────────────────────────────────────────

    def test_connection(self) -> Dict:
        """Test that both embedding models are accessible."""
        results = {"text": False, "visual": False}

        try:
            emb = self.embed_text("test connection")
            results["text"] = len(emb) == self.text_dimensions
            logger.info(f"Text embedding test: {'OK' if results['text'] else 'FAIL'} ({len(emb)} dims)")
        except Exception as e:
            logger.error(f"Text embedding test failed: {e}")

        try:
            emb = self.embed_visual_query("test connection")
            results["visual"] = len(emb) == VISUAL_DIMENSIONS
            logger.info(f"Visual embedding test: {'OK' if results['visual'] else 'FAIL'} ({len(emb)} dims)")
        except Exception as e:
            logger.error(f"Visual embedding test failed: {e}")

        return results
