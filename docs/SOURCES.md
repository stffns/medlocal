# MedLocal — Source Documents Plan

## Principio Fundamental: Trazabilidad Total

> Cada respuesta que MedLocal genera DEBE ser trazable a un documento oficial publicado.
> Si no hay fuente verificable, la respuesta no se genera.
> El sistema de recall (pares pregunta/respuesta) se valida contra el protocolo original.

### Cadena de Trazabilidad
```
Respuesta del LLM → Chunk de vstash → Protocolo estructurado → Documento fuente oficial
     ↑                    ↑                    ↑                       ↑
  Gemma E4B          chunk_id           data/core/protocols/     URL verificable
  (solo formatea)    (auditable)        (citacion exacta)        (descargable)
```

### Anti-Hallucination Architecture
```
                    ┌─────────────────────────────────┐
                    │     CORE.DB (read-only)          │
                    │   WHO/MSF/Hesperian protocols    │
                    │   Cada chunk trazable a fuente   │
                    └──────────┬──────────────────────┘
                               │ retrieval
                    ┌──────────▼──────────────────────┐
                    │   CONSULTATION PIPELINE          │
                    │   1. Multi-query retrieval        │
                    │   2. Confidence scoring           │
                    │   3. LLM generation              │
                    │   4. Dosage cross-check           │
                    │   5. Grounding verification       │
                    │   6. Audit log                    │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │   TRAINING PIPELINE              │
                    │   Par Q&A (teacher offline)       │
                    │   + Protocolo original (chunk)    │
                    │   = Doble validacion del juez     │
                    └─────────────────────────────────┘
```

---

## Regla de Formato: Protocolos Cortos y Enfocados

Los PDFs de WHO producen chunks con texto administrativo/tablas rotas.
Protocolos estructurados en markdown producen respuestas excelentes.

**Regla:** Cada protocolo debe cubrir UN tema especifico y ser ≤2000 caracteres.
Si es mas largo, dividir en documentos separados por seccion clinica.

Ejemplo:
- ❌ `tuberculosis-who.md` (documento largo con diagnosis + treatment + monitoring + side effects)
- ✅ `tb-diagnosis-who.md` (solo cuando sospechar + como diagnosticar)
- ✅ `tb-treatment-who.md` (solo regimenes + dosificacion)
- ✅ `tb-side-effects-who.md` (solo efectos adversos + danger signs)

---

## Tier 1 — Fuentes Primarias (WHO/OMS)

Documentos oficiales de la Organizacion Mundial de la Salud. Maximo nivel de autoridad.

