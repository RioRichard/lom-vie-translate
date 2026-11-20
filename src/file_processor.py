from __future__ import annotations

import asyncio
import heapq
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
from tqdm.asyncio import tqdm as async_tqdm

from src.logger import logger
from src.prompt_preparer import prepare_prompt_data
from src.utils import SPECIAL_CHARS, build_translation_prompt, parse_json_entries, preprocess_text

if TYPE_CHECKING:
    from src.translator import TranslationEngine


def _key_variants(key: str) -> tuple[str, ...]:
    if key.startswith("Story/"):
        return (key, key.removeprefix("Story/"))
    return (key, f"Story/{key}")


def _lookup_by_key(mapping: dict[str, str], key: str) -> str | None:
    for variant in _key_variants(key):
        val = mapping.get(variant)
        if val is not None:
            return val
    return None


def _store_by_key(mapping: dict[str, str], key: str, value: str) -> None:
    for variant in _key_variants(key):
        mapping[variant] = value


def _order_script_items(
    items: list[tuple[int, dict[str, Any], dict[str, Any]]],
    script_id: str,
    flowchart: Any | None,
) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    """Sort a script's mapped entries into flowchart execution order."""
    if len(items) <= 1:
        return items

    scripts_map = getattr(flowchart, "scripts", None) if flowchart is not None else None
    if isinstance(scripts_map, dict) and script_id in scripts_map:
        script_obj = scripts_map[script_id]
        script_lines = getattr(script_obj, "lines", None) or []
        order_by_key: dict[str, int] = {}
        for pos, line_obj in enumerate(script_lines):
            line_key = str(getattr(line_obj, "key", "") or "")
            if line_key:
                for variant in _key_variants(line_key):
                    order_by_key.setdefault(variant, pos)
        fallback_base = len(script_lines)
        return sorted(
            items,
            key=lambda item: (
                next(
                    (
                        order_by_key[v]
                        for v in _key_variants(
                            str(item[1].get("Name") or item[1].get("key") or "")
                        )
                        if v in order_by_key
                    ),
                    fallback_base + item[0],
                ),
                item[0],
            ),
        )

    # Fallback topological sort using prev_keys / next_keys when flowchart.scripts isn't populated
    idx_by_key: dict[str, int] = {}
    items_by_orig_idx: dict[int, tuple[int, dict[str, Any], dict[str, Any]]] = {}
    for item in items:
        orig_idx, entry, _ = item
        items_by_orig_idx[orig_idx] = item
        entry_name = str(entry.get("Name") or entry.get("key") or "")
        if entry_name:
            for variant in _key_variants(entry_name):
                idx_by_key.setdefault(variant, orig_idx)

    adj: dict[int, set[int]] = {orig_idx: set() for orig_idx in items_by_orig_idx}
    in_degree: dict[int, int] = {orig_idx: 0 for orig_idx in items_by_orig_idx}

    for orig_idx, _, p_data in items:
        for pk in p_data.get("prev_keys") or []:
            pred_idx = next((idx_by_key[v] for v in _key_variants(pk) if v in idx_by_key), None)
            if pred_idx is not None and pred_idx != orig_idx and orig_idx not in adj[pred_idx]:
                adj[pred_idx].add(orig_idx)
                in_degree[orig_idx] += 1
        for nk in p_data.get("next_keys") or []:
            succ_idx = next((idx_by_key[v] for v in _key_variants(nk) if v in idx_by_key), None)
            if succ_idx is not None and succ_idx != orig_idx and succ_idx not in adj[orig_idx]:
                adj[orig_idx].add(succ_idx)
                in_degree[succ_idx] += 1

    heap: list[int] = [orig_idx for orig_idx, deg in in_degree.items() if deg == 0]
    heapq.heapify(heap)
    ordered_indices: list[int] = []
    seen: set[int] = set()

    while heap:
        curr = heapq.heappop(heap)
        if curr in seen:
            continue
        seen.add(curr)
        ordered_indices.append(curr)
        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0 and nxt not in seen:
                heapq.heappush(heap, nxt)

    if len(ordered_indices) < len(items):
        for orig_idx, _, _ in sorted(items, key=lambda it: it[0]):
            if orig_idx not in seen:
                ordered_indices.append(orig_idx)

    return [items_by_orig_idx[orig_idx] for orig_idx in ordered_indices]


