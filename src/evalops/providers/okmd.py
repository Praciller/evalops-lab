"""OKMD model discovery, deterministic candidate selection, and quota gates."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evalops.evaluators.judge.providers import ProviderHTTPResponse

OKMD_BASE_URL = "https://gen.ai.kku.ac.th/okmd/api/v1"
OKMD_PREFERRED_MODELS = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "qwen3.6-flash",
    "qwen3.5-9b",
    "mistral-medium-3.1",
    "llama-4-scout",
    "llama-4-maverick",
)


@dataclass(frozen=True)
class OKMDModel:
    """Safe model catalog entry with optional non-secret catalog metadata."""

    model_id: str
    name: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OKMDQuota:
    """Daily token quota returned by the OKMD gateway."""

    daily_quota_tokens: int
    daily_usage_tokens: int
    daily_remaining_tokens: int


@dataclass(frozen=True)
class QuotaGateResult:
    """Deterministic quota decision made before any pilot request."""

    status: str
    estimated_tokens: int
    remaining_tokens: int


OKMDTransport = Callable[
    [str, str, dict[str, str], dict[str, object] | None, float], ProviderHTTPResponse
]


def _default_okmd_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, object] | None,
    timeout_seconds: float,
) -> ProviderHTTPResponse:
    request = Request(
        url,
        data=(json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None),
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS URL
            body = json.loads(response.read().decode("utf-8"))
            return ProviderHTTPResponse(
                status_code=response.status,
                body=body if isinstance(body, dict) else {},
                headers=dict(response.headers.items()),
            )
    except HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        return ProviderHTTPResponse(
            status_code=error.code,
            body=body if isinstance(body, dict) else {},
        )
    except (OSError, URLError, TimeoutError) as error:
        raise RuntimeError(
            "API_TIMEOUT" if isinstance(error, TimeoutError) else "API_NETWORK_ERROR"
        ) from error


class OKMDClient:
    """Small authenticated client for the OKMD discovery surface."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OKMD_BASE_URL,
        transport: OKMDTransport | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OKMD API key must not be empty")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._transport = transport or _default_okmd_transport
        self._timeout_seconds = timeout_seconds

    def _request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> ProviderHTTPResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return self._transport(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers,
            payload,
            self._timeout_seconds,
        )

    def discover_models(self) -> list[OKMDModel]:
        """Discover the catalog once, preferring the id/name chat mapping."""

        response = self._request("GET", "/chat/models-list")
        models = parse_models_response(response.body)
        if models:
            return models
        fallback = self._request("GET", "/models")
        return parse_models_response(fallback.body)


