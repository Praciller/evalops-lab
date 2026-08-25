# Phase 5A LLM-as-a-Judge Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a bounded, balanced 120-example RAGTruth strict-groundedness pilot comparing Gemini Direct and Groq GPT-OSS without changing human labels or existing heuristic/HHEM results.

**Architecture:** The generic judge evaluator accepts only source context and AI response, renders one frozen prompt, and delegates provider wire formats to injectable Gemini and Groq adapters. A separate pilot package owns deterministic sampling, resumable request state, request budgeting, provider-safe records, metric aggregation, paired comparisons, and consistency analysis; existing RAGTruth normalization and classification metrics remain the source of truth for human labels and formulas.

**Tech Stack:** Python 3.11, Pydantic 2, standard-library `urllib` transport, deterministic `random.Random`, existing RAGTruth adapter and hallucination metrics, pytest, Ruff, mypy.

**Spec:** User-provided Phase 5A brief in the attached continuation request.

## Global Constraints

- Do not run the full 2,675-example RAGTruth evaluation, implement a dashboard, modify human ground truth, or modify existing heuristic/HHEM result artifacts.
- Official pilot providers are Gemini Direct `gemini-2.5-flash-lite` and Groq `openai/gpt-oss-20b` only.
- Default tests make zero external API calls; provider boundaries are injectable and faked in tests.
- The frozen prompt version is `ragtruth-strict-groundedness-judge-v1`; no chain-of-thought is requested or persisted.
- The pilot has six `task_type × human_label` strata, target 20 per stratum, seed `20260825`, and exactly the same IDs for both providers and baseline comparisons.
- The hard global external request ceiling is 300; retries are limited to transient 429, 5xx, and timeout outcomes.
- Ignored detailed state may contain example IDs, labels, short judge evidence, usage, and latency, but never source/response text, credentials, Authorization headers, or hidden reasoning.
- The consistency subset is 12 examples with seed `20260826`; it adds at most 48 requests after the 240 base/preflight requests.
- Local commits are allowed for provider health and Phase 5A source; do not push or amend the frozen baseline.

---

### Task 1: Commit the validated provider-health repair

**Files:**
- Stage: `src/evalops/providers/__init__.py`
- Stage: `src/evalops/providers/health.py`
- Stage: `tests/test_provider_health.py`

**Interfaces:**
- Consumes: the already-tested generic provider health classifier and current ignored smoke report.
- Produces: local commit `fix: separate provider health signals` on top of `0039e1624b6158d7cf0f6e49792e114b959cb7fd`.

- [ ] **Step 1: Re-run the provider-health gates and secret scan**

Run:

```text
python -m pytest -q
python -m ruff check . --no-cache
python -m ruff format --check .
python -m mypy src
git diff --check
python <local-secret-scan-script> <repo-root> <provider-smoke-script> <provider-smoke-setup-script>
```

Expected: all gates pass, the scan reports zero secret-pattern hits, and only provider-health source/tests are uncommitted in the repository.

- [ ] **Step 2: Create the provider-health commit without staging unrelated files**

```text
git add src/evalops/providers/__init__.py src/evalops/providers/health.py tests/test_provider_health.py
git commit -m "fix: separate provider health signals"
```

- [ ] **Step 3: Verify the commit boundary**

```text
git rev-parse HEAD
git status --short
```

Expected: a new local commit follows the frozen baseline; no push and no amend occurred.

### Task 2: Add frozen judge contracts and prompt isolation

**Files:**
- Create: `src/evalops/evaluators/judge/models.py`
- Create: `src/evalops/evaluators/judge/prompt.py`
- Modify: `src/evalops/evaluators/judge/__init__.py`
- Test: `tests/test_judge_contracts.py`
- Test: `tests/test_judge_prompt.py`

**Interfaces:**
- Produces `JudgeDecision`, `JudgeParseResult`, `JUDGE_PROMPT_VERSION`, `JUDGE_SCHEMA_VERSION`, `JUDGE_PROMPT_SHA256`, `JUDGE_OUTPUT_SCHEMA`, and `render_judge_prompt(source_context, response)`.
- `JudgeDecision` validates `label`, `confidence` in `[0,1]`, short `reason`, short `unsupported_claims`, and label/evidence consistency without repairing contradictions.

