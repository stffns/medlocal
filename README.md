# MedLocal

**Offline-first clinical consultation and training for community health workers.**

Built for the [Kaggle Gemma 4 Good Hackathon 2026](https://www.kaggle.com/competitions/gemma-4-good-hackathon).
Impact tracks: Health & Sciences · Global Resilience · Digital Equity & Inclusivity.

> Works without internet. Fits in your pocket. Every answer is traceable to a
> WHO or MSF protocol, no fine-tuning, no hallucinated dosing, no cloud
> dependency. Validated against a 101-case clinical benchmark.

> ⚠️ **MEDICAL DISCLAIMER** — MedLocal is a research and educational
> demonstration of retrieval-augmented clinical reference tooling. It
> is **NOT a medical device**, is **NOT FDA, EMA, or otherwise
> regulatory-approved**, and is **NOT intended for clinical
> decision-making without supervision by a qualified healthcare
> professional**. The information retrieved is sourced from published
> WHO and MSF protocols for reference and educational purposes only
> and does not constitute medical advice. MedLocal does not replace
> clinical judgement, physical examination, laboratory testing, or
> consultation with a qualified healthcare provider. Any use in a
> live patient-care context is at the sole discretion and risk of the
> healthcare professional or organization deploying it. The author
> assumes no liability for any decisions made on the basis of this
> software. See [`LICENSE`](LICENSE) for the full disclaimer of
> warranty and limitation of liability.

## What it does

A community health worker (CHW) asks a question, in any language, on any
device, without internet. MedLocal retrieves the relevant published clinical
protocol and presents a structured response with assessment, numbered
actions, dosages, danger signs, and a source citation.

- **69 structured WHO/MSF protocols** covering pediatrics, maternal health,
  emergencies, infectious diseases, NCDs, toxicology, heavy-metal
  poisoning, and child protection / safeguarding
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
73 protocols, generating training cards with a teacher model) happens
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

## Dependencies

MedLocal is built on top of the following open-source projects,
installed as external dependencies from PyPI. **None of these are
bundled into this repository** — all are procured via `pip install`
at setup time. Under the Kaggle Gemma 4 Good Hackathon rules
(Section 3.6.c), only OSI-approved open-source licenses that allow
commercial use are used.

