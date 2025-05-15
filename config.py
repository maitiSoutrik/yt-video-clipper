import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1") # Default if not set

# Default Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Gets the directory where config.py is located
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloaded_videos")
CLIPS_DIR = os.path.join(BASE_DIR, "generated_clips")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Supported Platforms
SUPPORTED_PLATFORMS = ["TikTok", "YouTube_Shorts", "Instagram_Reels"]
