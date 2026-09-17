"""Async file pipeline with atomic writing, soft validation, and metadata preservation."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import aiofiles
from tqdm.asyncio import tqdm as async_tqdm

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.glossary import Glossary
from lom_translate.logger import logger
from lom_translate.models import LocalizationEntry, LocalizationFile
from lom_translate.prompt import build_prompts
from lom_translate.text import SPECIAL_CHARS
from lom_translate.translator import translate_text


async def process_entry(
    entry: LocalizationEntry,
    prompt_data: dict[str, Any],
    client_pool: LLMClientPool,
    caches: dict[str, Any],
    run_stats: dict[str, Any],
) -> LocalizationEntry:
    original = entry.Text.strip()
    if not original:
        run_stats["empty"] = run_stats.get("empty", 0) + 1
        return entry
    if original in SPECIAL_CHARS:
        run_stats["special_chars"] = run_stats.get("special_chars", 0) + 1
        return entry

    # 1. Cache lookups
    for cache_key in ["from_glossary", "from_pairs", "from_cache"]:
        cache = caches.get(cache_key, {})
        if cache and original in cache:
            run_stats[cache_key] = run_stats.get(cache_key, 0) + 1
            return entry.clone_with_translation(cache[original])

    # 2. LLM Translation with Soft Validation
    translated, duration, val_result = await translate_text(
        text=original,
        name=entry.Name,
        prompt=prompt_data["prompt"],
        client_pool=client_pool,
    )

    if not val_result.is_clean:
        run_stats["token_warnings"] = run_stats.get("token_warnings", 0) + 1

    caches.setdefault("from_pairs", {})[original] = translated
    return entry.clone_with_translation(translated)


async def process_file(
    file_path: Path,
    output_dir: Path,
    client_pool: LLMClientPool,
    glossary: Glossary,
    caches: dict[str, Any],
    run_stats: dict[str, Any],
    details_list: list[dict[str, Any]],
    mode: str = "translate",
    raw_content: str | None = None,
) -> None:
    try:
        app_config = cfg.get()
        async with aiofiles.open(file_path, encoding="utf-8-sig") as f:
            content = await f.read()

        loc_file = LocalizationFile.model_validate(json.loads(content))
        # DEF-09 FIX: full JSON parsing instead of fragile 4KB regex check
        if loc_file.Language != "ChineseSimplified":
            return

        entries = loc_file.get_entries()
        raw_entries = None
        if raw_content:
            raw_file = LocalizationFile.model_validate(json.loads(raw_content))
            raw_entries = raw_file.get_entries()

        prompts = build_prompts(entries, glossary, raw_entries)
        semaphore = asyncio.Semaphore(app_config.settings.max_concurrent)

        async def translate_one(e: LocalizationEntry, p: dict[str, Any]) -> LocalizationEntry:
            async with semaphore:
                return await process_entry(e, p, client_pool, caches, run_stats)

        translated_entries = await asyncio.gather(
            *[translate_one(e, p) for e, p in zip(entries, prompts, strict=False)]
        )

        # Store translation details for this file
        raw_map = {e.Name: e.Text for e in raw_entries} if raw_entries else {}
        for orig_e, trans_e in zip(entries, translated_entries, strict=False):
            details_list.append(
                {
                    "File": file_path.name,
                    "Name": orig_e.Name,
                    "Original": orig_e.Text,
                    "Raw": raw_map.get(orig_e.Name),
                    "Translated": trans_e.Text,
                }
            )

        # DEF-06/07 FIX: reconstruct output preserving schema format and extra fields
        output_data = loc_file.to_output_dict(translated_entries)
        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(output_dir),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(output_data, tmp, ensure_ascii=False, indent=2)
        Path(tmp.name).rename(output_dir / file_path.name)

        logger.info(f"✓ Completed {file_path.name}: {len(translated_entries)} entries")
    except Exception as e:
        logger.error(f"✗ Failed processing {file_path.name}: {e}")
        run_stats.setdefault("failed_files", []).append(str(file_path))


async def run_pipeline(
    input_dir: Path,
    output_dir: Path,
    client_pool: LLMClientPool,
    glossary: Glossary,
    mode: str = "translate",
    raw_dir: Path | None = None,
    caches: dict[str, Any] | None = None,
) -> dict[str, Any]:
    app_config = cfg.get()
    files = sorted(input_dir.glob("*.json"))
    file_sem = asyncio.Semaphore(app_config.settings.max_concurrent_files)
    run_stats: dict[str, Any] = {
        "from_cache": 0,
        "from_glossary": 0,
        "from_pairs": 0,
        "empty": 0,
        "special_chars": 0,
        "token_warnings": 0,
        "failed_files": [],
    }
    details_list: list[dict[str, Any]] = []
    active_caches = caches if caches is not None else {}
    start_time = time.time()

    async def worker(fp: Path) -> None:
        async with file_sem:
            raw = None
            if raw_dir:
                raw_path = raw_dir / fp.name
                if raw_path.exists():
                    async with aiofiles.open(raw_path, encoding="utf-8-sig") as rf:
                        raw = await rf.read()
            await process_file(
                fp,
                output_dir,
                client_pool,
                glossary,
                active_caches,
                run_stats,
                details_list,
                mode,
                raw,
            )

    with async_tqdm(total=len(files), desc="Processing files") as pbar:
        tasks = [worker(fp) for fp in files]
        for coro in asyncio.as_completed(tasks):
            await coro
            pbar.update(1)

    # Save translation details and pairs artifacts
    details_dir = output_dir.parent / "details"
    details_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(details_dir / "translation_details.json", "w", encoding="utf-8") as df:
        await df.write(json.dumps(details_list, ensure_ascii=False, indent=2))

    pairs_dir = output_dir.parent / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    pairs_cache = active_caches.get("from_pairs", {})
    pairs_content = "\n".join(f"{orig}={trans}" for orig, trans in pairs_cache.items())
    async with aiofiles.open(pairs_dir / "translation_pairs.txt", "w", encoding="utf-8") as pf:
        await pf.write(pairs_content)

    run_stats["total_time"] = time.time() - start_time
    run_stats["total_entries"] = len(details_list)
    return run_stats
