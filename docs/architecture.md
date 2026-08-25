# Evaluation architecture

EvalOps Lab keeps the evidence chain explicit:

```text
human dataset / benchmark manifest
              ↓
       validation report
              ↓
  runner + system predictions
              ↓
 deterministic metric evaluators
              ↓
 failure classifications + per-query evidence
              ↓
 traceable result envelope + baseline comparison
```

`RAGCase` is human-authored ground truth. `JudgeOutput` is a separate adapter
contract for model-generated judgments and carries its own model, prompt, and
evaluator versions. The project does not treat a judge score as ground truth.

The first implemented runner is retrieval evaluation. Generation and judge
layers expose typed interfaces but intentionally do not pretend to implement
correctness, faithfulness, or hallucination detection without a real evaluator.
