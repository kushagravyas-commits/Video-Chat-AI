"""
Main Flask API for Video Chat Application
Handles video upload, processing, and RAG queries
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging
from pathlib import Path
import json

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

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize modules
video_processor = VideoProcessor(storage_dir="./storage")
transcriber = Transcriber(model_name="base")  # Local Whisper - no API key needed!
rag_processor = RAGProcessor(api_key=os.getenv('OPENROUTER_API_KEY'))
llm_generator = LLMGenerator(api_key=os.getenv('OPENROUTER_API_KEY'))
chroma_store = ChromaStore(persist_dir=os.getenv('CHROMA_PERSIST_DIR', './chroma_data'))

# In-memory database for temporary storage during processing
IN_MEMORY_DATABASE = {}

# ============= STEP 1: VIDEO DOWNLOAD & AUDIO EXTRACTION =============

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """
    Upload video file or YouTube URL

    Request:
    {
        "source": "youtube" or "upload",
        "youtube_url": "https://...",  // if YouTube
        "file": <binary>,  // if upload
        "user_id": "user123"
    }
    """
    try:
        data = request.form
        user_id = data.get('user_id', 'anonymous')
        source = data.get('source')  # 'youtube' or 'upload'

        logger.info(f"Processing video upload from user: {user_id}")

        # Step 1: Download/Get Video
        if source == 'youtube':
            youtube_url = data.get('youtube_url')
            if not youtube_url:
                return jsonify({'error': 'YouTube URL required'}), 400

            video_path, metadata = video_processor.download_youtube(youtube_url)

        elif source == 'upload':
            if 'file' not in request.files:
                return jsonify({'error': 'Video file required'}), 400

            video_file = request.files['file']
            temp_path = f"./temp/{video_file.filename}"
            os.makedirs("./temp", exist_ok=True)
            video_file.save(temp_path)

            video_path, metadata = video_processor.process_uploaded_video(temp_path, user_id)

        else:
            return jsonify({'error': 'Invalid source. Use "youtube" or "upload"'}), 400

        # Step 2: Extract Audio
        logger.info("Step 2: Extracting audio...")
        audio_path = video_processor.extract_audio(video_path)

        video_id = Path(video_path).stem

        logger.info(f"Processing complete. Video: {video_path}, Audio: {audio_path}")

        return jsonify({
            'status': 'processing',
            'video_id': video_id,
            'video_path': video_path,
            'audio_path': audio_path,
            'metadata': metadata,
            'message': 'Video downloaded and audio extracted. Proceeding to transcription...'
        }), 202  # 202 Accepted

    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= STEP 2: TRANSCRIPTION =============

@app.route('/api/transcribe', methods=['POST'])
def transcribe_video():
    """
    Transcribe audio to text using Whisper

    Request:
    {
        "audio_path": "/path/to/audio.mp3",
        "video_id": "video123",
        "language": "en" or "hi"
    }
    """
    try:
        data = request.json
        audio_path = data.get('audio_path')
        video_id = data.get('video_id')
        language = data.get('language', 'en')

        if not audio_path:
            return jsonify({'error': 'Audio path required'}), 400

        logger.info(f"Transcribing video {video_id} in language {language}")

        # Step 1: Transcribe with Whisper
        logger.info("Step 3: Transcribing with Whisper...")
        transcript_data = transcriber.transcribe_audio(
            audio_path=audio_path,
            language=language
        )

        # Store transcript in memory and DB
        IN_MEMORY_DATABASE[video_id] = {
            'video_id': video_id,
            'transcript': transcript_data,
            'status': 'transcribed'
        }

        # Save to file
        transcript_file = f"./storage/transcripts/{video_id}_transcript.json"
        os.makedirs("./storage/transcripts", exist_ok=True)
        transcriber.save_transcript(transcript_data, transcript_file)

        # Save to MongoDB
        db_manager.save_transcript(video_id, transcript_data)

        return jsonify({
            'status': 'transcribed',
            'video_id': video_id,
            'transcript_summary': {
                'total_segments': len(transcript_data['segments']),
                'duration': transcript_data['duration'],
                'language': transcript_data['language'],
                'first_few_segments': transcript_data['segments'][:3]
            },
            'message': 'Transcription complete. Proceeding to RAG processing...'
        }), 200

    except Exception as e:
        logger.error(f"Error transcribing video: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= STEP 3: RAG PROCESSING =============

@app.route('/api/process-rag', methods=['POST'])
def process_rag():
    """
    Process transcript for RAG

    Request:
    {
        "video_id": "video123"
    }
    """
    try:
        data = request.json
        video_id = data.get('video_id')

        if video_id not in IN_MEMORY_DATABASE:
            return jsonify({'error': 'Video not found'}), 404

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

        # Save embeddings to Chroma DB
        logger.info("Saving embeddings to Chroma DB...")
        chroma_store.add_embeddings(
            collection_name='video_transcripts',
            video_id=video_id,
            chunks=rag_data['chunks']
        )
        chroma_store.persist()

        return jsonify({
            'status': 'rag_processed',
            'video_id': video_id,
            'rag_summary': {
                'total_segments': len(rag_data['segments']),
                'total_chunks': len(rag_data['chunks']),
                'embedding_model': rag_data['metadata']['embedding_model'],
            },
            'message': 'RAG processing complete. Video ready for queries!'
        }), 200

    except Exception as e:
        logger.error(f"Error processing RAG: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= STEP 4: CHAT / QUERIES =============

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat about the video / Ask questions

    Request:
    {
        "video_id": "video123",
        "query": "What is the main topic?"
    }
    """
    try:
        data = request.json
        video_id = data.get('video_id')
        query = data.get('query')

        if not query:
            return jsonify({'error': 'Query required'}), 400

        if video_id not in IN_MEMORY_DATABASE:
            return jsonify({'error': 'Video not found'}), 404

        if IN_MEMORY_DATABASE[video_id].get('status') != 'rag_processed':
            return jsonify({'error': 'Video not ready. Complete RAG processing first.'}), 400

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

        return jsonify({
            'status': 'success',
            'query': query,
            'video_id': video_id,
            'relevant_chunks': relevant_chunks,
            'llm_response': llm_response,
            'message': 'Chat response generated successfully using Open Router LLM'
        }), 200

    except Exception as e:
        logger.error(f"Error processing chat: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= STEP 5: HIGHLIGHT EXTRACTION =============

@app.route('/api/highlights', methods=['POST'])
def extract_highlights():
    """
    Extract key highlights from video based on query

    Request:
    {
        "video_id": "video123",
        "query": "What are the main points?"
    }
    """
    try:
        data = request.json
        video_id = data.get('video_id')
        query = data.get('query')

        if not query:
            return jsonify({'error': 'Query required'}), 400

        if video_id not in IN_MEMORY_DATABASE:
            return jsonify({'error': 'Video not found'}), 404

        if IN_MEMORY_DATABASE[video_id].get('status') != 'rag_processed':
            return jsonify({'error': 'Video not ready. Complete RAG processing first.'}), 400

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

        return jsonify({
            'status': 'success',
            'video_id': video_id,
            'query': query,
            'highlights': highlights_result.get('highlights', []),
            'summary': highlights_result.get('summary', ''),
            'relevant_chunks_count': len(relevant_chunks)
        }), 200

    except Exception as e:
        logger.error(f"Error extracting highlights: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= CHROMA DB MANAGEMENT ENDPOINTS =============

@app.route('/api/chroma/collections', methods=['GET'])
def list_chroma_collections():
    """List all Chroma DB collections"""
    try:
        collections = chroma_store.list_collections()
        return jsonify({
            'collections': collections,
            'total': len(collections)
        }), 200
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chroma/collection-info/<collection_name>', methods=['GET'])
def get_collection_info(collection_name):
    """Get information about a Chroma collection"""
    try:
        info = chroma_store.get_collection_info(collection_name)
        return jsonify(info), 200
    except Exception as e:
        logger.error(f"Error getting collection info: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chroma/clear/<collection_name>', methods=['POST'])
def clear_collection(collection_name):
    """Clear all embeddings from a collection"""
    try:
        chroma_store.clear_collection(collection_name)
        return jsonify({
            'status': 'success',
            'message': f'Collection {collection_name} cleared'
        }), 200
    except Exception as e:
        logger.error(f"Error clearing collection: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============= UTILITY ENDPOINTS =============

@app.route('/api/status/<video_id>', methods=['GET'])
def get_status(video_id):
    """Get processing status of a video"""
    if video_id in IN_MEMORY_DATABASE:
        return jsonify({
            'video_id': video_id,
            'status': IN_MEMORY_DATABASE[video_id].get('status'),
        }), 200
    else:
        return jsonify({'error': 'Video not found'}), 404


@app.route('/api/videos', methods=['GET'])
def list_videos():
    """List all processed videos"""
    return jsonify({
        'videos': list(IN_MEMORY_DATABASE.keys()),
        'total': len(IN_MEMORY_DATABASE)
    }), 200


@app.route('/api/db-stats', methods=['GET'])
def db_stats():
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

        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error getting db stats: {str(e)}")
        return jsonify({
            'vector_store': 'Chroma DB',
            'status': 'Error',
            'error': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        chroma_status = 'Connected'
        chroma_store.list_collections()
    except:
        chroma_status = 'Not Connected'

    return jsonify({
        'status': 'healthy',
        'in_memory_videos': len(IN_MEMORY_DATABASE),
        'chroma_db_status': chroma_status,
        'open_router_configured': bool(os.getenv('OPENROUTER_API_KEY')),
        'vector_store': 'Chroma DB (Local)'
    }), 200


# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# ============= MAIN =============

if __name__ == '__main__':
    os.makedirs('./storage', exist_ok=True)
    os.makedirs('./logs', exist_ok=True)

    logger.info("=" * 50)
    logger.info("Starting Video Chat Application")
    logger.info("=" * 50)
    logger.info(f"OpenAI API Key configured: {bool(os.getenv('OPENAI_API_KEY'))}")
    logger.info(f"MongoDB URI: {os.getenv('MONGODB_URI', 'Not configured')}")

    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('DEBUG', 'False') == 'True'
    )
