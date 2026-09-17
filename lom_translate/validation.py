"""Dual-tier validator engine for injected characters, rich text markup, and game tokens."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# =====================================================================
# Regular Expression Definitions
# =====================================================================

# Unified non-overlapping token pattern (prioritized alternation)
TOKEN_PATTERN = re.compile(
    r"(?P<bracketed_param>\[\{[^{}\]]+\}\]|\[\d+\])"
    r"|(?P<injected_break>\[\|+\])"
    r"|(?P<interpolation>\{[^{}\]]+\})"
    r"|(?P<rich_text></?[a-zA-Z0-9_]+(?:\s*=[^>]+)?>)"
)

# Dedicated rich-text tag scanner
RICH_TEXT_SCANNER = re.compile(r"<\s*(/)?\s*([a-zA-Z0-9_]+)(?:\s*=\s*([^>]+))?\s*>")

# Full CJK Unicode blocks (Unified Ideographs, Extension A, Compatibility)
CJK_EXTENDED_PATTERN = re.compile(
    r"[\u4e00-\u9fff"  # CJK Unified Ideographs (Common & Essential, 20,992 chars)
    r"\u3400-\u4dbf"  # CJK Unified Ideographs Extension A (Rare / Classical, 6,592 chars)
    r"\uf900-\ufaff]"  # CJK Compatibility Ideographs (512 chars)
)

# Legacy aliases for backward compatibility
TOKEN_INTERPOLATION = re.compile(r"\{[^}]*\}")
TOKEN_INJECTED_BREAKS = re.compile(r"\[\|+\]")
TOKEN_BRACKETED_PARAMS = re.compile(r"\[\{*\d+\}*\]")
RICH_TEXT_TAGS = re.compile(r"</?[a-zA-Z0-9_]+(?:=[^>]+)?>")
CJK_CHAR_PATTERN = CJK_EXTENDED_PATTERN

# Auto-healing patterns (LLM whitespace insertion artifacts)
HEAL_INJECTED_DOUBLE = re.compile(r"\[\s*\|\s*\|\s*\]")
HEAL_INJECTED_SINGLE = re.compile(r"\[\s*\|\s*\]")
HEAL_BRACKETED_SPACES = re.compile(r"\[\s*\{\s*([^{}\]]+?)\s*\}\s*\]")
HEAL_BRACKETED_DIGITS = re.compile(r"\[\s*(\d+)\s*\]")
HEAL_FORMATTED_SPACES = re.compile(r"\{\s*([a-zA-Z0-9_]+)\s*:\s*([a-zA-Z0-9_]+)\s*\}")
HEAL_BRACKET_SPACES = re.compile(r"\{\s*([a-zA-Z0-9_]+)\s*\}")
HEAL_TAG_CLOSING = re.compile(r"<\s*/\s*([a-zA-Z0-9_]+)\s*>")
HEAL_TAG_SPACES = HEAL_TAG_CLOSING  # Backward-compatible alias
HEAL_TAG_OPENING_ATTR = re.compile(r"<\s*([a-zA-Z0-9_]+)\s*=\s*([^>]+?)\s*>")
HEAL_TAG_OPENING_SIMPLE = re.compile(r"<\s*([a-zA-Z0-9_]+)\s*>")

# Rejected empty / placeholder outputs
REJECTED_PLACEHOLDERS = frozenset({
    "null",
    "none",
    "nil",
    "undefined",
    "(null)",
    "[empty]",
    "todo",
    "(trống)",
    "n/a",
})

# Void / self-closing rich text tags in Unity TextMeshPro
VOID_RICH_TEXT_TAGS = frozenset({"sprite", "quad"})


# =====================================================================
# Data Models
# =====================================================================

class ValidationSeverity(str, Enum):
    """Validation severity classification."""

    HARD = "hard"
    SOFT = "soft"


@dataclass
class ValidationIssue:
    """Individual issue detected during validation."""

    severity: ValidationSeverity
    category: str
    message: str
    diagnostic: str = ""
    details: list[str] = field(default_factory=list)


@dataclass
class ValidationContext:
    """Evaluation context passed to all validator instances."""

    original_text: str
    raw_translation: str
    healed_text: str
    glossary_matches: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Outcome of dual-tier validation on candidate translation."""

    healed_text: str
    is_hard_valid: bool = True
    is_soft_valid: bool = True
    is_clean: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    missing_tokens: list[str] = field(default_factory=list)
    extra_tokens: list[str] = field(default_factory=list)
    corrupted_tags: list[str] = field(default_factory=list)
    untranslated_cjk: list[str] = field(default_factory=list)
    missing_glossary: list[str] = field(default_factory=list)
    has_untranslated_cjk: bool = False
    warning_messages: list[str] = field(default_factory=list)

    @property
    def diagnostic_feedback(self) -> str:
        """Formatted diagnostic feedback for re-prompting LLM in Vietnamese."""
        if not self.issues:
            return ""
        lines = ["[LƯU Ý LỖI BẢN DỊCH TRƯỚC VÀ YÊU CẦU SỬA ĐỔI]:"]
        for issue in self.issues:
            if issue.diagnostic:
                lines.append(f"- {issue.diagnostic}")
            else:
                lines.append(f"- {issue.message}")
        lines.append(
            "Vui lòng dịch lại câu thoại trên và khắc phục triệt để các lỗi này. "
            "Chỉ trả về bản dịch hoàn chỉnh, không thêm lời giải thích ngoài lề."
        )
        return "\n".join(lines)


