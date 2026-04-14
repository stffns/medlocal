# MedLocal - Project Constitution

**Offline Clinical Consultation & Training for Community Health Workers**

*Kaggle Gemma 4 Good Hackathon 2026*
*Jayson Steffens - Independent Researcher & QA Lead*
*April 2026*

---

## 1. Vision

MedLocal is an offline medical consultation and training system designed for community health workers operating in areas without internet connectivity. It brings clinical guidelines, medication references, and adaptive learning to any device - from smartphones to laptops - without requiring cloud services, API subscriptions, or continuous connectivity.

**Core principle:** No internet? No problem. Clinical knowledge should be as accessible as the device in your pocket.

37% of the global population still lacks internet access. Community health workers serving rural populations in Africa, Asia, and Latin America operate in precisely these conditions. Current AI-powered medical tools require cloud connectivity, making them useless where they are needed most. MedLocal eliminates this barrier entirely.

---

## 2. The Problem

Community health workers face three interconnected challenges:

1. **Access to knowledge:** Clinical guidelines exist but are trapped in PDF documents, printed manuals, or cloud platforms. When a worker faces a patient with unfamiliar symptoms, they cannot search 800 pages of WHO protocols in real time.

2. **Continuous training:** Medical protocols change. Workers need ongoing education, but training sessions are infrequent and retention decays rapidly without reinforcement. A worker trained on neonatal protocols six months ago may not remember critical steps when facing an emergency.

3. **Visual identification:** A worker encounters an unfamiliar skin condition, an unlabeled medication, or a deteriorated printed guideline. Without connectivity, they cannot search for visual references or scan documents for digitization.

---

## 3. The Solution

MedLocal is a unified system with five operational modes, all running entirely offline on a single device.

### 3.1 Consultation Mode

The health worker asks a clinical question in natural language. The system retrieves relevant protocols from the knowledge base and generates a structured response with assessment, recommended actions, warning signs requiring referral, and source attribution. Every answer is traceable to a specific WHO guideline or local protocol.

### 3.2 Chat / Explain Mode

An interactive conversation with the clinical knowledge base. The worker can ask follow-up questions, request explanations of *why* a protocol recommends a specific action, and explore topics in depth. This mode builds understanding, not just compliance.

### 3.3 Training Mode (Recall)

Adaptive spaced repetition powered by FSRS (Free Spaced Repetition Scheduler). The system generates scenario-based questions from clinical guidelines, evaluates the worker's answers, and schedules reviews based on performance. Material the worker struggles with is repeated more frequently; mastered material fades to longer intervals. This is scientifically validated learning methodology applied to medical education.

### 3.4 Vision Mode

The worker takes a photo with their phone's camera. Three workflows are supported:

- **Visual triage:** Photo of a wound, rash, or lesion. Gemma 4 (the same on-device model used for text consultations) describes the visual findings in clinical terms, which are used to retrieve relevant treatment protocols.
- **Medication identification:** Photo of a medicine or its packaging. The system identifies the drug, dosage, and looks up interactions and contraindications in the formulary.
- **Document scanning:** Photo of a printed medical document. Text is extracted and automatically ingested into the local knowledge base, digitizing paper-based knowledge.

### 3.5 Admin Mode

Local administrators (supervisors, NGO coordinators, health ministry staff) can add country-specific protocols, regional guidelines, and local formularies without modifying the validated core knowledge base.

---

## 4. Technical Architecture

### 4.1 Dual-Profile Knowledge Base

The knowledge base uses a dual-profile architecture ensuring medical safety:

| Profile | Description |
|---------|-------------|
| **Core** (read-only) | Pre-built with WHO guidelines, essential medicines list, clinical protocols. Distributed with the application. Cannot be modified by end users. Updated only via official releases. |
| **Local** (editable) | Country-specific protocols, regional guidelines, scanned documents. Managed by local administrators. Can be added to or removed without affecting core. |

Search queries both profiles transparently via federated retrieval. Results compete on relevance regardless of source - the best answer wins whether it comes from a WHO guideline or a national protocol.

### 4.2 Technology Stack

