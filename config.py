"""
Configuration Management for Video Chat Application
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""

    # App
    APP_NAME = "Video Chat Application"
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False') == 'True'
    PORT = int(os.getenv('PORT', 5000))

    # API Keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    HUGGING_FACE_TOKEN = os.getenv('HUGGING_FACE_TOKEN')

    # Database
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/videochat')

    # Paths
    BASE_DIR = Path(__file__).parent
    STORAGE_DIR = Path(os.getenv('STORAGE_DIR', './storage'))
    TEMP_DIR = Path(os.getenv('TEMP_DIR', './temp'))
    LOGS_DIR = Path(os.getenv('LOGS_DIR', './logs'))

    # Create directories
    STORAGE_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    # Whisper Configuration
    WHISPER_MODEL = "whisper-1"
    WHISPER_LANGUAGE = "en"
    WHISPER_TEMPERATURE = 0

    # Embedding Configuration
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536

    # RAG Configuration
    RAG_CHUNK_SIZE = 512
    RAG_CHUNK_OVERLAP = 50
    RAG_TOP_K = 5

    # Video Configuration
    VIDEO_MAX_SIZE = 1024 * 1024 * 1024  # 1GB
    SUPPORTED_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.flv']
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_BITRATE = '192k'

    # FFmpeg Configuration
    FFMPEG_VERBOSE = False

    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def validate_config(cls):
        """Validate configuration"""
        errors = []

        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY not set in .env")

        if errors:
            print("\n⚠️  Configuration Errors:")
            for error in errors:
                print(f"  - {error}")
            print("\nPlease update your .env file\n")
            return False

        return True


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    MONGODB_URI = "mongodb://localhost:27017/videochat_test"


# Select config based on environment
ENV = os.getenv('FLASK_ENV', 'development')

if ENV == 'production':
    config = ProductionConfig()
elif ENV == 'testing':
    config = TestingConfig()
else:
    config = DevelopmentConfig()
