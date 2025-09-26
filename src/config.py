import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# API and Model Configuration
_raw_api_keys = os.getenv('API_KEYS', '')
API_KEYS = [key.strip() for key in _raw_api_keys.split(',') if key.strip()] if _raw_api_keys else []
if not API_KEYS:
    raise ValueError("No API keys found. Please set the API_KEYS environment variable.")
GOOGLE_STUDIO_AI_LLM = os.getenv('GOOGLE_STUDIO_AI_LLM', 'gemma-3-27b-it')

# Rate Limiting and Concurrency
RATE_LIMIT_DELAY = float(os.getenv('RATE_LIMIT_DELAY', '2'))
RATE_LIMIT_IF_QUOTA_EXCEEDED = float(os.getenv('RATE_LIMIT_IF_QUOTA_EXCEEDED', '60'))
MAX_CONCURRENT = int(os.getenv('MAX_CONCURRENT', '5'))

# Directory Configuration
BASE_DIR = os.getenv('BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_DIR = os.getenv('INPUT_DIR', os.path.join(BASE_DIR, 'Resource/LeanLocalJson'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', os.path.join(BASE_DIR, 'translated_output'))
IMPROVE_DIR = os.getenv('IMPROVE_DIR', os.path.join(BASE_DIR, 'improved_output'))
GROSSARY_DIR = os.getenv('GROSSARY_DIR', os.path.join(BASE_DIR, 'Resource/grossary'))

# Mode Configuration
VALID_MODES = ['translate', 'improve']
DEFAULT_MODE = os.getenv('DEFAULT_MODE', 'translate')
