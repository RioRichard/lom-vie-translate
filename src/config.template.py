# Rename this file to config.py and add your actual API keys
API_KEYS = [
    'your-api-key-1',
    'your-api-key-2'
]

# Model settings
GOOGLE_STUDIO_AI_LLM = 'gemini-pro'

# Directory settings
INPUT_DIR = 'testcase/resources/original'
OUTPUT_DIR = 'testcase/resources/translated'
GROSSARY_DIR = 'Resource/grossary'

# Rate limiting and concurrency
RATE_LIMIT_DELAY = 0.1
RATE_LIMIT_IF_QUOTA_EXCEEDED = 60
MAX_CONCURRENT = 5

# Valid modes
VALID_MODES = ['translate', 'improve']
