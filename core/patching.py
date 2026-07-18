"""Pure JavaScript patch application shared by mitm runtime and validators."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from sites._base import JsPatch


@dataclass(frozen=True)
class PatchResult:
    text: str
    counts: dict[str, int]
    messages: list[str]


def find_balanced_end(source: str, body_start: int) -> int:
    """Return the offset just after the closing brace for a function body."""
    depth = 1
    i = body_start
    n = len(source)
    while i < n and depth > 0:
        char = source[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char in "\"'":
            quote = char
            i += 1
            while i < n and source[i] != quote:
                i += 2 if source[i] == "\\" else 1
        elif char == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            i = end + 2 if end >= 0 else n
            continue
        i += 1
    if depth != 0:
        raise ValueError(f"unbalanced function body at offset {body_start}")
    return i


def apply_js_patches(source: str, patches: Iterable[JsPatch]) -> PatchResult:
    """Apply expression substitutions first, then balanced function-body patches."""
    patch_list = list(patches)
    text = source
    counts: Counter[str] = Counter()
    messages: list[str] = []

    for patch in patch_list:
        if patch.mode != "sub":
            continue
        text, count = patch.pattern.subn(patch.replacement, text)
        if count:
            counts[patch.name] += count
            messages.append(f"{patch.name}x{count}")

    body_hits: list[tuple[int, JsPatch]] = []
    for patch in patch_list:
        if patch.mode == "body":
            body_hits.extend((match.start(), patch) for match in patch.pattern.finditer(text))

    for start, patch in sorted(body_hits, key=lambda item: item[0], reverse=True):
        body_start = text.find("{", start) + 1
        if body_start <= 0:
            raise ValueError(f"{patch.name}: function opening brace not found")
        body_end = find_balanced_end(text, body_start)
        declaration = text[start:body_start] + patch.replacement_body[1:]
        text = text[:start] + declaration + text[body_end:]
        counts[patch.name] += 1
        messages.append(f"{patch.name}({body_end - start}b)")

    return PatchResult(text=text, counts=dict(counts), messages=messages)
