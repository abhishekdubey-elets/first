"""Tests for the tolerant JSON parser in the LLM service.

``_parse_json`` must survive small local models that wrap JSON in markdown
fences or surround it with prose, and raise ``LLMError`` on true garbage.
"""
from __future__ import annotations

import pytest

from app.services.llm import LLMError, _parse_json


def test_parses_raw_json():
    assert _parse_json('{"officer_name": "Anil", "confidence_score": 0.9}') == {
        "officer_name": "Anil",
        "confidence_score": 0.9,
    }


def test_parses_json_in_markdown_fences():
    content = '```json\n{"officer_name": "Priya", "state": "Kerala"}\n```'
    assert _parse_json(content) == {"officer_name": "Priya", "state": "Kerala"}


def test_parses_json_with_surrounding_prose():
    content = (
        "Sure! Here is the extracted record you asked for:\n"
        '{"officer_name": "Rajesh", "cadre": "MP"}\n'
        "Let me know if you need anything else."
    )
    assert _parse_json(content) == {"officer_name": "Rajesh", "cadre": "MP"}


def test_raises_on_garbage():
    with pytest.raises(LLMError):
        _parse_json("this is not json at all, no braces here")


def test_raises_on_empty_string():
    with pytest.raises(LLMError):
        _parse_json("")
