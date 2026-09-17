"""Contextual prompt generation, system persona, and corrective diagnostic feedback.

Supports standard translation prompting, improvement mode, and Anchor-and-Patch
corrective re-prompting with structured Vietnamese diagnostic feedback.
"""

from __future__ import annotations

import re
from typing import Any

from lom_translate.glossary import Glossary
from lom_translate.models import LocalizationEntry
from lom_translate.text import RULES_PROMPT, START_PROMPT, STORY_CONTEXT_PROMPT, preprocess_text
from lom_translate.validation import ValidationResult

# Canonical System Prompt (combines persona, game lore context, and translation rules)
CANONICAL_SYSTEM_PROMPT = f"{START_PROMPT}\n{STORY_CONTEXT_PROMPT}\n{RULES_PROMPT}".strip()

# Regex for detecting CJK characters in text during diagnostic checks
_CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def build_system_prompt() -> str:
    """Return canonical system prompt for game translation."""
    return CANONICAL_SYSTEM_PROMPT


def _normalize_glossary_matches(
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None,
) -> list[tuple[str, str]]:
    """Normalize glossary matches into a list of (source, target) tuples."""
    if not glossary_matches:
        return []
    normalized: list[tuple[str, str]] = []
    for item in glossary_matches:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((str(item[0]), str(item[1])))
        elif isinstance(item, dict):
            orig = item.get("orig") or item.get("source") or item.get("original") or item.get("Original") or ""
            trans = (
                item.get("trans")
                or item.get("target")
                or item.get("translation")
                or item.get("Translated")
                or ""
            )
            if orig and trans:
                normalized.append((str(orig), str(trans)))
    return normalized


def build_entry_prompt(
    original_text: str,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    raw_translation: str | None = None,
    include_system_prompt: bool = False,
) -> str:
    """Build the translation prompt for a single game entry."""
    parts: list[str] = []
    if include_system_prompt:
        parts.append(CANONICAL_SYSTEM_PROMPT)

    if raw_translation:
        parts.append("Hướng dẫn: Sử dụng bản dịch thô sau đây để THAM KHẢO về xưng hô và ngữ cảnh nhân vật.")

    norm_matches = _normalize_glossary_matches(glossary_matches)
    if norm_matches:
        parts.append("Bảng thuật ngữ bắt buộc (nguyên bản tiếng Trung => dịch sang Tiếng Việt):")
        for orig, trans in norm_matches:
            parts.append(f"- {orig} => {trans}")

    parts.append(f"Văn bản cần dịch: {original_text}")
    if raw_translation:
        parts.append(f"Bản dịch thô để tham khảo: {raw_translation}")

    return "\n\n".join(parts)


def build_translate_prompt(
    text: str,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    include_system_prompt: bool = True,
) -> str:
    """Build translation prompt for a single entry in translate mode."""
    return build_entry_prompt(
        original_text=text,
        glossary_matches=glossary_matches,
        raw_translation=None,
        include_system_prompt=include_system_prompt,
    )


def build_improve_prompt(
    text: str,
    raw_translation: str,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    include_system_prompt: bool = True,
) -> str:
    """Build improvement prompt for a single entry referencing a raw translation."""
    return build_entry_prompt(
        original_text=text,
        glossary_matches=glossary_matches,
        raw_translation=raw_translation,
        include_system_prompt=include_system_prompt,
    )


