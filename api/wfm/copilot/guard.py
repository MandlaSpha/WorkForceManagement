"""The deterministic output check (requirement AI-09).

Every word and every number of a final answer must come from this request's tool output or be a
constant of the templates. Anything else (a name, a figure, a queue the tools did not return)
blocks the reply, whichever adapter wrote it. This is the last line of defence, after the role
check on each tool and the scoping inside each selector."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .templates import vocabulary

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reason: str = ""  # a category for the audit trail, never the offending text


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER.findall(text)}


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def check(
    answer: str, tool_facts: Sequence[dict[str, Any]], *, extra_words: frozenset[str] = frozenset()
) -> Verdict:
    """Is every word and number of `answer` explained by the templates or the tool output?"""
    output = " ".join(json.dumps(f, sort_keys=True, default=str) for f in tool_facts)
    allowed_words = vocabulary() | _words(output) | extra_words
    allowed_numbers = _numbers(output)
    unexplained_words = _words(answer) - allowed_words
    if unexplained_words:
        return Verdict(False, "word_not_in_tool_output")
    if _numbers(answer) - allowed_numbers:
        return Verdict(False, "number_not_in_tool_output")
    return Verdict(True)