# =====================================================================
# Stage 1: Auto-Healing
# =====================================================================

def auto_heal_tokens(text: str) -> str:
    """Stage 1: Normalize common spacing flaws introduced by LLMs without reprompting."""
    if not text:
        return text

    # 1. Injected linebreaks [||] and [|]
    text = HEAL_INJECTED_DOUBLE.sub("[||]", text)
    text = HEAL_INJECTED_SINGLE.sub("[|]", text)

    # 2. Bracketed parameters [ { 0 } ] -> [{0}], [ 0 ] -> [0]
    text = HEAL_BRACKETED_SPACES.sub(r"[{\1}]", text)
    text = HEAL_BRACKETED_DIGITS.sub(r"[\1]", text)

    # 3. Formatted interpolation { 0 : N0 } -> {0:N0}
    text = HEAL_FORMATTED_SPACES.sub(r"{\1:\2}", text)

    # 4. Simple interpolation { title } -> {title}
    text = HEAL_BRACKET_SPACES.sub(r"{\1}", text)

    # 5. Rich-text tags: closing </ color > -> </color>
    text = HEAL_TAG_CLOSING.sub(r"</\1>", text)

    # 6. Rich-text tags: opening with attributes < color = #FF0000 > -> <color=#FF0000>
    text = HEAL_TAG_OPENING_ATTR.sub(r"<\1=\2>", text)

    # 7. Rich-text tags: opening simple < b > -> <b>
    text = HEAL_TAG_OPENING_SIMPLE.sub(r"<\1>", text)

    return text


def extract_all_tokens(text: str) -> list[str]:
    """Extract all tokens preserving non-overlapping priority order."""
    if not text:
        return []
    return [match.group(0) for match in TOKEN_PATTERN.finditer(text)]


# =====================================================================
# Validator Base Classes
# =====================================================================

