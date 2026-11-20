import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import RunConfig
from src.file_processor import _process_and_store_results, process_entry, process_json_file
from src.logger import TranslationLogger
from src.main import build_parser, file_producer, main_async
from src.translator import TranslationResult
from src.utils import CONTEXT_AWARE_IMPROVE_RULE_PROMPT, IMPROVE_RULE_PROMPT


async def test_multiline_cache_hit_preserves_newlines_and_skips_duplicate_llm_call(
    tmp_path: Path,
) -> None:
    multiline_zh = "第一行对话\n第二行对话"
    multiline_vi = "Lời thoại dòng 1\nLời thoại dòng 2"

    source_data = {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {"Name": "Story/Line1", "Text": multiline_zh},
                {"Name": "Story/Line2", "Text": multiline_zh},
            ]
        },
    }
    source_file = tmp_path / "story.json"
    file_content = json.dumps(source_data, ensure_ascii=False)
    source_file.write_text(file_content, encoding="utf-8")

    engine = MagicMock()
    engine.translate_text = AsyncMock(
        return_value=TranslationResult(
            text=multiline_vi,
            succeeded=True,
            route_used="local_openai.local.qwen3-14b",
        )
    )

    json_output_dir = tmp_path / "json_out"
    all_data_dict: list[dict] = []
    translation_pairs: dict[str, str] = {}
    run_stats = {
        "from_cache": 0,
        "from_glossary": 0,
        "special_chars": 0,
        "empty": 0,
        "from_pairs": 0,
        "failed": 0,
    }

    # max_concurrent=1 ensures the first duplicate completes and populates translation_pairs
    await process_json_file(
        file_path=source_file,
        file_content=file_content,
        translated_file_content=None,
        all_data_dict=all_data_dict,
        translation_pairs=translation_pairs,
        engine=engine,
        mode="translate",
        json_output_dir=json_output_dir,
        run_stats=run_stats,
        max_concurrent=1,
    )

    # LLM called only once; second identical multiline entry reused translation_pairs cache
    engine.translate_text.assert_awaited_once()
    assert run_stats["from_pairs"] == 1
    assert run_stats["failed"] == 0
    assert translation_pairs[multiline_zh] == multiline_vi

    output_data = json.loads((json_output_dir / "story.json").read_text(encoding="utf-8"))
    out_entries = output_data["entries"]["Array"]
    assert out_entries[0]["Text"] == multiline_vi
    assert out_entries[1]["Text"] == multiline_vi
    assert "\n" in out_entries[0]["Text"]
    assert "\\n" not in out_entries[0]["Text"]


async def test_failed_translation_increments_failed_stat_and_is_not_cached() -> None:
    engine = MagicMock()
    engine.translate_text = AsyncMock(
        return_value=TranslationResult(
            text="无法翻译的句子",
            succeeded=False,
            error="All routes exhausted",
        )
    )

    translate_pairs: dict[str, str] = {}
    run_stats = {"failed": 0, "from_pairs": 0}
    entry = {"Name": "Story/Fail1", "Text": "无法翻译的句子"}

    first_res = await process_entry(
        entry=entry,
        translate_pairs=translate_pairs,
        engine=engine,
        mode="translate",
        run_stats=run_stats,
    )

    assert first_res == {"Name": "Story/Fail1", "Text": "无法翻译的句子"}
    assert run_stats["failed"] == 1
    assert run_stats["from_pairs"] == 0
    assert "无法翻译的句子" not in translate_pairs
    assert translate_pairs == {}

    # A subsequent identical entry must call the engine again rather than hitting a poisoned cache
    await process_entry(
        entry={"Name": "Story/Fail2", "Text": "无法翻译的句子"},
        translate_pairs=translate_pairs,
        engine=engine,
        mode="translate",
        run_stats=run_stats,
    )
    assert engine.translate_text.await_count == 2
    assert run_stats["failed"] == 2
    assert translate_pairs == {}