| Package | Version | License | Role |
|---|---|---|---|
| [**vstash**](https://github.com/stffns/vstash) | ≥ 0.26.0 | MIT | Local hybrid retrieval substrate (vector + FTS5 + adaptive RRF) — a separate open-source project, used here as a library dependency in the same way as numpy or fastembed |
| [fastembed](https://github.com/qdrant/fastembed) | — | Apache 2.0 | ONNX embedding model runtime *(transitive via vstash)* |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | — | Apache 2.0 | SQLite vector search extension *(transitive via vstash)* |
| [typer](https://github.com/fastapi/typer) | ≥ 0.9 | MIT | CLI framework |
| [rich](https://github.com/Textualize/rich) | ≥ 13 | MIT | Terminal formatting |
| [pydantic](https://github.com/pydantic/pydantic) | ≥ 2.0 | MIT | Data models |
| [openai](https://github.com/openai/openai-python) | ≥ 1.0 | Apache 2.0 | OpenAI-compatible client (LM Studio / Ollama / OpenRouter) |
| [FastAPI](https://github.com/fastapi/fastapi) | ≥ 0.100 | MIT | HTTP server |
| [uvicorn](https://github.com/encode/uvicorn) | ≥ 0.20 | BSD-3 | ASGI runtime |
| [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) | ≥ 6.0 | MIT | Spaced repetition scheduler |

### Pretrained models and input data

The following **are not bundled** with this repository. Under Section
2.5 of the hackathon rules, pretrained models and input data with
independent licenses do not need to be re-licensed as part of any
winner license grant.

- **Gemma 4 E2B / E4B** (Apache 2.0, released by Google on 2026-03-31)
  — loaded at runtime by LM Studio, Ollama, or llama.cpp. The user
  procures the model file independently from
  [ai.google.dev/gemma](https://ai.google.dev/gemma) or
  [huggingface.co/google/gemma-4](https://huggingface.co/google).
- **Embedding models** — `BAAI/bge-small-en-v1.5` and
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` are
  downloaded on first use by fastembed from HuggingFace and cached
  locally.
- **Clinical content sources** — WHO, MSF, and Hesperian publications
  are cited in [`docs/SOURCES.md`](docs/SOURCES.md). MedLocal does
  **not** redistribute source documents; it redistributes only
  original protocol documents authored by the MedLocal project that
  describe the same factual medical content using original wording.
  See [`docs/SOURCES.md`](docs/SOURCES.md) for the originality and
  copyright disclosure.

## Architecture in one diagram

![MedLocal build-time ingest pipeline and offline runtime consult pipeline — WHO/MSF protocols flow through vstash into a single core.db, then the CHW question is classified by preflight, retrieved via the 4-pass FTS-boosted pipeline, and answered with schema-enforced structured output plus a safety layer.](image.png)

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

## License

MedLocal is licensed under the **Apache License 2.0**. See the
[`LICENSE`](LICENSE) file for the full text.

Copyright © 2026 Jayson Steffens.

### Hackathon winner license obligation

This project is an entry in the
[Kaggle Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon).
Per Section 2.5 of the competition rules, if MedLocal is awarded a
prize, the winning Submission and the source code used to generate
the Submission will additionally be licensed under
[**CC-BY 4.0**](https://creativecommons.org/licenses/by/4.0/) as an
additional license alongside Apache 2.0. This additional license
applies only to the snapshot of MedLocal as submitted to the
hackathon. Pretrained models and input data with incompatible
licenses (e.g., Gemma 4 weights under Apache 2.0, cited WHO/MSF
publications) are explicitly carved out by Section 2.5 of the rules
and are not subject to the winner license. Dependencies installed
from PyPI retain their original licenses — see the Dependencies
section above. Future development of MedLocal after the hackathon
submission remains under Apache 2.0 at the author's sole discretion.

### Content sources and originality

Clinical protocol documents in `data/core/protocols/` are **original
works** authored by the MedLocal project, based on **factual
medical information** from published WHO, MSF, and Hesperian
guidelines cited in [`docs/SOURCES.md`](docs/SOURCES.md). Factual
medical information (diagnostic criteria, drug dosages, clinical
thresholds, epidemiological data) is not subject to copyright
protection under U.S. law (17 U.S.C. § 102(b)) or most
international jurisdictions. The specific wording, structure,
clinical decision logic, and cross-references of the protocol
documents in this repository are original creative expression by
the author and are licensed under Apache 2.0 along with the rest
of the MedLocal codebase. No portion of any cited source document
is reproduced verbatim. See [`docs/SOURCES.md`](docs/SOURCES.md)
for the full originality and attribution disclosure.

### Medical disclaimer

MedLocal is a research and educational tool and is NOT a medical
device. See the disclaimer at the top of this README and the
warranty and liability sections of the [`LICENSE`](LICENSE) file
for the full terms. Use in any clinical setting is at the sole
discretion and risk of the deploying healthcare professional or
organization.

## Acknowledgments

Development of MedLocal and its retrieval engine vstash was assisted
by Claude (Anthropic) for code generation, refactoring, and
documentation, and by a second AI model used in a structured
code-review loop during the hardening phase. All architectural
decisions, algorithm choices, clinical protocol sourcing and
validation against WHO, MSF, UNICEF, and AAP publications, retrieval
benchmark design, safety-layer specification, and the evaluation
methodology were authored and verified by the human author. Every
clinical protocol in `data/core/protocols/` was cross-checked against
its cited source before inclusion. Any clinical error in this system
is the author's responsibility alone.