class BaseValidator(ABC):
    """Abstract base class for all validators."""

    @property
    @abstractmethod
    def severity(self) -> ValidationSeverity:
        """Validator severity tier (HARD or SOFT)."""
        ...

    @property
    @abstractmethod
    def category(self) -> str:
        """Category identifier."""
        ...

    @abstractmethod
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Validate candidate translation against context."""
        ...


# =====================================================================
# Stage 2: Hard Validators
# =====================================================================

class OutputExistenceValidator(BaseValidator):
    """Hard validator rejecting empty, whitespace-only, or placeholder outputs."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.HARD

    @property
    def category(self) -> str:
        return "output_existence"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        raw = context.raw_translation
        healed = context.healed_text

        if raw is None or not healed or not healed.strip():
            return [
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message="Bản dịch trống hoặc chỉ chứa khoảng trắng.",
                    diagnostic=(
                        "❌ [LỖI NỘI DUNG TRỐNG]: Bản dịch không được để trống hoặc trả về giá trị null. "
                        "Vui lòng cung cấp bản dịch Tiếng Việt đầy đủ cho câu thoại."
                    ),
                    details=["empty_or_whitespace"],
                )
            ]

        stripped_lower = healed.strip().lower()
        if stripped_lower in REJECTED_PLACEHOLDERS:
            return [
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message=f"Bản dịch trả về placeholder không hợp lệ: '{healed.strip()}'.",
                    diagnostic=(
                        f"❌ [LỖI GIÁ TRỊ TẠM THỜI]: Bản dịch không được là '{healed.strip()}'. "
                        "Vui lòng dịch trọn vẹn câu thoại sang Tiếng Việt."
                    ),
                    details=[healed.strip()],
                )
            ]

        return []


class TokenIntegrityValidator(BaseValidator):
    """Hard validator checking preservation of engine interpolation and linebreaks."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.HARD

    @property
    def category(self) -> str:
        return "token_integrity"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        orig_tokens = extract_all_tokens(context.original_text)
        trans_tokens = extract_all_tokens(context.healed_text)

        orig_counts: dict[str, int] = {}
        for t in orig_tokens:
            orig_counts[t] = orig_counts.get(t, 0) + 1

        trans_counts: dict[str, int] = {}
        for t in trans_tokens:
            trans_counts[t] = trans_counts.get(t, 0) + 1

        missing: list[str] = []
        for token, count in orig_counts.items():
            if trans_counts.get(token, 0) < count:
                diff = count - trans_counts.get(token, 0)
                missing.extend([token] * diff)

        issues: list[ValidationIssue] = []
        if missing:
            unique_missing = sorted(set(missing))
            issues.append(
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message=f"Missing required tokens: {unique_missing}",
                    diagnostic=(
                        f"❌ [LỖI KÝ HIỆU HỆ THỐNG]: Bản dịch bị thiếu các ký hiệu kỹ thuật bắt buộc: {unique_missing}. "
                        "Bạn BẮT BUỘC phải giữ nguyên chính xác 100% các ký hiệu này, không được dịch nghĩa và không được xóa bỏ."
                    ),
                    details=missing,
                )
            )

        return issues


class RichTextTagIntegrityValidator(BaseValidator):
    """Hard validator enforcing stack-based tag balancing and attribute preservation."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.HARD

    @property
    def category(self) -> str:
        return "rich_text_tag_integrity"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        corrupted: list[str] = []
        healed = context.healed_text
        orig = context.original_text

        # 1. Stack-based tag balancing
        stack: list[tuple[str, str]] = []  # (tag_name_lower, raw_tag_string)
        for match in RICH_TEXT_SCANNER.finditer(healed):
            is_closing = bool(match.group(1))
            tag_name = match.group(2).lower()
            raw_tag = match.group(0)

            if tag_name in VOID_RICH_TEXT_TAGS:
                continue

            if not is_closing:
                stack.append((tag_name, raw_tag))
            else:
                if not stack:
                    corrupted.append(f"Thẻ đóng '{raw_tag}' không có thẻ mở tương ứng")
                else:
                    last_open_name, _ = stack.pop()
                    if last_open_name != tag_name:
                        corrupted.append(
                            f"Thẻ đóng '{raw_tag}' không khớp thứ tự lồng với thẻ mở '<{last_open_name}>'"
                        )

        while stack:
            _, unclosed_tag = stack.pop()
            corrupted.append(f"Thẻ mở '{unclosed_tag}' chưa được đóng")

        # 2. Attribute preservation check
        orig_attr_tags: dict[str, int] = {}
        for match in RICH_TEXT_SCANNER.finditer(orig):
            if not match.group(1) and match.group(3) is not None:
                tag_str = match.group(0)
                orig_attr_tags[tag_str] = orig_attr_tags.get(tag_str, 0) + 1

        trans_attr_tags: dict[str, int] = {}
        for match in RICH_TEXT_SCANNER.finditer(healed):
            if not match.group(1) and match.group(3) is not None:
                tag_str = match.group(0)
                trans_attr_tags[tag_str] = trans_attr_tags.get(tag_str, 0) + 1

        for tag_str, count in orig_attr_tags.items():
            if trans_attr_tags.get(tag_str, 0) < count:
                corrupted.append(f"Thiếu hoặc sai thuộc tính của thẻ định dạng: '{tag_str}'")

        if corrupted:
            return [
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message=f"Corrupted or unbalanced rich-text tags: {corrupted}",
                    diagnostic=(
                        f"❌ [LỖI THẺ ĐỊNH DẠNG]: Thẻ định dạng Unity Rich Text không hợp lệ: {'; '.join(corrupted)}. "
                        "Vui lòng đảm bảo các thẻ mở (<color=...>, <b>) phải có thẻ đóng (</color>, </b>) tương ứng và giữ nguyên mã màu."
                    ),
                    details=corrupted,
                )
            ]

        return []