def _inject_dialogue_window(
    prompt_data: dict[str, Any],
    orig_by_key: dict[str, str],
    translated_by_key: dict[str, str],
    speaker_by_key: dict[str, str],
) -> None:
    """Rebuild prompt_data['prompt'] with the live sliding dialogue window."""
    story_header = prompt_data.get("story_context_header")
    if not story_header:
        return

    prev_speakers = prompt_data.get("prev_speakers") or {}
    next_speakers = prompt_data.get("next_speakers") or {}

    prev_lines_text: list[str] = []
    for pk in prompt_data.get("prev_keys") or []:
        orig_p = _lookup_by_key(orig_by_key, pk)
        trans_p = _lookup_by_key(translated_by_key, pk)
        if not orig_p and not trans_p:
            continue
        spk_p = prev_speakers.get(pk) or _lookup_by_key(speaker_by_key, pk) or "Nhân vật"
        if orig_p and trans_p:
            prev_lines_text.append(f"- {spk_p}: {orig_p} => {preprocess_text(trans_p)}")
        elif orig_p:
            prev_lines_text.append(f"- {spk_p}: {orig_p}")

    next_lines_text: list[str] = []
    for nk in prompt_data.get("next_keys") or []:
        orig_n = _lookup_by_key(orig_by_key, nk)
        if not orig_n:
            continue
        spk_n = next_speakers.get(nk) or _lookup_by_key(speaker_by_key, nk) or "Nhân vật"
        next_lines_text.append(f"- {spk_n}: {orig_n}")

    context_parts = [str(story_header)]
    if prev_lines_text:
        context_parts.append("Hội thoại trước đó:\n" + "\n".join(prev_lines_text))
    if next_lines_text:
        context_parts.append(
            "Lời thoại kế tiếp (để tham khảo ngữ cảnh):\n" + "\n".join(next_lines_text)
        )

    prompt_data["prompt"] = build_translation_prompt(
        original_text=prompt_data["original_text"],
        raw_translation=prompt_data.get("raw_translation"),
        glossary_matches=prompt_data.get("glossary_matches"),
        story_context="\n".join(context_parts),
    )


