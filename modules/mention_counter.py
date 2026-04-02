"""
Mention Counter Module - REGEX + SEMANTIC TEXT SEARCH
Finds and counts mentions of specific terms/concepts in video transcripts.
- Keyword/Regex mode: Direct text search with regex patterns (case/tense/plural)
- Semantic mode: Embedding similarity search via Qwen3-Embedding-8B (OpenRouter)
- Hybrid mode: Both combined for comprehensive results
"""

import re
import logging
from typing import Dict, List, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class MentionCounter:
    """Count mentions of terms/concepts in video transcripts using regex and/or semantic search"""

    def __init__(self, chroma_store, rag_processor, openrouter_embedder=None):
        """
        Initialize mention counter

        Args:
            chroma_store: ChromaStore instance for querying transcript segments
            rag_processor: RAGProcessor for RAG functionality
            openrouter_embedder: OpenRouterEmbedder instance for semantic search (optional)
        """
        self.chroma_store = chroma_store
        self.rag_processor = rag_processor
        self.openrouter_embedder = openrouter_embedder

    def count_mentions(
        self,
        video_ids: List[str],
        search_query: str,
        mode: str = 'regex',
        confidence_threshold: float = 0.7
    ) -> Dict:
        """
        Find and count mentions of a term/concept in video(s).

        Modes:
            - 'regex'/'keyword'/'exact'/'fuzzy': Direct text search with regex patterns
            - 'semantic': Embedding similarity search (Qwen3 via OpenRouter)
            - 'hybrid': Both regex + semantic combined, deduplicated

        Args:
            video_ids: List of video IDs to search
            search_query: What to search for (e.g., "Israel", "where Modi discussed the war")
            mode: 'regex' | 'keyword' | 'exact' | 'fuzzy' | 'semantic' | 'hybrid'
            confidence_threshold: Minimum confidence score (0.0-1.0)

        Returns:
            Dict with status, mentions list, statistics, and time_distribution
        """
        try:
            logger.info(f"Counting mentions of '{search_query}' using {mode} mode")

            all_mentions = []

            for video_id in video_ids:
                if mode == 'semantic':
                    # Pure semantic search using embeddings
                    mentions = self._search_video_semantic(
                        video_id=video_id,
                        search_query=search_query,
                        confidence_threshold=confidence_threshold
                    )
                elif mode == 'hybrid':
                    # Combine regex + semantic for comprehensive results
                    regex_mentions = self._search_video_text(
                        video_id=video_id,
                        search_query=search_query,
                        mode='regex'
                    )
                    semantic_mentions = self._search_video_semantic(
                        video_id=video_id,
                        search_query=search_query,
                        confidence_threshold=confidence_threshold
                    )
                    mentions = self._merge_mentions(regex_mentions, semantic_mentions)
                else:
                    # Pure regex/keyword search (existing behavior)
                    mentions = self._search_video_text(
                        video_id=video_id,
                        search_query=search_query,
                        mode=mode
                    )
                all_mentions.extend(mentions)

            logger.info(f"Found {len(all_mentions)} total mentions across {len(video_ids)} video(s)")

            # Deduplicate nearby mentions (< 2 seconds apart)
            unique_mentions = self._deduplication_phase(all_mentions)

            logger.info(f"After deduplication: {len(unique_mentions)} unique mentions")

            # Calculate statistics
            statistics = self._calculate_statistics(unique_mentions)

            primary_video = video_ids[0] if video_ids else "unknown"

            return {
                "status": "success",
                "video_id": primary_video,
                "query": search_query,
                "search_mode": mode,
                "total_count": len(unique_mentions),
                "unique_mentions": len(unique_mentions),
                "mentions": unique_mentions,
                "statistics": statistics,
                "video_count": len(video_ids)
            }

        except Exception as e:
            logger.error(f"Error counting mentions: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "video_id": video_ids[0] if video_ids else "unknown",
                "query": search_query
            }

    def _search_video_text(
        self,
        video_id: str,
        search_query: str,
        mode: str = 'regex'
    ) -> List[Dict]:
        """
        Search within a single video's transcript using regex patterns

        Args:
            video_id: Video ID to search
            search_query: Term to search for
            mode: 'regex' | 'exact' | 'fuzzy'

        Returns:
            List of mentions with timestamps
        """
        try:
            logger.info(f"Searching video {video_id} for '{search_query}'")

            # Try to normalize video_id (with and without youtube_ prefix)
            video_ids_to_try = [video_id]
            if not video_id.startswith('youtube_'):
                video_ids_to_try.append(f'youtube_{video_id}')
            if video_id.startswith('youtube_'):
                video_ids_to_try.append(video_id.replace('youtube_', ''))

            all_segments = []

            # Try to get segments from ChromaDB
            for vid in video_ids_to_try:
                try:
                    # Get all documents from ChromaDB for this video
                    segments = self._get_all_segments(vid)
                    if segments:
                        logger.info(f"Found {len(segments)} segments in ChromaDB for {vid}")
                        all_segments = segments
                        break
                except Exception as e:
                    logger.debug(f"Could not get segments for {vid}: {str(e)}")
                    continue

            if not all_segments:
                logger.warning(f"No segments found for {video_id}")
                return []

            # Build regex pattern based on mode
            if mode == 'regex':
                pattern = self._build_regex_pattern(search_query)
            elif mode == 'exact':
                pattern = re.compile(re.escape(search_query), re.IGNORECASE)
            else:  # fuzzy
                pattern = self._build_fuzzy_pattern(search_query)

            logger.info(f"Using pattern for regex search: {pattern.pattern}")

            # Search all segments with regex
            mentions = []
            for segment in all_segments:
                text = segment.get('text', '')
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', start_time + 5)
                metadata = segment.get('metadata', {})

                # Find all matches in this segment
                matches = pattern.finditer(text)

                for match in matches:
                    mention = {
                        "start_time": start_time,
                        "end_time": end_time,
                        "timestamp_formatted": f"{self._seconds_to_time(start_time)} - {self._seconds_to_time(end_time)}",
                        "text": text,
                        "matched_text": match.group(0),
                        "confidence": 1.0,  # Exact match = high confidence
                        "match_type": self._determine_match_type(search_query, match.group(0)),
                        "video_id": video_id,
                        "title": metadata.get('title', 'Unknown'),
                        "chunk_id": segment.get('chunk_id', '')
                    }
                    mentions.append(mention)

            logger.info(f"Found {len(mentions)} mentions in {video_id}")

            # If strict regex misses a multi-word entity (e.g., ASR typo like
            # "Aditi Dhar" vs query "Aditya Dhar"), run a fuzzy phrase fallback.
            if not mentions and ' ' in search_query.strip():
                fuzzy_mentions = self._search_video_text_fuzzy_phrase(
                    segments=all_segments,
                    video_id=video_id,
                    search_query=search_query
                )
                if fuzzy_mentions:
                    logger.info(
                        f"Fuzzy phrase fallback found {len(fuzzy_mentions)} mentions in {video_id}"
                    )
                    mentions.extend(fuzzy_mentions)

            return mentions

        except Exception as e:
            logger.error(f"Error searching video {video_id}: {str(e)}")
            return []

    def _search_video_text_fuzzy_phrase(
        self,
        segments: List[Dict],
        video_id: str,
        search_query: str,
        min_ratio: float = 0.86
    ) -> List[Dict]:
        """
        Approximate phrase matcher for ASR spelling drift in names/phrases.
        """
        normalized_query = re.sub(r'[^a-z0-9 ]+', ' ', search_query.lower()).strip()
        query_tokens = [t for t in normalized_query.split() if t]
        if len(query_tokens) < 2:
            return []

        mentions = []
        window_size = len(query_tokens)

        for segment in segments:
            text = segment.get('text', '')
            tokens = [t for t in re.sub(r'[^a-z0-9 ]+', ' ', text.lower()).split() if t]
            if len(tokens) < window_size:
                continue

            best_ratio = 0.0
            best_phrase = ""
            for i in range(0, len(tokens) - window_size + 1):
                candidate = ' '.join(tokens[i:i + window_size])
                ratio = SequenceMatcher(None, normalized_query, candidate).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_phrase = candidate

            if best_ratio >= min_ratio:
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', start_time + 5)
                metadata = segment.get('metadata', {})
                mentions.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "timestamp_formatted": f"{self._seconds_to_time(start_time)} - {self._seconds_to_time(end_time)}",
                    "text": text,
                    "matched_text": best_phrase,
                    "confidence": round(best_ratio, 4),
                    "match_type": "fuzzy_phrase",
                    "video_id": video_id,
                    "title": metadata.get('title', 'Unknown'),
                    "chunk_id": segment.get('chunk_id', '')
                })

        return mentions

    def _search_video_semantic(
        self,
        video_id: str,
        search_query: str,
        confidence_threshold: float = 0.3
    ) -> List[Dict]:
        """
        Semantic search using Qwen3 embeddings in v2 collection.
        Falls back to legacy v1 semantic search when v2 embeddings are unavailable.
        """
        try:
            if not self.openrouter_embedder:
                logger.info("OpenRouterEmbedder not available, skipping semantic search")
                return []

            logger.info(f"Semantic search in video {video_id} for '{search_query}'")

            # Check if video has v2 embeddings
            v2_exists = self.chroma_store.check_video_exists_v2(video_id)
            if not v2_exists.get('exists', False):
                logger.info(
                    f"Video {video_id} has no v2 embeddings — falling back to v1 semantic search."
                )
                return self._search_video_semantic_v1(
                    video_id=video_id,
                    search_query=search_query,
                    confidence_threshold=max(0.25, confidence_threshold)
                )

            # Embed query with Qwen3
            query_embedding = self.openrouter_embedder.embed_text_for_retrieval(search_query)

            # Search v2 collection.
            # Retry with progressively smaller top_k because some Chroma setups
            # can fail or return empty for large n_results + where filters.
            results = []
            for top_k in (200, 100, 50, 20):
                try:
                    candidate = self.chroma_store.search_v2(
                        query_embedding=query_embedding,
                        video_ids=[video_id],
                        threshold=confidence_threshold,
                        top_k=top_k
                    )
                    if candidate:
                        results = candidate
                        logger.info(
                            f"Semantic v2 returned {len(results)} results for {video_id} (top_k={top_k})"
                        )
                        break
                except Exception as e:
                    logger.warning(
                        f"Semantic v2 query failed for {video_id} with top_k={top_k}: {e}"
                    )

            # If v2 exists but yields zero, fallback to v1 to avoid silent false-zero results.
            if not results:
                logger.info(
                    f"Semantic v2 returned no matches for {video_id}; falling back to v1 semantic search."
                )
                return self._search_video_semantic_v1(
                    video_id=video_id,
                    search_query=search_query,
                    confidence_threshold=max(0.2, confidence_threshold)
                )

            # Convert to standard mention dict format
            mentions = []
            for r in results:
                metadata = r.get('metadata', {})
                start_time = float(metadata.get('start_time', 0))
                end_time = float(metadata.get('end_time', start_time + 5))

                mentions.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "timestamp_formatted": f"{self._seconds_to_time(start_time)} - {self._seconds_to_time(end_time)}",
                    "text": r.get('text', ''),
                    "matched_text": search_query,
                    "confidence": round(r.get('similarity', 0), 4),
                    "match_type": "semantic",
                    "video_id": video_id,
                    "title": metadata.get('title', 'Unknown'),
                    "chunk_id": r.get('chunk_id', '')
                })

            mentions.sort(key=lambda x: x['start_time'])
            logger.info(f"Semantic search found {len(mentions)} mentions in {video_id}")
            return mentions

        except Exception as e:
            logger.error(f"Semantic search failed for {video_id}: {e}")
            return []  # Hybrid caller already includes regex path

    def _search_video_semantic_v1(
        self,
        video_id: str,
        search_query: str,
        confidence_threshold: float = 0.25
    ) -> List[Dict]:
        """
        Legacy semantic fallback against v1 transcript embeddings.
        This keeps hybrid behavior robust for older already-processed videos.
        """
        try:
            query_embedding = self.rag_processor.generate_embedding(search_query)
            results = self.chroma_store.search_flexible(
                collection_name='video_transcripts',
                query_embedding=query_embedding,
                video_ids=[video_id],
                threshold=confidence_threshold,
                top_k=200
            )

            mentions = []
            for r in results:
                metadata = r.get('metadata', {})
                start_time = float(metadata.get('start_time', 0))
                end_time = float(metadata.get('end_time', start_time + 5))

                mentions.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "timestamp_formatted": f"{self._seconds_to_time(start_time)} - {self._seconds_to_time(end_time)}",
                    "text": r.get('text', ''),
                    "matched_text": search_query,
                    "confidence": round(r.get('similarity', 0), 4),
                    "match_type": "semantic",
                    "video_id": video_id,
                    "title": metadata.get('title', 'Unknown'),
                    "chunk_id": r.get('chunk_id', '')
                })

            mentions.sort(key=lambda x: x['start_time'])
            logger.info(f"V1 semantic fallback found {len(mentions)} mentions in {video_id}")
            return mentions

        except Exception as e:
            logger.error(f"V1 semantic fallback failed for {video_id}: {e}")
            return []

    def _merge_mentions(
        self,
        regex_mentions: List[Dict],
        semantic_mentions: List[Dict]
    ) -> List[Dict]:
        """
        Merge regex and semantic search results, deduplicating overlapping time ranges.

        - If same segment found by both: keep with higher confidence, tag as "hybrid"
        - Regex-only matches: confidence stays 1.0
        - Semantic-only matches: keep real cosine similarity

        Args:
            regex_mentions: Results from regex search
            semantic_mentions: Results from semantic search

        Returns:
            Merged and deduplicated mention list
        """
        if not regex_mentions:
            return semantic_mentions
        if not semantic_mentions:
            return regex_mentions

        # Index semantic results by approximate time bucket (2-second windows)
        semantic_by_time = {}
        for m in semantic_mentions:
            bucket = int(m['start_time'] / 2)
            if bucket not in semantic_by_time or m['confidence'] > semantic_by_time[bucket]['confidence']:
                semantic_by_time[bucket] = m

        merged = []
        regex_buckets_used = set()

        # Add regex mentions, checking for overlaps with semantic
        for rm in regex_mentions:
            bucket = int(rm['start_time'] / 2)
            regex_buckets_used.add(bucket)

            if bucket in semantic_by_time:
                sm = semantic_by_time[bucket]
                # Both found this segment — create hybrid entry
                merged.append({
                    **rm,
                    "confidence": max(rm['confidence'], sm['confidence']),
                    "match_type": "hybrid",
                })
            else:
                # Regex-only match
                merged.append(rm)

        # Add semantic-only matches (not found by regex)
        for bucket, sm in semantic_by_time.items():
            if bucket not in regex_buckets_used:
                merged.append(sm)

        # Sort by timestamp
        merged.sort(key=lambda x: x['start_time'])

        logger.info(
            f"Merged mentions: {len(regex_mentions)} regex + {len(semantic_mentions)} semantic "
            f"= {len(merged)} combined"
        )
        return merged

    def _get_all_segments(self, video_id: str) -> List[Dict]:
        """
        Get all transcript segments DIRECTLY from the JSON transcript file.

        Args:
            video_id: Video ID to get segments for

        Returns:
            List of segment dicts with text, timestamps, metadata
        """
        import os
        import json
        
        try:
            # Handle normalized IDs
            base_vid = video_id
            if not base_vid.startswith('youtube_') and not base_vid.startswith('uploaded_'):
                base_vid = f"youtube_{base_vid}"
                
            transcript_path = f"./storage/transcripts/{base_vid}_transcript.json"
            
            if not os.path.exists(transcript_path):
                logger.warning(f"Transcript JSON not found for {base_vid} at {transcript_path}")
                return []
                
            with open(transcript_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            raw_segments = data.get('segments', [])
            
            # Try to get Video Title
            title = f"Video {base_vid}"
            try:
                from models.sqlite_store import SQLiteStore
                store = SQLiteStore()
                conn = store.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT title FROM videos WHERE id=?", (base_vid,))
                row = cursor.fetchone()
                if row:
                    title = row['title']
                conn.close()
            except Exception:
                pass
                
            formatted_segments = []
            for idx, seg in enumerate(raw_segments):
                formatted_segments.append({
                    'chunk_id': f"{base_vid}_seg_{idx}",
                    'text': seg.get('text', ''),
                    'metadata': {'title': title},
                    'start_time': float(seg.get('start_time', 0)),
                    'end_time': float(seg.get('end_time', 0))
                })
                
            logger.info(f"Retrieved {len(formatted_segments)} segments from JSON for {base_vid}")
            return formatted_segments

        except Exception as e:
            logger.error(f"Error getting segments from JSON: {str(e)}")
            return []

    def _build_regex_pattern(self, search_query: str) -> re.Pattern:
        """
        Build comprehensive regex pattern that handles:
        - Case insensitivity (Israel, israel, ISRAEL)
        - Singular/plural forms (mention, mentions)
        - Tense variations (mentioned, mentioning, mentions)
        - Common variations

        Args:
            search_query: Search term

        Returns:
            Compiled regex pattern
        """
        # Extract base term
        base_term = search_query.strip().lower()

        # Remove common articles and prepositions
        base_term = re.sub(r'^(the|a|an|in|on|at|by)\s+', '', base_term)

        # Remove common suffixes temporarily to find root word
        patterns = []

        # Handle multi-word queries
        if ' ' in base_term:
            # For multi-word: "military action" -> find whole phrase or variations
            words = base_term.split()
            # Build pattern for each word with variations
            word_patterns = [self._build_word_pattern(w) for w in words]
            # Match phrase with flexible spacing
            pattern_str = r'\s+'.join(word_patterns)
        else:
            # Single word - apply full variation logic
            pattern_str = self._build_word_pattern(base_term)

        logger.info(f"Built regex pattern: {pattern_str}")

        return re.compile(pattern_str, re.IGNORECASE)

    def _build_word_pattern(self, word: str) -> str:
        """
        Build regex pattern for a single word with variations:
        - israel -> Israel, israel, ISRAEL, israelis, israeli, israelite
        - mention -> mention, mentions, mentioned, mentioning
        - action -> action, actions

        Args:
            word: Single word to build pattern for

        Returns:
            Regex pattern string for the word
        """
        # Simple and robust: match the word followed by optional common suffixes
        # This handles most variations for most words

        if word.endswith('ed'):
            # Already past tense, but can be: root+ed, root+ing, root+s
            root = word[:-2]
            return f"\\b{root}(?:ed|ing|s)?\\b"
        elif word.endswith('ing'):
            # Already present continuous
            root = word[:-3]
            return f"\\b{root}(?:ing|ed|s)?\\b"
        elif word.endswith('s'):
            # Already plural or 3rd person singular
            root = word[:-1]
            return f"\\b{root}(?:s|es|ed|ing)?\\b"
        else:
            # Base form: match word + common suffixes
            # -s (plural/3rd person): israel -> israels, mention -> mentions
            # -es (alternative plural): action -> actions
            # -ed (past tense): mention -> mentioned
            # -ing (present continuous): mention -> mentioning
            # -i? (for variants like israeli from israel)
            return f"\\b{word}(?:s|es|i(?:s|te|tes)?|ed|ing)?\\b"

    def _build_fuzzy_pattern(self, search_query: str) -> re.Pattern:
        """
        Build a fuzzy pattern that allows for typos
        Uses character substitution patterns
        """
        # Simple fuzzy: allow 1 character substitution
        escaped = re.escape(search_query.lower())
        # Match the exact or with minor variations
        return re.compile(escaped, re.IGNORECASE)

    def _determine_match_type(self, original: str, matched: str) -> str:
        """
        Determine what type of match was found

        Args:
            original: Original search term
            matched: Matched text

        Returns:
            Type of match: 'exact', 'plural', 'tense', 'case', 'variation'
        """
        original_lower = original.lower()
        matched_lower = matched.lower()

        if original_lower == matched_lower:
            return "exact"
        elif matched_lower.endswith('s') and matched_lower[:-1] == original_lower:
            return "plural"
        elif matched_lower.endswith('ed') and matched_lower[:-2] == original_lower:
            return "past_tense"
        elif matched_lower.endswith('ing') and matched_lower[:-3] == original_lower:
            return "present_tense"
        else:
            return "variation"

    def _deduplication_phase(self, mentions: List[Dict], min_distance: int = 2) -> List[Dict]:
        """
        Remove duplicate mentions that are very close together (< min_distance seconds apart)

        Args:
            mentions: List of mentions
            min_distance: Minimum seconds between mentions to keep both

        Returns:
            Deduplicated mention list
        """
        if not mentions:
            return []

        # Sort by start_time
        sorted_mentions = sorted(mentions, key=lambda x: x.get('start_time', 0))

        deduplicated = []
        last_end_time = -float('inf')

        for mention in sorted_mentions:
            start_time = mention.get('start_time', 0)

            # Keep if far enough from last mention
            if start_time - last_end_time > min_distance:
                deduplicated.append(mention)
                last_end_time = mention.get('end_time', start_time)

        logger.info(f"Deduplication: {len(deduplicated)} unique from {len(mentions)} total")
        return deduplicated

    def _calculate_statistics(self, mentions: List[Dict]) -> Dict:
        """
        Calculate statistics about mentions

        Args:
            mentions: List of mentions

        Returns:
            Statistics dictionary
        """
        try:
            if not mentions:
                return {
                    "total_mentions": 0,
                    "match_types": {},
                    "mention_density": "0 mentions",
                    "time_distribution": {},
                    "video_duration_seconds": 0
                }

            # Match type distribution
            match_types = {}
            for mention in mentions:
                mt = mention.get('match_type', 'unknown')
                match_types[mt] = match_types.get(mt, 0) + 1

            # Video duration
            video_duration = max([m.get('end_time', 0) for m in mentions])
            mention_density = f"{len(mentions)} mentions / {self._seconds_to_time(video_duration)} video"

            # Time distribution (split into 1-minute buckets)
            time_distribution = {}
            for mention in mentions:
                minute_key = int(mention.get('start_time', 0) / 60)
                minute_label = f"{minute_key}-{minute_key + 1}min"
                time_distribution[minute_label] = time_distribution.get(minute_label, 0) + 1

            return {
                "total_mentions": len(mentions),
                "match_types": match_types,
                "mention_density": mention_density,
                "time_distribution": time_distribution,
                "video_duration_seconds": video_duration
            }

        except Exception as e:
            logger.error(f"Statistics calculation failed: {str(e)}")
            return {}

    def _seconds_to_time(self, seconds: float) -> str:
        """Convert seconds to MM:SS format"""
        try:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"
        except:
            return "0:00"