async def test_process_and_store_results_supports_array_and_direct_list_in_improve_mode() -> None:
    original_entries = [
        {"Name": "Dialogue/1", "Text": "你好"},
        {"Name": "Dialogue/2", "Text": "再见"},
    ]
    translations = [
        {"Name": "Dialogue/1", "Text": "Xin chào"},
        {"Name": "Dialogue/2", "Text": "Tạm biệt"},
    ]

    # 1. entries.Array format for raw translated content
    raw_array_content = json.dumps(
        {
            "Language": "Vietnamese",
            "entries": {
                "Array": [
                    {"Name": "Dialogue/1", "Text": "  Chào thô  "},
                    {"Name": "Dialogue/2", "Text": "Tạm biệt thô"},
                ]
            },
        },
        ensure_ascii=False,
    )
    array_results: list[dict] = []
    await _process_and_store_results(
        file_name="array_test.json",
        translations=translations,
        original_entries=original_entries,
        all_data_dict=array_results,
        mode="improve",
        translated_file_content=raw_array_content,
    )
    assert array_results == [
        {"Name": "Dialogue/1", "Original": "你好", "Raw": "Chào thô", "Translated": "Xin chào"},
        {"Name": "Dialogue/2", "Original": "再见", "Raw": "Tạm biệt thô", "Translated": "Tạm biệt"},
    ]

    # 2. Direct-list entries format for raw translated content
    raw_direct_content = json.dumps(
        {
            "Language": "Vietnamese",
            "entries": [
                {"Name": "Dialogue/1", "Text": "Chào bản list"},
                {"Name": "Dialogue/2", "Text": "Hẹn gặp lại bản list"},
            ],
        },
        ensure_ascii=False,
    )
    direct_results: list[dict] = []
    await _process_and_store_results(
        file_name="direct_test.json",
        translations=translations,
        original_entries=original_entries,
        all_data_dict=direct_results,
        mode="improve",
        translated_file_content=raw_direct_content,
    )
    assert direct_results == [
        {
            "Name": "Dialogue/1",
            "Original": "你好",
            "Raw": "Chào bản list",
            "Translated": "Xin chào",
        },
        {
            "Name": "Dialogue/2",
            "Original": "再见",
            "Raw": "Hẹn gặp lại bản list",
            "Translated": "Tạm biệt",
        },
    ]