# =====================================================================
# Stage 3: Soft Validators
# =====================================================================

class LingeringCJKValidator(BaseValidator):
    """Soft validator detecting untranslated Chinese characters."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.SOFT

    @property
    def category(self) -> str:
        return "lingering_cjk"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        matches = CJK_EXTENDED_PATTERN.findall(context.healed_text)
        if not matches:
            return []

        unique_cjk = sorted(set(matches))
        return [
            ValidationIssue(
                severity=self.severity,
                category=self.category,
                message=f"Contains {len(matches)} untranslated Chinese characters",
                diagnostic=(
                    f"⚠️ [CẢNH BÁO SÓT CHỮ HÁN]: Bản dịch vẫn còn chứa {len(matches)} ký tự tiếng Trung chưa được dịch: {unique_cjk[:10]}. "
                    "Vui lòng dịch toàn bộ các chữ Hán này sang Tiếng Việt (hoặc âm Hán Việt phù hợp), tuyệt đối không để sót chữ Trung Quốc."
                ),
                details=matches,
            )
        ]


class VerbatimIdentityValidator(BaseValidator):
    """Soft validator detecting verbatim echoes of source Chinese text."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.SOFT

    @property
    def category(self) -> str:
        return "verbatim_identity"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        orig_clean = context.original_text.strip()
        trans_clean = context.healed_text.strip()

        # Only trigger if the source text contains CJK characters
        if not CJK_EXTENDED_PATTERN.search(orig_clean):
            return []

        if orig_clean == trans_clean:
            return [
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message="Translation is identical to source text without translation.",
                    diagnostic=(
                        "⚠️ [CẢNH BÁO NGUYÊN VĂN]: Bản dịch bị trùng khớp hoàn toàn với văn bản gốc tiếng Trung. "
                        "Vui lòng dịch nội dung sang Tiếng Việt thay vì sao chép lại nguyên văn."
                    ),
                    details=[orig_clean],
                )
            ]

        return []


