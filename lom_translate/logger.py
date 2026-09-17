"""Structured logging with lazy disk initialization."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tqdm import tqdm

TRANSLATION = 25
logging.addLevelName(TRANSLATION, "TRANSLATION")


class TranslationLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("lom_translate")
        self._logger.setLevel(logging.DEBUG)
        self._initialized = False
        # Suppress noisy third-party logs
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def initialize(self, log_dir: str = "logs") -> None:
        """Create log file. Call explicitly only when executing a run."""
        if self._initialized:
            return
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = path / f"translation_{timestamp}.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        self._logger.addHandler(handler)
        self._initialized = True

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(msg, *args, **kwargs)
        tqdm.write(msg)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(msg, *args, **kwargs)
        tqdm.write(f"[WARNING] {msg}")

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(msg, *args, **kwargs)
        tqdm.write(f"[ERROR] {msg}")

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.critical(msg, *args, **kwargs)
        tqdm.write(f"[CRITICAL] {msg}")

    def translation(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.log(TRANSLATION, msg, *args, **kwargs)
        tqdm.write(f"[TRANSLATION] {msg}")

    def translation_detail(
        self,
        *,
        name: str,
        original: str,
        translated: str,
        duration: float,
        raw_translation: str | None = None,
        mode: str = "translate",
    ) -> None:
        action = "Translation" if mode == "translate" else "Improvement"
        # DEF-22 FIX: cleanly formatted message without stray closing parenthesis
        message = f"{action} completed in {duration:.2f}s\n    Name: {name}\n    Original: {original}\n"
        if mode == "improve" and raw_translation:
            message += f"    Raw Translation: {raw_translation}\n"
        message += f"    Final Output: {translated}"
        self.translation(message)

    def run_summary(
        self,
        *,
        files_processed: int,
        total_translations: int,
        total_time: float,
        from_cache: int = 0,
        from_glossary: int = 0,
        from_pairs: int = 0,
        empty_lines: int = 0,
        special_chars: int = 0,
        failed_files: list[str] | None = None,
        token_warnings: int = 0,
    ) -> None:
        # DEF-17 FIX: accurately deduct reused translations from new count
        new_translations = total_translations - from_cache - from_glossary - from_pairs - empty_lines - special_chars
        summary = (
            f"\nRun Summary:\n"
            f"    Files Processed: {files_processed}\n"
            f"    Total Entries: {total_translations}\n"
            f"      - New Translations: {new_translations}\n"
            f"      - From Cache: {from_cache}\n"
            f"      - From Glossary: {from_glossary}\n"
            f"      - Reuse Translations: {from_pairs}\n"
            f"      - Empty Lines: {empty_lines}\n"
            f"      - Special Characters: {special_chars}\n"
            f"    Token / Formatting Warnings: {token_warnings}\n"
            f"    Failed Files: {len(failed_files or [])}\n"
            f"    Total Time: {total_time:.2f}s"
        )
        tqdm.write(summary)
        self._logger.info(summary)


logger = TranslationLogger()