async def test_file_producer_skips_english_and_queues_late_language_chinese(
    tmp_path: Path,
) -> None:
    en_file = tmp_path / "en.json"
    en_file.write_text(
        json.dumps({"Language": "English", "entries": [{"Name": "A", "Text": "Hello"}]}),
        encoding="utf-8",
    )

    zh_fast_file = tmp_path / "zh_fast.json"
    zh_fast_file.write_text(
        json.dumps(
            {"Language": "ChineseSimplified", "entries": [{"Name": "B", "Text": "你好"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Put >5KB of entries BEFORE "Language" so it lies past the 4096-byte fast-path read
    padded_entries = [
        {"Name": f"Entry/{i:04d}", "Text": f"Padding text block number {i:04d} " + ("x" * 60)}
        for i in range(60)
    ]
    zh_late_payload = {"entries": padded_entries, "Language": "ChineseSimplified"}
    zh_late_str = json.dumps(zh_late_payload, ensure_ascii=False)
    assert zh_late_str.index('"Language"') > 5000

    zh_late_file = tmp_path / "zh_late.json"
    zh_late_file.write_text(zh_late_str, encoding="utf-8")

    # Non-Chinese file with "Language" after byte 4096 must also be skipped
    jp_late_str = json.dumps({"entries": padded_entries, "Language": "Japanese"})
    assert jp_late_str.index('"Language"') > 5000
    jp_late_file = tmp_path / "jp_late.json"
    jp_late_file.write_text(jp_late_str, encoding="utf-8")

    queue: asyncio.Queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(4)

    await file_producer(
        file_paths=[en_file, zh_fast_file, zh_late_file, jp_late_file],
        queue=queue,
        semaphore=semaphore,
        progress_bar=None,
        mode="translate",
        translated_dir=None,
    )

    queued_items = []
    while not queue.empty():
        queued_items.append(await queue.get())

    queued_names = {Path(item[0]).name for item in queued_items}
    assert queued_names == {"zh_fast.json", "zh_late.json"}

    queued_by_name = {Path(item[0]).name: item[1] for item in queued_items}
    parsed_late = json.loads(queued_by_name["zh_late.json"])
    assert parsed_late["Language"] == "ChineseSimplified"
    assert len(parsed_late["entries"]) == 60


def test_logger_run_summary_math_and_no_implicit_logs_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    test_logger = TranslationLogger()
    captured: list[str] = []
    monkeypatch.setattr(test_logger, "info", lambda msg, *args, **kwargs: captured.append(str(msg)))

    # 20 - from_cache(2) - from_glossary(3) - from_reuse_translation(4)
    #    - empty_lines(1) - special_chars(2) - failed(3) = 5
    test_logger.run_summary(
        files_processed=3,
        total_translations=20,
        total_time=1.25,
        from_cache=2,
        from_glossary=3,
        empty_lines=1,
        special_chars=2,
        from_reuse_translation=4,
        failed=3,
    )

    assert len(captured) == 1
    summary_text = captured[0]
    assert "New Translations: 5" in summary_text
    assert "Reuse Translations: 4" in summary_text
    assert "Failed: 3" in summary_text

    # Clamped at 0 when deductions exceed total_translations
    test_logger.run_summary(
        files_processed=1,
        total_translations=4,
        total_time=0.5,
        from_reuse_translation=3,
        failed=5,
    )
    assert "New Translations: 0" in captured[1]

    # Without enable_file_logging(), no logs/ directory is created
    assert not (tmp_path / "logs").exists()


async def test_context_safe_caching_prevents_cross_speaker_collision_and_keeps_pairs_clean() -> None:
    engine = MagicMock()
    engine.translate_text = AsyncMock(
        side_effect=[
            TranslationResult(text="Đi thôi sư huynh!", succeeded=True),
            TranslationResult(text="Đi thôi sư phụ!", succeeded=True),
            TranslationResult(text="Đi thôi!", succeeded=True),
        ]
    )

    translate_pairs: dict[str, str] = {}
    contextual_pairs: dict[str, str] = {}
    run_stats = {"from_pairs": 0, "failed": 0}

    # Two distinct story entries with identical Chinese text must NOT collide via translate_pairs
    res1 = await process_entry(
        entry={"Name": "Story/S1_1", "Text": "走吧。"},
        translate_pairs=translate_pairs,
        engine=engine,
        prompt_data={"story_context_header": "Cảnh: S1\nNgười nói: Triệu Hoạt"},
        run_stats=run_stats,
        contextual_pairs=contextual_pairs,
    )
    res2 = await process_entry(
        entry={"Name": "Story/S1_2", "Text": "走吧。"},
        translate_pairs=translate_pairs,
        engine=engine,
        prompt_data={"story_context_header": "Cảnh: S1\nNgười nói: Đường Bố Y"},
        run_stats=run_stats,
        contextual_pairs=contextual_pairs,
    )
    # Exact same (Name, Original) hits contextual_pairs without an extra LLM call
    res1_repeat = await process_entry(
        entry={"Name": "Story/S1_1", "Text": "走吧。"},
        translate_pairs=translate_pairs,
        engine=engine,
        prompt_data={"story_context_header": "Cảnh: S1\nNgười nói: Triệu Hoạt"},
        run_stats=run_stats,
        contextual_pairs=contextual_pairs,
    )

    assert res1 == {"Name": "Story/S1_1", "Text": "Đi thôi sư huynh!"}
    assert res2 == {"Name": "Story/S1_2", "Text": "Đi thôi sư phụ!"}
    assert res1_repeat == {"Name": "Story/S1_1", "Text": "Đi thôi sư huynh!"}
    assert run_stats["from_pairs"] == 1
    # Clean translate_pairs must have no 'Name::Original' keys and no story-contextual entries
    assert translate_pairs == {}

    # Non-contextual UI entry still populates and reuses clean translate_pairs
    res_ui = await process_entry(
        entry={"Name": "UI/Go", "Text": "走吧。"},
        translate_pairs=translate_pairs,
        engine=engine,
        prompt_data={"story_context_header": None},
        run_stats=run_stats,
        contextual_pairs=contextual_pairs,
    )
    assert res_ui == {"Name": "UI/Go", "Text": "Đi thôi!"}
    assert translate_pairs == {"走吧。": "Đi thôi!"}
    assert engine.translate_text.await_count == 3


async def test_process_json_file_flowchart_execution_order_and_sliding_window(
    tmp_path: Path,
) -> None:
    # Entries in JSON are intentionally NOT in script execution order:
    # Script execution order is L1 -> L2 -> L3, while UI/Confirm is unmapped.
    source_data = {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {"Name": "Story/S1_L2", "Text": "走吧。"},
                {"Name": "UI/Confirm", "Text": "确认"},
                {"Name": "Story/S1_L1", "Text": "师弟准备好了吗？"},
                {"Name": "Story/S1_L3", "Text": "走吧。"},
            ]
        },
    }
    source_file = tmp_path / "story_mixed.json"
    file_content = json.dumps(source_data, ensure_ascii=False)
    source_file.write_text(file_content, encoding="utf-8")

    line1 = SimpleNamespace(
        key="Story/S1_L1",
        line_type="dialogue",
        speaker_id="brother1",
        speaker_custom_name=None,
        portrait_mood="normal",
        listeners_on_stage=["player"],
        branch_path="main",
    )
    line2 = SimpleNamespace(
        key="Story/S1_L2",
        line_type="dialogue",
        speaker_id="player",
        speaker_custom_name=None,
        portrait_mood="determined",
        listeners_on_stage=["brother1"],
        branch_path="main",
    )
    line3 = SimpleNamespace(
        key="Story/S1_L3",
        line_type="dialogue",
        speaker_id="brother1",
        speaker_custom_name=None,
        portrait_mood="serious",
        listeners_on_stage=["player"],
        branch_path="main",
    )
    script = SimpleNamespace(
        script_id="S1",
        title_zh="下山",
        ending_ids=[],
        lines=[line1, line2, line3],
    )

    class StubFlowchart:
        characters = {
            "player": SimpleNamespace(vi_name="Triệu Hoạt", zh_name="赵活", zh_title=""),
            "brother1": SimpleNamespace(vi_name="Đường Bố Y", zh_name="唐布衣", zh_title=""),
        }
        scripts = {"S1": script}

        def get_line_context(self, key: str, window: int = 4, lookahead: int = 1):
            order = [line1, line2, line3]
            for idx, node in enumerate(order):
                if node.key == key:
                    prev_lines = order[max(0, idx - window) : idx] if window > 0 else []
                    next_lines = order[idx + 1 : idx + 1 + lookahead] if lookahead > 0 else []
                    return SimpleNamespace(
                        script=script,
                        line=node,
                        prev_lines=prev_lines,
                        next_lines=next_lines,
                    )
            return None

    class StubMatrix:
        def resolve_pair(self, speaker_id: str, listener_id: str, script_id=None, branch_path=None):
            if speaker_id == "player":
                return SimpleNamespace(
                    self_pronoun="đệ",
                    target_pronoun="đại sư huynh",
                    third_person="huynh ấy",
                    tone="tôn kính",
                    stage_id="disciple",
                )
            return SimpleNamespace(
                self_pronoun="ta",
                target_pronoun="sư đệ",
                third_person="hắn",
                tone="ôn hòa",
                stage_id="senior",
            )

    call_order: list[str] = []
    prompts_by_name: dict[str, str] = {}
    outputs_by_name = {
        "Story/S1_L1": "Sư đệ chuẩn bị xong chưa?",
        "Story/S1_L2": "Đệ sẵn sàng rồi, đại sư huynh đi thôi!",
        "Story/S1_L3": "Đi thôi, sư đệ!",
        "UI/Confirm": "Xác nhận",
    }

    async def fake_translate_text(**kwargs):
        name = kwargs["name"]
        call_order.append(name)
        prompts_by_name[name] = kwargs["prompt_data"]["prompt"]
        return TranslationResult(text=outputs_by_name[name], succeeded=True)

    engine = MagicMock()
    engine.translate_text = AsyncMock(side_effect=fake_translate_text)

    json_output_dir = tmp_path / "json_out"
    all_data_dict: list[dict] = []
    translation_pairs: dict[str, str] = {}
    run_stats = {
        "from_cache": 0,
        "from_glossary": 0,
        "special_chars": 0,
        "empty": 0,
        "from_pairs": 0,
        "failed": 0,
    }

    await process_json_file(
        file_path=source_file,
        file_content=file_content,
        translated_file_content=None,
        all_data_dict=all_data_dict,
        translation_pairs=translation_pairs,
        engine=engine,
        mode="translate",
        json_output_dir=json_output_dir,
        run_stats=run_stats,
        max_concurrent=4,
        flowchart=StubFlowchart(),
        relationship_matrix=StubMatrix(),
        dialogue_window=2,
    )

    # Mapped script lines executed in flowchart order L1 -> L2 -> L3
    story_order = [name for name in call_order if name.startswith("Story/")]
    assert story_order == ["Story/S1_L1", "Story/S1_L2", "Story/S1_L3"]
    assert "UI/Confirm" in call_order
    # L2 and L3 have identical text "走吧。" but different speakers; neither collided via cache
    assert engine.translate_text.await_count == 4

    # L1 saw L2 lookahead
    assert "Lời thoại kế tiếp" in prompts_by_name["Story/S1_L1"]
    assert "Triệu Hoạt (赵活): 走吧。" in prompts_by_name["Story/S1_L1"]

    # L2 saw translated L1 in prev_lines and raw L3 in next_lines
    assert "Hội thoại trước đó:" in prompts_by_name["Story/S1_L2"]
    assert (
        "Đường Bố Y (唐布衣): 师弟准备好了吗？ => Sư đệ chuẩn bị xong chưa?"
        in prompts_by_name["Story/S1_L2"]
    )
    assert "Đường Bố Y (唐布衣): 走吧。" in prompts_by_name["Story/S1_L2"]

    # L3 saw BOTH translated L1 and L2 in sliding window (window=2)
    assert (
        "Đường Bố Y (唐布衣): 师弟准备好了吗？ => Sư đệ chuẩn bị xong chưa?"
        in prompts_by_name["Story/S1_L3"]
    )
    assert (
        "Triệu Hoạt (赵活): 走吧。 => Đệ sẵn sàng rồi, đại sư huynh đi thôi!"
        in prompts_by_name["Story/S1_L3"]
    )

    # Final JSON and all_data_dict must preserve exact original entries_list index order
    out_data = json.loads((json_output_dir / "story_mixed.json").read_text(encoding="utf-8"))
    assert out_data["entries"]["Array"] == [
        {"Name": "Story/S1_L2", "Text": "Đệ sẵn sàng rồi, đại sư huynh đi thôi!"},
        {"Name": "UI/Confirm", "Text": "Xác nhận"},
        {"Name": "Story/S1_L1", "Text": "Sư đệ chuẩn bị xong chưa?"},
        {"Name": "Story/S1_L3", "Text": "Đi thôi, sư đệ!"},
    ]
    assert [item["Name"] for item in all_data_dict] == [
        "Story/S1_L2",
        "UI/Confirm",
        "Story/S1_L1",
        "Story/S1_L3",
    ]
    # translation_pairs remains clean (no '::' contextual keys)
    assert translation_pairs == {"确认": "Xác nhận"}


async def test_process_json_file_improve_mode_with_flowchart_uses_context_aware_rule(
    tmp_path: Path,
) -> None:
    source_data = {
        "Language": "ChineseSimplified",
        "entries": [{"Name": "Story/S2_L1", "Text": "师兄\n请留步"}],
    }
    raw_data = {
        "Language": "Vietnamese",
        "entries": [{"Name": "Story/S2_L1", "Text": "Anh ơi\r\ndừng bước"}],
    }
    source_file = tmp_path / "improve_story.json"
    file_content = json.dumps(source_data, ensure_ascii=False)
    raw_content = json.dumps(raw_data, ensure_ascii=False)
    source_file.write_text(file_content, encoding="utf-8")

    line = SimpleNamespace(
        key="Story/S2_L1",
        line_type="dialogue",
        speaker_id="player",
        speaker_custom_name=None,
        portrait_mood="urgent",
        listeners_on_stage=["brother1"],
        branch_path="main",
    )
    script = SimpleNamespace(script_id="S2", title_zh="", ending_ids=[], lines=[line])

    class StubFlowchart:
        characters = {
            "player": SimpleNamespace(vi_name="Triệu Hoạt", zh_name="赵活", zh_title=""),
            "brother1": SimpleNamespace(vi_name="Đường Bố Y", zh_name="唐布衣", zh_title=""),
        }
        scripts = {"S2": script}

        def get_line_context(self, key: str, window: int = 4, lookahead: int = 1):
            if key == "Story/S2_L1":
                return SimpleNamespace(script=script, line=line, prev_lines=[], next_lines=[])
            return None

    captured_prompts: list[str] = []

    async def fake_translate_text(**kwargs):
        captured_prompts.append(kwargs["prompt_data"]["prompt"])
        return TranslationResult(text="Sư huynh\nxin dừng bước", succeeded=True)

    engine = MagicMock()
    engine.translate_text = AsyncMock(side_effect=fake_translate_text)

    all_data_dict: list[dict] = []
    await process_json_file(
        file_path=source_file,
        file_content=file_content,
        translated_file_content=raw_content,
        all_data_dict=all_data_dict,
        translation_pairs={},
        engine=engine,
        mode="improve",
        translated_dir=tmp_path,
        json_output_dir=tmp_path / "out",
        flowchart=StubFlowchart(),
    )

    assert len(captured_prompts) == 1
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT in captured_prompts[0]
    assert IMPROVE_RULE_PROMPT not in captured_prompts[0]
    assert "Bản dịch thô để tham khảo:\nAnh ơi[|][||]dừng bước" in captured_prompts[0]
    assert all_data_dict == [
        {
            "Name": "Story/S2_L1",
            "Original": "师兄\n请留步",
            "Raw": "Anh ơi\r\ndừng bước",
            "Translated": "Sư huynh\nxin dừng bước",
        }
    ]


async def test_config_and_main_cli_flowchart_flags_and_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = RunConfig()
    assert cfg.flowchart_file is None
    assert cfg.relationship_file is None
    assert cfg.dialogue_window == 4

    parser = build_parser()
    parsed = parser.parse_args(
        ["-ff", "flow.json", "-rf", "rel.json", "-dw", "6"]
    )
    assert parsed.flowchart_file == "flow.json"
    assert parsed.relationship_file == "rel.json"
    assert parsed.dialogue_window == 6

    # Missing explicit --flowchart-file triggers SystemExit (parser.error) without creating logs/
    monkeypatch.chdir(tmp_path)
    template_cfg = Path(__file__).resolve().parent.parent / "config.toml.template"
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "sample.json").write_text(
        json.dumps({"Language": "ChineseSimplified", "entries": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        await main_async(
            [
                "-c",
                str(template_cfg),
                "-id",
                str(input_dir),
                "-ff",
                str(tmp_path / "missing_flowchart.json"),
            ]
        )
    assert not (tmp_path / "logs").exists()
