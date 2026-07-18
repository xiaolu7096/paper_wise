import re
import unicodedata

HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)


def is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in HAN_RANGES)


def search_terms(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    current: list[str] = []
    current_kind: str | None = None

    def flush() -> None:
        nonlocal current, current_kind
        if not current:
            return
        value = "".join(current)
        if current_kind == "han" and len(value) > 1:
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        else:
            tokens.append(value)
        current = []
        current_kind = None

    for character in normalized:
        if is_han(character):
            kind = "han"
        elif character.isalpha() or character.isdigit():
            kind = "word"
        else:
            flush()
            continue
        if current_kind != kind:
            flush()
            current_kind = kind
        current.append(character)
    flush()
    return " ".join(tokens)


def clean_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)
