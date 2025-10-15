import os
from dotenv import load_dotenv

load_dotenv()

# API and Model Configuration
_raw_api_keys = os.getenv("API_KEYS", "")
API_KEYS = (
    [key.strip() for key in _raw_api_keys.split(",") if key.strip()]
    if _raw_api_keys
    else []
)
if not API_KEYS:
    raise ValueError("No API keys found. Please set the API_KEYS environment variable.")
PRIMARY_LLM_MODEL = os.getenv("PRIMARY_LLM_MODEL", "gemma-3-27b-it")
_raw_fallback_models = os.getenv("FALLBACK_LLM_MODELS", "")
FALLBACK_LLM_MODELS = [
    model.strip() for model in _raw_fallback_models.split(",") if model.strip()
]
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "2"))
# Rate Limiting and Concurrency
RATE_LIMIT_IF_QUOTA_EXCEEDED = float(os.getenv("RATE_LIMIT_IF_QUOTA_EXCEEDED", "30"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "5"))
MAX_CONCURRENT_FILE_OPENS = int(os.getenv("MAX_CONCURRENT_FILE_OPENS", "999"))
MAX_GLOBAL_RETRIES = int(os.getenv("MAX_GLOBAL_RETRIES", "3"))

# Directory Configuration
BASE_DIR = os.getenv(
    "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
INPUT_DIR = os.getenv("INPUT_DIR", os.path.join(BASE_DIR, "Resource/LeanLocalJson"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "translated_output"))
IMPROVE_DIR = os.getenv("IMPROVE_DIR", os.path.join(BASE_DIR, "improved_output"))
GLOSSARY_DIR = os.getenv("GLOSSARY_DIR", os.path.join(BASE_DIR, "Resource/glossary"))

# Mode Configuration
VALID_MODES = ["translate", "improve"]
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "translate")