class GlossaryComplianceValidator(BaseValidator):
    """Soft validator verifying that injected glossary terms appear in translation."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.SOFT

    @property
    def category(self) -> str:
        return "glossary_compliance"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        if not context.glossary_matches:
            return []

        healed_lower = context.healed_text.lower()
        missing_terms: list[str] = []

        for item in context.glossary_matches:
            orig, trans = self._extract_pair(item)
            if not orig or not trans:
                continue
            if trans.lower() not in healed_lower:
                missing_terms.append(f"{orig}={trans}")

        if missing_terms:
            return [
                ValidationIssue(
                    severity=self.severity,
                    category=self.category,
                    message=f"Missing required glossary terms: {missing_terms}",
                    diagnostic=(
                        f"⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]: Bản dịch chưa tuân thủ thuật ngữ game đã quy định: {missing_terms[:5]}. "
                        "Vui lòng dịch chính xác theo các thuật ngữ này."
                    ),
                    details=missing_terms,
                )
            ]

        return []

    @staticmethod
    def _extract_pair(item: Any) -> tuple[str, str]:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            return str(item[0]).strip(), str(item[1]).strip()
        if isinstance(item, dict):
            orig = item.get("Original") or item.get("orig") or item.get("name") or ""
            trans = item.get("Translated") or item.get("trans") or ""
            return str(orig).strip(), str(trans).strip()
        return "", ""


class LengthRatioValidator(BaseValidator):
    """Soft validator detecting extreme truncation or commentary bloat."""

    @property
    def severity(self) -> ValidationSeverity:
        return ValidationSeverity.SOFT

    @property
    def category(self) -> str:
        return "length_ratio"

    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        # Strip tokens and markup for clean character length comparison
        clean_orig = TOKEN_PATTERN.sub("", context.original_text).strip()
        clean_trans = TOKEN_PATTERN.sub("", context.healed_text).strip()

        len_orig = len(clean_orig)
        len_trans = len(clean_trans)

        if len_orig == 0:
            return []

        # Normal dialogue (>= 6 chars)
        if len_orig >= 6:
            ratio = len_trans / len_orig
            if ratio < 0.3:
                return [
                    ValidationIssue(
                        severity=self.severity,
                        category=self.category,
                        message=f"Translation is unusually short (ratio {ratio:.2f} < 0.3)",
                        diagnostic=(
                            f"⚠️ [CẢNH BÁO ĐỘ DÀI QUÁ NGẮN]: Bản dịch quá ngắn bất thường so với câu gốc "
                            f"(gốc: {len_orig} ký tự, dịch: {len_trans} ký tự). "
                            "Vui lòng đảm bảo dịch trọn vẹn toàn bộ ý và không lược bỏ câu thoại."
                        ),
                        details=[f"len_orig={len_orig}", f"len_trans={len_trans}", f"ratio={ratio:.2f}"],
                    )
                ]
            if ratio > 6.0:
                return [
                    ValidationIssue(
                        severity=self.severity,
                        category=self.category,
                        message=f"Translation is unusually long (ratio {ratio:.2f} > 6.0)",
                        diagnostic=(
                            f"⚠️ [CẢNH BÁO ĐỘ DÀI QUÁ DÀI]: Bản dịch quá dài bất thường so với câu gốc "
                            f"(gốc: {len_orig} ký tự, dịch: {len_trans} ký tự). "
                            "Vui lòng chỉ dịch trực tiếp câu thoại, không thêm lời giải thích hay bình luận ngoài lề."
                        ),
                        details=[f"len_orig={len_orig}", f"len_trans={len_trans}", f"ratio={ratio:.2f}"],
                    )
                ]
        else:
            # Short phrase (< 6 chars) ceiling
            if len_trans > 60:
                return [
                    ValidationIssue(
                        severity=self.severity,
                        category=self.category,
                        message=f"Short phrase translation bloated ({len_trans} chars > 60)",
                        diagnostic=(
                            f"⚠️ [CẢNH BÁO ĐỘ DÀI]: Câu gốc rất ngắn nhưng bản dịch lại quá dài ({len_trans} ký tự). "
                            "Vui lòng dịch súc tích đúng với câu gốc, không thêm giải thích."
                        ),
                        details=[f"len_orig={len_orig}", f"len_trans={len_trans}"],
                    )
                ]

        return []


# =====================================================================
# Validation Orchestration
# =====================================================================

DEFAULT_HARD_VALIDATORS: list[BaseValidator] = [
    OutputExistenceValidator(),
    TokenIntegrityValidator(),
    RichTextTagIntegrityValidator(),
]

DEFAULT_SOFT_VALIDATORS: list[BaseValidator] = [
    LingeringCJKValidator(),
    VerbatimIdentityValidator(),
    GlossaryComplianceValidator(),
    LengthRatioValidator(),
]


def validate_translation(
    original_text: str,
    raw_translation: str,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
) -> ValidationResult:
    """Execute Stage 1 auto-healing and dual-tier (Hard + Soft) validation."""
    # 1. Pre-validation auto-healing
    healed = auto_heal_tokens(raw_translation)

    # Normalize glossary matches to list of tuples
    normalized_glossary: list[tuple[str, str]] = []
    if glossary_matches:
        for item in glossary_matches:
            pair = GlossaryComplianceValidator._extract_pair(item)
            if pair[0] and pair[1]:
                normalized_glossary.append(pair)

    context = ValidationContext(
        original_text=original_text,
        raw_translation=raw_translation,
        healed_text=healed,
        glossary_matches=normalized_glossary,
    )

    all_issues: list[ValidationIssue] = []

    # Run Hard validators
    for validator in DEFAULT_HARD_VALIDATORS:
        all_issues.extend(validator.validate(context))

    # Run Soft validators
    for validator in DEFAULT_SOFT_VALIDATORS:
        all_issues.extend(validator.validate(context))

    # Aggregate issues by category and tier
    missing_tokens: list[str] = []
    extra_tokens: list[str] = []
    corrupted_tags: list[str] = []
    untranslated_cjk: list[str] = []
    missing_glossary: list[str] = []

    # Compute extra tokens for legacy reporting
    orig_tokens = extract_all_tokens(original_text)
    trans_tokens = extract_all_tokens(healed)
    orig_counts: dict[str, int] = {}
    for t in orig_tokens:
        orig_counts[t] = orig_counts.get(t, 0) + 1
    trans_counts: dict[str, int] = {}
    for t in trans_tokens:
        trans_counts[t] = trans_counts.get(t, 0) + 1
    for token, count in trans_counts.items():
        if orig_counts.get(token, 0) < count:
            diff = count - orig_counts.get(token, 0)
            extra_tokens.extend([token] * diff)

    for issue in all_issues:
        if issue.category == "token_integrity":
            missing_tokens.extend(issue.details)
        elif issue.category == "rich_text_tag_integrity":
            corrupted_tags.extend(issue.details)
        elif issue.category == "lingering_cjk":
            untranslated_cjk.extend(issue.details)
        elif issue.category == "glossary_compliance":
            missing_glossary.extend(issue.details)

    is_hard_valid = not any(i.severity == ValidationSeverity.HARD for i in all_issues)
    is_soft_valid = not any(i.severity == ValidationSeverity.SOFT for i in all_issues)

    # Legacy warnings construction
    warning_messages: list[str] = []
    if missing_tokens:
        warning_messages.append(f"Missing required tokens: {sorted(set(missing_tokens))}")
    if extra_tokens:
        warning_messages.append(f"Unexpected extra tokens: {sorted(set(extra_tokens))}")
    if untranslated_cjk:
        warning_messages.append(f"Contains {len(untranslated_cjk)} untranslated Chinese characters")
    if corrupted_tags:
        warning_messages.append(f"Corrupted or unbalanced rich-text tags: {corrupted_tags}")
    if missing_glossary:
        warning_messages.append(f"Missing required glossary terms: {missing_glossary}")
    for issue in all_issues:
        if issue.category in ("output_existence", "verbatim_identity", "length_ratio"):
            warning_messages.append(issue.message)

    # Legacy is_clean definition: both hard and soft valid
    is_clean = is_hard_valid and is_soft_valid

    return ValidationResult(
        healed_text=healed,
        is_hard_valid=is_hard_valid,
        is_soft_valid=is_soft_valid,
        is_clean=is_clean,
        issues=all_issues,
        missing_tokens=missing_tokens,
        extra_tokens=extra_tokens,
        corrupted_tags=corrupted_tags,
        untranslated_cjk=untranslated_cjk,
        missing_glossary=missing_glossary,
        has_untranslated_cjk=len(untranslated_cjk) > 0,
        warning_messages=warning_messages,
    )


def soft_validate_translation(
    original_text: str,
    raw_translation: str,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
) -> ValidationResult:
    """Backward-compatible alias for validate_translation."""
    return validate_translation(
        original_text=original_text,
        raw_translation=raw_translation,
        glossary_matches=glossary_matches,
    )
