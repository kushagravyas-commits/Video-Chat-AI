"""
Audio Transcription Module using Local Whisper
Generates transcripts with timestamps and speaker identification
No API key needed - uses open-source Whisper model
"""

import os
from pathlib import Path
from typing import Dict, List
import json
import logging
import whisper
from datetime import datetime

logger = logging.getLogger(__name__)

class Transcriber:
    def __init__(self, model_name: str = "base"):
        """
        Initialize transcriber with local Whisper model (lazy-loaded)

        Args:
            model_name: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
                       base = good balance of speed and accuracy
        """
        self.model_name = model_name
        self.model = None  # Lazy-load on first use
        logger.info(f"Transcriber initialized with model: {model_name} (will load on first use)")

    def detect_language(self, audio_path: str) -> tuple:
        """
        Detect the language of an audio file using Whisper's built-in detection.
        Analyzes the first 30 seconds of audio.

        Args:
            audio_path: Path to audio file

        Returns:
            Tuple of (language_code, confidence) e.g. ("hi", 0.97)
        """
        # Lazy-load the model
        if self.model is None:
            logger.info(f"Loading local Whisper model for language detection: {self.model_name}")
            self.model = whisper.load_model(self.model_name)

        # Load and preprocess first 30 seconds
        audio = whisper.load_audio(audio_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(self.model.device)

        # Detect language
        _, probs = self.model.detect_language(mel)
        detected_lang = max(probs, key=probs.get)
        confidence = probs[detected_lang]

        logger.info(f"Language detection: {detected_lang} (confidence: {confidence:.2f})")
        return detected_lang, confidence

    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "auto",
        verbose: bool = False
    ) -> Dict:
        """
        Transcribe audio using local Whisper model.
        Auto-detects language and translates non-English to English.

        Args:
            audio_path: Path to audio file (MP3, WAV, etc.)
            language: Language code ('en', 'hi', etc.) or 'auto' for auto-detection
            verbose: Enable verbose output

        Returns:
            Dictionary with transcript, segments, and metadata
        """
        try:
            # Lazy-load the model on first use
            if self.model is None:
                logger.info(f"Loading local Whisper model on first use: {self.model_name}")
                self.model = whisper.load_model(self.model_name)
                logger.info(f"Whisper model '{self.model_name}' loaded successfully (no API key needed!)")

            # Auto-detect language if set to "auto"
            original_language = language
            if language == "auto":
                detected_lang, confidence = self.detect_language(audio_path)
                language = detected_lang
                logger.info(f"Auto-detected language: {language} (confidence: {confidence:.2f})")

            logger.info(f"Transcribing audio: {audio_path}")
            logger.info(f"Language: {language}")

            # Transcribe in the NATIVE language (Hindi → Hindi text, English → English text)
            result = self.model.transcribe(
                audio_path,
                language=language,
                verbose=verbose
            )

            logger.info("Transcription completed")

            # Process Whisper response into our format
            processed = self._process_whisper_response(result)

            # If non-English, translate to English using Gemini
            if language != 'en':
                logger.info(f"Non-English transcript detected ({language}). Translating to English...")
                processed = self.translate_transcript_to_english(processed)
                logger.info("Translation to English completed")

            return processed

        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
            raise

    def _process_whisper_response(self, whisper_response) -> Dict:
        """
        Convert Whisper response to our transcript format

        Args:
            whisper_response: Response from local Whisper model

        Returns:
            Formatted transcript dictionary
        """

        segments = []

        for i, segment in enumerate(whisper_response.get('segments', [])):
            processed_segment = {
                'segment_id': i,
                'text': segment.get('text', '').strip(),
                'start_time': segment.get('start', 0),
                'end_time': segment.get('end', 0),
                'confidence': segment.get('confidence', 0.95),
                'speaker': self._detect_speaker(segment, i),  # Basic speaker detection
                'embedding': None  # Will be filled in RAG processing
            }
            segments.append(processed_segment)

        transcript_data = {
            'transcript_id': self._generate_transcript_id(),
            'full_text': whisper_response.get('text', ''),
            'language': whisper_response.get('language', 'en'),
            'duration': max([s.get('end', 0) for s in segments], default=0),
            'segments': segments,
            'metadata': {
                'transcribed_at': datetime.now().isoformat(),
                'whisper_model': f'whisper-{self.model_name}',
                'whisper_type': 'local (free)',
                'total_segments': len(segments)
            }
        }

        logger.info(f"Processed {len(segments)} segments")

        return transcript_data

    def _detect_speaker(self, segment: Dict, segment_id: int) -> str:
        """
        Basic speaker detection
        In production, use pyannote.audio for better speaker diarization

        Args:
            segment: Whisper segment
            segment_id: Segment index

        Returns:
            Speaker name/ID
        """
        # TODO: Implement proper speaker diarization using pyannote
        # For now, use simple heuristic

        return f"Speaker_1"  # Placeholder

    def _generate_transcript_id(self) -> str:
        """Generate unique transcript ID"""
        import uuid
        return str(uuid.uuid4())

    def transcribe_with_diarization(
        self,
        audio_path: str,
        language: str = "en"
    ) -> Dict:
        """
        Transcribe with speaker diarization (requires pyannote.audio)

        Args:
            audio_path: Path to audio file
            language: Language code

        Returns:
            Transcript with speaker identification
        """
        try:
            from pyannote.audio import Pipeline

            logger.info("Starting transcription with speaker diarization")

            # First, get base transcription
            transcript_data = self.transcribe_audio(audio_path, language)

            # Initialize speaker diarization pipeline
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv('HUGGING_FACE_TOKEN')
            )

            # Run diarization
            diarization = pipeline(audio_path)

            # Match diarization with transcript segments
            transcript_data = self._match_speakers_with_segments(
                transcript_data,
                diarization
            )

            return transcript_data

        except ImportError:
            logger.warning("pyannote.audio not installed, skipping speaker diarization")
            return self.transcribe_audio(audio_path, language)
        except Exception as e:
            logger.error(f"Error with speaker diarization: {str(e)}")
            return self.transcribe_audio(audio_path, language)

    def _match_speakers_with_segments(
        self,
        transcript_data: Dict,
        diarization
    ) -> Dict:
        """
        Match speaker diarization output with transcript segments
        """

        for segment in transcript_data['segments']:
            start_time = segment['start_time']
            end_time = segment['end_time']

            # Find which speaker is active during this segment
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                if turn.start <= start_time and turn.end >= end_time:
                    segment['speaker'] = speaker
                    break

        return transcript_data

    def save_transcript(self, transcript_data: Dict, output_path: str):
        """
        Save transcript to JSON file

        Args:
            transcript_data: Transcript dictionary
            output_path: Path to save JSON
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Transcript saved to: {output_path}")

    def translate_transcript_to_english(self, transcript_data: Dict) -> Dict:
        """
        Translate a native language (e.g. Hindi) transcript to perfect English 
        using gemini-2.5-flash-lite via OpenRouter, maintaining timestamps.
        
        Args:
            transcript_data: The native transcript dictionary
            
        Returns:
            A new translated transcript dictionary
        """
        try:
            from openai import OpenAI
            import copy
            
            api_key = os.getenv('OPENROUTER_API_KEY')
            if not api_key:
                logger.warning("OPENROUTER_API_KEY missing, skipping translation.")
                return transcript_data
                
            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            
            logger.info("Starting translation of transcript to English using gemini-2.5-flash-lite...")
            translated_data = copy.deepcopy(transcript_data)
            translated_data['language'] = 'en'
            translated_data['metadata']['translated_at'] = datetime.now().isoformat()
            translated_data['metadata']['translator_model'] = 'google/gemini-2.5-flash-lite'
            
            # Translate segments in batches to avoid enormous prompts or missing context
            # A batch size of 20-30 segments usually works well
            batch_size = 20
            segments = translated_data['segments']
            
            for i in range(0, len(segments), batch_size):
                batch = segments[i:i+batch_size]
                
                # Format batch for prompt
                batch_text = []
                for idx, seg in enumerate(batch):
                    batch_text.append(f"[{idx}] {seg['text']}")
                
                prompt = (
                    "You are a professional translator specializing in South Asian languages. "
                    "The following script is an ASR (speech-to-text) output of a Hindi/Urdu video. "
                    "Because Hindi and Urdu sound similar, the text might be written in Urdu script, Devanagari script, or English script. "
                    "Regardless of the input script, your job is to translate EVERYTHING into perfect, fluent English. "
                    "Make sure to preserve strong political/cultural words accurately (like 'Dhurandhar' or 'Godi Media'). "
                    "Return ONLY the translated text, keeping the exact same bracketed index format e.g., '[0] English translation'.\n\n"
                    + "\n".join(batch_text)
                )
                
                response = client.chat.completions.create(
                    model="google/gemini-2.5-flash-lite",
                    messages=[
                        {"role": "system", "content": "You are a precise translator. You must output ONLY English text, maintaining the exact bracketed indices."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                
                translated_text = response.choices[0].message.content
                
                # Parse translated text back into segments
                import re
                lines = translated_text.strip().split('\n')
                for line in lines:
                    match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
                    if match:
                        local_idx = int(match.group(1))
                        translated_content = match.group(2)
                        if local_idx < len(batch):
                            batch[local_idx]['text'] = translated_content
                            
            # Update full_text
            translated_data['full_text'] = " ".join([seg['text'] for seg in translated_data['segments']])
            logger.info("Translation complete.")
            return translated_data
            
        except ImportError:
            logger.error("openai module not installed.")
            return transcript_data
        except Exception as e:
            logger.error(f"Error during translation: {e}")
            return transcript_data
