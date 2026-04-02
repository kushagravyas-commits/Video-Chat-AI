"""
LLM Response Generator Module
Uses Open Router for generating intelligent responses based on video context
"""

import os
from typing import Dict, List
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMGenerator:
    """Generate LLM responses using Open Router"""

    def __init__(self, api_key: str = None):
        """
        Initialize LLM Generator with OpenRouter

        Args:
            api_key: Open Router API key
        """
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')

        # Use fast, cost-effective model from Open Router
        self.model = "openai/gpt-4o-mini"

        # Initialize OpenAI client with OpenRouter base URL
        if self.api_key:
            try:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                logger.info("OpenAI client configured for OpenRouter API")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenRouter client: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("OPENROUTER_API_KEY not set. LLM generation will use fallback.")

    def generate_response(
        self,
        query: str,
        context: List[Dict],
        system_prompt: str = None
    ) -> Dict:
        """
        Generate LLM response based on video context

        Args:
            query: User query
            context: List of relevant chunks with timestamps
            system_prompt: Optional custom system prompt (uses default if not provided)

        Returns:
            Dictionary with response and metadata
        """
        try:
            logger.info(f"Generating LLM response for query: {query}")

            # Build context string from relevant chunks
            context_text = self._build_context(context)

            # Use default system prompt if not provided
            if not system_prompt:
                system_prompt = """You are a helpful assistant analyzing video content.
You have been provided with relevant excerpts from a video transcript.
Answer the user's question based on this context.
Be specific and reference timestamps when relevant.
Keep your answer concise and focused."""

            user_prompt = f"""Video Context:
{context_text}

User Question: {query}

Please answer the question based on the video context provided above.
Include relevant timestamps [hh:mm:ss] when referencing specific parts of the video."""

            # Call Open Router using OpenAI client
            response = self._call_openrouter(system_prompt, user_prompt)

            # Parse response
            result = {
                'query': query,
                'response': response,
                'model': self.model,
                'context_chunks': len(context),
                'status': 'success'
            }

            logger.info(f"LLM response generated successfully")
            return result

        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}")
            # Fallback: Generate response from context without LLM
            fallback_response = self._generate_fallback_response(query, context)
            return {
                'query': query,
                'response': fallback_response,
                'status': 'success_fallback',
                'note': 'Generated using context analysis (LLM API unavailable)'
            }

    def extract_highlights(
        self,
        query: str,
        context: List[Dict]
    ) -> Dict:
        """
        Extract key highlights from video based on query

        Args:
            query: What to highlight
            context: List of relevant chunks

        Returns:
            Dictionary with highlights and summary
        """
        try:
            logger.info(f"Extracting highlights for query: {query}")

            # Build context
            context_text = self._build_context(context)

            system_prompt = """You are an expert at identifying and extracting key highlights from video content.
Return your response as valid JSON with 'highlights' array and 'summary' string."""

            user_prompt = f"""Video Context:
{context_text}

Query: {query}

Extract key highlights and provide a summary. Return as JSON:
{{
  "highlights": [
    {{"text": "highlight text", "timestamp": "HH:MM:SS", "importance": 0.9}}
  ],
  "summary": "Summary of key points"
}}"""

            # Call Open Router
            response_text = self._call_openrouter(system_prompt, user_prompt)

            # Parse JSON response
            try:
                response_data = __import__('json').loads(response_text)
            except __import__('json').JSONDecodeError:
                logger.warning("Failed to parse LLM JSON response, using raw text")
                response_data = {
                    'highlights': [],
                    'summary': response_text
                }

            # Clean highlight boundaries to avoid splitting words/sentences
            highlights = response_data.get('highlights', [])
            cleaned_highlights = []

            for highlight in highlights:
                if isinstance(highlight, dict) and 'text' in highlight:
                    # Clean the highlight text boundaries
                    cleaned_text = self._clean_highlight_text(highlight['text'], context_text)
                    cleaned_highlight = highlight.copy()
                    cleaned_highlight['text'] = cleaned_text
                    cleaned_highlights.append(cleaned_highlight)
                else:
                    cleaned_highlights.append(highlight)

            result = {
                'query': query,
                'highlights': cleaned_highlights,
                'summary': response_data.get('summary', ''),
                'status': 'success'
            }

            logger.info(f"Extracted {len(result['highlights'])} highlights")
            return result

        except Exception as e:
            logger.error(f"Error extracting highlights: {str(e)}")
            return {
                'query': query,
                'highlights': [],
                'status': 'error',
                'error': str(e)
            }

    def _build_context(self, context: List[Dict]) -> str:
        """
        Build context string from relevant chunks

        Args:
            context: List of relevant chunks

        Returns:
            Formatted context string
        """
        context_lines = []

        for chunk in context:
            # Get timestamps
            start_time = chunk.get('metadata', {}).get('start_time', '0')
            end_time = chunk.get('metadata', {}).get('end_time', '0')
            speakers = chunk.get('metadata', {}).get('speakers', 'Unknown')

            # Format timestamp
            timestamp = f"[{self._format_timestamp(float(start_time))} - {self._format_timestamp(float(end_time))}]"

            # Add to context
            line = f"{timestamp} ({speakers}): {chunk['text']}"
            context_lines.append(line)

        return "\n".join(context_lines)

    def _clean_highlight_text(self, text: str, full_context: str) -> str:
        """
        Clean highlight text boundaries to avoid splitting words or sentences.
        Ensures highlights don't start/end in the middle of words or with partial sentences.

        Args:
            text: Original highlight text (may have partial words at boundaries)
            full_context: Full context text to find proper boundaries

        Returns:
            Cleaned highlight text with proper word/sentence boundaries
        """
        try:
            text = text.strip()
            if not text:
                return text

            # If text not found in context, return as-is (assume it's already clean)
            if text not in full_context:
                # Try to find partial match and adjust
                import re
                # Remove punctuation from ends and try to find match
                clean_text = text.rstrip('.,;:!?\'" ')
                if clean_text in full_context:
                    text = clean_text

            # Find the text in context
            idx = full_context.find(text)
            if idx == -1:
                return text

            # Adjust start: move forward to the start of a word
            start = idx
            while start > 0 and full_context[start - 1].isalnum():
                start += 1

            # Adjust end: move forward to the end of a word
            end = idx + len(text)
            while end < len(full_context) and full_context[end].isalnum():
                end += 1

            # Also try to align with sentence boundaries
            # Move to next period, question mark, or exclamation mark for sentence-level boundary
            sentence_end = end
            for i in range(end, min(end + 100, len(full_context))):
                if full_context[i] in '.!?':
                    sentence_end = i + 1
                    break

            # Prefer sentence boundary if it's not too far
            if sentence_end - end <= 50:  # Within 50 chars, use sentence boundary
                end = sentence_end

            # Extract cleaned text
            cleaned = full_context[start:end].strip()

            # Remove leading article/conjunction if extracted text starts oddly
            import re
            if re.match(r'^(and|but|or|the|a|an)\s+', cleaned, re.IGNORECASE):
                cleaned = re.sub(r'^(and|but|or|the|a|an)\s+', '', cleaned, flags=re.IGNORECASE).strip()

            logger.debug(f"Cleaned highlight: '{text}' -> '{cleaned}'")
            return cleaned if cleaned else text

        except Exception as e:
            logger.warning(f"Error cleaning highlight text: {str(e)}")
            return text

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _call_openrouter(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Open Router API using OpenAI client

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            Response text from LLM
        """
        try:
            if not self.client:
                raise Exception("OpenRouter client not initialized. Check OPENROUTER_API_KEY.")

            # Call using OpenAI client (with OpenRouter base URL)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000,
                extra_headers={
                    "HTTP-Referer": "http://localhost:5000",
                    "X-OpenRouter-Title": "Video Chat Application"
                }
            )

            # Extract message
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                logger.debug(f"LLM response received ({len(content)} chars)")
                return content

            logger.error(f"Unexpected response format: {response}")
            raise Exception("Unexpected response format from Open Router")

        except Exception as e:
            logger.error(f"Error calling Open Router: {str(e)}")
            raise

    def _generate_fallback_response(self, query: str, context: List[Dict]) -> str:
        """
        Generate a fallback response from context when LLM API is unavailable

        Args:
            query: User query
            context: List of relevant chunks

        Returns:
            Generated response based on context
        """
        if not context:
            return f"Cannot answer '{query}' - no context available."

        # Extract relevant information from context
        total_chunks = len(context)
        timestamps = []
        text_snippets = []

        for chunk in context:
            metadata = chunk.get('metadata', {})
            start_time = self._format_timestamp(metadata.get('start_time', 0))
            timestamps.append(start_time)
            text_snippets.append(chunk.get('text', '')[:100])

        # Build fallback response
        response = f"Based on the video content:\n\n"
        response += f"Found {total_chunks} relevant section(s) at timestamps: {', '.join(timestamps)}\n\n"
        response += "Key excerpts:\n"
        for i, snippet in enumerate(text_snippets, 1):
            response += f"• {snippet}...\n"

        response += f"\n(Note: This response was generated from context analysis. For AI-powered responses, please ensure your Open Router API key is configured correctly.)"

        return response