def format_diagnostic_feedback(
    val_result: ValidationResult | None,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    original_text: str = "",
) -> str:
    """Format structured validation errors into actionable Vietnamese diagnostic bullets.

    Categories:
    - ❌ [LỖI KÝ HIỆU HỆ THỐNG]: Missing engine tokens
    - ❌ [LỖI THẺ ĐỊNH DẠNG]: Corrupted / unclosed Rich Text tags
    - ❌ [LỖI NỘI DUNG RỖNG]: Empty or whitespace-only response
    - ⚠️ [CẢNH BÁO SÓT CHỮ HÁN]: Untranslated Chinese characters
    - ⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]: Missed mandatory glossary mappings
    - ⚠️ [CẢNH BÁO ĐỘ DÀI]: Extreme expansion or truncation ratio
    - ⚠️ [CẢNH BÁO TRÙNG LẶP NGUYÊN BẢN]: Verbatim source copy
    """
    if val_result is None:
        return ""

    diagnostics: list[str] = []
    healed = getattr(val_result, "healed_text", "") or ""
    issues = getattr(val_result, "issues", [])
    warnings = getattr(val_result, "warning_messages", [])

    # 1. Hard: Missing / Corrupted Engine Tokens
    missing_tokens = list(getattr(val_result, "missing_tokens", []))
    for issue in issues:
        cat = getattr(issue, "category", "").lower()
        if cat in {"token", "token_integrity", "missing_tokens"}:
            det = getattr(issue, "details", [])
            if isinstance(det, (list, tuple)):
                missing_tokens.extend([str(d) for d in det])

    if missing_tokens:
        unique_missing = sorted(set(missing_tokens))
        token_lines = [
            "❌ [LỖI KÝ HIỆU HỆ THỐNG]:",
            f"- Thiếu các ký hiệu điều khiển game engine bắt buộc: {unique_missing}",
        ]
        extra_tokens = list(getattr(val_result, "extra_tokens", []))
        if extra_tokens:
            token_lines.append(f"- Ký hiệu xuất hiện thừa không có trong bản gốc: {sorted(set(extra_tokens))}")
        token_lines.append(
            "- Quy tắc: Các ký hiệu [|], [||], {0}, {title}, {0:N0}, [{0}] là mã điều khiển của game engine. "
            "BẮT BUỘC giữ nguyên 100%, đúng vị trí logic, không được xóa, không dịch nghĩa, không thêm khoảng trắng bên trong."
        )
        diagnostics.append("\n".join(token_lines))

    # 2. Hard: Rich-Text Tag Integrity
    corrupted_tags = list(getattr(val_result, "corrupted_tags", []))
    tag_issues: list[str] = []
    for issue in issues:
        cat = getattr(issue, "category", "").lower()
        if cat in {"tag", "rich_text", "rich_text_tag", "tag_integrity", "rich_text_tag_integrity"}:
            tag_issues.append(getattr(issue, "message", str(issue)))

    tag_warnings = [
        w for w in warnings if any(k in w.lower() for k in ["tag", "rich_text", "<color", "</color", "thẻ"])
    ]
    all_tag_details = sorted(set(corrupted_tags + tag_issues + tag_warnings))

    if all_tag_details:
        diagnostics.append(
            "❌ [LỖI THẺ ĐỊNH DẠNG]:\n"
            "- Thẻ định dạng Unity Rich Text không hợp lệ hoặc chưa đóng kín.\n"
            f"- Chi tiết: {'; '.join(all_tag_details)}\n"
            "- Quy tắc: Mọi thẻ mở (<color=#...>, <b>, <i>, <size=...>) BẮT BUỘC phải có thẻ đóng tương ứng "
            "(</color>, </b>, </i>, </size>). Giữ nguyên chính xác mã màu và cấu trúc thẻ của Unity."
        )

    # 3. Hard: Empty / Null Response
    is_empty = not healed.strip() or any(
        getattr(i, "category", "").lower() in {"output_existence", "empty"} for i in issues
    )
    if is_empty:
        diagnostics.append(
            "❌ [LỖI NỘI DUNG RỖNG]:\n"
            "- Bản dịch trả về bị rỗng hoặc chỉ chứa khoảng trắng.\n"
            "- Quy tắc: Hãy dịch toàn bộ câu văn gốc sang Tiếng Việt."
        )

    # 4. Soft: Lingering CJK Characters
    has_cjk = getattr(val_result, "has_untranslated_cjk", False)
    untranslated_cjk = list(getattr(val_result, "untranslated_cjk", []))
    for issue in issues:
        if getattr(issue, "category", "").lower() in {"cjk", "lingering_cjk"}:
            has_cjk = True
            det = getattr(issue, "details", [])
            if isinstance(det, (list, tuple)):
                untranslated_cjk.extend([str(d) for d in det])

    if not untranslated_cjk and healed:
        untranslated_cjk = _CJK_CHAR_PATTERN.findall(healed)
    if untranslated_cjk:
        has_cjk = True

    if has_cjk:
        unique_chars = sorted(set(untranslated_cjk))
        sample_str = ", ".join(repr(c) for c in unique_chars[:10])
        diagnostics.append(
            "⚠️ [CẢNH BÁO SÓT CHỮ HÁN]:\n"
            f"- Bản dịch vẫn còn chứa ký tự chữ Hán chưa được dịch: {sample_str}\n"
            "- Quy tắc: Toàn bộ câu thoại phải được chuyển ngữ hoàn toàn sang Tiếng Việt "
            "(hoặc âm Hán Việt phù hợp bối cảnh kiếm hiệp), tuyệt đối không để sót chữ Hán trong bản dịch."
        )

    # 5. Soft: Mandatory Glossary Compliance
    missing_glossary: list[str] = list(getattr(val_result, "missing_glossary", []))
    norm_matches = _normalize_glossary_matches(glossary_matches)
    if norm_matches and healed:
        healed_lower = healed.lower()
        for orig, expected_trans in norm_matches:
            if expected_trans.lower() not in healed_lower:
                missing_glossary.append(f"'{orig}' bắt buộc dịch là '{expected_trans}'")

    for issue in issues:
        if getattr(issue, "category", "").lower() in {"glossary", "glossary_compliance"}:
            msg = getattr(issue, "message", "")
            if msg and msg not in missing_glossary:
                missing_glossary.append(msg)

    if missing_glossary:
        unique_gloss = sorted(set(missing_glossary))
        bullets = "\n".join(f"  * {item}" for item in unique_gloss)
        diagnostics.append(
            "⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]:\n"
            f"- Thuật ngữ chưa tuân thủ đúng bảng từ điển bắt buộc:\n{bullets}\n"
            "- Quy tắc: BẮT BUỘC sử dụng chính xác từ dịch quy định cho các danh xưng, môn phái, địa danh và thuật ngữ game."
        )

    # 6. Soft: Verbatim Identity
    is_verbatim = False
    for issue in issues:
        if getattr(issue, "category", "").lower() in {"verbatim", "verbatim_identity"}:
            is_verbatim = True

    if original_text and healed and original_text.strip() == healed.strip():
        if _CJK_CHAR_PATTERN.search(original_text):
            is_verbatim = True

    if is_verbatim:
        diagnostics.append(
            "⚠️ [CẢNH BÁO TRÙNG LẶP NGUYÊN BẢN]:\n"
            "- Bản dịch trùng khớp 100% với văn bản gốc tiếng Trung mà chưa được dịch sang Tiếng Việt.\n"
            "- Quy tắc: Hãy dịch toàn bộ câu văn sang Tiếng Việt."
        )

    # 7. Soft: Extreme Length Ratio Anomaly
    has_length_issue = False
    length_msg = ""
    for issue in issues:
        if getattr(issue, "category", "").lower() in {"length", "length_ratio"}:
            has_length_issue = True
            length_msg = getattr(issue, "message", "")

    if not has_length_issue and original_text and healed:
        clean_orig = original_text.strip()
        clean_trans = healed.strip()
        orig_len = len(clean_orig)
        trans_len = len(clean_trans)
        if orig_len >= 6:
            ratio = trans_len / orig_len
            if ratio < 0.3:
                has_length_issue = True
                length_msg = f"Bản dịch quá ngắn ({trans_len} ký tự so với {orig_len} ký tự gốc, tỷ lệ: {ratio:.2f})"
            elif ratio > 6.0:
                has_length_issue = True
                length_msg = f"Bản dịch quá dài ({trans_len} ký tự so với {orig_len} ký tự gốc, tỷ lệ: {ratio:.2f})"
        elif orig_len < 6 and trans_len > 60:
            has_length_issue = True
            length_msg = f"Bản dịch quá dài cho câu ngắn ({trans_len} ký tự so với {orig_len} ký tự gốc)"

    if has_length_issue:
        diagnostics.append(
            "⚠️ [CẢNH BÁO ĐỘ DÀI]:\n"
            f"- Độ dài bản dịch bất thường: {length_msg}\n"
            "- Quy tắc: Kiểm tra xem bản dịch có bị dịch thiếu câu hoặc thêm thấu các lời giải thích thừa ngoài lề không."
        )

    # 8. Unclassified Warnings Fallback
    handled_tokens = ["missing required tokens", "untranslated chinese", "cjk", "tag", "color", "rỗng", "empty"]
    other_warnings = [
        w for w in warnings if not any(ht in w.lower() for ht in handled_tokens)
    ]
    if other_warnings and not diagnostics:
        for w in other_warnings:
            diagnostics.append(f"⚠️ [CẢNH BÁO]:\n- {w}")

    return "\n\n".join(diagnostics)


