# MedLocal

**Offline-first clinical consultation and training for community health workers.**

Built for the [Kaggle Gemma 4 Good Hackathon 2026](https://www.kaggle.com/competitions/gemma-3n-impact-challenge).
Tracks: Health · Education · Accessibility.

> Works without internet. Fits in your pocket. Every answer is traceable to a
> WHO or MSF protocol, no fine-tuning, no hallucinated dosing, no cloud
> dependency. Validated against a 100-case clinical benchmark.

## What it does

A community health worker (CHW) asks a question, in any language, on any
device, without internet. MedLocal retrieves the relevant published clinical
protocol and presents a structured response with assessment, numbered
actions, dosages, danger signs, and a source citation.

- **68 structured WHO/MSF protocols** covering pediatrics, maternal health,
  emergencies, infectious diseases, NCDs, toxicology, and heavy-metal
  poisoning
- **Zero-hallucination architecture** — vstash retrieves, the model formats.
  If a fact is not in a protocol it does not appear in the answer.
- **Pre-flight translator** — one structured LLM call classifies scope and
  emergency status before retrieval, in any language, with no hardcoded
  keywords
- **Safety layer** — regex emergency fast path, dosage cross-check against
  source protocols, confidence scoring, optional grounding verification,
  audit log
- **Spaced repetition training** — 201 cards across 15 clinical topics
  (FSRS-6) with a teacher/judge double-grounding loop
- **Vision mode** — photo of wound, medication package, or scanned document,
  combined with the CHW's text context
- **Multilingual** — answers in the language of the question (verified for
  ES, FR, SW, HA, PT, AR, HI, AM)
- **`medlocal protocol` skill** — author, validate, and audit clinical
  protocols with the same rigor as the rest of the pipeline

## Why offline matters

37% of the world has no reliable internet. The community health workers
who would benefit most from clinical AI live and work in exactly that
gap. Cloud-only tools are useless where they are most needed.

MedLocal runs the full pipeline — retrieval, reasoning, vision, training
— on a single device. The build-time cost (downloading and chunking
~70 protocols, generating training cards with a teacher model) happens
once with internet. The runtime cost is zero.

## Quick start

```bash
git clone https://github.com/stffns/medlocal.git
cd medlocal
pip install -e ".[dev]"

# Start LM Studio with gemma-4-e4b-it loaded at n_ctx >= 8192
# Then ingest the bundled protocols and start the server
medlocal ingest data/core/protocols --profile core
medlocal serve

# Open http://localhost:8765 in any browser, on any device on the LAN.
```

CLI examples:

```bash
# One-shot consultation
medlocal consult-cmd "Niño de 2 meses con fiebre, ¿qué le doy?"

# Validate or audit clinical protocols
medlocal protocol validate data/core/protocols/measles-who.md
medlocal protocol audit

# Author a new protocol with retrieval reachability checks
medlocal protocol new drafts/new-protocol.md \
  -q "Lay-language CHW query 1" \
  -q "Adversarial reword 2"

# Direct knowledge-base search
medlocal search "pesticide poisoning organophosphate"
```

## Architecture in one diagram


![alt text](image.png)

The deep dive lives in [`docs/PIPELINE.md`](docs/PIPELINE.md), including
the four compounding retrieval bugs we fixed in the organophosphate
poisoning case and the upstream vstash improvements that came out of
the debugging.

## Benchmarks (gemma-4-e4b-it @ n_ctx ≥ 8192)

| Suite                    | Cases | Status                                |
|--------------------------|-------|---------------------------------------|
| Smoke (`smoke_critical`) | 21    | **21 / 21 PASS** (~5 min)             |
| Comprehensive            | 100   | **100 / 100 PASS** (~47 min, 28 s/q)  |

14 categories, **all at 100 %**: safety · emergency · clinical · dosage
· hallucination · protocol · contraindication · multilingual ·
emergency_skip · age_safety · rabies · anaphylaxis · cross-lingual ·
heavy_metals.

vstash retrieval (the engine underneath) holds NDCG@10 = 0.7255 on
SciFact, +9.1 % over BM25 and +4.7 % over ColBERTv2 — see ARCHITECTURE.md
for the BEIR table.

## Two principles that explain every design decision

1. **Knowledge lives in documents, not in model weights.** No
   fine-tuning. No memorised answers. The LLM formats and selects;
   vstash retrieves; the protocols are the source of truth. If a fact
   is not in a protocol it should not appear in the answer.
2. **Double grounding on everything that validates.** The judge
   compares both the model answer and the expected answer against the
   source protocol chunk. Either link failing drops confidence to LOW
   and the safety layer raises a "verify with supervisor" banner.

These two rules govern when to refuse, when to defer, and what to put
in front of a CHW at 2 a.m. in a clinic with no signal.

## Documentation

- [`docs/PIPELINE.md`](docs/PIPELINE.md) — full pipeline deep dive,
  retrieval internals, debugging playbook, hackathon narrative source
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system overview,
  benchmarks, lessons learned
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — current state and next steps
- [`docs/SOURCES.md`](docs/SOURCES.md) — source-document traceability
- [`docs/constitution.md`](docs/constitution.md) — vision and principles
- [`CHANGELOG.md`](CHANGELOG.md) — release history (keep-a-changelog)
- [`CLAUDE.md`](CLAUDE.md) — instructions for the agent that builds with this repo

## License

Apache 2.0 — Jayson Steffens, 2026.