| Component | Role & Details |
|-----------|---------------|
| **vstash** | Hybrid retrieval engine (vector + keyword via Reciprocal Rank Fusion). Benchmarked: NDCG@10 = 0.7255 on BEIR SciFact, surpassing ColBERTv2 (+4.7%) and BM25 (+9.1%). Single SQLite file, 4.7ms latency on 3.6K docs. |
| **Gemma 4 (E2B and E4B)** | On-device multimodal LLMs by Google, released 2026-03-31. Apache 2.0 license. Supports text, image, audio. Gemma 4 E2B (~2 GB RAM at Q4_K_S quantisation) is the phone-class design point; Gemma 4 E4B (~5 GB RAM) is the laptop / tablet option. Both score 101/101 on MedLocal's 101-case adversarial clinical benchmark with the MedLocal pipeline and the LLM-as-judge evaluator - the on-device pipeline is the determinant of clinical safety across the 2B-4B range, not the parameter count. See the hackathon writeup §5.5 for the full trade-off comparison between the two configurations. |
| **py-fsrs (FSRS-6)** | Spaced repetition scheduling algorithm. Determines optimal review intervals based on learner performance. MIT license. |
| **FastAPI** | Lightweight web server for the mobile-first interface. Serves locally on the device - no external connectivity. |
| **SQLite** | All data stored in portable single files. Core knowledge base, local additions, training progress, and review history. |

### 4.3 Retrieval Performance

| Dataset | Docs | NDCG@10 | vs BM25 | vs ColBERTv2 | Latency |
|---------|------|---------|---------|--------------|---------|
| SciFact | 5K | 0.7255 | +9.1% | +4.7% | 12.7ms |
| SciDocs | 25K | 0.1911 | +21.0% | +24.1% | 35.6ms |
| NFCorpus | 3.6K | 0.3525 | +8.5% | +2.5% | 4.7ms |
| FiQA | 57K | 0.3789 | +60.6% | +6.4% | 81.8ms |

### 4.4 Head-to-Head vs Chroma

| Dataset | vstash | Chroma | Delta |
|---------|--------|--------|-------|
| SciFact | 0.7255 | 0.7201 | +0.7% |
| NFCorpus | 0.3525 | 0.3379 | +4.3% |
| SciDocs | 0.1911 | 0.1968 | -2.9% |

---

## 5. Hackathon Objective

**Primary goal:** A working prototype that a community health worker can use on their phone, without internet, to consult clinical guidelines, identify medications from photos, and learn protocols through spaced repetition.

The project addresses all three official Kaggle Gemma 4 Good Hackathon impact tracks simultaneously:

- **Health & Sciences:** Clinical decision support with protocol-backed answers, structured triage, dosage cross-check against source protocols, and visual medication identification - grounded in published WHO and MSF guidelines.
- **Global Resilience:** Offline-first architecture for health workers in crisis zones, rural clinics, and communities with intermittent or no connectivity. The full pipeline (retrieval, reasoning, vision, training) runs on a single device without cloud dependency.
- **Digital Equity & Inclusivity:** 37% of the world lacks reliable internet; MedLocal targets exactly that gap. Runs on phone-class hardware with a 2-billion-parameter model (Gemma 4 E2B), supports 7 languages (ES, FR, SW, HA, PT, AR, HI, AM), and is Apache 2.0 so health ministries and NGOs can deploy and adapt it without license friction.

---

## 6. Potential Impact

There are approximately 5 million community health workers worldwide, serving over 1 billion people in low-resource settings.

1. **Reducing diagnostic errors:** Protocol-backed guidance at the point of care.
2. **Improving knowledge retention:** Spaced repetition for long-term learning.
3. **Digitizing local knowledge:** Document scanning preserves paper-based protocols.

---

## 7. Deliverables

1. Open-source Python package (Apache 2.0) installable via pip.
2. Pre-built core knowledge base with WHO essential guidelines.
3. Mobile-first web interface accessible via any browser.
4. CLI for advanced users and system administrators.
5. Kaggle notebook demonstrating the complete workflow.
6. Reproducible benchmarks comparing retrieval performance against published baselines.

---

> *"Works without internet. Fits in your pocket. Backed by benchmarks."*
