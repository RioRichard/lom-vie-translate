import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.config import load_config
from src.logger import logger
from src.translator import TranslationEngine
from src.utils import build_translation_prompt, parse_json_entries


async def improve_glossary_prompts(
    glossary_file_path: str | Path,
    engine: TranslationEngine,
    override_provider: str | None = None,
    override_tier: str | None = None,
    override_model: str | None = None,
    max_concurrent: int | None = None,
) -> list[dict[str, str]]:
    """Improve glossary entries via the configured LLM translation engine."""
    glossary_path = Path(glossary_file_path)
    logger.info(f"Processing glossary file: {glossary_path}")

    if max_concurrent is None:
        engine_config = getattr(engine, "config", None)
        if engine_config is not None and hasattr(engine_config, "resolve_task_routes"):
            routes, _ = engine_config.resolve_task_routes(
                "improve_glossary",
                provider=override_provider,
                tier=override_tier,
                model=override_model,
            )
            max_concurrent = routes[0].max_concurrent if routes else 5
        else:
            max_concurrent = 5

    semaphore = asyncio.Semaphore(max(max_concurrent, 1))

    with open(glossary_path, encoding="utf-8") as f:
        glossary_data = json.load(f)

    if isinstance(glossary_data, dict):
        entries, _ = parse_json_entries(glossary_data)
    elif isinstance(glossary_data, list):
        entries = glossary_data
    else:
        entries = []

    tasks: list[tuple[str, str, str, str]] = []
    for entry in entries:
        original_text = (entry.get("Original") or "").strip()
        raw_translation = (entry.get("Translated") or "").strip()
        name = entry.get("Name", "") or original_text

        if not original_text or not raw_translation:
            logger.warning(
                f"Skipping entry due to missing original or translated text: {entry}"
            )
            continue

        prompt = build_translation_prompt(
            original_text,
            raw_translation=raw_translation,
        )
        tasks.append((name, original_text, raw_translation, prompt))

    pbar = tqdm(total=len(tasks), desc="Processing entries", mininterval=0.1)

    async def safe_run(task_args: tuple[str, str, str, str]) -> dict[str, Any]:
        name, original_text, raw_translation, prompt = task_args
        async with semaphore:
            translation_result = await engine.translate_text(
                text=original_text,
                task_name="improve_glossary",
                name=name,
                prompt_data={"prompt": prompt},
                override_provider=override_provider,
                override_tier=override_tier,
                override_model=override_model,
            )

            if not translation_result.succeeded:
                logger.warning(
                    f"Glossary improvement failed for '{name}': "
                    f"{translation_result.error or 'unknown error'}"
                )

            entry_result = {
                "Name": name,
                "Original": original_text,
                "RawTranslated": raw_translation,
                "Translated": translation_result.text,
            }
        tqdm.write(f"Processed entry: {entry_result}")
        pbar.update(1)
        return entry_result

    try:
        improved_translations = await asyncio.gather(*[safe_run(task) for task in tasks])
    finally:
        pbar.close()

    return improved_translations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Improve glossary translations using configured LLM routes."
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default=None,
        help="Path to TOML configuration file (defaults to LOM_CONFIG_FILE or config.toml).",
    )
    parser.add_argument(
        "-gf",
        "--glossary-file",
        type=str,
        required=True,
        help="Path to the input glossary JSON file.",
    )
    parser.add_argument(
        "-od",
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save the output JSON file.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Override primary provider for the improve_glossary task.",
    )
    parser.add_argument(
        "--tier",
        default=None,
        help="Override primary tier for the improve_glossary task.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override primary model for the improve_glossary task.",
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    glossary_path = Path(args.glossary_file)
    if not glossary_path.is_file():
        parser.error(f"Glossary file not found: {glossary_path}")

    try:
        config = load_config(args.config_file)
        routes, _ = config.resolve_task_routes(
            "improve_glossary",
            provider=args.provider,
            tier=args.tier,
            model=args.model,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    logger.enable_file_logging()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = TranslationEngine(config)
    improved = await improve_glossary_prompts(
        glossary_path,
        engine=engine,
        override_provider=args.provider,
        override_tier=args.tier,
        override_model=args.model,
        max_concurrent=routes[0].max_concurrent if routes else 5,
    )

    output_file_path = output_dir / f"improved_glossary_prompts_{glossary_path.stem}.json"
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(improved, f, ensure_ascii=False, indent=4)
    logger.info(f"Improved glossary saved to: {output_file_path}")


def main_cli(argv: list[str] | None = None) -> None:
    asyncio.run(main(argv))


if __name__ == "__main__":
    main_cli()
