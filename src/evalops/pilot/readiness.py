"""Provider-agnostic readiness gates for bounded LLM judge pilots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def assess_llm_judge_readiness(
    selected_providers: Sequence[str],
    provider_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Separate single-provider judge readiness from provider diversity readiness."""

    qualified_providers: list[str] = []
    provider_families: list[str] = []
    disqualified_providers: list[str] = []
    for provider in selected_providers:
        result = provider_results.get(provider, {})
        api_success_count = result.get("api_success_count")
        parse_success_count = result.get("parse_success_count")
        if (
            isinstance(api_success_count, int)
            and isinstance(parse_success_count, int)
            and api_success_count > 0
            and api_success_count == parse_success_count
        ):
            qualified_providers.append(provider)
            family = result.get("provider_family")
            provider_families.append(
                str(family) if isinstance(family, str) and family else provider
            )
        else:
            disqualified_providers.append(provider)

    return {
        "llm_judge_ready": bool(qualified_providers),
        "multi_provider_ready": len(qualified_providers) >= 2 and len(set(provider_families)) >= 2,
        "qualified_providers": qualified_providers,
        "disqualified_providers": disqualified_providers,
        "provider_families": provider_families,
    }
