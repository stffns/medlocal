# MedLocal

Offline clinical consultation & training for community health workers.

Works without internet. Fits in your pocket. Backed by benchmarks.

## Quick Start

```bash
pip install -e ".[dev]"
medlocal serve
# Open http://localhost:8765
```

## What It Does

A community health worker asks a question — in any language, on any device, without internet. MedLocal retrieves the relevant WHO clinical protocol and presents a structured, actionable response with dosages, steps, danger signs, and source attribution.

- **54 clinical protocols** covering pediatrics, maternal health, infectious diseases, NCDs, emergencies
- **Zero hallucination architecture** — every answer traceable to a WHO/MSF published guideline
- **Safety layer** — emergency detection, dosage verification, allergy checks, audit logging
- **Spaced repetition training** — 201 cards across 15 clinical topics
- **Vision mode** — photo of wound, medication, or document for analysis
- **Multilingual** — responds in the language of the question

## Architecture

```
Teacher (Gemini, offline)          On-Device (Gemma 4 E4B/E2B)
  Reads WHO protocols              CHW asks question
  Generates Q&A index              vstash retrieves protocols + index
  Generates training cards         Gemma formats response
  One-time process                 100% offline, no API cost
```

## License

Apache 2.0
