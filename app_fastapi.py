"""
Main FastAPI Application for Video Chat
Handles video upload, processing, and RAG queries
Migrated from Flask to FastAPI for better performance and type safety
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import os
from dotenv import load_dotenv
import logging
from pathlib import Path
import json
import time

# Import our modules
from modules.video_processor import VideoProcessor
from modules.transcriber import Transcriber
from modules.rag_processor import RAGProcessor
from modules.llm_generator import LLMGenerator
from models.chroma_store import ChromaStore

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Video Chat API",
    description="Upload videos, transcribe, and chat with RAG",
    version="1.0.0"
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Emit stable per-request logs independent of uvicorn access logger."""
    start = time.perf_counter()
    logger.info(f"REQ START {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"REQ ERROR {request.method} {request.url.path} in {duration_ms:.2f}ms: {e}"
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"REQ END {request.method} {request.url.path} -> {response.status_code} in {duration_ms:.2f}ms"
    )
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount storage directory for static file serving
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Initialize modules
video_processor = VideoProcessor(storage_dir="./storage")
transcriber = Transcriber(model_name="base")  # Local Whisper - no API key needed!
rag_processor = RAGProcessor(api_key=os.getenv('OPENROUTER_API_KEY'))
llm_generator = LLMGenerator(api_key=os.getenv('OPENROUTER_API_KEY'))
chroma_store = ChromaStore(persist_dir=os.getenv('CHROMA_PERSIST_DIR', './chroma_data'))

# New MasterAgent for the service layer
from modules.agent import MasterAgent
agent_service = MasterAgent(api_key=os.getenv('OPENROUTER_API_KEY'), chroma_store=chroma_store)

# SQLite Store for relational metadata
from models.sqlite_store import SQLiteStore
sqlite_store = SQLiteStore(db_path="./storage/database.sqlite")

# Clip Trash Manager for soft-delete operations
from models.clip_trash_manager import ClipTrashManager
clip_trash_manager = ClipTrashManager(storage_dir="./storage")

# In-memory database for temporary storage during processing
IN_MEMORY_DATABASE = {}


# ============= PYDANTIC MODELS FOR REQUEST VALIDATION =============

class TranscribeRequest(BaseModel):
    """Request model for transcription endpoint"""
    audio_path: str
    video_id: str
    language: str = "auto"  # Auto-detect language, translate non-English to English


class ProcessRAGRequest(BaseModel):
    """Request model for RAG processing endpoint"""
    video_id: str


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    video_id: str
    query: str

class ChatAgentRequest(BaseModel):
    """Request for the new streaming agent chat"""
    query: str
    video_id: Optional[str] = None
    video_ids: Optional[List[str]] = None
    clear_history: Optional[bool] = False


class HighlightsRequest(BaseModel):
    """Request model for highlights extraction endpoint"""
    video_id: str
    query: str


class ClearCollectionRequest(BaseModel):
    """Request model for clearing collection"""
    collection_name: str


class CountMentionsRequest(BaseModel):
    """Request model for counting mentions in video(s)"""
    video_ids: List[str]
    search_query: str
    mode: Optional[str] = "hybrid"  # semantic, keyword, or hybrid
    confidence_threshold: Optional[float] = 0.7


class CreateClipsRequest(BaseModel):
    """Request model for creating clips from mentions"""
    video_id: str
    mentions: List[Dict]  # List of mention objects from count_mentions result
    clip_duration_before: Optional[float] = 2.0
    clip_duration_after: Optional[float] = 3.0
    smart_grouping: Optional[bool] = False
    grouping_threshold_seconds: Optional[float] = 7.0