async def process_entry(
    entry: dict[str, Any],
    translate_pairs: dict[str, str],
    engine: TranslationEngine,
    mode: str = "translate",
    task_name: str | None = None,
    prompt_data: dict[str, Any] | None = None,
    glossary_text: dict[str, str] | None = None,
    translation_cache: dict[str, str] | None = None,
    run_stats: dict[str, int] | None = None,
    override_provider: str | None = None,
    override_tier: str | None = None,
    override_model: str | None = None,
    contextual_pairs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Process a single entry for translation or improvement.

    Args:
        entry: The entry to process (dict with 'Name' and 'Text' keys).
        translate_pairs: In-run cache mapping raw original text to raw translated text.
        engine: TranslationEngine instance used for LLM calls.
        mode: 'translate' for fresh translation or 'improve' for improving existing translations.
        task_name: Task name in config.toml (defaults to mode).
        prompt_data: Pre-prepared prompt data containing context, templates, and optional raw_translation.
        glossary_text: Glossary map from original text to translated text.
        translation_cache: Cache of previously translated text.
        run_stats: Dictionary to record run statistics.
        override_provider: Optional provider override for routing.
        override_tier: Optional tier override for routing.
        override_model: Optional model override for routing.
        contextual_pairs: Optional context-safe cache keyed by '{Name}::{original_text}' for story lines.

    Returns:
        dict: The processed entry with translated text.
    """
    if "Name" not in entry or "Text" not in entry:
        logger.warning(f"Entry missing required fields: {entry}")
        return entry

    name = entry["Name"]
    original_text = (entry["Text"] or "").strip()

    # Skip empty text
    if not original_text:
        logger.debug(f"Skipping empty text for entry: {name}")
        if run_stats is not None:
            run_stats["empty"] = run_stats.get("empty", 0) + 1
        return entry

    # Skip special characters
    if original_text in SPECIAL_CHARS:
        logger.debug(f"Skipping special character: {original_text}")
        if run_stats is not None:
            run_stats["special_chars"] = run_stats.get("special_chars", 0) + 1
        return {"Name": name, "Text": original_text}

    # 1. Check for exact match in glossary
    if glossary_text:
        existing_translation = glossary_text.get(original_text)
        if existing_translation:
            logger.info(
                f"Reusing glossary for original text: '{original_text}' -> '{existing_translation}'"
            )
            if run_stats is not None:
                run_stats["from_glossary"] = run_stats.get("from_glossary", 0) + 1
            return {"Name": name, "Text": existing_translation}

    has_story_context = isinstance(prompt_data, dict) and bool(
        prompt_data.get("story_context_header")
    )
    context_cache_key = f"{name}::{original_text}"

    # 2. Check in-run cache (context-keyed for story-contextual entries to prevent cross-speaker collisions)
    if has_story_context:
        if contextual_pairs is not None and context_cache_key in contextual_pairs:
            cached_pair = contextual_pairs[context_cache_key]
            logger.info(
                f"Reusing context-matched translation for '{name}': '{original_text}' -> '{cached_pair}'"
            )
            if run_stats is not None:
                run_stats["from_pairs"] = run_stats.get("from_pairs", 0) + 1
            return {"Name": name, "Text": cached_pair}
    elif translate_pairs is not None and original_text in translate_pairs:
        cached_pair = translate_pairs[original_text]
        logger.info(
            f"Reusing existing translation for original text: '{original_text}' -> '{cached_pair}'"
        )
        if run_stats is not None:
            run_stats["from_pairs"] = run_stats.get("from_pairs", 0) + 1
        return {"Name": name, "Text": cached_pair}

    # 3. Check old translation cache
    if translation_cache:
        cached_translation = translation_cache.get(original_text)
        if cached_translation:
            logger.info(
                f"Reusing old translation for original text: '{original_text}' -> '{cached_translation}'"
            )
            if run_stats is not None:
                run_stats["from_cache"] = run_stats.get("from_cache", 0) + 1
            return {"Name": name, "Text": cached_translation}

    # 4. Translate via TranslationEngine
    line_start = time.time()
    resolved_task = task_name or mode

    result = await engine.translate_text(
        text=original_text,
        task_name=resolved_task,
        name=name,
        prompt_data=prompt_data,
        override_provider=override_provider,
        override_tier=override_tier,
        override_model=override_model,
    )

    line_end = time.time()
    raw_translation = (
        prompt_data.get("raw_translation") if isinstance(prompt_data, dict) else None
    )

    if not result.succeeded:
        if run_stats is not None:
            run_stats["failed"] = run_stats.get("failed", 0) + 1
        logger.warning(
            f"Translation failed for '{name}' (not cached): {result.error or 'unknown error'}"
        )
        return {"Name": name, "Text": result.text}

    if has_story_context:
        if contextual_pairs is not None and context_cache_key not in contextual_pairs:
            contextual_pairs[context_cache_key] = result.text
    elif translate_pairs is not None and original_text not in translate_pairs:
        translate_pairs[original_text] = result.text

    logger.translation_detail(
        name=name,
        original=original_text,
        translated=result.text,
        duration=line_end - line_start,
        raw_translation=raw_translation,
        mode=mode,
    )
    return {"Name": name, "Text": result.text}


async def process_json_file(
    file_path: str | Path,
    file_content: str,
    translated_file_content: str | None,
    all_data_dict: list[dict[str, Any]],
    translation_pairs: dict[str, str],
    engine: TranslationEngine,
    mode: str = "translate",
    translated_dir: str | Path | None = None,
    json_output_dir: str | Path | None = None,
    glossary_text: dict[str, str] | None = None,
    translation_cache: dict[str, str] | None = None,
    run_stats: dict[str, int] | None = None,
    max_concurrent: int = 5,
    override_provider: str | None = None,
    override_tier: str | None = None,
    override_model: str | None = None,
    flowchart: Any | None = None,
    relationship_matrix: Any | None = None,
    dialogue_window: int = 4,
) -> None:
    """Process a JSON file for translation or improvement."""
    if mode == "improve" and not translated_dir:
        raise ValueError("translated_dir is required when using improve mode")

    file_path = Path(file_path)
    file_name = file_path.name
    output_dir = Path(json_output_dir) if json_output_dir else Path("translated_output") / "json"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name

    try:
        file_start = time.time()

        data = json.loads(file_content)

        prompt_data_list, _ = await prepare_prompt_data(
            original_file_path=file_path,
            original_data=data,
            translated_file_content=translated_file_content if mode == "improve" else None,
            original_to_translated=glossary_text,
            flowchart=flowchart,
            relationship_matrix=relationship_matrix,
            dialogue_window=dialogue_window,
        )
        entries_list, is_array_format = parse_json_entries(data)

        concurrency = max(max_concurrent, 1)
        logger.concurrent_info(len(entries_list), concurrency)

        tasks = _create_translation_tasks(entries_list, prompt_data_list)
        semaphore = asyncio.Semaphore(concurrency)
        contextual_pairs: dict[str, str] = {}
        pbar = async_tqdm(
            total=len(tasks),
            desc=f"Entries in {file_name}",
            leave=False,
            mininterval=0.1,
        )

        orig_by_key: dict[str, str] = {}
        speaker_by_key: dict[str, str] = {}
        translated_by_key: dict[str, str] = {}

        script_groups: dict[str, list[tuple[int, dict[str, Any], dict[str, Any]]]] = {}
        unmapped_items: list[tuple[int, dict[str, Any], dict[str, Any]]] = []

        for idx, (entry, prompt) in enumerate(tasks):
            entry_name = str(entry.get("Name") or entry.get("key") or "")
            orig_text = str(prompt.get("original_text") or "")
            if entry_name and orig_text:
                _store_by_key(orig_by_key, entry_name, orig_text)
            speaker_label = prompt.get("speaker_label")
            if entry_name and speaker_label:
                _store_by_key(speaker_by_key, entry_name, str(speaker_label))

            script_id = prompt.get("script_id")
            if flowchart is not None and (script_id or prompt.get("story_context_header")):
                group_id = str(script_id or "__story__")
                script_groups.setdefault(group_id, []).append((idx, entry, prompt))
            else:
                unmapped_items.append((idx, entry, prompt))

        translations: list[dict[str, Any] | None] = [None] * len(tasks)

        async def run_single_entry(
            idx: int, entry: dict[str, Any], prompt: dict[str, Any]
        ) -> dict[str, Any]:
            async with semaphore:
                result = await process_entry(
                    entry=entry,
                    translate_pairs=translation_pairs,
                    engine=engine,
                    mode=mode,
                    task_name=mode,
                    prompt_data=prompt,
                    glossary_text=glossary_text,
                    translation_cache=translation_cache,
                    run_stats=run_stats,
                    override_provider=override_provider,
                    override_tier=override_tier,
                    override_model=override_model,
                    contextual_pairs=contextual_pairs,
                )
                pbar.update(1)
                translations[idx] = result
                return result

        async def run_script_group(
            script_id: str, items: list[tuple[int, dict[str, Any], dict[str, Any]]]
        ) -> None:
            ordered = _order_script_items(items, script_id=script_id, flowchart=flowchart)
            for idx, entry, prompt in ordered:
                _inject_dialogue_window(
                    prompt_data=prompt,
                    orig_by_key=orig_by_key,
                    translated_by_key=translated_by_key,
                    speaker_by_key=speaker_by_key,
                )
                failed_before = run_stats.get("failed", 0) if run_stats is not None else 0
                result = await run_single_entry(idx, entry, prompt)
                failed_after = run_stats.get("failed", 0) if run_stats is not None else 0
                entry_name = str(result.get("Name") or entry.get("Name") or "")
                result_text = (result.get("Text") or "").strip()
                if entry_name and result_text and failed_after == failed_before:
                    _store_by_key(translated_by_key, entry_name, result_text)

        try:
            coros = [
                run_script_group(script_id, items)
                for script_id, items in script_groups.items()
            ]
            coros.extend(
                run_single_entry(idx, entry, prompt)
                for idx, entry, prompt in unmapped_items
            )
            if coros:
                await asyncio.gather(*coros)
        finally:
            pbar.close()

        final_translations = [
            item if item is not None else entries_list[idx]
            for idx, item in enumerate(translations)
        ]

        if is_array_format:
            data["entries"]["Array"] = final_translations
        else:
            data["entries"] = final_translations

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

        await _process_and_store_results(
            file_name=file_name,
            translations=final_translations,
            original_entries=entries_list,
            all_data_dict=all_data_dict,
            mode=mode,
            translated_file_content=translated_file_content,
        )

        file_end = time.time()
        logger.info(
            f"Completed {file_name} - {len(final_translations)} translations in {file_end - file_start:.2f}s"
        )
    except Exception as e:
        logger.error(f"Error processing {file_name}: {str(e)}")


def _create_translation_tasks(
    entries_list: list[dict[str, Any]],
    prompt_data_list: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if len(prompt_data_list) != len(entries_list):
        logger.warning(
            f"Number of prompts ({len(prompt_data_list)}) doesn't match number of entries ({len(entries_list)})"
        )
        logger.debug(f"Entries list: {entries_list}")
        logger.debug(f"Prompt data list: {prompt_data_list}")

    tasks: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for idx, entry in enumerate(entries_list):
        prompt = (
            prompt_data_list[idx]
            if idx < len(prompt_data_list)
            else {
                "idx": idx,
                "name": entry.get("key", "") or entry.get("Name", ""),
                "original_text": entry.get("value", "") or (entry.get("Text") or "").strip(),
                "glossary_matches": [],
                "raw_translation": None,
                "prompt": None,
            }
        )
        tasks.append((entry, prompt))
    return tasks


async def _process_and_store_results(
    file_name: str,
    translations: list[dict[str, Any]],
    original_entries: list[dict[str, Any]],
    all_data_dict: list[dict[str, Any]],
    mode: str,
    translated_file_content: str | None,
) -> None:
    raw_by_name: dict[str, str] = {}
    if mode == "improve" and translated_file_content:
        try:
            raw_translation_data = json.loads(translated_file_content)
        except json.JSONDecodeError:
            logger.error(f"Could not parse raw translated file content for {file_name}")
        else:
            if isinstance(raw_translation_data, dict):
                raw_entries, _ = parse_json_entries(raw_translation_data)
                for trans_entry in raw_entries:
                    trans_name = trans_entry.get("Name") or trans_entry.get("key")
                    if trans_name and trans_name not in raw_by_name:
                        raw_text = trans_entry.get("Text") or trans_entry.get("value") or ""
                        raw_by_name[trans_name] = raw_text.strip()

    for entry, original_entry in zip(translations, original_entries, strict=False):
        name = entry.get("Name")
        original_text = (original_entry.get("Text") or "").strip()
        final_text = (entry.get("Text") or "").strip()

        if name and original_text and final_text:
            entry_details = {
                "Name": name,
                "Original": original_text,
                "Raw": raw_by_name.get(name) if mode == "improve" else None,
                "Translated": final_text,
            }
            all_data_dict.append(entry_details)