### PDFs Descargados
| Documento | Pags | URL |
|-----------|------|-----|
| Essential Medicines List 24th (2025) | 74 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/17642505-ecd3-4940-a691-4f1dfa0d835a/content) |
| IMCI Adaptation Guide | 10 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/mca-documents/child/imci-integrated-management-of-childhood-illness/adaptation-guide/who-shs-guideline_web_v28.pdf) |
| IMCI Assessment Booklet (2m-5yr) | 6 | [platform.who.int](https://platform.who.int/docs/default-source/mca-documents/policy-documents/operational-guidance/EGY-CH-59-01-OPERATIONALGUIDANCE-eng-IMCI-Assessment-Booklet-2m-5yrs.pdf) |
| Quality of Maternal/Newborn Care | ~80 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/mca-documents/qoc/quality-of-care/standards-for-improving-quality-of-maternal-and-newborn-care-in-health-facilities_1a22426e-fdd0-42b4-95b2-4b5b9c590d76.pdf) |
| Postnatal Care Recommendations | ~60 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/a6696f52-fa0f-42fc-bedd-ebfc8725b65b/content) |
| Snakebite Management 2nd Ed | 20 | [cdn.who.int](https://cdn.who.int/media/docs/default-source/searo/india/health-topic-pdf/who-guidance-on-management-of-snakebites.pdf) |
| IMAI Acute Care | 121 | [iris.who.int](https://iris.who.int/server/api/core/bitstreams/a9ce216f-7f3b-411f-b06c-432b8322a8a5/content) |

### PDFs Pendientes (ALTA prioridad)
| Documento | URL |
|-----------|-----|
| IMCI Chart Booklet completo | [who.int](https://www.who.int/publications/i/item/9789241506823) |
| IMAI District Clinician Manual Vol 1 | [apps.who.int](http://apps.who.int/iris/bitstream/10665/77751/1/9789241548281_Vol1_eng.pdf) |
| Pocket Book of Hospital Care for Children | [who.int](https://www.who.int/publications/i/item/978-92-4-154837-3) |
| WHO PEN (Essential NCD Interventions) | [who.int](https://www.who.int/publications/i/item/who-package-of-essential-noncommunicable-(pen)-disease-interventions-for-primary-health-care) |
| Consolidated HIV Guidelines (2021+2026) | [who.int](https://www.who.int/publications/i/item/9789240031593) |
| TB Module 4: Treatment and Care | [who.int](https://www.who.int/publications/i/item/9789240107243) |
| Malaria Treatment Guidelines 3rd Ed | [who.int](https://www.who.int/publications/i/item/9789241549127) |

### PDFs Pendientes (MEDIA prioridad)
| Documento | URL |
|-----------|-----|
| Surgical Care at District Hospital | [who.int](https://www.who.int/publications/i/item/9241545755) |
| Basic Emergency Care | [who.int](https://www.who.int/publications/i/item/basic-emergency-care) |
| Rabies PEP Guide | [who.int](https://www.who.int/publications/i/item/who-guide-for-rabies-pre-and-post-exposure-prophylaxis-in-humans) |
| Antenatal Care Recommendations | [who.int](https://www.who.int/publications/i/item/9789241549912) |
| Family Planning Guidelines | [who.int](https://www.who.int/publications/i/item/9780999203705) |
| mhGAP Intervention Guide (Mental Health) | [who.int](https://www.who.int/publications/i/item/9789241549790) |
| WASH Guidelines | [who.int](https://www.who.int/publications/i/item/9789241548151) |

---

## Tier 2 — MSF (Medecins Sans Frontieres)

La MEJOR fuente practica — escrita para exactamente el contexto de MedLocal.

| Documento | Estado | URL |
|-----------|--------|-----|
| Essential Drugs Guide (663 pgs) | ✅ PDF | [medicalguidelines.msf.org](https://medicalguidelines.msf.org/sites/default/files/pdf/guideline-339-en.pdf) |
| Clinical Guidelines: Diagnosis and Treatment | PENDIENTE | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |
| Obstetrics Guidelines | PENDIENTE | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |
| Nutrition Guidelines | PENDIENTE | [medicalguidelines.msf.org](https://medicalguidelines.msf.org) |

---

## Tier 3 — Hesperian Health Guides

Clasico para community health workers. Creative Commons.

| Documento | Estado | URL |
|-----------|--------|-----|
| Where There Is No Doctor (2025) | Parcial | [hesperian.org](https://hesperian.org/wp-content/uploads/pdf/en_wtnd_2025/en_wtnd_2025_fm.pdf) |
| Where There Is No Doctor (2011 full) | PENDIENTE | [frankshospitalworkshop.com](http://www.frankshospitalworkshop.com/organisation/biomed_documents/Where%20there%20is%20no%20Doctor%20-%20David%20Werner.pdf) |
| Where Women Have No Doctor | PENDIENTE | [hesperian.org](https://hesperian.org/books-and-resources/) |

---

## Tier 4 — Fuentes Regionales (perfil LOCAL)

Van al perfil `local` (editable), no al `core`.

| Region | Fuente | URL |
|--------|--------|-----|
| Kenya | Kenya Clinical Guidelines | [apps.who.int](https://apps.who.int/iris/) |
| South Africa | Standard Treatment Guidelines | [health.gov.za](https://www.health.gov.za/) |
| India | National Health Mission | [nhm.gov.in](https://nhm.gov.in/) |
| Colombia | Guias MinSalud | [minsalud.gov.co](https://www.minsalud.gov.co/) |
| Brazil | Protocolos do SUS | [saude.gov.br](https://www.gov.br/saude/) |

---

## Protocolos Estructurados — Estado Actual

14 protocolos creados, 12+ pendientes.

### Completados ✅
| Protocolo | Fuente Oficial |
|-----------|---------------|
| `diarrhea-imci.md` | WHO/UNICEF IMCI Guidelines |
| `malaria-who.md` | WHO Malaria Treatment 3rd Ed |
| `pneumonia-imci.md` | WHO/UNICEF IMCI Guidelines |
| `preeclampsia-who.md` | WHO Pre-eclampsia Guidelines |
| `newborn-care-who.md` | WHO Newborn Health Recommendations |
| `newborn-resuscitation-who.md` | WHO/HBB Newborn Resuscitation |
| `nutrition-who.md` | WHO Acute Malnutrition Management |
| `hiv-who.md` | WHO Consolidated HIV Guidelines |
| `tuberculosis-who.md` | WHO TB Module 4 |
| `diabetes-who.md` | WHO PEN for Primary Care |
| `snakebite-who.md` | WHO Snakebite Management 2nd Ed |
| `burns-who.md` | WHO ETAT+ / Basic Emergency Care |
| `immunization-who.md` | WHO Immunization in Practice |
| `wound-care-who.md` | WHO Basic Emergency Care |

### Pendientes ❌
| Protocolo | Fuente |
|-----------|--------|
| `family-planning-who.md` | WHO MEC for Contraceptives |
| `anemia-who.md` | WHO Iron Supplementation |
| `hypertension-who.md` | WHO PEN / HEARTS |
| `asthma-copd-who.md` | WHO PEN |
| `epilepsy-who.md` | WHO mhGAP |
| `depression-who.md` | WHO mhGAP |
| `sti-who.md` | WHO STI Guidelines |
| `eye-infections-who.md` | WHO Primary Eye Care |
| `ear-infections-who.md` | WHO/IMCI |
| `deworming-who.md` | WHO Deworming |
| `cholera-who.md` | WHO Cholera Treatment |
| `dengue-who.md` | WHO Dengue Guidelines |

---

## Validacion Checklist

Antes de incluir cualquier protocolo en core.db:

- [ ] Fuente oficial verificable (URL funcional)
- [ ] Documento vigente (no reemplazado)
- [ ] Dosificaciones verificadas contra fuente
- [ ] Formato consistente (headers, steps, danger signs)
- [ ] Citacion `Source:` incluida con año
- [ ] ≤2000 chars por documento (o dividido en secciones)
- [ ] Probado con 2+ queries en MedLocal
- [ ] Respuesta verificada contra documento original
- [ ] Safety check: emergency detection funciona
- [ ] Safety check: dosages en respuesta matchean protocolo
