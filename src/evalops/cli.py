"""Small CLI that delegates to reusable dataset and evaluation logic."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalops.benchmarks.miracl import run_miracl_benchmark, write_trec_run
from evalops.benchmarks.ragtruth import run_ragtruth_benchmark
from evalops.datasets.io import load_retrieval_ground_truth, load_retrieval_predictions
from evalops.datasets.miracl_prepare import (
    MIRACL_CORPUS_REVISION,
    MIRACL_TOPICS_QRELS_REVISION,
    prepare_miracl,
)
from evalops.datasets.ragtruth import load_ragtruth_dataset
from evalops.datasets.ragtruth_prepare import RAGTRUTH_REVISION, prepare_ragtruth
from evalops.datasets.validation import load_rag_cases, validate_rag_cases
from evalops.evaluators.hallucination.comparison import compare_hallucination_artifacts
from evalops.evaluators.hallucination.heuristic import HeuristicHallucinationEvaluator
from evalops.evaluators.hallucination.hhem import (
    HHEM_MODEL_REVISION,
    HHEMHallucinationEvaluator,
    load_hhem_score_model,
)
from evalops.evaluators.hallucination.interface import HallucinationEvaluator
from evalops.export import (
    ClaimScope,
    DataKind,
    PopulationCompatibility,
    PublicArtifact,
    VerificationStatus,
    adapt_evaluation_result,
    adapt_regression_report,
    build_public_index,
    load_public_artifact,
    serialize_public_artifact,
)
from evalops.models.hallucination import AnnotationPolicy
from evalops.models.runs import RunConfig
from evalops.regression.comparison import MetricRule, compare_metrics
from evalops.runners.retrieval import run_retrieval_evaluation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalops", description="Testing-first AI evaluation tools."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    dataset = commands.add_parser("dataset", help="Validate and inspect datasets.")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    validate = dataset_commands.add_parser("validate", help="Validate a RAG case JSONL file.")
    validate.add_argument("path", type=Path)
    validate.add_argument(
        "--document-catalog",
        type=Path,
        help="Optional newline-delimited catalog used to check relevant document IDs.",
    )
    prepare = dataset_commands.add_parser("prepare", help="Prepare an external benchmark locally.")
    prepare_commands = prepare.add_subparsers(dest="prepare_command", required=True)
    miracl_prepare = prepare_commands.add_parser("miracl", help="Prepare MIRACL Thai artifacts.")
    miracl_prepare.add_argument("--language", default="th")
    miracl_prepare.add_argument("--split", default="dev")
    miracl_prepare.add_argument(
        "--output-dir", type=Path, default=Path("datasets/external/miracl/th/dev")
    )
    miracl_prepare.add_argument("--mini", action="store_true")
    miracl_prepare.add_argument("--fixture-dir", type=Path)
    miracl_prepare.add_argument("--topics-source")
    miracl_prepare.add_argument("--qrels-source")
    miracl_prepare.add_argument("--corpus-source")
    miracl_prepare.add_argument("--topics-qrels-only", action="store_true")
    ragtruth_prepare = prepare_commands.add_parser(
        "ragtruth", help="Prepare RAGTruth response/source JSONL files."
    )
    ragtruth_prepare.add_argument(
        "--output-dir", type=Path, default=Path("datasets/external/ragtruth")
    )
    ragtruth_prepare.add_argument("--mini", action="store_true")
    ragtruth_prepare.add_argument("--fixture-dir", type=Path)
    ragtruth_prepare.add_argument("--response-source")
    ragtruth_prepare.add_argument("--source-info-source")
    ragtruth_prepare.add_argument("--expected-response-sha256")
    ragtruth_prepare.add_argument("--expected-source-sha256")

    retrieval = commands.add_parser("retrieval", help="Evaluate retrieval rankings.")
    retrieval_commands = retrieval.add_subparsers(dest="retrieval_command", required=True)
    evaluate = retrieval_commands.add_parser(
        "evaluate", help="Run deterministic retrieval metrics."
    )
    evaluate.add_argument("--ground-truth", required=True, type=Path)
    evaluate.add_argument("--predictions", required=True, type=Path)
    evaluate.add_argument("--k", required=True, type=int)
    evaluate.add_argument("--run-id", default="local-run")
    evaluate.add_argument("--dataset-name", default="local-retrieval-fixture")
    evaluate.add_argument("--dataset-version", default="unversioned-local-fixture")
    evaluate.add_argument("--system-name", default="local-system")
    evaluate.add_argument("--random-seed", type=int)
    evaluate.add_argument("--output", type=Path)

    benchmark = commands.add_parser("benchmark", help="Run a benchmark retriever.")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    miracl_benchmark = benchmark_commands.add_parser("miracl", help="Run MIRACL retrieval.")
    miracl_benchmark.add_argument("--language", default="th")
    miracl_benchmark.add_argument("--split", default="dev")
    miracl_benchmark.add_argument("--retriever", choices=["bm25"], default="bm25")
    miracl_benchmark.add_argument("--k", required=True, type=int)
    miracl_benchmark.add_argument(
        "--data-dir", type=Path, default=Path("datasets/external/miracl/th/dev")
    )
    miracl_benchmark.add_argument("--mini", action="store_true")
    miracl_benchmark.add_argument(
        "--fixture-dir", type=Path, default=Path("datasets/fixtures/miracl-th-mini")
    )
    miracl_benchmark.add_argument("--run-id", default="local-miracl-run")
    miracl_benchmark.add_argument("--dataset-version")
    miracl_benchmark.add_argument("--system-name", default="evalops-bm25")
    miracl_benchmark.add_argument("--random-seed", type=int)
    miracl_benchmark.add_argument("--output", type=Path)
    miracl_benchmark.add_argument("--trec-run", type=Path)

    hallucination = commands.add_parser(
        "hallucination", help="Evaluate human-annotated hallucination datasets."
    )
    hallucination_commands = hallucination.add_subparsers(
        dest="hallucination_command", required=True
    )
    hallucination_evaluate = hallucination_commands.add_parser(
        "evaluate", help="Evaluate a hallucination detector against human labels."
    )
    hallucination_evaluate.add_argument(
        "--dataset", choices=["ragtruth", "ragtruth-mini"], required=True
    )
    hallucination_evaluate.add_argument("--split", default="test")
    hallucination_evaluate.add_argument(
        "--data-dir", type=Path, default=Path("datasets/external/ragtruth")
    )
    hallucination_evaluate.add_argument(
        "--mini", action="store_true", help="Use the synthetic fixture; never an official result."
    )
    hallucination_evaluate.add_argument(
        "--fixture-dir", type=Path, default=Path("datasets/fixtures/ragtruth-mini")
    )
    hallucination_evaluate.add_argument(
        "--evaluator",
        choices=["heuristic-baseline", "hhem-2.1-open"],
        default="heuristic-baseline",
    )
    hallucination_evaluate.add_argument(
        "--annotation-policy",
        choices=[policy.value for policy in AnnotationPolicy],
        default=AnnotationPolicy.STRICT_GROUNDEDNESS.value,
    )
    hallucination_evaluate.add_argument(
        "--quality",
        action="append",
        help="Quality value to include; repeat for multiple values (default: good).",
    )
    hallucination_evaluate.add_argument("--run-id", default="local-ragtruth-run")
    hallucination_evaluate.add_argument("--dataset-version", default="ragtruth-v1")
    hallucination_evaluate.add_argument("--system-name")
    hallucination_evaluate.add_argument("--random-seed", type=int)
    hallucination_evaluate.add_argument("--output", type=Path)
    hallucination_evaluate.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    hallucination_evaluate.add_argument("--batch-size", type=int, default=1)
    hallucination_evaluate.add_argument("--threshold", type=float)
    hallucination_evaluate.add_argument("--cache-dir", type=Path)
    hallucination_evaluate.add_argument("--local-files-only", action="store_true")
    hallucination_evaluate.add_argument("--model-manifest", type=Path)
    hallucination_compare = hallucination_commands.add_parser(
        "compare", help="Compare two saved hallucination evaluator artifacts."
    )
    hallucination_compare.add_argument("--baseline", required=True, type=Path)
    hallucination_compare.add_argument("--candidate", required=True, type=Path)
    hallucination_compare.add_argument("--output", type=Path)

    regression = commands.add_parser("regression", help="Compare saved evaluation results.")
    regression_commands = regression.add_subparsers(dest="regression_command", required=True)
    compare = regression_commands.add_parser("compare", help="Compare a candidate to a baseline.")
    compare.add_argument("--baseline", required=True, type=Path)
    compare.add_argument("--candidate", required=True, type=Path)
    compare.add_argument("--policy", required=True, type=Path)
    compare.add_argument("--output", type=Path)

    evidence = commands.add_parser(
        "evidence", help="Transform approved evaluation outputs into public artifacts."
    )
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_export = evidence_commands.add_parser(
        "export", help="Export one explicit run or regression source as public JSON."
    )
    evidence_export.add_argument("--source", required=True, type=Path)
    evidence_export.add_argument("--source-type", choices=["run", "comparison"], required=True)
    evidence_export.add_argument("--output", required=True, type=Path)
    evidence_export.add_argument("--artifact-id", required=True)
    evidence_export.add_argument(
        "--verification-status",
        choices=[status.value for status in VerificationStatus],
        required=True,
    )
    evidence_export.add_argument(
        "--data-kind", choices=[kind.value for kind in DataKind], required=True
    )
    evidence_export.add_argument(
        "--claim-scope", choices=[scope.value for scope in ClaimScope], required=True
    )
    evidence_export.add_argument("--limitation", action="append", default=[])
    evidence_export.add_argument("--baseline-artifact-id")
    evidence_export.add_argument("--candidate-artifact-id")
    evidence_export.add_argument(
        "--population-compatibility",
        choices=[status.value for status in PopulationCompatibility],
        default=PopulationCompatibility.UNVERIFIED.value,
    )
    evidence_index = evidence_commands.add_parser(
        "index", help="Index an explicit list of already-approved public artifacts."
    )
    evidence_index.add_argument("--artifact", action="append", required=True, type=Path)
    evidence_index.add_argument("--output", required=True, type=Path)
    return parser


def _write_json(payload: dict[str, Any], output: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


def _load_catalog(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _current_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _dataset_validate(args: argparse.Namespace) -> int:
    try:
        cases = load_rag_cases(args.path)
    except ValueError as error:
        _write_json(
            {
                "valid": False,
                "records_checked": 0,
                "issues": [{"code": "PARSE_ERROR", "message": str(error)}],
            },
            None,
        )
        return 1
    report = validate_rag_cases(cases, document_ids=_load_catalog(args.document_catalog))
    _write_json(report.model_dump(mode="json"), None)
    return 0 if report.valid else 1


def _retrieval_evaluate(args: argparse.Namespace) -> int:
    try:
        ground_truth = load_retrieval_ground_truth(args.ground_truth)
        predictions = load_retrieval_predictions(args.predictions)
    except ValueError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    config = RunConfig(
        run_id=args.run_id,
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        system_name=args.system_name,
        top_k=args.k,
        random_seed=args.random_seed,
        git_commit=_current_git_commit(),
        evaluator_versions={"retrieval": "deterministic-v1"},
    )
    result = run_retrieval_evaluation(ground_truth, predictions, config)
    _write_json(result.model_dump(mode="json"), args.output)
    return 0


def _miracl_prepare(args: argparse.Namespace) -> int:
    try:
        summary = prepare_miracl(
            language=args.language,
            split=args.split,
            output_dir=args.output_dir,
            mini=args.mini,
            fixture_dir=args.fixture_dir,
            topics_source=args.topics_source,
            qrels_source=args.qrels_source,
            corpus_source=args.corpus_source,
            topics_qrels_only=args.topics_qrels_only,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    _write_json(summary.model_dump(mode="json"), None)
    return 0


def _miracl_benchmark(args: argparse.Namespace) -> int:
    fixture_dir = args.fixture_dir if args.mini else args.data_dir
    topics_path = fixture_dir / "topics.tsv"
    qrels_path = fixture_dir / "qrels.tsv"
    corpus_paths = sorted(
        (fixture_dir / "corpus").glob("*.jsonl.gz")
        if not args.mini
        else fixture_dir.glob("corpus.jsonl")
    )
    if not topics_path.is_file() or not qrels_path.is_file() or not corpus_paths:
        print(
            json.dumps(
                {
                    "error": (
                        f"MIRACL inputs are unavailable under {fixture_dir}; "
                        "run 'evalops dataset prepare miracl' first"
                    )
                }
            ),
            file=sys.stderr,
        )
        return 2
    config = RunConfig(
        run_id=args.run_id,
        dataset_name="miracl-th-mini" if args.mini else "miracl-th",
        dataset_version=args.dataset_version
        or ("synthetic-fixture-v1" if args.mini else "miracl-v1.0"),
        system_name=args.system_name,
        top_k=args.k,
        random_seed=args.random_seed,
        git_commit=_current_git_commit(),
        benchmark="miracl",
        language=args.language,
        split=args.split,
        dataset_revision=("synthetic-fixture-v1" if args.mini else MIRACL_TOPICS_QRELS_REVISION),
        corpus_revision=("synthetic-fixture-v1" if args.mini else MIRACL_CORPUS_REVISION),
        retriever="bm25",
        retriever_version="bm25-local-v1",
        evaluator_versions={"retrieval": "deterministic-v1"},
    )
    try:
        result = run_miracl_benchmark(
            topics_path=topics_path,
            qrels_path=qrels_path,
            corpus_paths=corpus_paths,
            config=config,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.trec_run is not None:
        write_trec_run(result, args.trec_run)
    _write_json(result.model_dump(mode="json"), args.output)
    return 0


def _ragtruth_prepare(args: argparse.Namespace) -> int:
    try:
        summary = prepare_ragtruth(
            output_dir=args.output_dir,
            mini=args.mini,
            fixture_dir=args.fixture_dir,
            response_source=args.response_source,
            source_info_source=args.source_info_source,
            expected_response_sha256=args.expected_response_sha256,
            expected_source_sha256=args.expected_source_sha256,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    _write_json(summary.model_dump(mode="json"), None)
    return 0


def _preparation_revision(data_dir: Path) -> str:
    manifest_path = data_dir / "preparation-manifest.json"
    if not manifest_path.is_file():
        return "synthetic-fixture-v1" if "fixtures" in data_dir.parts else RAGTRUTH_REVISION
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RAGTRUTH_REVISION
    return str(payload.get("source_revision", RAGTRUTH_REVISION))


def _hallucination_evaluate(args: argparse.Namespace) -> int:
    mini = args.mini or args.dataset == "ragtruth-mini"
    data_dir = args.fixture_dir if mini else args.data_dir
    response_path = data_dir / "response.jsonl"
    source_info_path = data_dir / "source_info.jsonl"
    if not response_path.is_file() or not source_info_path.is_file():
        print(
            json.dumps(
                {
                    "error": (
                        f"RAGTruth inputs are unavailable under {data_dir}; run "
                        "'evalops dataset prepare ragtruth' first"
                    )
                }
            ),
            file=sys.stderr,
        )
        return 2
    try:
        dataset = load_ragtruth_dataset(
            response_path,
            source_info_path,
            split=args.split,
            source_revision=_preparation_revision(data_dir),
        )
        evaluator: HallucinationEvaluator
        if args.evaluator == "heuristic-baseline":
            evaluator = HeuristicHallucinationEvaluator()
        elif args.evaluator == "hhem-2.1-open":
            device = args.device
            if device == "auto":
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            evaluator = HHEMHallucinationEvaluator(
                score_model=load_hhem_score_model(
                    revision=HHEM_MODEL_REVISION,
                    manifest_path=args.model_manifest,
                    cache_dir=args.cache_dir,
                    device=device,
                    local_files_only=args.local_files_only,
                ),
                threshold=args.threshold if args.threshold is not None else 0.5,
                threshold_source=(
                    "user-provided"
                    if args.threshold is not None
                    else "fixed-probability-boundary-v1"
                ),
                batch_size=args.batch_size,
                device=device,
            )
        else:
            raise AssertionError("unhandled hallucination evaluator")
        config = RunConfig(
            run_id=args.run_id,
            dataset_name="ragtruth-mini" if mini else "ragtruth",
            dataset_version=("synthetic-fixture-v1" if mini else args.dataset_version),
            system_name=args.system_name or evaluator.name,
            random_seed=args.random_seed,
            git_commit=_current_git_commit(),
            benchmark="ragtruth",
            split=args.split,
            dataset_revision=dataset.source_revision,
        )
        result = run_ragtruth_benchmark(
            dataset,
            evaluator,
            config=config,
            annotation_policy=AnnotationPolicy(args.annotation_policy),
            quality_filter=set(args.quality) if args.quality else None,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    _write_json(result.model_dump(mode="json"), args.output)
    return 0


def _hallucination_compare(args: argparse.Namespace) -> int:
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        payload = compare_hallucination_artifacts(baseline, candidate)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    _write_json(payload, args.output)
    return 0


def _regression_compare(args: argparse.Namespace) -> int:
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        policy_payload = json.loads(args.policy.read_text(encoding="utf-8"))
        policy_records = policy_payload.get("rules", policy_payload)
        rules = [MetricRule.model_validate(record) for record in policy_records]
        report = compare_metrics(candidate["metrics"], baseline["metrics"], rules)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    payload = {
        "baseline_run_id": baseline.get("run", {}).get("run_id"),
        "candidate_run_id": candidate.get("run", {}).get("run_id"),
        **report.model_dump(mode="json"),
    }
    _write_json(payload, args.output)
    return 0 if report.passed else 1


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_public_artifact_json(artifact: PublicArtifact, output: Path) -> None:
    serialized = serialize_public_artifact(artifact)
    output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


def _public_export_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(str(detail.get("msg", "validation failed")) for detail in error.errors())
    return str(error)


def _evidence_export(args: argparse.Namespace) -> int:
    try:
        source = _read_json(args.source)
        common = {
            "artifact_id": args.artifact_id,
            "verification_status": VerificationStatus(args.verification_status),
            "data_kind": DataKind(args.data_kind),
            "claim_scope": ClaimScope(args.claim_scope),
            "limitations": args.limitation,
        }
        artifact: PublicArtifact
        if args.source_type == "run":
            artifact = adapt_evaluation_result(source, **common)
        else:
            if not args.baseline_artifact_id or not args.candidate_artifact_id:
                raise ValueError(
                    "comparison exports require --baseline-artifact-id and --candidate-artifact-id"
                )
            artifact = adapt_regression_report(
                source,
                baseline_artifact_id=args.baseline_artifact_id,
                candidate_artifact_id=args.candidate_artifact_id,
                population_compatibility=PopulationCompatibility(args.population_compatibility),
                **common,
            )
        _write_public_artifact_json(artifact, args.output)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps({"error": _public_export_error(error)}, ensure_ascii=False), file=sys.stderr
        )
        return 2
    return 0


def _evidence_index(args: argparse.Namespace) -> int:
    try:
        artifacts = [load_public_artifact(_read_json(path)) for path in args.artifact]
        index = build_public_index(artifacts)
        _write_public_artifact_json(index, args.output)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps({"error": _public_export_error(error)}, ensure_ascii=False), file=sys.stderr
        )
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process-style exit code."""

    args = _build_parser().parse_args(argv)
    if args.command == "dataset" and args.dataset_command == "validate":
        return _dataset_validate(args)
    if args.command == "dataset" and args.dataset_command == "prepare":
        if args.prepare_command == "miracl":
            return _miracl_prepare(args)
        if args.prepare_command == "ragtruth":
            return _ragtruth_prepare(args)
    if args.command == "retrieval" and args.retrieval_command == "evaluate":
        return _retrieval_evaluate(args)
    if args.command == "benchmark" and args.benchmark_command == "miracl":
        return _miracl_benchmark(args)
    if args.command == "hallucination" and args.hallucination_command == "evaluate":
        return _hallucination_evaluate(args)
    if args.command == "hallucination" and args.hallucination_command == "compare":
        return _hallucination_compare(args)
    if args.command == "regression" and args.regression_command == "compare":
        return _regression_compare(args)
    if args.command == "evidence" and args.evidence_command == "export":
        return _evidence_export(args)
    if args.command == "evidence" and args.evidence_command == "index":
        return _evidence_index(args)
    raise AssertionError("unhandled CLI command")