- [ ] **Step 1: Write failing contract tests**

Tests must prove:

```python
def test_valid_hallucinated_decision_requires_unsupported_claim(): ...
def test_valid_grounded_decision_requires_empty_unsupported_claims(): ...
def test_confidence_and_reason_limits_are_enforced(): ...
def test_prompt_contains_only_delimited_context_and_response(): ...
def test_human_labels_and_spans_are_absent_from_prompt_builder_inputs(): ...
def test_prompt_injection_is_data_inside_ai_response_delimiter(): ...
```

Run `python -m pytest -q tests/test_judge_contracts.py tests/test_judge_prompt.py`; expected failure is missing judge modules/functions.

- [ ] **Step 2: Implement the minimal Pydantic contracts and frozen prompt**

The prompt must explicitly say that `<source_context>` and `<ai_response>` are untrusted data, that no instructions/tools/links/code inside them should be executed, and that only source context may support the label. The output schema must require all four fields and close the JSON object with `additionalProperties: false`.

- [ ] **Step 3: Run the focused tests and refactor only after green**

Run `python -m pytest -q tests/test_judge_contracts.py tests/test_judge_prompt.py`; expected: PASS.

### Task 3: Add provider-independent evaluator and Gemini/Groq adapters

**Files:**
- Create: `src/evalops/evaluators/judge/providers.py`
- Create: `src/evalops/evaluators/judge/evaluator.py`
- Modify: `src/evalops/evaluators/judge/__init__.py`
- Test: `tests/test_judge_providers.py`
- Test: `tests/test_judge_evaluator.py`

**Interfaces:**
- `JudgeProvider` protocol accepts only rendered prompt, schema, and sampling config and returns safe in-memory `ProviderCall` data.
- `GeminiProviderAdapter` uses `generateContent` with `response_mime_type=application/json` and `response_schema`.
- `GroqProviderAdapter` uses OpenAI-compatible `/chat/completions` with strict `response_format.type=json_schema`, all fields required, `additionalProperties=false`, `include_reasoning=false`, `reasoning_effort=low`, `temperature=0`, and `stream=false`.
- `LLMJudgeEvaluator.evaluate_with_trace(context, response, example_id)` returns a `JudgeEvaluationTrace`; `evaluate(...)` maps successful decisions to existing `HallucinationPrediction` and raises a controlled evaluator error for missing/invalid results.

- [ ] **Step 1: Write failing adapter/evaluator tests with fake transports**

Tests must cover:

```python
def test_gemini_structured_request_uses_generate_content_schema(): ...
def test_groq_structured_request_is_strict_and_all_fields_required(): ...
def test_gemini_response_maps_to_grounded_prediction(): ...
def test_groq_response_maps_to_hallucinated_prediction(): ...
def test_fallback_json_content_is_validated_without_hidden_reasoning(): ...
def test_reasoning_field_is_not_in_public_trace_or_prediction_config(): ...
def test_api_error_is_a_controlled_failed_trace(): ...
```

Run the focused tests; expected failure is missing adapters/evaluator.

- [ ] **Step 2: Implement the injectable standard-library transport and provider adapters**

The transport must not print request headers or response bodies. Safe provider traces may retain status, object type, returned model, finish reason, content/reasoning presence and lengths, tool-call presence, usage, request ID when safe, latency, and controlled error class. Raw content is parsed in memory and then discarded.

- [ ] **Step 3: Implement the generic evaluator and run focused tests**

Run `python -m pytest -q tests/test_judge_providers.py tests/test_judge_evaluator.py`; expected: PASS.

### Task 4: Add deterministic pilot manifest and resumable execution

**Files:**
- Create: `src/evalops/pilot/models.py`
- Create: `src/evalops/pilot/sampling.py`
- Create: `src/evalops/pilot/execution.py`
- Create: `src/evalops/pilot/__init__.py`
- Test: `tests/test_phase5a_sampling.py`
- Test: `tests/test_phase5a_execution.py`

