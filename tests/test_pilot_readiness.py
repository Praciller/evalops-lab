from __future__ import annotations

from evalops.pilot.readiness import assess_llm_judge_readiness


def _result(*, family: str, api: int, parse: int) -> dict[str, object]:
    return {
        "provider_family": family,
        "api_success_count": api,
        "parse_success_count": parse,
    }


def test_single_qualified_provider_is_ready_without_multi_provider_readiness() -> None:
    readiness = assess_llm_judge_readiness(
        ("gemini",), {"gemini": _result(family="Gemini", api=2, parse=2)}
    )

    assert readiness["llm_judge_ready"] is True
    assert readiness["multi_provider_ready"] is False
    assert readiness["qualified_providers"] == ["gemini"]


def test_no_qualified_provider_blocks_the_judge_pilot() -> None:
    readiness = assess_llm_judge_readiness(
        ("gemini", "okmd"),
        {
            "gemini": _result(family="Gemini", api=2, parse=1),
            "okmd": _result(family="OKMD", api=0, parse=0),
        },
    )

    assert readiness["llm_judge_ready"] is False
    assert readiness["multi_provider_ready"] is False
    assert readiness["qualified_providers"] == []


def test_two_qualified_distinct_families_are_multi_provider_ready() -> None:
    readiness = assess_llm_judge_readiness(
        ("gemini", "groq"),
        {
            "gemini": _result(family="Gemini", api=2, parse=2),
            "groq": _result(family="Groq", api=2, parse=2),
        },
    )

    assert readiness["llm_judge_ready"] is True
    assert readiness["multi_provider_ready"] is True
    assert readiness["provider_families"] == ["Gemini", "Groq"]


def test_two_qualified_same_family_providers_do_not_prove_diversity() -> None:
    readiness = assess_llm_judge_readiness(
        ("gateway-a", "gateway-b"),
        {
            "gateway-a": _result(family="SameBackend", api=2, parse=2),
            "gateway-b": _result(family="SameBackend", api=2, parse=2),
        },
    )

    assert readiness["llm_judge_ready"] is True
    assert readiness["multi_provider_ready"] is False
