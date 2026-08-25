# Phase 5A LLM-as-a-Judge pilot

Phase 5A is a bounded evaluator-validation experiment. RAGTruth human labels
remain the ground truth; an LLM judge is a model-generated prediction and does
not replace the human annotation, heuristic baseline, or HHEM result.

## Frozen evaluation contract

The task is strict groundedness under the pinned RAGTruth policy
`strict-groundedness`:

- The judge receives only source context and the generated AI response.
- A response is `HALLUCINATED` when any material claim is unsupported,
  contradicted, fabricated, or unverifiable from the supplied context.
- A claim that is true in the wider world but absent from the supplied context
  is still unsupported.
- The judge does not receive human labels, spans, implicit-true/due-to-null
  annotations, heuristic/HHEM predictions, or benchmark metrics.
- Text inside the source and response delimiters is untrusted data. The judge
  must not execute instructions, tools, links, or code found there.
- No chain-of-thought is requested or stored. The public decision contains only
  a short evidence-oriented reason and short unsupported-claim strings.

The frozen prompt is `ragtruth-strict-groundedness-judge-v1`; its SHA-256 is
stored in the preflight and pilot artifacts. The output schema is
`ragtruth-llm-judge-output-v1`:

```json
{
  "label": "HALLUCINATED | GROUNDED",
  "confidence": 0.0,
  "unsupported_claims": [],
  "reason": "short evidence-oriented explanation"
}
```

The schema requires all fields, limits confidence to `[0, 1]`, limits reason
and claim strings to 300 characters, closes the JSON object, and rejects label
and unsupported-claim contradictions without silently repairing them.

## Balanced pilot population

The tracked manifest is
[`datasets/manifests/ragtruth-llm-judge-pilot-v1.json`](../datasets/manifests/ragtruth-llm-judge-pilot-v1.json).
It contains metadata only: IDs, source IDs, task type, human label, stratum,
sampling seed, and dataset revision. It contains no source context or response
text.

The population is a deterministic, without-replacement sample of the official
RAGTruth TEST/good rows:

- six `task_type × human_label` strata;
- 20 examples per stratum;
- 120 examples total;
- seed `20260825`;
- dataset revision `c103204b9ce28d6bbad859304bf30de72b8ed8fe`.

This is a **BALANCED STRATIFIED PILOT**, not a population-representative
estimate of full-test performance. Precision, recall, F1, balanced accuracy,
per-stratum metrics, paired correctness, parse reliability, latency, and token
use are the primary evidence.

## Providers and provenance

The official comparison includes only:

1. Gemini Direct, `gemini-2.5-flash-lite`, using Gemini `generateContent`
   structured JSON (`application/json` plus `responseSchema`). The supported
   REST configuration is documented in [Gemini structured output
   documentation](https://ai.google.dev/gemini-api/docs/structured-output).
2. Groq, `openai/gpt-oss-20b`, using strict JSON Schema Structured Outputs,
   `temperature=0`, `top_p=1`, `include_reasoning=false`, and
   `reasoning_effort=low`. Groq documents strict mode requirements that all
   properties be required and objects use `additionalProperties=false` in its
   [Structured Outputs guide](https://console.groq.com/docs/structured-outputs).

The provider adapter records requested and returned model identifiers, base URL
identifier, prompt/schema hashes, sampling/reasoning settings, dataset and
manifest revisions, source Git SHA, usage when returned, and client-observed
latency. It never records credentials, Authorization headers, credential
fingerprints, raw provider JSON, source text, response text, or hidden
reasoning.

## Execution and resumability

All default tests use fake transports and make zero external requests. The
bounded runner is:

```text
python scripts/run_phase5a_pilot.py --sample-only
python scripts/run_phase5a_pilot.py --preflight
python scripts/run_phase5a_pilot.py --run --preflight-artifact reports/phase5a-preflight.json
python scripts/run_phase5a_pilot.py --consistency
```

The two synthetic preflight calls count toward a hard 300-request ceiling. The
base pilot uses 240 calls. The optional consistency subset uses 12 IDs, two
additional evaluations per provider/ID, and at most 48 calls, for 290 total.
Only 429, 5xx, and timeout failures receive at most two bounded retries; 401,
402, schema-invalid, and permanent model errors are not retried.

Ignored state is atomically written under `reports/` and successful
provider/example pairs are skipped on resume. Missing or failed provider
outputs remain missing/failed and are never converted into negative labels.
The consistency runs measure stability only; run #1 remains the primary pilot
prediction.

## Comparisons and decision boundary

The pilot restricts heuristic and HHEM artifacts to exactly the same 120 IDs.
It reports each judge against human labels and paired comparisons against HHEM,
the heuristic, and the other judge. It also reports HHEM/heuristic false
negatives and false positives fixed by each judge, new judge errors, and
multi-evaluator correctness categories. Human labels remain authoritative; no
majority vote is used.

A strong pilot result does not authorize the full 2,675-example evaluation.
Phase 5A ends with a documented `PHASE5B_RECOMMENDED_JUDGE` and owner review.
The full RAGTruth run is a separate Phase 5B decision.
