import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.glossary import find_original_matches, load_glossary, load_glossary_async
from src.prompt_preparer import prepare_prompt_data
from src.utils import (
    CONTEXT_AWARE_IMPROVE_RULE_PROMPT,
    IMPROVE_RULE_PROMPT,
    build_translation_prompt,
    parse_json_entries,
    postprocess_text,
    preprocess_text,
)


def test_preprocess_and_postprocess_preserve_markers_and_linebreaks() -> None:
    raw_game_text = "  捅人伤害+{{0:N0}} {title} [{0}]\r\n第二行  "
    preprocessed = preprocess_text(raw_game_text)
    assert preprocessed == "捅人伤害+{{0:N0}} {title} [{0}][|][||]第二行"

    # Existing [|] / [||] and markup placeholders remain intact in preprocess_text
    assert preprocess_text("[|]{{0:N0}}[||]{title}[{0}]") == "[|]{{0:N0}}[||]{title}[{0}]"

    # postprocess_text(for_json=True) restores real \r and \n and cleans wrapper noise
    llm_output = "Đây là bản dịch:\n**Đâm người +{{0:N0}}** {title} [{0}][|][||]Dòng 2\\nDòng 3"
    processed_json = postprocess_text(llm_output, for_json=True)
    assert processed_json == "Đâm người +{{0:N0}} {title} [{0}]\r\nDòng 2\nDòng 3"

    # postprocess_text(for_json=False) escapes \r and \n as literal \\r and \\n for .txt output
    processed_txt = postprocess_text(llm_output, for_json=False)
    assert processed_txt == "Đâm người +{{0:N0}} {title} [{0}]\\r\\nDòng 2\\nDòng 3"


def test_parse_json_entries_array_direct_and_missing() -> None:
    array_data = {
        "Language": "ChineseSimplified",
        "entries": {"Array": [{"Name": "A", "Text": "甲"}, {"Name": "B", "Text": "乙"}]},
    }
    entries, is_array = parse_json_entries(array_data)
    assert is_array is True
    assert entries == [{"Name": "A", "Text": "甲"}, {"Name": "B", "Text": "乙"}]

    direct_data = {
        "Language": "ChineseSimplified",
        "entries": [{"Name": "C", "Text": "丙"}],
    }
    entries_direct, is_array_direct = parse_json_entries(direct_data)
    assert is_array_direct is False
    assert entries_direct == [{"Name": "C", "Text": "丙"}]

    # Empty & missing cases
    assert parse_json_entries({"entries": {"Array": []}}) == ([], True)
    assert parse_json_entries({"entries": []}) == ([], False)
    assert parse_json_entries({}) == ([], False)
    assert parse_json_entries({"entries": None}) == ([], False)
    assert parse_json_entries({"entries": {"Other": []}}) == ([], False)