def build_corrective_prompt(
    original_text: str,
    failed_translation: str,
    val_result: ValidationResult | None = None,
    diagnostic_messages: list[str] | None = None,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    raw_translation: str | None = None,
    base_prompt: str | None = None,
) -> str:
    """Build an Anchor-and-Patch corrective re-prompt guiding the model to fix validation errors.

    The prompt presents:
    1. Context: Source text, optional raw translation, and mandatory glossary table.
    2. Anchor: The previous candidate translation to preserve valid parts.
    3. Target: Structured Vietnamese diagnostic directives.
    4. Patch Directives: Strict rules to patch only errors with zero filler or apologies.
    """
    if val_result is not None:
        diag_feedback = format_diagnostic_feedback(
            val_result=val_result,
            glossary_matches=glossary_matches,
            original_text=original_text,
        )
        if not diag_feedback and diagnostic_messages:
            diag_feedback = "\n".join(f"- {msg}" for msg in diagnostic_messages)
        elif not diag_feedback:
            diag_feedback = "- Bản dịch trước đó chưa đạt yêu cầu kỹ thuật. Vui lòng kiểm tra và sửa lại theo đúng quy tắc dịch."
    elif diagnostic_messages:
        diag_feedback = "\n".join(f"- {msg}" for msg in diagnostic_messages)
    else:
        diag_feedback = "- Bản dịch trước đó chưa đạt yêu cầu kỹ thuật. Vui lòng kiểm tra và sửa lại theo đúng quy tắc dịch."

    candidate_display = (
        failed_translation.strip()
        if failed_translation and failed_translation.strip()
        else "(Không có phản hồi / nội dung rỗng)"
    )

    prompt_parts = [
        "Bạn đã dịch câu văn sau nhưng kết quả chưa đạt yêu cầu kỹ thuật. Hãy điều chỉnh theo hướng dẫn bên dưới.",
        f"--- VĂN BẢN GỐC (TIẾNG TRUNG) ---\n{original_text}",
    ]

    if raw_translation:
        prompt_parts.append(f"--- BẢN DỊCH THÔ THAM KHẢO ---\n{raw_translation}")

    norm_matches = _normalize_glossary_matches(glossary_matches)
    if norm_matches:
        gloss_lines = ["--- BẢNG THUẬT NGỮ BẮT BUỘC ---"]
        for orig, trans in norm_matches:
            gloss_lines.append(f"- {orig} => {trans}")
        prompt_parts.append("\n".join(gloss_lines))

    prompt_parts.extend([
        f"--- BẢN DỊCH HIỆN TẠI CỦA BẠN (CẦN SỬA) ---\n{candidate_display}",
        f"--- DANH SÁCH LỖI CẦN SỬA ---\n{diag_feedback}",
        (
            "--- HƯỚNG DẪN ĐIỀU CHỈNH (ANCHOR-AND-PATCH) ---\n"
            "1. Giữ nguyên văn phong, cấu trúc câu và các phần đã dịch tốt của bản dịch hiện tại.\n"
            "2. CHỈ điều chỉnh chính xác các vị trí bị báo lỗi ở trên:\n"
            "   - Khôi phục đúng 100% các ký hiệu hệ thống [|], [||], {0}, {title}, {0:N0}, [{0}].\n"
            "   - Đảm bảo thẻ định dạng Unity Rich Text (<color>...</color>, <b>...</b>, v.v.) được mở và đóng chính xác.\n"
            "   - Sửa đúng thuật ngữ quy định theo bảng đối chiếu.\n"
            "   - Dịch nốt các ký tự chữ Hán còn sót sang Tiếng Việt.\n"
            "3. Tuyệt đối KHÔNG thêm lời giải thích, xin lỗi, ghi chú ngoài lề hay định dạng markdown (như ``` hoặc **).\n"
            "4. Chỉ trả về DUY NHẤT câu dịch Tiếng Việt hoàn chỉnh sau khi đã sửa."
        ),
    ])

    return "\n\n".join(prompt_parts)