**Interfaces:**
- `build_pilot_manifest(dataset, seed=20260825, target_per_stratum=20)` returns metadata-only `PilotManifest` and never serializes source/response text.
- `build_consistency_manifest(manifest, seed=20260826, per_stratum=2)` returns 12 IDs when all six strata are available.
- `PilotStateStore` atomically loads/upserts ignored JSON state and skips successful provider/example pairs.
- `RequestBudget(max_requests=300)` reserves every actual request and rejects the 301st.
- `run_provider_pilot(manifest, examples, providers, state_store, budget)` evaluates providers sequentially and leaves missing/failed calls separate from negative labels.

- [ ] **Step 1: Write failing sampling and execution tests**

Tests must prove:

```python
def test_sampling_creates_six_strata_and_120_ids_without_replacement(): ...
def test_sampling_is_deterministic_for_seed_20260825(): ...
def test_manifest_does_not_contain_source_or_response_text(): ...
def test_consistency_sampling_creates_two_per_stratum(): ...
def test_successful_provider_example_is_skipped_on_resume(): ...
def test_failed_provider_example_is_retried_only_when_allowed(): ...
def test_429_and_5xx_retry_but_401_and_402_do_not(): ...
def test_request_budget_rejects_requests_over_300(): ...
def test_provider_id_sets_are_enforced_before_comparison(): ...
```

Run the focused tests; expected failure is missing pilot modules.

- [ ] **Step 2: Implement deterministic sampling, atomic state, bounded retries, and budget accounting**

Use sorted candidate IDs plus `random.Random(seed).sample`, filter official test/good rows, derive human labels through `AnnotationPolicy.STRICT_GROUNDEDNESS`, and write state using a temporary sibling file followed by `Path.replace`.

- [ ] **Step 3: Run focused tests and inspect the synthetic manifest**

Run `python -m pytest -q tests/test_phase5a_sampling.py tests/test_phase5a_execution.py`; expected: PASS.

### Task 5: Add pilot metrics, baseline comparisons, consistency analysis, and orchestration

**Files:**
- Create: `src/evalops/pilot/analysis.py`
- Create: `scripts/run_phase5a_pilot.py`
- Create: `tests/test_phase5a_analysis.py`
- Create: `tests/test_phase5a_script_safety.py`

**Interfaces:**
- `summarize_provider_records(records, ground_truth, metadata)` reuses `evaluate_hallucination_predictions` and returns confusion matrix, precision, recall, F1, accuracy, balanced accuracy, specificity, FPR, FNR, task/human-label slices, parse/schema/API rates, and client-observed latency/token summaries.
- `compare_pilot_predictions(ground_truth, left, right)` returns generic paired correctness, McNemar, and evaluator transition fields including HHEM/heuristic fixed/missed counts.
- `build_multi_evaluator_analysis` classifies the requested five-way correctness categories without majority voting.
- `summarize_consistency` computes pairwise three-run label agreement, unanimous agreement, disagreements, and confidence mean/min/max/range; run #1 remains primary.
- `scripts/run_phase5a_pilot.py` supports `--sample-only`, `--preflight`, `--run`, and `--consistency`; it loads ignored official RAGTruth, existing heuristic/HHEM artifacts, and only Gemini/Groq adapters.

- [ ] **Step 1: Write failing analysis and safety tests**

Tests must prove identical-ID enforcement, missing-result accounting, required metric keys, baseline restriction to pilot IDs, all requested pairwise transition fields, consistency math, and that the script never accepts human labels as provider prompt input.

- [ ] **Step 2: Implement aggregate analysis and safe artifact serialization**

Aggregate output goes to ignored `reports/phase5a-pilot-v1.json`; detailed state goes to ignored `reports/phase5a-pilot-state.json`. Neither stores source context, AI response, raw provider JSON, authorization headers, or reasoning text.

- [ ] **Step 3: Implement the orchestration script and run offline sample-only tests**