async def test_load_glossary_sync_and_async_all_formats(tmp_path: Path) -> None:
    # 1. JSON list format
    json_list_file = tmp_path / "glossary_list.json"
    json_list_file.write_text(
        json.dumps(
            [
                {"Name": "UI/Confirm", "Original": "确认", "Translated": "Xác nhận"},
                {"Name": "Sect/Tang", "Original": "唐门", "Translated": "Đường Môn"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    sync_names, sync_origs = load_glossary(json_list_file)
    async_names, async_origs = await load_glossary_async(json_list_file)
    assert sync_names == async_names == {"UI/Confirm": "Xác nhận", "Sect/Tang": "Đường Môn"}
    assert sync_origs == async_origs == {"确认": "Xác nhận", "唐门": "Đường Môn"}

    # 2. JSON dict format — must populate BOTH name_to_translated AND original_to_translated
    json_dict_file = tmp_path / "glossary_dict.json"
    json_dict_file.write_text(
        json.dumps({"赵活": "Triệu Hoạt", "UI/Cancel": "Hủy"}, ensure_ascii=False),
        encoding="utf-8",
    )

    dict_sync_names, dict_sync_origs = load_glossary(json_dict_file)
    dict_async_names, dict_async_origs = await load_glossary_async(json_dict_file)
    expected_dict = {"赵活": "Triệu Hoạt", "UI/Cancel": "Hủy"}
    assert dict_sync_names == expected_dict
    assert dict_sync_origs == expected_dict
    assert dict_async_names == expected_dict
    assert dict_async_origs == expected_dict

    # 3. Plain .txt format (orig=trans) — populates both maps
    txt_file = tmp_path / "glossary.txt"
    txt_file.write_text(
        "唐门=Đường Môn\n  赵活 = Triệu Hoạt  \ninvalid_line_without_equals\n=missing_key\n",
        encoding="utf-8",
    )

    txt_sync_names, txt_sync_origs = load_glossary(txt_file)
    txt_async_names, txt_async_origs = await load_glossary_async(txt_file)
    expected_txt = {"唐门": "Đường Môn", "赵活": "Triệu Hoạt"}
    assert txt_sync_names == expected_txt
    assert txt_sync_origs == expected_txt
    assert txt_async_names == expected_txt
    assert txt_async_origs == expected_txt

    # 4. Missing explicit file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_glossary(tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError):
        await load_glossary_async(tmp_path / "does_not_exist.json")


def test_find_original_matches_longest_first() -> None:
    glossary = {
        "唐": "Đường",
        "唐门": "Đường Môn",
        "唐门外姓弟子": "Đệ tử ngoại thất Đường Môn",
        "武林": "Võ lâm",
    }

    matches = find_original_matches("赵活是唐门外姓弟子，闯荡江湖。", glossary)
    assert matches == [
        ("唐门外姓弟子", "Đệ tử ngoại thất Đường Môn"),
        ("唐门", "Đường Môn"),
        ("唐", "Đường"),
    ]
    assert find_original_matches("", glossary) == []
    assert find_original_matches("唐门", None) == []
    assert find_original_matches("唐门", {}) == []


def test_build_translation_prompt_numbering_and_optional_sections() -> None:
    # Translate mode (no raw_translation)
    translate_prompt = build_translation_prompt(
        original_text="唐门外姓弟子",
        glossary_matches=[("唐门", "Đường Môn")],
    )
    assert translate_prompt.count("\n8.") == 1
    assert "\n9." not in translate_prompt
    assert IMPROVE_RULE_PROMPT not in translate_prompt
    assert "Bản dịch thô để tham khảo:" not in translate_prompt
    assert "- 唐门=Đường Môn" in translate_prompt
    assert "Văn bản cần được dịch:\n唐门外姓弟子" in translate_prompt

    # Improve mode (with raw_translation)
    improve_prompt = build_translation_prompt(
        original_text="唐门外姓弟子",
        raw_translation="Đệ tử ngoài họ Đường Môn",
    )
    assert improve_prompt.count("\n8.") == 1
    assert improve_prompt.count("\n9.") == 1
    assert IMPROVE_RULE_PROMPT in improve_prompt
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT not in improve_prompt
    assert "Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:" not in improve_prompt
    assert "Bản dịch thô để tham khảo:\nĐệ tử ngoài họ Đường Môn" in improve_prompt
    assert "Một số thuật ngữ/cụm từ cần giữ nguyên:" not in improve_prompt


def test_build_translation_prompt_with_story_context_translate_and_improve() -> None:
    ctx = "Cảnh: S1001\nNgười nói: Triệu Hoạt (赵活) [dialogue]"

    # Whitespace-only story_context preserves backward-compatible behavior
    blank_ctx_improve = build_translation_prompt(
        original_text="师兄好",
        raw_translation="Chào sư huynh",
        story_context="   \n ",
    )
    assert IMPROVE_RULE_PROMPT in blank_ctx_improve
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT not in blank_ctx_improve
    assert "Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:" not in blank_ctx_improve

    # Translate mode with story_context inserts context before glossary & target text
    ctx_translate = build_translation_prompt(
        original_text="师兄好",
        glossary_matches=[("师兄", "Sư huynh")],
        story_context=f"  {ctx}  ",
    )
    assert "\n9." not in ctx_translate
    assert f"Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:\n{ctx}" in ctx_translate
    ctx_idx = ctx_translate.index("Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:")
    glossary_idx = ctx_translate.index("Một số thuật ngữ/cụm từ cần giữ nguyên:")
    target_idx = ctx_translate.index("Văn bản cần được dịch:")
    assert ctx_idx < glossary_idx < target_idx

    # Improve mode with story_context switches rule 9 to CONTEXT_AWARE_IMPROVE_RULE_PROMPT
    ctx_improve = build_translation_prompt(
        original_text="师兄好",
        raw_translation="Chào anh",
        story_context=ctx,
    )
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT in ctx_improve
    assert IMPROVE_RULE_PROMPT not in ctx_improve
    assert ctx_improve.count("\n9.") == 1
    assert f"Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:\n{ctx}" in ctx_improve
    assert "Bản dịch thô để tham khảo:\nChào anh" in ctx_improve


async def test_prepare_prompt_data_raw_preprocessing_and_story_context() -> None:
    original_data = {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {"Name": "Story/S100_L2", "Text": "师兄，\n走吧！"},
                {"Name": "UI/Confirm", "Text": "确认"},
            ]
        },
    }
    raw_content = json.dumps(
        {
            "Language": "Vietnamese",
            "entries": {
                "Array": [
                    {"Name": "Story/S100_L2", "Text": "  Anh ơi,\r\nđi thôi!  "},
                    {"Name": "UI/Confirm", "Text": "   "},
                ]
            },
        },
        ensure_ascii=False,
    )

    prev_line = SimpleNamespace(
        key="Story/S100_L1",
        speaker_id="brother1",
        speaker_custom_name=None,
    )
    curr_line = SimpleNamespace(
        key="Story/S100_L2",
        line_type="dialogue",
        speaker_id="player",
        speaker_custom_name=None,
        portrait_mood="happy",
        listeners_on_stage=["brother1"],
        branch_path="choice_1",
    )
    next_line = SimpleNamespace(
        key="Story/S100_L3",
        speaker_id="brother1",
        speaker_custom_name=None,
    )
    script = SimpleNamespace(
        script_id="S100",
        title_zh="唐门日常",
        ending_ids=["END_01"],
    )

    class StubFlowchart:
        characters = {
            "player": SimpleNamespace(vi_name="Triệu Hoạt", zh_name="赵活", zh_title="Đệ tử ngoại thất"),
            "brother1": SimpleNamespace(vi_name="Đường Bố Y", zh_name="唐布衣", zh_title="Đại sư huynh"),
        }

        def get_line_context(self, key: str, window: int = 4, lookahead: int = 1):
            assert window == 3
            assert lookahead == 1
            if key == "Story/S100_L2":
                return SimpleNamespace(
                    script=script,
                    line=curr_line,
                    prev_lines=[prev_line],
                    next_lines=[next_line],
                )
            return None

    class StubMatrix:
        def resolve_pair(self, speaker_id: str, listener_id: str, script_id=None, branch_path=None):
            assert speaker_id == "player"
            assert listener_id == "brother1"
            assert script_id == "S100"
            assert branch_path == "choice_1"
            return SimpleNamespace(
                self_pronoun="đệ",
                target_pronoun="đại sư huynh",
                third_person="huynh ấy",
                tone="kính trọng",
                stage_id="disciple",
            )

    prompt_data, _ = await prepare_prompt_data(
        original_file_path="story.json",
        original_data=original_data,
        translated_file_content=raw_content,
        original_to_translated={"师兄": "Sư huynh"},
        flowchart=StubFlowchart(),
        relationship_matrix=StubMatrix(),
        dialogue_window=3,
    )

    assert len(prompt_data) == 2

    story_item = prompt_data[0]
    assert story_item["original_text"] == "师兄，[||]走吧！"
    # Raw translation must be stripped and preprocessed consistently with original_text
    assert story_item["raw_translation"] == "Anh ơi,[|][||]đi thôi!"
    assert story_item["prev_keys"] == ["Story/S100_L1"]
    assert story_item["next_keys"] == ["Story/S100_L3"]
    assert story_item["speaker_label"] == "Triệu Hoạt (赵活)"
    assert story_item["script_id"] == "S100"

    header = story_item["story_context_header"]
    assert header is not None
    assert "S100" in header
    assert "唐门日常" in header
    assert "choice_1" in header
    assert "END_01" in header
    assert "Triệu Hoạt (赵活)" in header
    assert "happy" in header
    assert "Đường Bố Y (唐布衣)" in header
    assert "tự xưng 'đệ' / gọi 'đại sư huynh'" in header
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT in story_item["prompt"]
    assert "Bản dịch thô để tham khảo:\nAnh ơi,[|][||]đi thôi!" in story_item["prompt"]

    # Unmapped UI item has empty story context and whitespace-only raw translation normalized to None
    ui_item = prompt_data[1]
    assert ui_item["raw_translation"] is None
    assert ui_item["prev_keys"] == []
    assert ui_item["next_keys"] == []
    assert ui_item["speaker_label"] is None
    assert ui_item["script_id"] is None
    assert ui_item["story_context_header"] is None
    assert CONTEXT_AWARE_IMPROVE_RULE_PROMPT not in ui_item["prompt"]
