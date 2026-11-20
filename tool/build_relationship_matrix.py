from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from src.config import load_config
from src.glossary import load_glossary
from src.relationship_matrix import PronounRule, RelationshipMatrix, build_matrix_from_flowchart
from src.story_flowchart import StoryFlowchart
from src.translator import TranslationEngine
from src.utils import parse_json_entries


def _load_story_text_lookup(json_dir: str | Path | None) -> dict[str, str]:
    """Load Chinese story text by entry Name from unpacked LeanLocalJson files."""
    if not json_dir:
        return {}
    root = Path(json_dir)
    if not root.is_dir():
        return {}

    lookup: dict[str, str] = {}
    for file_path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("Language") != "ChineseSimplified":
            continue
        entries, _ = parse_json_entries(payload)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("Name") or entry.get("key") or "").strip()
            text = str(entry.get("Text") or entry.get("value") or "").strip()
            if name.startswith("Story/") and text:
                lookup[name] = text
    return lookup


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    match = re.search(r"\{[^{}]*\}", raw_text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def enrich_matrix_with_llm(
    matrix: RelationshipMatrix,
    flowchart: StoryFlowchart,
    engine: TranslationEngine,
    max_pairs: int = 20,
    story_texts: dict[str, str] | None = None,
    override_provider: str | None = None,
    override_tier: str | None = None,
    override_model: str | None = None,
) -> int:
    """Enrich top uncurated/interacting pairs using an LLM task (`analyze_relationships` or `translate`)."""
    cfg = getattr(engine, "config", None)
    tasks = getattr(cfg, "tasks", {}) if cfg is not None else {}
    task_name = "analyze_relationships" if "analyze_relationships" in tasks else "translate"

    sample_lines_by_pair: dict[str, list[str]] = {}
    for script_id, script in flowchart.scripts.items():
        for line in script.lines:
            for listener in line.listeners_on_stage:
                pair_id = f"{line.speaker_id}->{listener}"
                bucket = sample_lines_by_pair.setdefault(pair_id, [])
                if len(bucket) < 3:
                    zh = story_texts.get(line.key, "") if story_texts else ""
                    snippet = f"[{script_id}] {line.key}: {zh}" if zh else f"[{script_id}] {line.key}"
                    bucket.append(snippet)

    candidates = [
        (pair_id, pair)
        for pair_id, pair in matrix.pairs.items()
        if pair.interaction_count > 0
    ][: max(0, max_pairs)]

    enriched = 0
    for pair_id, pair in candidates:
        spk = flowchart.characters.get(pair.speaker_id)
        lst = flowchart.characters.get(pair.listener_id)
        spk_desc = f"{pair.speaker_id} ({spk.zh_name if spk else ''} / {spk.vi_name if spk else ''})"
        lst_desc = f"{pair.listener_id} ({lst.zh_name if lst else ''} / {lst.vi_name if lst else ''})"
        samples = "\n".join(sample_lines_by_pair.get(pair_id, [])[:3]) or "(no samples)"

        prompt = (
            "Bạn là chuyên gia bản địa hóa game kiếm hiệp cổ trang Legend of Mortal (Trung -> Việt).\n"
            "Hãy xác định cách xưng hô tiếng Việt kiếm hiệp phù hợp nhất giữa hai nhân vật sau.\n"
            f"Người nói: {spk_desc}\n"
            f"Người nghe: {lst_desc}\n"
            f"Quy tắc hiện tại: self={pair.default.self_pronoun}, target={pair.default.target_pronoun}, tone={pair.default.tone}\n"
            f"Mẫu lời thoại:\n{samples}\n\n"
            "Trả về DUY NHẤT một JSON object với các khóa: "
            '{"self_pronoun": "...", "target_pronoun": "...", "third_person": "...", "tone": "...", "notes": "..."}.'
        )
        result = await engine.translate_text(
            text=pair_id,
            task_name=task_name,
            name=f"Relationship/{pair_id}",
            prompt_data={"prompt": prompt},
            override_provider=override_provider,
            override_tier=override_tier,
            override_model=override_model,
        )
        if not result.succeeded:
            continue
        parsed = _extract_json_object(result.text)
        if not parsed:
            continue

        self_p = str(parsed.get("self_pronoun") or "").strip()
        target_p = str(parsed.get("target_pronoun") or "").strip()
        if not self_p or not target_p:
            continue

        updated = PronounRule(
            stage_id="default",
            self_pronoun=self_p,
            target_pronoun=target_p,
            third_person=str(parsed.get("third_person") or pair.default.third_person).strip(),
            tone=str(parsed.get("tone") or pair.default.tone).strip(),
            notes=str(parsed.get("notes") or pair.default.notes).strip(),
        )
        pair.default = updated
        pair.stages["default"] = updated
        enriched += 1

    return enriched


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build RelationshipMatrix JSON from a StoryFlowchart JSON.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-ff",
        "--flowchart-file",
        default="Resource/story_flowchart.json",
        help="Path to input story_flowchart.json.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="Resource/relationship_matrix.json",
        help="Output path for relationship_matrix.json.",
    )
    parser.add_argument(
        "-gf",
        "--glossary-file",
        default=None,
        help="Optional glossary JSON/TXT file to enrich Vietnamese character names.",
    )
    parser.add_argument(
        "--enrich-with-llm",
        action="store_true",
        help="Optionally enrich top interacting pairs via LLM (task analyze_relationships or translate).",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default=None,
        help="Path to TOML configuration file (used with --enrich-with-llm).",
    )
    parser.add_argument(
        "-jd",
        "--json-dir",
        default=None,
        help="Optional unpacked LeanLocalJson directory to attach sample dialogues for --enrich-with-llm.",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=20,
        help="Maximum number of top interacting pairs to enrich when --enrich-with-llm is set.",
    )
    parser.add_argument("--provider", default=None, help="Override primary provider for LLM enrichment.")
    parser.add_argument("--tier", default=None, help="Override primary tier for LLM enrichment.")
    parser.add_argument("--model", default=None, help="Override primary model for LLM enrichment.")
    return parser


def main(argv: list[str] | None = None) -> RelationshipMatrix:
    parser = build_parser()
    args = parser.parse_args(argv)

    flowchart_path = Path(args.flowchart_file)
    if not flowchart_path.is_file():
        parser.error(f"Flowchart file not found: {flowchart_path}")

    flowchart = StoryFlowchart.from_json_file(flowchart_path)

    glossary_map: dict[str, str] | None = None
    if args.glossary_file:
        name_map, orig_map = load_glossary(args.glossary_file)
        glossary_map = {**orig_map, **name_map}

    matrix = build_matrix_from_flowchart(flowchart, glossary_name_map=glossary_map)

    if args.enrich_with_llm:
        config = load_config(args.config_file)
        engine = TranslationEngine(config)
        story_texts = _load_story_text_lookup(args.json_dir)
        enriched = asyncio.run(
            enrich_matrix_with_llm(
                matrix=matrix,
                flowchart=flowchart,
                engine=engine,
                max_pairs=args.max_pairs,
                story_texts=story_texts,
                override_provider=args.provider,
                override_tier=args.tier,
                override_model=args.model,
            )
        )
        print(f"Enriched {enriched} relationship pairs via LLM.")

    out_path = matrix.to_json_file(args.output)
    print(
        f"RelationshipMatrix written to {out_path} "
        f"(characters={len(matrix.characters)}, pairs={len(matrix.pairs)})"
    )
    return matrix


def main_cli(argv: list[str] | None = None) -> None:
    main(argv)


if __name__ == "__main__":
    main_cli()
