# Phase 5A LLM-as-a-Judge pilot

Phase 5A is a bounded evaluator-validation experiment. RAGTruth human labels
remain the ground truth; an LLM judge is a model-generated prediction and does
not replace the human annotation, heuristic baseline, or HHEM result.

The current Phase 5A experiment is a **generic single-provider LLM judge
validation pilot**. The readiness gate accepts any provider that completes the
synthetic structured-output preflight; this run uses Gemini Direct because it
is the only provider that qualified. Multi-provider comparison is a separate
deferred scope and is not required to validate one judge against human labels,
HHEM, and the heuristic baseline.

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

The provider chronology is intentionally preserved:

1. Gemini Direct, `gemini-2.5-flash-lite`, using Gemini `generateContent`
   structured JSON (`responseMimeType=application/json` plus
   `responseJsonSchema`). The prior `generationConfig.responseFormat.text`
   request was rejected by the native `v1beta` endpoint with HTTP 400
   `INVALID_ARGUMENT`; the adapter now uses the direct native fields. The supported
   REST configuration is documented in [Gemini structured output
   documentation](https://ai.google.dev/gemini-api/docs/structured-output).
2. The initial secondary path was Groq, `openai/gpt-oss-20b`, using strict JSON Schema Structured Outputs,
   `temperature=0`, `top_p=1`, `include_reasoning=false`, and
   `reasoning_effort=low`. Groq documents strict mode requirements that all
   properties be required and objects use `additionalProperties=false` in its
   [Structured Outputs guide](https://console.groq.com/docs/structured-outputs).

3. Groq basic completion returned an account-level HTTP 403 even without
structured-output parameters; the provider did not return a safe error object,
so its permission code was not guessed. The OpenRouter fallback was then
tested but returned one locally invalid/unfinished JSON response and one HTTP
503. It was not admitted to the pilot.
4. OKMD was then tested through
`https://gen.ai.kku.ac.th/okmd/api/v1`. Live discovery found 24 catalog models;
the bounded deterministic candidate order tested `deepseek-v4-flash`,
`deepseek-v4-pro`, and `qwen3.6-flash`. Each candidate returned API success for
both synthetic cases, but neither the initial attempt nor one bounded
regeneration produced parseable `choices[0].message.content` under
`json-text-local-validation`. No quota metadata was returned, so the mandatory
120-example quota gate also remained unverified. The OKMD gateway therefore did
not qualify as the secondary judge, and the pilot was not started.

5. Cerebras was checked as a possible additional provider but its quota was
exhausted, so it was not retried or admitted. ThaiLLM was policy-blocked and
was not used. These provider results and the OKMD adapter remain preserved as
provenance and future-provider work; they do not expand the current pilot.

Provider output mode is recorded separately from judge semantics. The supported
paths are `json-schema-strict`, `json-schema-best-effort`,
`json-object-local-validation`, and `json-text-local-validation`. Every path is
validated by the same local Pydantic contract. If Groq basic completion is
permission-blocked, the optional fallback is the exact OpenRouter model
`liquid/lfm-2.5-2.6b:free`; it is explicitly marked `routing_immutable=false`
and is not equivalent to a direct reproducible provider. In the repaired
preflight, Groq basic completion returned HTTP 403 without a provider error
object, so its permission code remains unavailable rather than guessed. The
OpenRouter fallback returned one API-successful but locally invalid/unfinished
JSON response and one HTTP 503, so it did not qualify as the secondary judge.

For OKMD, the adapter records gateway, requested model ID, catalog name,
returned model/provider fields when exposed, `backend_revision=unavailable`,
quota fields when returned, and `routing_immutable=false`. It does not imply
immutable backend reproducibility. The provider adapter records requested and
returned model identifiers, base URL identifier, prompt/schema hashes,
sampling/reasoning settings, dataset and manifest revisions, source Git SHA,
usage when returned, response ID, and client-observed latency. It never records
credentials, Authorization headers, credential fingerprints, raw provider JSON,
source text, response text, or hidden reasoning. `modelVersion` and response ID
are recorded when Gemini returns them; missing historical fields are reported
as unavailable rather than backfilled.

## Execution and resumability

All default tests use fake transports and make zero external requests. The
bounded runner is:

```text
python scripts/run_phase5a_pilot.py --sample-only
python scripts/run_phase5a_pilot.py --preflight
python scripts/run_phase5a_pilot.py --run --preflight-artifact reports/phase5a-preflight.json
python scripts/run_phase5a_pilot.py --consistency
```

The original preflight and repair history is retained, but a resumed pilot uses
a separate fresh 180-request ceiling. The resume procedure performs at most
one synthetic Gemini health check, then evaluates only pending IDs from the
immutable manifest. It paces requests at least 10 seconds apart, honors a
provider `Retry-After` delay when present, stops immediately on an explicit
requests-per-day (`RPD`) signal, and trips after three consecutive 429s. The
nominal base pilot uses 120 calls. The optional consistency subset uses 12 IDs,
two additional evaluations per ID, and at most 24 calls for one provider.
Retries consume the same fresh budget. The historical ledger records the
earlier Gemini/Groq/OpenRouter and OKMD qualification attempts; the current
pilot does not repeat those deferred provider checks.
Only 429, 5xx, and timeout failures receive at most two bounded retries; 401,
402, schema-invalid, and permanent model errors are not retried.

Ignored state is atomically written under `reports/` and successful
provider/example pairs are skipped on resume. Missing or failed provider
outputs remain missing/failed and are never converted into negative labels.
The consistency runs measure stability only; run #1 remains the primary pilot
prediction.

The 2026-08-26 Gemini resume was stopped safely at
`DAILY_QUOTA_EXHAUSTED`: the health check passed, 13 additional pilot IDs
completed, and 21 fresh requests were consumed in total (one health check plus
pilot attempts/retries). The report contains the exact start partition, request
ledger, and rate-limit diagnostics; the ignored state file is the source of
truth for the remaining IDs. The first five historical
successful traces have `modelVersion` unavailable, while resumed successful
traces consistently report `gemini-2.5-flash-lite`; continuity is therefore
`UNVERIFIED`, not asserted as a pass. No historical success was overwritten, no
other provider was tried, and Phase 5B remains unauthorized.

## Comparisons and decision boundary

The pilot restricts heuristic and HHEM artifacts to exactly the same 120 IDs.
It reports the selected judge against human labels and paired comparisons
against HHEM and the heuristic. It also reports HHEM/heuristic false negatives
and false positives fixed by the judge, new judge errors, and three-evaluator
correctness categories. Human labels remain authoritative; no majority vote is
used. The report sets `multi_provider_ready=false` for this scope and does not
invent a secondary-provider comparison.

A strong pilot result does not authorize the full 2,675-example evaluation.
Phase 5A ends with a documented `PHASE5B_RECOMMENDED_JUDGE` and owner review.
The full RAGTruth run is a separate Phase 5B decision. The single-provider
pilot recommendation is therefore a validation input, not authorization for a
full Gemini run.
