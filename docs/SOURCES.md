# MedLocal — Source Documents

## Copyright, originality, and license compatibility

The clinical protocol documents in `data/core/protocols/` are
**original works** authored by the MedLocal project, based on
**factual medical information** from the publicly available
guidelines cited in this document. Factual medical information —
diagnostic criteria, drug dosages, clinical thresholds, dose
schedules, epidemiological data, and similar facts — is not
subject to copyright protection under U.S. law
([17 U.S.C. § 102(b)](https://www.law.cornell.edu/uscode/text/17/102))
or most international jurisdictions, which protect only the
specific expression of ideas and not the underlying facts or
methods of operation.

The specific wording, structure, clinical decision logic,
internal cross-references, multilingual aliases, and lay-language
rewrites of the protocol documents in this repository are
**original creative expression** by the MedLocal author, written
to be readable by community health workers with limited formal
medical training. They are licensed under **Apache 2.0** along
with the rest of the MedLocal codebase (see [`../LICENSE`](../LICENSE)).

**No portion of any cited source document is reproduced verbatim
in this repository.** Where a cited WHO or MSF publication
provided structural inspiration (for example, the IMCI decision
trees or the WHO Basic Emergency Care triage flow), the MedLocal
protocols implement the same underlying clinical logic using
independent wording written from scratch by the MedLocal author
after reviewing the source.

### License compatibility note

Some cited WHO publications are released under
[CC-BY-NC-SA 3.0 IGO](https://creativecommons.org/licenses/by-nc-sa/3.0/igo/),
which restricts commercial redistribution. This restriction does
**not** apply to MedLocal because MedLocal does not redistribute
any CC-BY-NC-SA content. MedLocal redistributes only original
documents authored by the MedLocal project that describe the same
factual medical content using different wording. This is the same
relationship a textbook, review article, or encyclopedia entry
has with its cited primary sources — the author draws on them for
facts and cites them for attribution, but does not reproduce their
expression.

MedLocal does not download, bundle, or redistribute source PDFs.
The "Downloaded PDFs" referenced below are used at build time by
the author for research and are not part of the shipped
repository or the PyPI distribution. Users who wish to consult
the original sources directly are linked to the publisher URLs
for each source.

### Attribution practice

Every protocol document in `data/core/protocols/` includes an
attribution line in its header identifying the upstream source
(WHO publication, MSF guideline, Hesperian book, etc.) that
informed the factual content. This attribution is a matter of
good scientific practice and does not imply endorsement or
sponsorship by the cited organizations.

---

## Founding Principle: Total Traceability

> Every answer MedLocal generates MUST be traceable to an officially
> published document. If there is no verifiable source, the answer is
> not generated. The training Q&A pairs are validated against the
> original protocol via the judge's double-grounding loop.

### Traceability chain

```
LLM answer → vstash chunk → structured protocol → official source document
    ↑              ↑                  ↑                       ↑
Gemma 4 E4B    chunk_id        data/core/protocols/      verifiable URL
(formats only) (auditable)     (exact citation)          (downloadable)
```

### Anti-hallucination architecture

```
                    ┌─────────────────────────────────┐
                    │     core.db (read-only)          │
                    │   WHO / MSF / Hesperian          │
                    │   every chunk traceable to a     │
                    │   published source               │
                    └──────────┬──────────────────────┘
                               │ retrieval
                    ┌──────────▼──────────────────────┐
                    │   CONSULT PIPELINE                │
                    │   1. Multi-query retrieval        │
                    │      (4 passes, FTS-boosted)      │
                    │   2. Confidence scoring           │
                    │   3. LLM generation (schema)      │
                    │   4. Dosage cross-check           │
                    │   5. Grounding verification (opt) │
                    │   6. Audit log                    │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │   TRAINING PIPELINE              │
                    │   Q&A pair (teacher, offline)     │
                    │   + source protocol chunk         │
                    │   = judge double-grounding        │
                    └─────────────────────────────────┘
```

---

## Authoring rule (load-bearing — updated 2026-04-08)

The original `≤2000 chars per file` rule was wrong. The real rule
discovered by the `medlocal protocol audit` skill on 2026-04-08 is:

> **Use AT MOST ONE `##` header per protocol file. Prefer
> `**bold labels**` for sub-sections.**
>
> vstash splits at every markdown header before checking size, so a
> 1500-char file with five `##` headings produces 5 chunks while a
> 4000-char flat file with no `##` produces 1. Only one chunk per
> document reaches the LLM (`mmr_lambda=1.0`), so any content stuck in
> a "losing" chunk silently disappears from the answer.

The template is `data/core/protocols/poisoning-organophosphate-who.md`.
Validate every change with `medlocal protocol validate <path>` and
the whole corpus with `medlocal protocol audit` before release.

---

## Tier 1 — Primary Sources (WHO)

Official documents from the World Health Organization. Highest
authority level.

### Downloaded PDFs (used at build time, not committed to the repo)

| Document | Pages | URL |
|----------|-------|-----|
| Essential Medicines List 24th (2025) | 74 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/17642505-ecd3-4940-a691-4f1dfa0d835a/content) |
| IMCI Adaptation Guide | 10 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/mca-documents/child/imci-integrated-management-of-childhood-illness/adaptation-guide/who-shs-guideline_web_v28.pdf) |
| IMCI Assessment Booklet (2m–5yr) | 6 | [platform.who.int](https://platform.who.int/docs/default-source/mca-documents/policy-documents/operational-guidance/EGY-CH-59-01-OPERATIONALGUIDANCE-eng-IMCI-Assessment-Booklet-2m-5yrs.pdf) |
| Quality of Maternal/Newborn Care Standards | ~80 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/mca-documents/qoc/quality-of-care/standards-for-improving-quality-of-maternal-and-newborn-care-in-health-facilities_1a22426e-fdd0-42b4-95b2-4b5b9c590d76.pdf) |
| Postnatal Care Recommendations | ~60 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/a6696f52-fa0f-42fc-bedd-ebfc8725b65b/content) |
| Snakebite Management (2nd Ed) | 20 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/searo/india/health-topic-pdf/who-guidance-on-management-of-snakebites.pdf) |
| IMAI Acute Care | 121 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/a9ce216f-7f3b-411f-b06c-432b8322a8a5/content) |

