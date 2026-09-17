"""High-performance glossary ingestion and Aho-Corasick matching."""

from __future__ import annotations

import json
from pathlib import Path

import ahocorasick
import aiofiles

from lom_translate.logger import logger


class Glossary:
    def __init__(self) -> None:
        self.name_to_translated: dict[str, str] = {}
        self.original_to_translated: dict[str, str] = {}
        self._automaton: ahocorasick.Automaton | None = None

    async def load(self, path: Path | str | None = None, glossary_dir: Path | str | None = None) -> None:
        files: list[Path] = []
        if path:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"Glossary file not found: {path}")
            files.append(p)
        elif glossary_dir:
            g_path = Path(glossary_dir)
            if g_path.exists():
                files.extend(g_path.glob("*.json"))
                files.extend(g_path.glob("*.txt"))

        for f in files:
            await self._load_file(f)

        self._build_automaton()
        logger.info(
            f"Glossary loaded: {len(self.original_to_translated)} terms, {len(self.name_to_translated)} name entries"
        )

    async def _load_file(self, file: Path) -> None:
        try:
            async with aiofiles.open(file, encoding="utf-8-sig") as f:
                content = await f.read()

            if file.suffix == ".json":
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        name = item.get("Name", "").strip()
                        orig = item.get("Original", "").strip()
                        trans = item.get("Translated", "").strip()
                        if name and trans:
                            self.name_to_translated[name] = trans
                        if orig and trans:
                            self.original_to_translated[orig] = trans
                elif isinstance(data, dict):
                    # DEF-10 FIX: populate BOTH mapping tables for dict glossaries
                    for k, v in data.items():
                        key, val = str(k).strip(), str(v).strip()
                        if key and val:
                            self.name_to_translated[key] = val
                            self.original_to_translated[key] = val
            elif file.suffix == ".txt":
                for line in content.splitlines():
                    if "=" in line:
                        orig, trans = line.split("=", 1)
                        orig, trans = orig.strip(), trans.strip()
                        if orig and trans:
                            self.original_to_translated[orig] = trans
                            self.name_to_translated[orig] = trans
        except Exception as e:
            logger.error(f"Failed to read glossary {file.name}: {e}")

    def _build_automaton(self) -> None:
        self._automaton = ahocorasick.Automaton()
        for orig, trans in self.original_to_translated.items():
            self._automaton.add_word(orig, (orig, trans))
        if self.original_to_translated:
            self._automaton.make_automaton()

    def find_matches(self, text: str) -> list[tuple[str, str]]:
        """O(text length) search with longest-match substring deduplication."""
        if not text or not self._automaton or not self.original_to_translated:
            return []

        raw_matches: dict[str, tuple[str, str]] = {}
        for _, (orig, trans) in self._automaton.iter(text):
            if orig not in raw_matches or len(orig) > len(raw_matches[orig][0]):
                raw_matches[orig] = (orig, trans)

        sorted_matches = sorted(raw_matches.values(), key=lambda x: len(x[0]), reverse=True)
        filtered: list[tuple[str, str]] = []
        matched_words: set[str] = set()
        for orig, trans in sorted_matches:
            if not any(orig in longer and orig != longer for longer in matched_words):
                filtered.append((orig, trans))
                matched_words.add(orig)
        return filtered

    def get_by_name(self, name: str) -> str | None:
        return self.name_to_translated.get(name)


async def load_old_translations(input_dir: Path | str, translated_dir: Path | str) -> dict[str, str]:
    """Asynchronously load existing translations by pairing input files with translated files."""
    old_translations: dict[str, str] = {}
    in_path = Path(input_dir)
    trans_path = Path(translated_dir)

    if not in_path.exists() or not trans_path.exists():
        return old_translations

    for t_file in trans_path.glob("*.json"):
        i_file = in_path / t_file.name
        if not i_file.exists():
            continue

        try:
            async with aiofiles.open(i_file, encoding="utf-8-sig") as f:
                i_data = json.loads(await f.read())
            async with aiofiles.open(t_file, encoding="utf-8-sig") as f:
                t_data = json.loads(await f.read())

            from lom_translate.models import LocalizationFile

            i_entries = LocalizationFile.model_validate(i_data).get_entries()
            t_entries = LocalizationFile.model_validate(t_data).get_entries()

            t_map = {e.Name: e.Text for e in t_entries}
            for e in i_entries:
                if e.Name in t_map and e.Text.strip() and t_map[e.Name].strip():
                    old_translations[e.Text.strip()] = t_map[e.Name].strip()
        except Exception as err:
            logger.warning(f"Error loading cache pair ({i_file.name}, {t_file.name}): {err}")

    return old_translations
