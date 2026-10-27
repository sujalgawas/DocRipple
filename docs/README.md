# DocRipple documentation

This directory explains how DocRipple is designed, how a change moves through the system, and how to run it safely.

## Read in this order

1. [Architecture](architecture.md) - the system view and the decisions behind the pipeline.
2. [Backend workflow](backend.md) - the FastAPI services and Stage 0-5 execution path.
3. [API reference](api.md) - routes used by GitHub, the frontend, and operators.
4. [Data model](data-model.md) - SQLite tables and the repository memory graph.
5. [Frontend](frontend.md) - dashboard routes, API client, and local configuration.
6. [Deployment and operations](deployment.md) - Render, Vercel, webhooks, health checks, and limits.
7. [File structure](filestructure.md) - where to make a change.

## Product vocabulary

- **DocStyleSkill:** Repository-specific writing rules mined during onboarding.
- **RepoMemoryMap:** A graph of modules, files, symbols, and documentation sections.
- **ChangeReport:** Deterministic description of symbols changed by a commit.
- **DriftReport:** Deterministic description of documentation sections affected by those symbols.
- **Evidence table:** The audit trail included in every generated pull request.
- **Delivery ID:** GitHub's unique webhook ID used for idempotency.

## A note on design intent

DocRipple is deliberately conservative. The analyzer and drift engine are deterministic so the system can reject irrelevant changes before using a model. The model is used for language work, not for deciding whether arbitrary code is related to arbitrary documentation. Every generated update is verified and published through the same reviewable Git workflow a human would use.