### Live WHO fact sheets (referenced for the latest position)

| Topic | URL | Last verified |
|-------|-----|---------------|
| Lead poisoning | [who.int](https://www.who.int/news-room/fact-sheets/detail/lead-poisoning-and-health) | 2026-04-08 (sheet updated 2024-09-27) |
| Mercury and health | [who.int](https://www.who.int/news-room/fact-sheets/detail/mercury-and-health) | 2026-04-08 (2024 update) |
| Arsenic | [who.int](https://www.who.int/news-room/fact-sheets/detail/arsenic) | 2026-04-08 (2022 update) |

### High-priority pending sources

| Document | URL |
|----------|-----|
| IMCI Chart Booklet (full) | [who.int](https://www.who.int/publications/i/item/9789241506823) |
| IMAI District Clinician Manual Vol 1 | [apps.who.int](http://apps.who.int/iris/bitstream/10665/77751/1/9789241548281_Vol1_eng.pdf) |
| Pocket Book of Hospital Care for Children | [who.int](https://www.who.int/publications/i/item/978-92-4-154837-3) |
| WHO PEN (Essential NCD Interventions) | [who.int](https://www.who.int/publications/i/item/who-package-of-essential-noncommunicable-(pen)-disease-interventions-for-primary-health-care) |
| Consolidated HIV Guidelines (2021 + 2026 update) | [who.int](https://www.who.int/publications/i/item/9789240031593) |

---

## Tier 2 — MSF (Médecins Sans Frontières)

The single best practical source — written for exactly the field
context MedLocal targets.

| Document | Status | URL |
|----------|--------|-----|
| Essential Drugs Guide (663 pp) | ✅ downloaded | [medicalguidelines.msf.org](https://medicalguidelines.msf.org/sites/default/files/pdf/guideline-339-en.pdf) |
| Clinical Guidelines: Diagnosis and Treatment | pending | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |
| Obstetrics Guidelines | pending | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |
| Nutrition Guidelines | pending | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |

---

## Tier 3 — Hesperian Health Guides

Classic reference for community health workers. Creative Commons.

| Document | Status | URL |
|----------|--------|-----|
| Where There Is No Doctor (2025) | partial | [hesperian.org](https://hesperian.org/wp-content/uploads/pdf/en_wtnd_2025/en_wtnd_2025_fm.pdf) |
| Where There Is No Doctor (2011 full) | pending | [frankshospitalworkshop.com](http://www.frankshospitalworkshop.com/organisation/biomed_documents/Where%20there%20is%20no%20Doctor%20-%20David%20Werner.pdf) |
| Where Women Have No Doctor | pending | [hesperian.org](https://hesperian.org/books-and-resources/) |

---

## Tier 4 — Regional Sources (`local` profile)

These go into the editable `local` profile, not the read-only `core`.

| Region | Source | URL |
|--------|--------|-----|
| Kenya | Kenya Clinical Guidelines | [apps.who.int](https://apps.who.int/iris/) |
| South Africa | Standard Treatment Guidelines | [health.gov.za](https://www.health.gov.za/) |
| India | National Health Mission | [nhm.gov.in](https://nhm.gov.in/) |
| Colombia | Guías MinSalud | [minsalud.gov.co](https://www.minsalud.gov.co/) |
| Brazil | Protocolos do SUS | [saude.gov.br](https://www.gov.br/saude/) |

---

## Structured Protocols — Current State (73 files, all single-chunk)

As of 2026-04-09 every protocol in `data/core/protocols/` produces
exactly one vstash chunk (verified by `medlocal protocol audit`).
Grouped by clinical domain for readability.

### Maternal & Newborn

| File | Source |
|------|--------|
| `pregnancy-antenatal-who.md` | WHO Antenatal Care Recommendations |
| `preeclampsia-who.md` | WHO Pre-eclampsia/Eclampsia Guidelines |
| `hypertension-pregnancy-who.md` | WHO PEN / WHO Pregnancy Hypertension |
| `gestational-diabetes-who.md` | WHO/IADPSG GDM Diagnosis & Management |
| `malaria-pregnancy-who.md` | WHO Malaria in Pregnancy |
| `childbirth-emergency-who.md` | WHO Managing Complications in Pregnancy |
| `breastfeeding-who.md` | WHO/UNICEF Breastfeeding Guidance |
| `newborn-care-who.md` | WHO Newborn Health Recommendations |
| `newborn-resuscitation-who.md` | WHO/HBB Newborn Resuscitation |
| `family-planning-who.md` | WHO MEC for Contraceptives |

### Pediatrics — IMCI core

| File | Source |
|------|--------|
| `pneumonia-imci.md` | WHO/UNICEF IMCI |
| `diarrhea-imci.md` | WHO/UNICEF IMCI |
| `fever-assessment-imci.md` | WHO/UNICEF IMCI |
| `ear-infections-imci.md` | WHO/UNICEF IMCI |
| `malnutrition-adults-who.md` | WHO Acute Malnutrition Management |
| `nutrition-who.md` | WHO Acute Malnutrition Management |
| `deworming-who.md` | WHO Deworming Guidelines |
| `vaccine-preventable-diseases-who.md` | WHO/UNICEF Immunization in Practice |
| `immunization-who.md` | WHO Immunization in Practice |
| `measles-who.md` | WHO Measles Position Paper (2017, updated 2022); WHO/UNICEF IMCI |

### Emergencies & First Aid

| File | Source |
|------|--------|
| `cardiovascular-emergency-who.md` | WHO Basic Emergency Care |
| `chest-pain-who.md` | WHO Basic Emergency Care |
| `stroke-who.md` | WHO Basic Emergency Care; STR-FAST recognition |
| `shock-who.md` | WHO Basic Emergency Care |
| `anaphylaxis-who.md` | WHO Basic Emergency Care; UpToDate consensus |
| `allergic-reactions-who.md` | WHO Basic Emergency Care |
| `burns-who.md` | WHO ETAT+ / Basic Emergency Care |
| `wound-care-who.md` | WHO Basic Emergency Care |
| `fractures-first-aid.md` | WHO Basic Emergency Care |
| `choking-first-aid.md` | WHO Basic Emergency Care; ERC choking algorithm |
| `drowning-cpr-who.md` | WHO Basic Emergency Care |
| `foreign-body-aspiration-who.md` | WHO Basic Emergency Care; ERC pediatric algorithm |
| `heat-illness-who.md` | WHO Basic Emergency Care |
| `meningitis-who.md` | WHO Bacterial Meningitis Guidelines |
| `meningococcemia-who.md` | WHO Meningococcal Disease |

### Infectious Disease

| File | Source |
|------|--------|
| `malaria-who.md` | WHO Malaria Treatment Guidelines (3rd Ed) |
| `tuberculosis-who.md` | WHO TB Module 4 (Treatment & Care) |
| `hiv-who.md` | WHO Consolidated HIV Guidelines |
| `hiv-pep-who.md` | WHO 2024 + CDC 2025 HIV PEP |
| `sti-who.md` | WHO STI Guidelines |
| `hepatitis-who.md` | WHO Hepatitis Guidelines |
| `cholera-who.md` | WHO Cholera Treatment |
| `dengue-who.md` | WHO Dengue Guidelines |
| `typhoid-who.md` | WHO Typhoid Position Paper |
| `fever-differential-tropical.md` | WHO IMAI / IMCI fever differential |
| `diarrhea-adults-who.md` | WHO Adult Diarrhea Management |
| `uti-who.md` | WHO PEN / IDSA |
| `tetanus-who.md` | WHO Tetanus Prevention & Treatment |
| `rabies-who.md` | WHO Rabies Position Paper |
| `rabies-pep-who.md` | WHO Guide for Rabies Pre/Post-Exposure Prophylaxis |
| `snakebite-who.md` | WHO Snakebite Management (2nd Ed) |

### Skin / Eyes / ENT

| File | Source |
|------|--------|
| `skin-infections-who.md` | WHO PEN / IMCI skin |
| `scabies-who.md` | WHO Scabies Position Paper |
| `eczema-dermatitis-who.md` | WHO Primary Care Dermatology |
| `herpes-shingles-who.md` | WHO STI / Herpes guidance |
| `tropical-skin-ntds.md` | WHO Skin NTDs (Leprosy, Buruli, Leishmaniasis, Mycetoma, Yaws) |
| `eye-infections-who.md` | WHO Primary Eye Care |
| `oral-health-who.md` | WHO Primary Oral Health |

### Chronic Disease & Mental Health

| File | Source |
|------|--------|
| `diabetes-who.md` | WHO PEN for Primary Care |
| `hypertension-who.md` | WHO PEN / HEARTS |
| `asthma-who.md` | WHO PEN / GINA-aligned |
| `anemia-who.md` | WHO Iron Supplementation |
| `epilepsy-mhgap-who.md` | WHO mhGAP Intervention Guide |
| `depression-mhgap-who.md` | WHO mhGAP Intervention Guide |

### Toxicology

| File | Source |
|------|--------|
| `poisoning-general-who.md` | WHO/IPCS INTOX; WHO Basic Emergency Care |
| `poisoning-organophosphate-who.md` | WHO Clinical Management of Acute Pesticide Intoxication; WHO/IPCS INTOX |
| `poisoning-heavy-metals-who.md` | WHO Lead Poisoning fact sheet (2024); WHO Mercury and Health (2024); WHO Arsenic (2022); WHO/IPCS INTOX |

### Drug Safety Helpers

| File | Source |
|------|--------|
| `drug-allergies-alternatives.md` | WHO Essential Medicines List + UpToDate alternative regimens |

### Child Protection & Safeguarding

| File | Source |
|------|--------|
| `child-protection-who.md` | WHO Clinical Handbook "Responding to child maltreatment: a clinical handbook for health professionals" (2022, ISBN 9789240048737); WHO INSPIRE: Seven Strategies for Ending Violence Against Children (2016); Pierce MC et al., TEN-4-FACESp bruising rule (JAMA Network Open 2021); WHO "Responding to children and adolescents who have been sexually abused" (2017) |

---

## Validation Checklist

Before any new protocol is included in `core.db`:

- [ ] Official source verified (working URL, current edition)
- [ ] Document is the latest version (not superseded)
- [ ] Dosages cross-checked against the source
- [ ] Consistent format (H1 title + bold labels for sub-sections)
- [ ] `Source:` line included with year
- [ ] **At most ONE `##` header in the file** (real chunking constraint)
- [ ] `medlocal protocol validate <path>` reports 0 errors
- [ ] `medlocal protocol new <path> -q "<lay query>" -q "<adversarial reword>"`
      shows the protocol surfacing in the top 6 of the merged retrieval
- [ ] `medlocal protocol audit` still passes after the new file is added
- [ ] Smoke or benchmark case added if the protocol covers a clinically
      important condition not already exercised by an existing case

---

*Last updated: 2026-04-08 — corpus flatten, heavy-metals protocol
(case HM01), and child-protection protocol (case CP01) all landed
on the same day. Copyright and originality disclosure added
reflecting the hackathon rules review.*