# ============= EXCEPTION HANDLERS =============

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    import traceback
    logger.error(f"Internal server error: {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ============= STARTUP & SHUTDOWN EVENTS =============

@app.on_event("startup")
async def startup():
    """Initialize application on startup"""
    os.makedirs('./storage', exist_ok=True)
    os.makedirs('./logs', exist_ok=True)

    logger.info("=" * 50)
    logger.info("Starting Video Chat Application (FastAPI)")
    logger.info("=" * 50)
    logger.info(f"Open Router API Key configured: {bool(os.getenv('OPENROUTER_API_KEY'))}")
    logger.info(f"Chroma DB persist directory: {os.getenv('CHROMA_PERSIST_DIR', './chroma_data')}")

    # Initialize trash cleanup scheduler
    from modules.trash_cleanup_scheduler import TrashCleanupScheduler, create_cleanup_function
    cleanup_func = create_cleanup_function(sqlite_store, clip_trash_manager)
    trash_scheduler = TrashCleanupScheduler(cleanup_func=cleanup_func, interval_hours=24)
    trash_scheduler.start()
    app.state.trash_scheduler = trash_scheduler  # Store reference for shutdown


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("Shutting down Video Chat Application")
    # Stop trash scheduler if it exists
    if hasattr(app.state, 'trash_scheduler'):
        app.state.trash_scheduler.stop()


# ============= STEP 1: VIDEO DOWNLOAD & AUDIO EXTRACTION =============

@app.post('/api/upload', status_code=202)
async def upload_video(
    source: str = Form(...),
    youtube_url: Optional[str] = Form(None),
    user_id: str = Form("anonymous"),
    file: Optional[UploadFile] = File(None)
):
    """
    Upload video file or YouTube URL

    - **source**: "youtube" or "upload"
    - **youtube_url**: YouTube URL (required if source is youtube)
    - **file**: Video file (required if source is upload)
    - **user_id**: User identifier
    """
    try:
        logger.info(f"Processing video upload from user: {user_id}")

        # Validate source
        if source not in ['youtube', 'upload']:
            raise HTTPException(status_code=400, detail='Invalid source. Use "youtube" or "upload"')

        # Step 1: Download/Get Video
        if source == 'youtube':
            if not youtube_url:
                raise HTTPException(status_code=400, detail='YouTube URL required')

            video_path, metadata = video_processor.download_youtube(youtube_url)

        elif source == 'upload':
            if file is None:
                raise HTTPException(status_code=400, detail='Video file required')

            # Save uploaded file
            os.makedirs("./temp", exist_ok=True)
            temp_path = f"./temp/{file.filename}"

            # Save file to disk
            with open(temp_path, 'wb') as f:
                content = await file.read()
                f.write(content)

            video_path, metadata = video_processor.process_uploaded_video(temp_path, user_id)

        # Step 2: Extract Audio
        logger.info("Step 2: Extracting audio...")
        audio_path = video_processor.extract_audio(video_path)

        # Get video ID from the parent folder (e.g. youtube_123)
        video_id = Path(video_path).parent.name
        if not video_id.startswith('youtube_') and not video_id.startswith('uploaded_'):
            video_id = Path(video_path).stem

        # Save to SQLite
        try:
            url = youtube_url if source == 'youtube' else ''
            
            # Extract date if available (often YYYYMMDD in yt-dlp)
            pub_date = metadata.get('upload_date', '')
            if pub_date and len(pub_date) == 8:
                pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:]}"
                
            sqlite_store.upsert_video({
                'id': video_id,
                'title': metadata.get('title', 'Unknown'),
                'channel': metadata.get('channel', ''),
                'url': url,
                'published_at': pub_date,
                'video_path': str(video_path),
                'audio_path': str(audio_path)
            })
        except Exception as e:
            logger.error(f"Error saving video to SQLite: {e}")

        logger.info(f"Processing complete. Video: {video_path}, Audio: {audio_path}")

        return {
            'status': 'processing',
            'video_id': video_id,
            'video_path': str(video_path),
            'audio_path': str(audio_path),
            'metadata': metadata,
            'message': 'Video downloaded and audio extracted. Proceeding to transcription...'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= STEP 2: TRANSCRIPTION =============

@app.post('/api/transcribe')
async def transcribe_video(request_data: TranscribeRequest):
    """
    Transcribe audio to text using Whisper

    - **audio_path**: Path to audio file
    - **video_id**: Video identifier
    - **language**: Language code (en, hi, etc.)
    """
    try:
        audio_path = request_data.audio_path
        video_id = request_data.video_id
        language = request_data.language

        if not audio_path:
            raise HTTPException(status_code=400, detail='Audio path required')

        logger.info(f"Transcribing video {video_id} in language {language}")

        # Step 1: Transcribe with Whisper (Native language)
        logger.info("Step 3: Transcribing with Whisper (Native)...")
        transcript_data = transcriber.transcribe_audio(
            audio_path=audio_path,
            language=language
        )

        # Note: Translation is now handled inside transcribe_audio() automatically
        # when language is auto-detected as non-English

        # Store transcript in memory
        IN_MEMORY_DATABASE[video_id] = {
            'video_id': video_id,
            'transcript': transcript_data,
            'status': 'transcribed'
        }

        # Save to file
        transcript_file = f"./storage/transcripts/{video_id}_transcript.json"
        os.makedirs("./storage/transcripts", exist_ok=True)
        transcriber.save_transcript(transcript_data, transcript_file)

        # Update transcript path in SQLite
        try:
            sqlite_store.update_video_paths(video_id, transcript_path=transcript_file)
        except Exception as e:
            logger.error(f"Error updating transcript path in SQLite: {e}")

        return {
            'status': 'transcribed',
            'video_id': video_id,
            'transcript_summary': {
                'total_segments': len(transcript_data['segments']),
                'duration': transcript_data['duration'],
                'language': transcript_data['language'],
                'first_few_segments': transcript_data['segments'][:3]
            },
            'message': 'Transcription and translation complete. Proceeding to RAG processing...'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= STEP 3: RAG PROCESSING =============

@app.post('/api/process-rag')
async def process_rag(request_data: ProcessRAGRequest):
    """
    Process transcript for RAG (embeddings and chunking)

    - **video_id**: Video identifier
    """
    try:
        video_id = request_data.video_id

        if video_id not in IN_MEMORY_DATABASE:
            raise HTTPException(status_code=404, detail='Video not found')

        logger.info(f"Processing RAG for video {video_id}")

        # Get transcript
        transcript_data = IN_MEMORY_DATABASE[video_id]['transcript']

        # Step 1: Process for RAG (chunking + embeddings)
        logger.info("Step 4: Processing for RAG...")
        rag_data = rag_processor.process_transcript_for_rag(transcript_data)

        # Store RAG data
        IN_MEMORY_DATABASE[video_id]['rag_data'] = rag_data
        IN_MEMORY_DATABASE[video_id]['status'] = 'rag_processed'

        # Save RAG data to file
        rag_file = f"./storage/rag/{video_id}_rag.json"
        os.makedirs("./storage/rag", exist_ok=True)
        with open(rag_file, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, indent=2, default=str)

        # Save embeddings to Chroma DB (v1 - local all-minilm-l6-v2)
        logger.info("Saving v1 embeddings to Chroma DB...")
        chroma_store.add_embeddings(
            collection_name='video_transcripts',
            video_id=video_id,
            chunks=rag_data['chunks']
        )
        chroma_store.persist()

        # Also generate v2 embeddings (Qwen3 via OpenRouter) for semantic search
        try:
            if agent_service.openrouter_embedder:
                logger.info("Generating v2 (Qwen3) embeddings for semantic search...")
                v2_count = rag_processor.reembed_transcript_for_v2(
                    video_id=video_id,
                    openrouter_embedder=agent_service.openrouter_embedder,
                    chroma_store=chroma_store,
                    title=IN_MEMORY_DATABASE[video_id].get('metadata', {}).get('title', 'Unknown'),
                    channel=IN_MEMORY_DATABASE[video_id].get('metadata', {}).get('channel', ''),
                    youtube_url=IN_MEMORY_DATABASE[video_id].get('metadata', {}).get('url', '')
                )
                logger.info(f"V2 embeddings generated: {v2_count} chunks")
        except Exception as e:
            logger.warning(f"V2 embedding generation failed (non-critical): {e}")

        return {
            'status': 'rag_processed',
            'video_id': video_id,
            'rag_summary': {
                'total_segments': len(rag_data['segments']),
                'total_chunks': len(rag_data['chunks']),
                'embedding_model': rag_data['metadata']['embedding_model'],
            },
            'message': 'RAG processing complete. Video ready for queries!'
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error processing RAG: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= STEP 4: CHAT / QUERIES =============

@app.post('/api/chat')
async def chat(request_data: ChatRequest):
    """
    Chat about the video / Ask questions

    - **video_id**: Video identifier
    - **query**: Question about the video
    """
    try:
        video_id = request_data.video_id
        query = request_data.query

        if not query:
            raise HTTPException(status_code=400, detail='Query required')

        if video_id not in IN_MEMORY_DATABASE:
            raise HTTPException(status_code=404, detail='Video not found')

        if IN_MEMORY_DATABASE[video_id].get('status') != 'rag_processed':
            raise HTTPException(status_code=400, detail='Video not ready. Complete RAG processing first.')

        logger.info(f"Processing query for video {video_id}: {query}")

        # Get RAG data from memory for query embedding
        rag_data = IN_MEMORY_DATABASE[video_id]['rag_data']

        # Step 1: Generate query embedding using Open Router
        logger.info("Generating query embedding with Open Router...")
        query_embedding = rag_processor.generate_embedding(query)

        # Step 2: Retrieve relevant segments from Chroma DB
        logger.info("Retrieving relevant segments from Chroma DB...")
        relevant_chunks = chroma_store.search(
            collection_name='video_transcripts',
            query_embedding=query_embedding,
            video_id=video_id,
            top_k=5
        )

        logger.info(f"Found {len(relevant_chunks)} relevant chunks from Chroma DB")

        # Step 3: Generate LLM response
        logger.info("Generating LLM response with Open Router...")
        llm_response = llm_generator.generate_response(
            query=query,
            context=relevant_chunks
        )

        return {
            'status': 'success',
            'query': query,
            'video_id': video_id,
            'relevant_chunks': relevant_chunks,
            'llm_response': llm_response,
            'message': 'Chat response generated successfully using Open Router LLM'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= AGENT CHAT (STREAMING / SSE) =============

@app.post('/api/agent-chat')
async def agent_chat(request_data: ChatAgentRequest):
    """
    Streamed chat using the MasterAgent (Service Layer)
    Returns Server-Sent Events (SSE)
    Supports single video_id or multiple video_ids for cross-video search
    """
    try:
        if not request_data.query:
            raise HTTPException(status_code=400, detail="Query is required")

        if request_data.clear_history:
            agent_service.clear_conversation()

        # DEBUG: Log what the frontend sends
        logger.info(f"[AGENT-CHAT] query='{request_data.query}', video_id={request_data.video_id}, video_ids={request_data.video_ids}")

        # Store reference video IDs in session for multi-video search
        if request_data.video_ids and len(request_data.video_ids) > 0:
            agent_service.session_data['reference_video_ids'] = request_data.video_ids
            # Set active video to the first one in the list
            agent_service.session_data['last_video_id'] = request_data.video_ids[0]
        elif request_data.video_id:
            # Single video mode (backward compatibility)
            agent_service.session_data['reference_video_ids'] = [request_data.video_id]
            agent_service.session_data['last_video_id'] = request_data.video_id
        else:
            # No videos provided - CLEAR the reference video IDs
            # This handles the case when user removes all reference videos
            agent_service.session_data['reference_video_ids'] = []
            agent_service.session_data['last_video_id'] = None

        # Use a queue to bridge sync agent callbacks to async stream
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def agent_callback(data):
            # This runs in the agent's thread, so we use the captured 'loop' from the main thread
            loop.call_soon_threadsafe(queue.put_nowait, data)

        async def event_generator():
            # Start agent in a background thread
            agent_task = asyncio.create_task(asyncio.to_thread(agent_service.chat, request_data.query))

            # Set the callback
            agent_service.callback = agent_callback

            # Monitor the queue and yield events
            try:
                while True:
                    # Wait for data or completion
                    if queue.empty() and agent_task.done():
                        break

                    try:
                        # Short timeout to check if task is done
                        data = await asyncio.wait_for(queue.get(), timeout=0.1)
                        yield f"data: {json.dumps(data)}\n\n"
                        queue.task_done()
                    except asyncio.TimeoutError:
                        continue

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            finally:
                agent_service.callback = None
                # Await agent task safely so task exceptions don't collapse SSE into HTTP 500
                try:
                    await agent_task
                except Exception as e:
                    logger.error(f"Agent task failed during SSE stream: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Agent task failed: {str(e)}'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/api/agent-chat failed before stream start: {e}")
        raise HTTPException(status_code=500, detail=f"agent-chat failed: {str(e)}")


# ============= STEP 4B: MENTION COUNTING =============

@app.post('/api/count-mentions')
async def count_mentions(request_data: CountMentionsRequest):
    """
    Count mentions of a term/concept in video(s)

    - **video_ids**: List of video IDs to search
    - **search_query**: What to search for (entity, concept, term)
    - **mode**: Search mode (semantic, keyword, hybrid)
    - **confidence_threshold**: Minimum confidence score (0.0-1.0)

    Returns list of mentions with timestamps and statistics
    """
    try:
        if not request_data.video_ids or not request_data.search_query:
            raise HTTPException(
                status_code=400,
                detail="video_ids and search_query are required"
            )

        logger.info(f"Counting mentions of '{request_data.search_query}' in {len(request_data.video_ids)} video(s)")

        # Create mention counter using agent's services
        from modules.mention_counter import MentionCounter

        counter = MentionCounter(chroma_store, agent_service.rag_processor, agent_service.openrouter_embedder)

        # Count mentions
        result = counter.count_mentions(
            video_ids=request_data.video_ids,
            search_query=request_data.search_query,
            mode=request_data.mode,
            confidence_threshold=request_data.confidence_threshold
        )

        return {
            "status": "success",
            "data": result
        }

    except ValueError as e:
        logger.error(f"Validation error in count_mentions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error counting mentions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to count mentions: {str(e)}"
        )


# ============= STEP 4C: CLIP GENERATION FROM MENTIONS =============

@app.post('/api/create-clips-from-mentions')
async def create_clips_from_mentions(request_data: CreateClipsRequest):
    """
    Create video clips from mention timestamps

    - **video_id**: Video ID to create clips from
    - **mentions**: List of mentions (from count_mentions result)
    - **clip_duration_before**: Seconds to include before mention (default: 2.0)
    - **clip_duration_after**: Seconds to include after mention (default: 3.0)
    - **smart_grouping**: Whether to group nearby mentions (default: False)
    - **grouping_threshold_seconds**: Group mentions within this many seconds (default: 7.0)

    Returns list of created clips with metadata
    """
    try:
        if not request_data.video_id or not request_data.mentions:
            raise HTTPException(
                status_code=400,
                detail="video_id and mentions are required"
            )

        logger.info(
            f"Creating clips from {len(request_data.mentions)} mentions "
            f"(grouping={request_data.smart_grouping})"
        )

        # Create clip generator
        from modules.clip_generator import ClipGenerator

        clip_generator = ClipGenerator(storage_dir="./storage")

        # Get video path from agent's session or disk
        video_path = agent_service.session_data.get('last_video_path', '')

        # If not in session, try to find on disk
        if not video_path or not os.path.exists(video_path):
            from pathlib import Path
            potential_dirs = [
                Path("./storage/videos") / request_data.video_id,
                Path("./storage/videos") / request_data.video_id.replace('youtube_', '')
            ]

            for potential_dir in potential_dirs:
                if potential_dir.exists():
                    for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
                        v_file = potential_dir / f"video{ext}" if ext else potential_dir / "video"
                        if v_file.exists():
                            video_path = str(v_file.resolve())
                            break
                if video_path:
                    break

        if not video_path or not os.path.exists(video_path):
            raise HTTPException(
                status_code=404,
                detail=f"Could not find video file for {request_data.video_id}"
            )

        # Create clips
        result = clip_generator.create_clips_from_mentions(
            video_id=request_data.video_id,
            video_path=video_path,
            mentions=request_data.mentions,
            clip_duration_before=request_data.clip_duration_before,
            clip_duration_after=request_data.clip_duration_after,
            smart_grouping=request_data.smart_grouping,
            grouping_threshold_seconds=request_data.grouping_threshold_seconds
        )

        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to create clips")
            )

        return {
            "status": "success",
            "data": result
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in create_clips: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating clips: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create clips: {str(e)}"
        )


# ============= STEP 5: HIGHLIGHT EXTRACTION =============

@app.post('/api/highlights')
async def extract_highlights(request_data: HighlightsRequest):
    """
    Extract key highlights from video based on query

    - **video_id**: Video identifier
    - **query**: What to highlight (e.g., "main points", "key findings")
    """
    try:
        video_id = request_data.video_id
        query = request_data.query

        if not query:
            raise HTTPException(status_code=400, detail='Query required')

        if video_id not in IN_MEMORY_DATABASE:
            raise HTTPException(status_code=404, detail='Video not found')

        if IN_MEMORY_DATABASE[video_id].get('status') != 'rag_processed':
            raise HTTPException(status_code=400, detail='Video not ready. Complete RAG processing first.')

        logger.info(f"Extracting highlights for video {video_id}: {query}")

        # Get RAG data
        rag_data = IN_MEMORY_DATABASE[video_id]['rag_data']

        # Step 1: Generate query embedding
        logger.info("Generating query embedding...")
        query_embedding = rag_processor.generate_embedding(query)

        # Step 2: Retrieve relevant segments
        logger.info("Retrieving relevant segments...")
        relevant_chunks = chroma_store.search(
            collection_name='video_transcripts',
            query_embedding=query_embedding,
            video_id=video_id,
            top_k=5
        )

        logger.info(f"Found {len(relevant_chunks)} relevant chunks")

        # Step 3: Extract highlights using LLM
        logger.info("Extracting highlights with LLM...")
        highlights_result = llm_generator.extract_highlights(
            query=query,
            context=relevant_chunks
        )

        return {
            'status': 'success',
            'video_id': video_id,
            'query': query,
            'highlights': highlights_result.get('highlights', []),
            'summary': highlights_result.get('summary', ''),
            'relevant_chunks_count': len(relevant_chunks)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting highlights: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= CHROMA DB MANAGEMENT ENDPOINTS =============

@app.get('/api/chroma/collections')
async def list_chroma_collections():
    """List all Chroma DB collections"""
    try:
        collections = chroma_store.list_collections()
        return {
            'collections': collections,
            'total': len(collections)
        }
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/chroma/collection-info/{collection_name}')
async def get_collection_info(collection_name: str):
    """Get information about a Chroma collection"""
    try:
        info = chroma_store.get_collection_info(collection_name)
        return info
    except Exception as e:
        logger.error(f"Error getting collection info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/chroma/clear/{collection_name}')
async def clear_collection(collection_name: str):
    """Clear all embeddings from a collection"""
    try:
        chroma_store.clear_collection(collection_name)
        return {
            'status': 'success',
            'message': f'Collection {collection_name} cleared'
        }
    except Exception as e:
        logger.error(f"Error clearing collection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= UTILITY ENDPOINTS =============

@app.get('/api/status/{video_id}')
async def get_status(video_id: str):
    """Get processing status of a video"""
    if video_id in IN_MEMORY_DATABASE:
        return {
            'video_id': video_id,
            'status': IN_MEMORY_DATABASE[video_id].get('status'),
        }
    else:
        raise HTTPException(status_code=404, detail='Video not found')

@app.get('/api/videos')
async def list_videos():
    """List all processed videos from SQLite store"""
    try:
        videos = sqlite_store.get_all_videos()

        return {
            'status': 'success',
            'videos': videos,
            'total': len(videos)
        }
    except Exception as e:
        logger.error(f"Error listing videos from SQLite: {str(e)}")
        return {
            'status': 'error',
            'videos': [],
            'total': 0,
            'message': str(e)
        }


@app.get('/api/clips')
async def list_clips():
    """List all clips from storage/clips directory"""
    try:
        clips = []
        clips_dir = Path('./storage/clips')

        # Create directory if it doesn't exist
        clips_dir.mkdir(parents=True, exist_ok=True)

        # Get all video files from clips directory
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}

        # List all files in the clips directory
        if clips_dir.exists():
            clip_files = [f for f in clips_dir.iterdir() if f.is_file() and f.suffix.lower() in video_extensions]

            # Sort by modification time (newest first)
            clip_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Create clip objects
            for idx, clip_file in enumerate(clip_files, 1):
                stat = clip_file.stat()
                created_time = stat.st_mtime

                # Calculate time ago
                import time
                time_diff = time.time() - created_time
                if time_diff < 60:
                    time_ago = "just now"
                elif time_diff < 3600:
                    time_ago = f"{int(time_diff/60)} minutes ago"
                elif time_diff < 86400:
                    time_ago = f"{int(time_diff/3600)} hours ago"
                else:
                    time_ago = f"{int(time_diff/86400)} days ago"

                # Determine clip_id to find metadata
                # Format is {clip_id}_{YYYYMMDD}_{HHMMSS}.mp4
                parts = clip_file.stem.split('_')
                if len(parts) >= 3:
                    clip_id = '_'.join(parts[:-2])
                else:
                    clip_id = clip_file.stem
                    
                metadata_path = Path('./storage/clips/metadata') / f"{clip_id}_metadata.json"
                
                # Default estimation (only if ffprobe fails)
                size_mb = stat.st_size / (1024 * 1024)
                duration_str = f"{max(1, int(size_mb/5))}:00"
                
                if metadata_path.exists():
                    try:
                        import json
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                            dur_sec = metadata.get("duration", 0)
                            if dur_sec:
                                m = int(dur_sec // 60)
                                s = int(dur_sec % 60)
                                duration_str = f"{m}:{s:02d}"
                    except Exception as e:
                        logger.error(f"Error reading metadata for {clip_file.name}: {e}")
                else:
                    # Self-heal: Run ffprobe to get exact duration and save to metadata
                    try:
                        import subprocess
                        logger.info(f"Metadata missing for {clip_file.name}, running ffprobe to self-heal.")
                        cmd = [
                            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                            "-of", "default=noprint_wrappers=1:nokey=1", str(clip_file)
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
                        if result.stdout.strip():
                            dur_sec = float(result.stdout.strip())
                            m = int(dur_sec // 60)
                            s = int(dur_sec % 60)
                            duration_str = f"{m}:{s:02d}"
                            
                            # Cache it
                            try:
                                import json
                                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                                with open(metadata_path, 'w') as f:
                                    json.dump({"duration": dur_sec, "self_healed": True}, f, indent=2)
                            except Exception as me:
                                logger.error(f"Failed to save healed metadata for {clip_file.name}: {me}")
                    except Exception as e:
                        logger.error(f"Failed to run ffprobe for fallback duration of {clip_file.name}: {e}")

                clip_obj = {
                    'id': idx,
                    'title': clip_file.stem.replace('_', ' '),  # Cleaner title
                    'duration': duration_str,
                    'created': time_ago,
                    'videoId': f'clip-{clip_file.stem}',
                    'youtubeUrl': f'/api/clips/stream/{clip_file.name}',
                    'isLocal': True
                }
                clips.append(clip_obj)

        return {
            'status': 'success',
            'clips': clips,
            'total': len(clips)
        }
    except Exception as e:
        logger.error(f"Error listing clips: {str(e)}")
        return {
            'status': 'error',
            'clips': [],
            'total': 0,
            'message': str(e)
        }


@app.get('/api/clips/stream/{filename}')
async def stream_clip(filename: str):
    """Stream a clip video file"""
    try:
        clip_path = Path('./storage/clips') / filename

        # Security: Ensure the file is in the clips directory (prevent directory traversal)
        if not clip_path.resolve().parent.resolve() == Path('./storage/clips').resolve():
            raise HTTPException(status_code=403, detail="Access denied")

        if not clip_path.exists():
            raise HTTPException(status_code=404, detail="Clip not found")

        # Return file as stream
        def file_stream():
            with open(clip_path, 'rb') as f:
                while True:
                    chunk = f.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            file_stream(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming clip: {str(e)}")
        raise HTTPException(status_code=500, detail="Error streaming clip")


@app.get('/api/db-stats')
async def db_stats():
    """Get database statistics"""
    try:
        # Get Chroma DB stats
        collections = chroma_store.list_collections()
        stats = {
            'vector_store': 'Chroma DB',
            'collections': collections,
            'total_collections': len(collections),
            'status': 'Connected'
        }

        # Add collection details
        for collection_name in collections:
            info = chroma_store.get_collection_info(collection_name)
            stats[f'{collection_name}_count'] = info['count']

        return stats
    except Exception as e:
        logger.error(f"Error getting db stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= CHROMADB CLEANUP HELPERS =============

def _remove_video_from_chromadb(video_id: str):
    """Remove a video's embeddings from ALL ChromaDB collections (v1, v2, visual)."""
    from models.chroma_store import VIDEO_TRANSCRIPTS_V2, VIDEO_VISUAL_EMBEDDINGS

    for collection_name in ['video_transcripts', VIDEO_TRANSCRIPTS_V2, VIDEO_VISUAL_EMBEDDINGS]:
        try:
            collection = chroma_store.client.get_collection(name=collection_name)
            results = collection.get(where={"video_id": {"$eq": video_id}})
            if results['ids']:
                collection.delete(ids=results['ids'])
                logger.info(f"Removed {len(results['ids'])} embeddings from '{collection_name}' for {video_id}")
        except Exception as e:
            logger.debug(f"Could not clean {collection_name} for {video_id}: {e}")


def _reembed_video_to_chromadb(video_id: str):
    """Re-embed a recovered video into ChromaDB collections (v1 + v2)."""
    import json

    transcript_path = f"./storage/transcripts/{video_id}_transcript.json"
    if not os.path.exists(transcript_path):
        logger.warning(f"Cannot re-embed {video_id}: transcript not found at {transcript_path}")
        return

    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)

        # Get video metadata
        video_record = sqlite_store.get_video(video_id)
        title = video_record.get('title', 'Unknown') if video_record else 'Unknown'
        channel = video_record.get('channel', '') if video_record else ''
        youtube_url = video_record.get('url', '') if video_record else ''

        # Re-process for v1 embeddings (local all-minilm-l6-v2)
        rag_data = rag_processor.process_transcript_for_rag(transcript_data)
        chroma_store.add_embeddings(
            collection_name='video_transcripts',
            video_id=video_id,
            chunks=rag_data['chunks'],
            title=title,
            channel=channel,
            youtube_url=youtube_url
        )
        logger.info(f"Re-embedded {len(rag_data['chunks'])} v1 chunks for {video_id}")

        # Re-process for v2 embeddings (Qwen3 via OpenRouter)
        if agent_service.openrouter_embedder:
            v2_count = rag_processor.reembed_transcript_for_v2(
                video_id=video_id,
                openrouter_embedder=agent_service.openrouter_embedder,
                chroma_store=chroma_store,
                title=title,
                channel=channel,
                youtube_url=youtube_url
            )
            logger.info(f"Re-embedded {v2_count} v2 chunks for {video_id}")

    except Exception as e:
        logger.error(f"Failed to re-embed {video_id}: {e}")


# ============= TRASH & SOFT-DELETE OPERATIONS =============

@app.post('/api/videos/{video_id}/delete')
async def delete_video(video_id: str):
    """Soft delete a video (move to trash, recoverable for 10 days)"""
    try:
        if sqlite_store.soft_delete_video(video_id):
            # Also remove embeddings from ALL ChromaDB collections
            # so the agent doesn't think the video is still available
            _remove_video_from_chromadb(video_id)
            return {'status': 'success', 'message': f'Video {video_id} moved to trash'}
        else:
            raise HTTPException(status_code=404, detail=f'Video {video_id} not found')
    except Exception as e:
        logger.error(f"Error deleting video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/clips/{clip_id}/delete')
async def delete_clip(clip_id: str):
    """Soft delete a clip (move to trash, recoverable for 10 days)"""
    try:
        # Find the clip file
        clips_dir = Path('./storage/clips')
        clip_files = [f for f in clips_dir.iterdir() if f.is_file() and f.stem == clip_id and f.suffix.lower() in {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}]

        if not clip_files:
            raise HTTPException(status_code=404, detail=f'Clip {clip_id} not found')

        clip_file = clip_files[0]
        if clip_trash_manager.soft_delete_clip(clip_file.name, clip_file):
            return {'status': 'success', 'message': f'Clip {clip_id} moved to trash'}
        else:
            raise HTTPException(status_code=500, detail='Failed to delete clip')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting clip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/trash')
async def get_trash():
    """Get all items in trash (deleted videos and clips)"""
    try:
        trash_videos = sqlite_store.get_trash_videos()
        trash_clips = clip_trash_manager.get_trash_clips()

        return {
            'status': 'success',
            'videos': trash_videos,
            'clips': trash_clips,
            'total_videos': len(trash_videos),
            'total_clips': len(trash_clips)
        }
    except Exception as e:
        logger.error(f"Error getting trash: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/trash/videos/{video_id}/recover')
async def recover_deleted_video(video_id: str):
    """Recover a deleted video from trash and re-embed into ChromaDB"""
    try:
        if sqlite_store.recover_video(video_id):
            # Re-embed into ChromaDB so the agent can find it again
            _reembed_video_to_chromadb(video_id)
            return {'status': 'success', 'message': f'Video {video_id} recovered and re-indexed'}
        else:
            raise HTTPException(status_code=404, detail=f'Video {video_id} not found in trash')
    except Exception as e:
        logger.error(f"Error recovering video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/trash/clips/{clip_filename}/recover')
async def recover_deleted_clip(clip_filename: str):
    """Recover a deleted clip from trash"""
    try:
        if clip_trash_manager.recover_clip(clip_filename):
            return {'status': 'success', 'message': f'Clip {clip_filename} recovered from trash'}
        else:
            raise HTTPException(status_code=404, detail=f'Clip {clip_filename} not found in trash')
    except Exception as e:
        logger.error(f"Error recovering clip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/api/trash/videos/{video_id}')
async def permanently_delete_video(video_id: str):
    """Permanently delete a video from trash"""
    try:
        # First check if it's in trash
        video = sqlite_store.get_video(video_id)
        if not video or not video.get('is_deleted'):
            raise HTTPException(status_code=404, detail=f'Video {video_id} not found in trash')

        if sqlite_store.permanently_delete_video(video_id):
            # Also delete associated files
            video_path = video.get('video_path')
            audio_path = video.get('audio_path')
            transcript_path = video.get('transcript_path')

            for path in [video_path, audio_path, transcript_path]:
                if path and Path(path).exists():
                    try:
                        Path(path).unlink()
                    except Exception as e:
                        logger.warning(f"Could not delete file {path}: {e}")

            # Ensure ChromaDB embeddings are removed too
            _remove_video_from_chromadb(video_id)

            return {'status': 'success', 'message': f'Video {video_id} permanently deleted'}
        else:
            raise HTTPException(status_code=500, detail='Failed to permanently delete video')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error permanently deleting video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/api/trash/clips/{clip_filename}')
async def permanently_delete_clip(clip_filename: str):
    """Permanently delete a clip from trash"""
    try:
        if clip_trash_manager.permanently_delete_clip(clip_filename):
            return {'status': 'success', 'message': f'Clip {clip_filename} permanently deleted'}
        else:
            raise HTTPException(status_code=404, detail=f'Clip {clip_filename} not found in trash')
    except Exception as e:
        logger.error(f"Error permanently deleting clip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/trash/cleanup')
async def cleanup_expired_trash():
    """Cleanup expired items from trash (items older than 10 days)"""
    try:
        from datetime import datetime, timedelta

        # Cleanup expired clips
        expired_clips_count = clip_trash_manager.auto_delete_expired_clips()

        # Cleanup expired videos
        expired_videos_count = 0
        trash_videos = sqlite_store.get_trash_videos()
        cutoff_date = (datetime.now() - timedelta(days=10)).isoformat()

        for video in trash_videos:
            if video.get('deleted_at') and video['deleted_at'] < cutoff_date:
                if sqlite_store.permanently_delete_video(video['id']):
                    expired_videos_count += 1

        return {
            'status': 'success',
            'expired_videos_deleted': expired_videos_count,
            'expired_clips_deleted': expired_clips_count,
            'message': f'Cleaned up {expired_videos_count} videos and {expired_clips_count} clips from trash'
        }
    except Exception as e:
        logger.error(f"Error cleaning up trash: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/health')
async def health():
    """Health check endpoint"""
    try:
        chroma_status = 'Connected'
        chroma_store.list_collections()
    except:
        chroma_status = 'Not Connected'

    return {
        'status': 'healthy',
        'in_memory_videos': len(IN_MEMORY_DATABASE),
        'chroma_db_status': chroma_status,
        'open_router_configured': bool(os.getenv('OPENROUTER_API_KEY')),
        'vector_store': 'Chroma DB (Local)',
        'build_marker': 'mention-fix-2026-04-01-v3'
    }


# ============= MAIN =============

if __name__ == '__main__':
    import uvicorn

    os.makedirs('./storage', exist_ok=True)
    os.makedirs('./logs', exist_ok=True)

    logger.info("=" * 50)
    logger.info("Starting Video Chat Application (FastAPI)")
    logger.info("=" * 50)

    uvicorn.run(
        'app_fastapi:app',
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5055)),
        reload=os.getenv('DEBUG', 'False') == 'True'
    )