def _model_entries(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for key in ("data", "models", "items", "result"):
            nested = value.get(key)
            entries = _model_entries(nested)
            if entries:
                return entries
        for key in ("models", "data", "items"):
            nested = value.get(key)
            if isinstance(nested, Mapping):
                entries = _model_entries(nested)
                if entries:
                    return entries
    return []


def parse_models_response(payload: Mapping[str, object]) -> list[OKMDModel]:
    """Normalize common OKMD catalog response shapes without retaining secrets."""

    models: list[OKMDModel] = []
    seen: set[str] = set()
    for entry in _model_entries(payload):
        model_id = _first_string(entry, ("id", "model_id", "modelId", "model"))
        name = _first_string(entry, ("name", "display_name", "displayName", "label"))
        if model_id is None:
            continue
        if name is None:
            name = model_id
        if not name:
            continue
        normalized_id = model_id.strip()
        if normalized_id in seen:
            continue
        seen.add(normalized_id)
        safe_metadata = {
            str(key): value
            for key, value in entry.items()
            if key
            not in {
                "id",
                "model_id",
                "modelId",
                "model",
                "name",
                "display_name",
                "displayName",
                "label",
                "api_key",
                "token",
                "authorization",
                "secret",
            }
            and isinstance(value, (str, int, float, bool))
        }
        models.append(OKMDModel(model_id=normalized_id, name=name.strip(), metadata=safe_metadata))
    return models


def _first_string(entry: Mapping[str, object], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def model_family(model: OKMDModel | str) -> str:
    """Return a conservative family label for model-diversity gating."""

    text = model.model_id + " " + model.name if isinstance(model, OKMDModel) else model
    lowered = text.casefold()
    families = (
        ("Gemini", ("gemini", "gemma", "google")),
        ("DeepSeek", ("deepseek",)),
        ("Qwen", ("qwen",)),
        ("Mistral", ("mistral",)),
        ("Meta/Llama", ("llama", "meta")),
        ("Claude", ("claude", "anthropic")),
        ("OpenAI", ("openai", "gpt-")),
        ("xAI", ("grok", "xai")),
        ("Nova", ("nova",)),
        ("Perplexity", ("perplexity",)),
    )
    for family, terms in families:
        if any(term in lowered for term in terms):
            return family
    return "Other"


def _is_text_chat_model(model: OKMDModel) -> bool:
    text = f"{model.model_id} {model.name}".casefold()
    return not any(
        term in text for term in ("embedding", "rerank", "vision", "image", "audio", "tts")
    )


def _remaining_quota(model: OKMDModel) -> int:
    value = model.metadata.get("daily_remaining_tokens")
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else -1


def select_okmd_candidates(
    catalog: Sequence[OKMDModel], *, max_candidates: int = 3
) -> list[OKMDModel]:
    """Select at most three deterministic non-Gemini text candidates."""

    if not 1 <= max_candidates <= 3:
        raise ValueError("max_candidates must be between 1 and 3")
    preferred = {model_id: index for index, model_id in enumerate(OKMD_PREFERRED_MODELS)}
    eligible = [
        model for model in catalog if model_family(model) != "Gemini" and _is_text_chat_model(model)
    ]
    eligible.sort(
        key=lambda model: (
            preferred.get(model.model_id, len(preferred)),
            1 if "preview" in f"{model.model_id} {model.name}".casefold() else 0,
            -_remaining_quota(model),
            model.model_id,
        )
    )
    return eligible[:max_candidates]


def estimate_pilot_tokens(
    prompts: Sequence[str], *, output_tokens: int = 256, safety_margin: float = 0.25
) -> int:
    """Estimate one OKMD request per prompt with a conservative 3-char/token ratio."""

    if output_tokens < 0 or safety_margin < 0:
        raise ValueError("output_tokens and safety_margin must be non-negative")
    input_tokens = sum(math.ceil(len(prompt) / 3) for prompt in prompts)
    raw_total = input_tokens + (len(prompts) * output_tokens)
    return math.ceil(raw_total * (1.0 + safety_margin))


def parse_quota(value: object) -> OKMDQuota | None:
    if not isinstance(value, Mapping):
        return None
    fields = ("daily_quota_tokens", "daily_usage_tokens", "daily_remaining_tokens")
    values: list[int] = []
    for field_name in fields:
        field_value = value.get(field_name)
        if not isinstance(field_value, (int, float)) or isinstance(field_value, bool):
            return None
        values.append(int(field_value))
    return OKMDQuota(*values)


def validate_quota_gate(quota: OKMDQuota | None, *, estimated_tokens: int) -> QuotaGateResult:
    """Require an actual gateway remaining-token value before the pilot."""

    if quota is None:
        raise ValueError("daily_remaining_tokens is required for the OKMD quota gate")
    status = (
        "PASS"
        if quota.daily_remaining_tokens >= estimated_tokens
        else "OKMD_QUOTA_INSUFFICIENT_FOR_120"
    )
    return QuotaGateResult(status, estimated_tokens, quota.daily_remaining_tokens)


def discovery_snapshot_payload(models: Sequence[OKMDModel]) -> dict[str, object]:
    """Serialize only timestamp and catalog id/name fields for ignored local evidence."""

    return {
        "discovered_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": [{"model_id": model.model_id, "name": model.name} for model in models],
    }