def build_prompts(
    entries: list[LocalizationEntry],
    glossary: Glossary,
    raw_entries: list[LocalizationEntry] | None = None,
    separate_system_prompt: bool = False,
) -> list[dict[str, Any]]:
    """Build prompts for all entries in a file.

    Maintains 100% backward compatibility with existing callers.
    DEF-15 FIX: raw translations pre-indexed into a dict for O(1) matching instead of O(N*M).
    """
    raw_map: dict[str, str] = {e.Name: e.Text for e in raw_entries} if raw_entries else {}
    system_prompt = build_system_prompt()

    prompts: list[dict[str, Any]] = []
    for entry in entries:
        text = preprocess_text(entry.Text.strip())
        matches = glossary.find_matches(text)
        raw = raw_map.get(entry.Name)

        if separate_system_prompt:
            user_prompt = build_entry_prompt(
                original_text=text,
                glossary_matches=matches,
                raw_translation=raw,
                include_system_prompt=False,
            )
        else:
            # Preserves exact existing format when separate_system_prompt is False
            parts = [f"{START_PROMPT}\n{STORY_CONTEXT_PROMPT}\n{RULES_PROMPT}\n"]
            if raw:
                parts.append("8. Sử dụng bản dịch thô để THAM KHẢO về xưng hô và quan hệ nhân vật.\n")
            if matches:
                parts.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
                for orig, trans in matches:
                    parts.append(f"\n- {orig}={trans}")
            parts.append(f"\nVăn bản cần dịch: {text}")
            if raw:
                parts.append(f"\nBản dịch thô để tham khảo: {raw}")
            user_prompt = "\n".join(parts)

        prompt_dict: dict[str, Any] = {
            "name": entry.Name,
            "original_text": text,
            "glossary_matches": matches,
            "raw_translation": raw,
            "prompt": user_prompt,
        }
        if separate_system_prompt:
            prompt_dict["system_prompt"] = system_prompt

        prompts.append(prompt_dict)

    return prompts
