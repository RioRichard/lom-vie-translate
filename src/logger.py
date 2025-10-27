import logging
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# Define custom log levels for our specific needs
TRANSLATION = 25  # Between INFO and WARNING
logging.addLevelName(TRANSLATION, "TRANSLATION")


class TranslationLogger:
    def __init__(self, log_dir="logs"):
        self.logger = logging.getLogger("translation")
        self.logger.setLevel(logging.DEBUG)

        # Suppress warnings from google.generativeai library
        logging.getLogger("google.generativeai").setLevel(logging.ERROR)

        # Create log directory if it doesn't exist
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamp for log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"translation_{timestamp}.log"

        # File handler with detailed format
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)

        # Add handlers to logger
        self.logger.addHandler(file_handler)

    def translation(self, msg, *args, **kwargs):
        """Log translation-specific information"""
        self.logger.log(TRANSLATION, msg, *args, **kwargs)
        tqdm.write(f"[TRANSLATION] {msg}", *args, **kwargs, nolock=False)

    def debug(self, msg, *args, **kwargs):
        """Log detailed information for debugging"""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Log general information about program execution"""
        self.logger.info(msg, *args, **kwargs)
        tqdm.write(msg, *args, **kwargs, nolock=False)

    def warning(self, msg, *args, **kwargs):
        """Log warnings about potential issues"""
        self.logger.warning(msg, *args, **kwargs)
        tqdm.write(f"[WARNING] {msg}", *args, **kwargs, nolock=False)

    def error(self, msg, *args, **kwargs):
        """Log errors that don't stop program execution"""
        self.logger.error(msg, *args, **kwargs)
        tqdm.write(f"[ERROR] {msg}", *args, **kwargs, nolock=False)

    def critical(self, msg, *args, **kwargs):
        """Log critical errors that might stop program execution"""
        self.logger.critical(msg, *args, **kwargs)
        tqdm.write(f"[CRITICAL] {msg}", *args, **kwargs)

    def translation_detail(
        self,
        name,
        original,
        translated,
        duration,
        raw_translation=None,
        mode="translate",
    ):
        """Log details of a single translation

        Args:
            name: Entry name/key
            original: Original text
            translated: Final translated/improved text
            duration: Time taken for translation
            raw_translation: Raw translation (for improve mode)
            mode: 'translate' or 'improve'
        """
        action = "Translation" if mode == "translate" else "Improvement"
        message = (
            f"{action} completed in {duration:.2f}s\n )"
            f"    Name: {name}\n"
            f"    Original: {original}\n"
        )

        if mode == "improve" and raw_translation:
            message += f"    Raw Translation: {raw_translation}\n"

        message += f"    Final Output: {translated}"

        self.translation(message)

    def run_summary(
        self,
        files_processed,
        total_translations,
        total_time,
        from_cache=0,
        from_glossary=0,
        empty_lines=0,
        special_chars=0,
        from_reuse_translation=0,
    ):
        """Log a summary of the entire run"""
        new_translations = (
            total_translations
            - from_cache
            - from_glossary
            - empty_lines
            - special_chars
        )
        summary = (
            f"\nRun Summary:\n"
            f"    Files Processed: {files_processed}\n"
            f"    Total Translations: {total_translations}\n"
            f"      - From Cache: {from_cache}\n"
            f"      - From Glossary: {from_glossary}\n"
            f"      - Empty Lines: {empty_lines}\n"
            f"      - Special Characters: {special_chars}\n"
            f"      - New Translations: {new_translations}\n"
            f"      - Reuse Translations: {from_reuse_translation}\n"
            f"    Total Time: {total_time:.2f}s"
        )
        tqdm.write(summary)

    def api_call(self, key_index, api_key, model_name):
        """Log API key and model usage"""
        masked_key = f"{api_key[:10]}...{api_key[-4:]}"
        self.debug(f"Using Model: {model_name}, API key {key_index}: {masked_key}")

    def translation_start(self, name, text, model_name):
        """Log the start of a translation"""
        self.debug(
            f"Starting translation for {name} with Model {model_name}: {text[:50]}..."
        )

    def translation_output(self, text, duration, model_name):
        """Log translation output"""
        self.debug(f"Translation with Model {model_name} completed in {duration:.2f}s")
        self.debug(f"Output: {text}")

    def concurrent_info(self, count, workers):
        """Log concurrent processing information"""
        tqdm.write(f"Processing {count} entries with {workers} concurrent workers")

    def google_api_warning(self, message):
        """Log Google API related warnings at debug level to reduce noise"""
        self.debug(f"Google API: {message}")


# Create a global logger instance
logger = TranslationLogger()
