import logging
from datetime import datetime
from pathlib import Path

# Define custom log levels for our specific needs
TRANSLATION = 25  # Between INFO and WARNING
logging.addLevelName(TRANSLATION, 'TRANSLATION')

class TranslationLogger:
    def __init__(self, log_dir="logs"):
        self.logger = logging.getLogger('translation')
        self.logger.setLevel(logging.DEBUG)

        # Create log directory if it doesn't exist
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamp for log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f"translation_{timestamp}.log"

        # File handler with detailed format
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)8s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)

        # Console handler with more concise format
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('[%(levelname)s] %(message)s')
        console_handler.setFormatter(console_format)

        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def translation(self, msg, *args, **kwargs):
        """Log translation-specific information"""
        self.logger.log(TRANSLATION, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Log detailed information for debugging"""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Log general information about program execution"""
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """Log warnings about potential issues"""
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Log errors that don't stop program execution"""
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """Log critical errors that might stop program execution"""
        self.logger.critical(msg, *args, **kwargs)

    def file_start(self, filename):
        """Log the start of processing a file"""
        self.info(f"Processing file: {filename}")

    def file_end(self, filename, count, duration):
        """Log the completion of processing a file"""
        self.info(f"Completed {filename} - {count} translations in {duration:.2f}s")

    def translation_detail(self, name, original, translated, duration, raw_translation=None, mode='translate'):
        """Log details of a single translation

        Args:
            name: Entry name/key
            original: Original text
            translated: Final translated/improved text
            duration: Time taken for translation
            raw_translation: Raw translation (for improve mode)
            mode: 'translate' or 'improve'
        """
        action = "Translation" if mode == 'translate' else "Improvement"
        message = (
            f"{action} completed in {duration:.2f}s\n"
            f"    Name: {name}\n"
            f"    Original: {original}\n"
        )

        if mode == 'improve' and raw_translation:
            message += f"    Raw Translation: {raw_translation}\n"

        message += f"    Final Output: {translated}"

        self.translation(message)

    def run_summary(self, files_processed, total_translations, total_time):
        """Log a summary of the entire run"""
        self.info(
            f"\nRun Summary:\n"
            f"    Files Processed: {files_processed}\n"
            f"    Total Translations: {total_translations}\n"
            f"    Total Time: {total_time:.2f}s"
        )

    def api_call(self, key_index, api_key):
        """Log API key usage"""
        masked_key = f"{api_key[:10]}...{api_key[-4:]}"
        self.debug(f"Using API key {key_index}: {masked_key}")

    def translation_start(self, name, text):
        """Log the start of a translation"""
        self.debug(f"Starting translation for {name}: {text[:50]}...")

    def translation_output(self, text, duration):
        """Log translation output"""
        self.debug(f"Translation completed in {duration:.2f}s")
        self.debug(f"Output: {text}")

    def concurrent_info(self, count, workers):
        """Log concurrent processing information"""
        self.info(f"Processing {count} entries with {workers} concurrent workers")

    def google_api_warning(self, message):
        """Log Google API related warnings at debug level to reduce noise"""
        self.debug(f"Google API: {message}")

# Create a global logger instance
logger = TranslationLogger()
