"""Tests for Pydantic data models (DEF-06, DEF-07)."""

from __future__ import annotations

from lom_translate.models import LocalizationEntry, LocalizationFile, Settings


def test_schema_a_parsing(sample_schema_a_dict):
    """DEF-07: Schema A (wrapped entries.Array) parses correctly."""
    loc_file = LocalizationFile.model_validate(sample_schema_a_dict)
    assert loc_file.is_schema_a is True
    entries = loc_file.get_entries()
    assert len(entries) == 2
    assert entries[0].Name == "Story/Intro_1"
    assert entries[1].Name == "Story/Intro_2"


def test_schema_b_parsing(sample_schema_b_dict):
    """DEF-07: Schema B (flat entries list) parses correctly without AttributeError."""
    loc_file = LocalizationFile.model_validate(sample_schema_b_dict)
    assert loc_file.is_schema_a is False
    entries = loc_file.get_entries()
    assert len(entries) == 2
    assert entries[0].Name == "LegendInfo/Skill_1"


def test_metadata_preservation_on_clone():
    """DEF-06: Cloning an entry with translated text preserves all auxiliary engine fields."""
    entry = LocalizationEntry.model_validate(
        {
            "Id": 999,
            "Name": "Combat/Dialog_1",
            "Text": "原文字符",
            "Speaker": "ZhaoHuo",
            "Voice": "zh_01.wav",
            "Context": "BattleStart",
            "CustomTag": 42,
        }
    )

    cloned = entry.clone_with_translation("Văn bản dịch")
    dumped = cloned.model_dump()

    assert dumped["Name"] == "Combat/Dialog_1"
    assert dumped["Text"] == "Văn bản dịch"
    assert dumped["Id"] == 999
    assert dumped["Speaker"] == "ZhaoHuo"
    assert dumped["Voice"] == "zh_01.wav"
    assert dumped["Context"] == "BattleStart"
    assert dumped["CustomTag"] == 42


def test_output_dict_preserves_schema_a_structure(sample_schema_a_dict):
    """Output dict for Schema A produces identical wrapping in entries.Array."""
    loc_file = LocalizationFile.model_validate(sample_schema_a_dict)
    entries = loc_file.get_entries()
    translated = [e.clone_with_translation(f"Translated: {e.Text}") for e in entries]

    output_dict = loc_file.to_output_dict(translated)
    assert "entries" in output_dict
    assert "Array" in output_dict["entries"]
    assert len(output_dict["entries"]["Array"]) == 2
    assert output_dict["entries"]["Array"][0]["Speaker"] == "HuynhNhi"
    assert output_dict["entries"]["Array"][0]["Voice"] == "voice_101.wav"


def test_output_dict_preserves_schema_b_structure(sample_schema_b_dict):
    """Output dict for Schema B produces identical flat entries list."""
    loc_file = LocalizationFile.model_validate(sample_schema_b_dict)
    entries = loc_file.get_entries()
    translated = [e.clone_with_translation(f"Translated: {e.Text}") for e in entries]

    output_dict = loc_file.to_output_dict(translated)
    assert isinstance(output_dict["entries"], list)
    assert output_dict["entries"][0]["Context"] == "CombatSkill"


def test_entry_key_value_alias_polymorphism():
    """LocalizationEntry supports both 'key'/'value' and 'Name'/'Text' keys."""
    entry_kv = LocalizationEntry.model_validate({"key": "MyKey", "value": "MyValue"})
    assert entry_kv.Name == "MyKey"
    assert entry_kv.Text == "MyValue"

    entry_nt = LocalizationEntry.model_validate({"Name": "MyKey2", "Text": "MyValue2"})
    assert entry_nt.Name == "MyKey2"
    assert entry_nt.Text == "MyValue2"


def test_settings_soft_validation_max_retries():
    """Verify Settings model exposes soft_validation_max_retries with default 2."""
    default_settings = Settings()
    assert default_settings.soft_validation_max_retries == 2

    custom_settings = Settings(soft_validation_max_retries=5)
    assert custom_settings.soft_validation_max_retries == 5