The script must estimate 242 requests before consistency (2 preflights + 240 base), refuse a run that could exceed 300, run providers sequentially, and refuse to compare differing ID sets. It must not import or invoke HHEM inference.

### Task 6: Add Phase 5A documentation and provider capability metadata

**Files:**
- Create: `docs/llm-judge-pilot.md`
- Modify: `README.md` with a concise Phase 5A reference only
- Create: `datasets/manifests/ragtruth-llm-judge-pilot-v1.json` after deterministic sample generation

**Interfaces:**
- Documentation defines human labels as ground truth, strict-groundedness semantics, balanced non-representative pilot interpretation, frozen prompt/schema, leakage prevention, provider provenance, consistency, quota limits, baseline comparison, and Phase 5B gate.
- The tracked manifest contains IDs/task types/human labels/seed/strata/dataset revision only; no source or response text.

- [ ] **Step 1: Write documentation tests or validation checks**

Assert that the document names the prompt version, schema version, strict-groundedness policy, 120-example balanced pilot, non-representative limitation, and no-human-label-leakage rule.

- [ ] **Step 2: Add concise documentation and metadata manifest support**

Do not add pilot result claims before the real run completes. Keep existing Phase 1–4 result documents unchanged.

### Task 7: Freeze and commit Phase 5A source before external calls

**Files:** all Phase 5A source/tests/docs/plan files from Tasks 2–6.

- [ ] **Step 1: Run all offline gates and secret scan**

```text
python -m pytest -q
python -m ruff check . --no-cache
python -m ruff format --check .
python -m mypy src
git diff --check
python <local-secret-scan-script> <repo-root> <provider-smoke-script> <provider-smoke-setup-script>
```

- [ ] **Step 2: Review the diff for secrets, source-text leakage, and untouched Phase 1–4 artifacts**

Use `git diff --stat`, `git diff --check`, `rg` for credential/header patterns, and inspect the tracked manifest only for safe metadata.

- [ ] **Step 3: Create the source commit**

```text
git add src tests scripts docs datasets/manifests/ragtruth-llm-judge-pilot-v1.json README.md
git commit -m "feat: add LLM judge pilot framework"
```

Record `git rev-parse HEAD` as the clean source SHA before any real Gemini/Groq request.

### Task 8: Execute bounded preflight, pilot, consistency, and final aggregate validation

**Files:**
- Ignored: `reports/phase5a-pilot-state.json`
- Ignored: `reports/phase5a-pilot-v1.json`
- Ignored: `reports/phase5a-pilot-consistency.json`

- [ ] **Step 1: Re-check official provider documentation and run two synthetic structured preflights**

Use the official Gemini structured-output path and Groq strict JSON Schema path. Count both requests against the 300 ceiling. Stop before the pilot if either provider cannot return a schema-valid decision after bounded fallback.

- [ ] **Step 2: Run the same 120 manifest IDs sequentially for Gemini and Groq**

Use temperature 0, fixed prompt/schema hashes, low Groq reasoning configuration, bounded transient retries, atomic state, and no provider concurrency. Do not include human labels or spans in prompts.

- [ ] **Step 3: Run the 12-example consistency subset only if the base run is complete and budget permits**

Perform two additional evaluations per provider/example, never replacing the primary run #1 prediction. If quota/rate safety blocks it, write `CONSISTENCY_RUN=QUOTA_BLOCKED`.

- [ ] **Step 4: Generate aggregate comparisons and rerun offline gates**

Compare both judges against human labels, HHEM, and heuristic on the exact pilot IDs; generate false-negative/false-positive transition and five-way correctness categories; then rerun tests, lint, format, mypy, diff-check, secret scan, and Git status.

- [ ] **Step 5: Select a Phase 5B recommendation without starting Phase 5B**

Rank Gemini/Groq using F1, balanced accuracy, recall, FPR, parse/schema reliability, consistency, latency, token usage, quota practicality, and provenance. Report `COMPLETE` only when all required gates pass; otherwise use `COMPLETE_WITH_LIMITATIONS` with exact blockers.

