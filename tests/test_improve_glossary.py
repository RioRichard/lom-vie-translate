import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import load_config
from src.translator import TranslationEngine, TranslationResult
from tool.improve_glossary import improve_glossary_prompts

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_CONFIG = REPO_ROOT / "config.toml.template"


async def test_improve_glossary_prompts_passes_task_and_dict_prompt_data(
    tmp_path: Path,
) -> None:
    glossary_file = tmp_path / "glossary.json"
    glossary_entries = [
        {"Name": "Sect/Tang", "Original": "唐门", "Translated": "Môn Đường"},
        {"Name": "", "Original": "赵活", "Translated": "Triệu Hoạt thô"},
        {"Name": "Skipped/Empty", "Original": "", "Translated": "Bỏ qua"},
    ]
    glossary_file.write_text(
        json.dumps(glossary_entries, ensure_ascii=False),
        encoding="utf-8",
    )

    translations_by_original = {
        "唐门": "Đường Môn",
        "赵活": "Triệu Hoạt",
    }

    async def fake_translate_text(**kwargs):
        return TranslationResult(
            text=translations_by_original[kwargs["text"]],
            succeeded=True,
            route_used="local_openai.local.qwen3-14b",
        )

    engine = MagicMock()
    engine.config = None
    engine.translate_text = AsyncMock(side_effect=fake_translate_text)

    results = await improve_glossary_prompts(
        glossary_file_path=glossary_file,
        engine=engine,
        override_provider="gemini",
        override_tier="free",
        override_model="gemini-2.5-flash",
        max_concurrent=2,
    )

    assert engine.translate_text.await_count == 2
    assert results == [
        {
            "Name": "Sect/Tang",
            "Original": "唐门",
            "RawTranslated": "Môn Đường",
            "Translated": "Đường Môn",
        },
        {
            "Name": "赵活",
            "Original": "赵活",
            "RawTranslated": "Triệu Hoạt thô",
            "Translated": "Triệu Hoạt",
        },
    ]

    for call, expected_orig, expected_raw in zip(
        engine.translate_text.call_args_list,
        ["唐门", "赵活"],
        ["Môn Đường", "Triệu Hoạt thô"],
        strict=True,
    ):
        assert call.kwargs["task_name"] == "improve_glossary"
        assert call.kwargs["override_provider"] == "gemini"
        assert call.kwargs["override_tier"] == "free"
        assert call.kwargs["override_model"] == "gemini-2.5-flash"

        prompt_data = call.kwargs["prompt_data"]
        assert isinstance(prompt_data, dict)
        assert isinstance(prompt_data.get("prompt"), str)
        assert expected_orig in prompt_data["prompt"]
        assert expected_raw in prompt_data["prompt"]
        assert "9." in prompt_data["prompt"]


async def test_improve_glossary_prompts_integrates_with_translation_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    glossary_file = tmp_path / "glossary_integration.json"
    glossary_file.write_text(
        json.dumps(
            [{"Name": "Skill/1", "Original": "暗器", "Translated": "Vũ khí ẩn"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cfg = load_config(TEMPLATE_CONFIG, load_env=False)
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Ám khí"))]
        )
    )
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    results = await improve_glossary_prompts(glossary_file, engine=engine)

    assert results == [
        {
            "Name": "Skill/1",
            "Original": "暗器",
            "RawTranslated": "Vũ khí ẩn",
            "Translated": "Ám khí",
        }
    ]
    mock_completion.assert_awaited_once()
    sent_prompt = mock_completion.call_args.kwargs["messages"][0]["content"]
    assert "暗器" in sent_prompt
    assert "Vũ khí ẩn" in sent_prompt
    assert mock_completion.call_args.kwargs["num_retries"] == 0
