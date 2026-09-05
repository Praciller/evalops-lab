# EvalOps Lab Context

## Purpose

EvalOps Lab is a testing-first Python framework for reproducible AI reliability evaluation. Its initial domain is Thai/English retrieval and chatbot evaluation. The repository is an evaluation product and evidence generator; it is not a chatbot runtime.

## Domain glossary

- **Human label**: an authored relevance, groundedness, or failure annotation used as evaluation ground truth.
- **System output**: a retriever ranking or generated response produced by the evaluated system.
- **Evaluation result**: a structured result produced by deterministic metrics or a future evaluator adapter.
- **Benchmark result**: a result tied to a named dataset protocol, revision, language, and split.
- **Synthetic fixture**: a small repository-controlled fixture for integration behavior; it is not an official benchmark score.
- **Evidence artifact**: a versioned, sanitized publication object containing only approved metadata, aggregate metrics, safe record references, and bounded failure summaries.
- **Public claim**: a statement supported by an evidence artifact and bounded by its verification status, data kind, and claim scope.
- **Evidence Dashboard**: a future static, read-only presentation of approved evidence artifacts.

## Required separations

Human labels, system outputs, evaluator outputs, and public evidence remain distinct. Dataset provenance and claim scope are explicit. A successful local fixture run does not become a production or official benchmark claim by being exported.

## Public evidence boundary

The public boundary is a static artifact pipeline: approved internal results are transformed into versioned, sanitized JSON, then consumed by a future frontend. Public artifacts do not execute evaluation, call providers, expose credentials, publish raw corpus text, or discover arbitrary files. The Python evaluation core remains the source of truth.
