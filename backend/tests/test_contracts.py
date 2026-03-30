from __future__ import annotations

import json

import pytest

from qnu_copilot.domain.enums import ContractType
from qnu_copilot.services.contracts import ContractParserService
from qnu_copilot.services.errors import ContractValidationError


def build_recommendation_payload() -> str:
    zh_items = [
        {
            "title": f"中文论文{i}",
            "language": "zh",
            "year": 2024,
            "venue": "中文期刊",
            "download_url": f"https://example.com/zh/{i}.pdf",
            "impact_note": "important",
            "bibtex": f"@article{{zh{i}, title={{中文论文{i}}}}}",
        }
        for i in range(1, 16)
    ]
    en_items = [
        {
            "title": f"English Paper {i}",
            "language": "en",
            "year": 2024,
            "venue": "Conference",
            "download_url": f"https://example.com/en/{i}.pdf",
            "impact_note": "important",
            "bibtex": f"@article{{en{i}, title={{English Paper {i}}}}}",
        }
        for i in range(1, 16)
    ]
    return json.dumps({"topic": "topic", "papers": zh_items + en_items}, ensure_ascii=False)


def test_contract_parser_removes_code_fences_and_repairs_single_closer(
    contract_parser: ContractParserService,
) -> None:
    raw_text = "```json\n" + build_recommendation_payload()[:-1] + "\n```"
    parsed = contract_parser.parse(ContractType.REFERENCE_RECOMMENDATION, raw_text)

    assert parsed.contract_type == ContractType.REFERENCE_RECOMMENDATION
    assert parsed.errors == []
    assert "removed_markdown_code_fences" in parsed.warnings
    assert "appended_single_missing_closer" in parsed.warnings
    assert parsed.parsed_object["topic"] == "topic"


def test_contract_parser_rejects_missing_required_fields(
    contract_parser: ContractParserService,
) -> None:
    raw_text = '{"title":"outline only"}'
    with pytest.raises(ContractValidationError):
        contract_parser.parse(ContractType.OUTLINE, raw_text)
