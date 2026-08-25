"""Optional HHEM-2.1-Open adapter with a pinned custom-code security gate."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from evalops.evaluators.hallucination.context import build_hhem_context
from evalops.models.hallucination import (
    HallucinationExample,
    HallucinationLabel,
    HallucinationPrediction,
)

HHEM_MODEL_REPOSITORY = "vectara/hallucination_evaluation_model"
HHEM_MODEL_REVISION = "8e4a2e6e96c708cc76c2344f7e4757df2515292c"
HHEM_TOKENIZER_REPOSITORY = "google/flan-t5-base"
HHEM_TOKENIZER_REVISION = "7bcac572ce56db69c1ea7c8af255c5d7c9672fc2"
HHEM_EVALUATOR_VERSION = f"hhem-2.1-open@{HHEM_MODEL_REVISION[:12]}"
HHEM_SECURITY_APPROVAL = (
    "hhem-2.1-open:8e4a2e6e96c708cc76c2344f7e4757df2515292c:custom-code-reviewed-v1"
)
HHEM_CUSTOM_CODE_HASHES = {
    "configuration_hhem_v2.py": "ec57fe344e3104d0d4a99b13d893529aac1e2bd69e83c2814235baf37cdcacc7",
    "modeling_hhem_v2.py": "fcc9cfcee513cc08eb46eac21f1acb498b122572fb35a7dec4d85fae45cb9bba",
}
HHEM_CONFIG_HASH = "773139fe764fe20e146ab14e627b188ccafae35f93cf6f5258dc6c237016b870"
HHEM_WEIGHT_FILE = "model.safetensors"
HHEM_WEIGHT_HF_ETAG = "b5c41f4c1e953e3375973422f014eade266a4832a01fa718e7583e5638453372"


class HHEMScoreModel(Protocol):
    """Small boundary that can be replaced by deterministic test scores."""

    def predict(self, pairs: list[tuple[str, str]]) -> Sequence[float]: ...


HHEMInput = tuple[str, str] | HallucinationExample | Mapping[str, str]


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[4] / "models" / "manifests" / "hhem-2.1-open.json"


def validate_hhem_manifest(payload: Mapping[str, Any], *, revision: str) -> None:
    """Reject any model revision or custom-code hash not covered by review."""

    if revision != HHEM_MODEL_REVISION:
        raise ValueError(
            "HHEM custom code is not approved for this revision; use the reviewed exact revision"
        )
    if payload.get("repository") != HHEM_MODEL_REPOSITORY:
        raise ValueError("HHEM manifest repository does not match the approved model")
    if payload.get("revision") != HHEM_MODEL_REVISION:
        raise ValueError("HHEM manifest revision does not match the approved model")
    if payload.get("tokenizer") != HHEM_TOKENIZER_REPOSITORY:
        raise ValueError("HHEM manifest tokenizer does not match the approved tokenizer")
    if payload.get("tokenizer_revision") != HHEM_TOKENIZER_REVISION:
        raise ValueError("HHEM manifest tokenizer revision does not match the approved tokenizer")
    if payload.get("security_status") != "approved-pinned-review-v1":
        raise ValueError("HHEM model execution requires an approved security manifest")
    if payload.get("approval_marker") != HHEM_SECURITY_APPROVAL:
        raise ValueError("HHEM security approval marker is missing or does not match")
    if payload.get("custom_code_hashes") != HHEM_CUSTOM_CODE_HASHES:
        raise ValueError("HHEM custom-code hashes do not match the reviewed files")
    if payload.get("config_sha256") != HHEM_CONFIG_HASH:
        raise ValueError("HHEM config hash does not match the reviewed config")
    weight_file = payload.get("weight_file")
    if not isinstance(weight_file, Mapping):
        raise ValueError("HHEM manifest is missing the reviewed weight file")
    if (
        weight_file.get("name") != HHEM_WEIGHT_FILE
        or weight_file.get("hf_etag") != HHEM_WEIGHT_HF_ETAG
    ):
        raise ValueError("HHEM weight-file identity does not match the reviewed artifact")


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read approved HHEM manifest: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("approved HHEM manifest must contain an object")
    return payload


def _as_pair(item: HHEMInput) -> tuple[str, str, str]:
    if isinstance(item, HallucinationExample):
        context = build_hhem_context(item)
        return context.example_id, context.premise, context.hypothesis
    if isinstance(item, tuple):
        if len(item) != 2:
            raise ValueError("HHEM tuple input must contain context and response")
        return "", str(item[0]), str(item[1])
    if "example_id" not in item or "source_context" not in item or "response" not in item:
        raise ValueError("HHEM mapping input requires example_id, source_context, and response")
    return str(item["example_id"]), str(item["source_context"]), str(item["response"])


class HHEMHallucinationEvaluator:
    """Map HHEM support scores to the generic hallucination prediction contract."""

    name = "hhem-2.1-open"
    version = HHEM_EVALUATOR_VERSION

    def __init__(
        self,
        *,
        score_model: HHEMScoreModel,
        threshold: float = 0.5,
        threshold_source: str = "fixed-probability-boundary-v1",
        batch_size: int = 1,
        device: str = "cpu",
        dtype: str = "float32",
        context_strategy: str = "ragtruth-source-context-v1",
        model_file_hashes: Mapping[str, str] | None = None,
        tokenizer_repository: str = HHEM_TOKENIZER_REPOSITORY,
        tokenizer_revision: str = HHEM_TOKENIZER_REVISION,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("HHEM threshold must be between 0 and 1")
        if batch_size < 1:
            raise ValueError("HHEM batch_size must be at least 1")
        self.score_model = score_model
        self.threshold = threshold
        self.threshold_source = threshold_source
        self.batch_size = batch_size
        self.device = device
        self.dtype = dtype
        self.context_strategy = context_strategy
        self.tokenizer_repository = tokenizer_repository
        self.tokenizer_revision = tokenizer_revision
        self.model_file_hashes = dict(
            model_file_hashes
            or {
                "model.safetensors.hf_etag": HHEM_WEIGHT_HF_ETAG,
                **HHEM_CUSTOM_CODE_HASHES,
                "config.json": HHEM_CONFIG_HASH,
            }
        )

    @property
    def config(self) -> dict[str, Any]:
        return {
            "model_repository": HHEM_MODEL_REPOSITORY,
            "model_revision": HHEM_MODEL_REVISION,
            "model_file_hashes": self.model_file_hashes,
            "tokenizer": self.tokenizer_repository,
            "tokenizer_revision": self.tokenizer_revision,
            "threshold": self.threshold,
            "threshold_source": self.threshold_source,
            "device": self.device,
            "batch_size": self.batch_size,
            "dtype": self.dtype,
            "context_strategy": self.context_strategy,
            "security_approval": HHEM_SECURITY_APPROVAL,
        }

    def _prediction(
        self,
        example_id: str,
        support_score: float,
        *,
        input_length: int | None = None,
        truncated: bool | None = None,
    ) -> HallucinationPrediction:
        if not 0.0 <= support_score <= 1.0:
            raise ValueError("HHEM support score must be between 0 and 1")
        label = (
            HallucinationLabel.GROUNDED
            if support_score >= self.threshold
            else HallucinationLabel.HALLUCINATED
        )
        return HallucinationPrediction(
            example_id=example_id,
            label=label,
            score=1.0 - support_score,
            support_score=support_score,
            input_length=input_length,
            truncated=truncated,
            context_strategy=self.context_strategy,
            evaluator_name=self.name,
            evaluator_version=self.version,
            evaluator_config=self.config,
        )

    def evaluate(
        self, context: str, response: str, *, example_id: str = ""
    ) -> HallucinationPrediction:
        return self.evaluate_batch([(context, response)], example_ids=[example_id])[0]

    def evaluate_batch(
        self,
        inputs: Sequence[HHEMInput],
        *,
        example_ids: Sequence[str] | None = None,
    ) -> list[HallucinationPrediction]:
        normalized = [_as_pair(item) for item in inputs]
        if example_ids is not None and len(example_ids) != len(normalized):
            raise ValueError("HHEM example_ids must align with inputs")
        predictions: list[HallucinationPrediction] = []
        for start in range(0, len(normalized), self.batch_size):
            chunk = normalized[start : start + self.batch_size]
            pairs = [(context, response) for _, context, response in chunk]
            try:
                scores = list(self.score_model.predict(pairs))
            except RuntimeError as error:
                if "out of memory" in str(error).casefold():
                    raise RuntimeError(
                        "HHEM inference ran out of memory; reduce --batch-size or use --device cpu"
                    ) from error
                raise
            if len(scores) != len(chunk):
                raise ValueError("HHEM score model returned a different number of scores")
            batch_metadata = getattr(
                self.score_model,
                "last_batch_metadata",
                [{"input_length": None, "truncated": None} for _ in chunk],
            )
            if len(batch_metadata) != len(chunk):
                batch_metadata = [{"input_length": None, "truncated": None} for _ in chunk]
            for offset, raw_score in enumerate(scores):
                try:
                    support_score = float(raw_score)
                except (TypeError, ValueError) as error:
                    raise ValueError("HHEM support score must be numeric") from error
                example_id = (
                    str(example_ids[start + offset])
                    if example_ids is not None
                    else chunk[offset][0]
                )
                predictions.append(
                    self._prediction(
                        example_id,
                        support_score,
                        input_length=batch_metadata[offset].get("input_length"),
                        truncated=batch_metadata[offset].get("truncated"),
                    )
                )
        return predictions


class _LoadedHHEMScoreModel:
    def __init__(self, model: Any) -> None:
        self.model = model
        self.last_batch_metadata: list[dict[str, Any]] = []
        self.tokenizer_repository = HHEM_TOKENIZER_REPOSITORY
        self.tokenizer_revision = HHEM_TOKENIZER_REVISION

    def predict(self, pairs: list[tuple[str, str]]) -> Sequence[float]:
        self.last_batch_metadata = []
        tokenizer = getattr(self.model, "tokenzier", None)
        prompt = getattr(self.model, "prompt", None)
        if tokenizer is not None and isinstance(prompt, str):
            for premise, hypothesis in pairs:
                formatted = prompt.format(text1=premise, text2=hypothesis)
                encoded = tokenizer(formatted, truncation=False, padding=False)
                self.last_batch_metadata.append(
                    {"input_length": len(encoded["input_ids"]), "truncated": False}
                )
        else:
            self.last_batch_metadata = [{"input_length": None, "truncated": None} for _ in pairs]
        values = self.model.predict(pairs)
        if hasattr(values, "detach"):
            values = values.detach().cpu().tolist()
        return cast(Sequence[float], values)


def load_hhem_score_model(
    *,
    revision: str = HHEM_MODEL_REVISION,
    manifest_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
    device: str = "cpu",
    local_files_only: bool = False,
) -> _LoadedHHEMScoreModel:
    """Load HHEM only after the exact reviewed revision and hashes are approved."""

    manifest = _load_manifest(Path(manifest_path) if manifest_path else _default_manifest_path())
    validate_hhem_manifest(manifest, revision=revision)
    try:
        import torch

        transformers_module = import_module("transformers")
        AutoModelForSequenceClassification = transformers_module.AutoModelForSequenceClassification
    except ImportError as error:
        raise RuntimeError(
            "HHEM requires the optional dependencies; install evalops[hhem]"
        ) from error
    try:
        model = AutoModelForSequenceClassification.from_pretrained(
            HHEM_MODEL_REPOSITORY,
            revision=revision,
            trust_remote_code=True,
            cache_dir=str(cache_dir) if cache_dir else None,
            local_files_only=local_files_only,
            torch_dtype=torch.float32,
        )
        model.to(device)
        model.eval()
    except RuntimeError as error:
        if "out of memory" in str(error).casefold():
            raise RuntimeError(
                "HHEM model load ran out of memory; use CPU or a smaller machine"
            ) from error
        raise
    return _LoadedHHEMScoreModel(model)
