from __future__ import annotations

from datetime import UTC, datetime

from evalops.evaluators.generation.interface import GenerationEvaluation
from evalops.evaluators.judge.interface import JudgeOutput
from evalops.failures.taxonomy import FailureCategory, FailureClass, FailureClassification
from evalops.models.runs import EvaluationResult, RunConfig


def test_run_and_evaluation_result_round_trip_as_json() -> None:
    config = RunConfig(
        run_id="run-001",
        dataset_name="thai-rag-eval-200",
        dataset_version="fixture-v1",
        system_name="retrieval-fixture",
        top_k=5,
        random_seed=7,
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
    )
    result = EvaluationResult(
        evaluation_type="retrieval",
        run=config,
        metrics={"recall_at_5": 1.0},
        failures=[
            FailureClassification(
                category=FailureCategory.RETRIEVAL_MISS,
                failure_class=FailureClass.SYSTEM,
                message="no relevant result",
            )
        ],
    )

    restored = EvaluationResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.run.timestamp.tzinfo is not None


def test_judge_output_is_separate_from_human_ground_truth() -> None:
    output = JudgeOutput(
        case_id="THQA-001",
        score=0.75,
        label="mostly_supported",
        reasoning="The answer covers the main claim.",
        model="local-judge",
        prompt_version="judge-prompt-v1",
        evaluator_version="judge-adapter-v1",
    )

    assert output.model == "local-judge"
    assert not hasattr(output, "ground_truth")


def test_generation_evaluation_is_an_output_contract_not_a_fake_model_judgment() -> None:
    evaluation = GenerationEvaluation(
        case_id="THQA-001",
        evaluator_name="placeholder-adapter",
        evaluator_version="0.1",
        scores={"correctness": 0.5},
        notes="Produced by an explicitly configured adapter.",
    )

    assert evaluation.scores["correctness"] == 0.5
