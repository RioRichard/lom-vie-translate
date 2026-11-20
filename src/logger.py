import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tqdm import tqdm

# Define custom log levels for our specific needs
TRANSLATION = 25  # Between INFO and WARNING
logging.addLevelName(TRANSLATION, "TRANSLATION")

_NOISY_LOGGERS = ("LiteLLM", "litellm", "httpx", "httpcore")


class TranslationLogger:
    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.logger = logging.getLogger("translation")
        self.logger.setLevel(logging.DEBUG)
        self._default_log_dir = Path(log_dir)
        self._file_handler: logging.FileHandler | None = None
        self._log_file: Path | None = None

        # Suppress noisy third-party loggers
        for noisy_name in _NOISY_LOGGERS:
            logging.getLogger(noisy_name).setLevel(logging.WARNING)

    def enable_file_logging(self, log_dir: str | Path | None = None) -> Path:
        """Lazily create the log directory and attach a UTF-8 FileHandler (idempotent)."""
        if (
            self._file_handler is not None
            and self._log_file is not None
            and self._file_handler in self.logger.handlers
        ):
            return self._log_file

        target_dir = Path(log_dir) if log_dir is not None else self._default_log_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = target_dir / f"translation_{timestamp}.log"

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)

        self.logger.addHandler(file_handler)
        self._file_handler = file_handler
        self._log_file = log_file
        return log_file

    @staticmethod
    def _format_msg(msg: Any, args: tuple[Any, ...]) -> str:
        if args:
            try:
                return str(msg) % args
            except Exception:
                return str(msg)
        return str(msg)

    @staticmethod
    def mask_api_key(api_key: str | None) -> str:
        """Safely mask an API key for debug logging."""
        if not api_key:
            return "<none>"
        if len(api_key) <= 14:
            return "***"
        return f"{api_key[:6]}...{api_key[-4:]}"

    def translation(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log translation-specific information."""
        self.logger.log(TRANSLATION, msg, *args, **kwargs)
        tqdm.write(f"[TRANSLATION] {self._format_msg(msg, args)}", nolock=False)

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log detailed information for debugging."""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log general information about program execution."""
        self.logger.info(msg, *args, **kwargs)
        tqdm.write(self._format_msg(msg, args), nolock=False)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log warnings about potential issues."""
        self.logger.warning(msg, *args, **kwargs)
        tqdm.write(f"[WARNING] {self._format_msg(msg, args)}", nolock=False)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log errors that don't stop program execution."""
        self.logger.error(msg, *args, **kwargs)
        tqdm.write(f"[ERROR] {self._format_msg(msg, args)}", nolock=False)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log critical errors that might stop program execution."""
        self.logger.critical(msg, *args, **kwargs)
        tqdm.write(f"[CRITICAL] {self._format_msg(msg, args)}", nolock=False)

    def translation_detail(
        self,
        name: str,
        original: str,
        translated: str,
        duration: float,
        raw_translation: str | None = None,
        mode: str = "translate",
    ) -> None:
        """Log details of a single translation."""
        action = "Translation" if mode == "translate" else "Improvement"
        message = (
            f"{action} completed in {duration:.2f}s\n"
            f"    Name: {name}\n"
            f"    Original: {original}\n"
        )

        if mode == "improve" and raw_translation:
            message += f"    Raw Translation: {raw_translation}\n"

        message += f"    Final Output: {translated}"

        self.translation(message)

    def run_summary(
        self,
        files_processed: int,
        total_translations: int,
        total_time: float,
        from_cache: int = 0,
        from_glossary: int = 0,
        empty_lines: int = 0,
        special_chars: int = 0,
        from_reuse_translation: int = 0,
        failed: int = 0,
    ) -> None:
        """Log a summary of the entire run to both file (when enabled) and console."""
        new_translations = max(
            0,
            total_translations
            - from_cache
            - from_glossary
            - from_reuse_translation
            - empty_lines
            - special_chars
            - failed,
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
            f"      - Failed: {failed}\n"
            f"    Total Time: {total_time:.2f}s"
        )
        self.info(summary)

    def api_call(self, key_index: int, api_key: str | None, route_label: str) -> None:
        """Log API key and route usage with masked credentials."""
        masked_key = self.mask_api_key(api_key)
        self.debug(f"Using Route: {route_label}, API key {key_index}: {masked_key}")

    def translation_start(self, name: str | None, text: str, route_label: str) -> None:
        """Log the start of a translation."""
        self.debug(f"Starting translation for {name} with Route {route_label}: {text[:50]}...")

    def translation_output(self, text: str, duration: float, route_label: str) -> None:
        """Log translation output."""
        self.debug(f"Translation with Route {route_label} completed in {duration:.2f}s")
        self.debug(f"Output: {text}")

    def concurrent_info(self, count: int, workers: int) -> None:
        """Log concurrent processing information."""
        self.info(f"Processing {count} entries with {workers} concurrent workers")


# Create a global logger instance (no file I/O at import time)
logger = TranslationLogger()
