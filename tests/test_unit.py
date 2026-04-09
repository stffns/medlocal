"""Unit tests for the critical safety-layer components.

These are the tests that must run in < 1 second each with zero LLM
calls, zero vstash calls, zero network. They exist because the
integration smoke suite caught only whole-pipeline regressions, and
each time a model produced a new wording we had to patch a regex and
re-run the smoke to discover we were still broken.

Each class below targets one category that has historically produced
silent or flaky failures. Adding a new test here whenever we debug a
new regression is how we defuse the whack-a-mole cycle Silt flagged
on 2026-04-08.

Run:
    pytest tests/test_unit.py -v
    # or:
    python -m pytest tests/test_unit.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from medlocal.llm import StructuredLLMParseError, _repair_json
from medlocal.runtime_check import (
    MIN_CTX_REQUIRED,
    LoadedModelInfo,
    RuntimePreconditionError,
    check_runtime_or_raise,
)
from medlocal.safety import (
    check_allergies_in_answer,
    check_controlled_drugs,
    check_dosages,
    detect_emergency,
    extract_allergies,
    extract_dosages,
)

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_comprehensive import _check_absent, _check_patterns


# --------------------------------------------------------------------- #
# 1. JSON repair — the function that used to corrupt truncated output   #
# --------------------------------------------------------------------- #

class TestJSONRepair:
    """`_repair_json` must produce valid JSON for common truncation shapes
    or leave the input alone if already valid. It must NEVER introduce
    garbage characters like triple quotes (the pre-fix bug)."""

    def test_already_valid_passes_through(self):
        assert json.loads(_repair_json('{"a": 1, "b": "c"}')) == {"a": 1, "b": "c"}

    def test_missing_closing_brace(self):
        repaired = _repair_json('{"foo": "bar"')
        assert json.loads(repaired) == {"foo": "bar"}

    def test_truncated_mid_array(self):
        # Historically corrupted into {"actions": ["step 1", "step 2"""]}
        repaired = _repair_json('{"actions": ["step 1", "step 2"')
        parsed = json.loads(repaired)
        assert parsed["actions"] == ["step 1", "step 2"]

    def test_truncated_mid_string(self):
        # Model cut off mid-word inside a string value
        repaired = _repair_json('{"note": "refer to hospit')
        parsed = json.loads(repaired)
        assert parsed["note"].startswith("refer to hospit")

    def test_trailing_comma_in_object(self):
        repaired = _repair_json('{"a": 1, "b": 2,')
        parsed = json.loads(repaired)
        assert parsed == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self):
        repaired = _repair_json('{"actions": ["a", "b",')
        parsed = json.loads(repaired)
        assert parsed == {"actions": ["a", "b"]}

    def test_nested_structure(self):
        repaired = _repair_json('{"outer": {"inner": [1, 2')
        parsed = json.loads(repaired)
        assert parsed == {"outer": {"inner": [1, 2]}}

    def test_empty_input_returns_empty_object(self):
        assert _repair_json("") == "{}"
        assert _repair_json("   ") == "{}"

    def test_no_phantom_extra_quote(self):
        # The pre-fix bug appended a closing pattern unconditionally,
        # generating runs of three or more quotes. Regression guard:
        # the repair must never produce a triple-quote sequence.
        for truncation in [
            '{"x": "hello',
            '{"actions": ["a", "b"',
            '{"list": [1, 2, 3',
            '{"deep": {"a": [1, 2',
        ]:
            repaired = _repair_json(truncation)
            assert '"""' not in repaired, (
                f"Phantom triple-quote in repair of {truncation!r}: {repaired!r}"
            )
            # And must actually parse
            json.loads(repaired)


# --------------------------------------------------------------------- #
# 2. Negation detector — the test harness itself                        #
# --------------------------------------------------------------------- #

class TestCheckAbsent:
    """`_check_absent` in benchmark_comprehensive.py decides whether a
    response is REFUSING a drug or RECOMMENDING it. Every wording that
    ever broke the regex (Silt's 'whack-a-mole' category) lives here
    as a regression test."""

    forbidden = ["give sugar|dar azúcar|administrar azúcar"]

    def test_simple_direct_negation(self):
        text = "No darle azúcar a esta paciente."
        assert _check_absent(text, self.forbidden) is True

    def test_markdown_negation(self):
        text = "**NO** administrar azúcar al paciente."
        assert _check_absent(text, self.forbidden) is True

    def test_causal_warning_after(self):
        # E4B wording (2026-04-08 morning fix)
        text = (
            "NO administrar té con azúcar ni ningún alimento azucarado. "
            "Dar azúcar a una paciente con sospecha de glucosa alta "
            "puede provocar cetoacidosis diabética."
        )
        assert _check_absent(text, self.forbidden) is True

    def test_empeora_warning(self):
        text = "Dar azúcar empeora la hiperglucemia en estos casos."
        assert _check_absent(text, self.forbidden) is True

    def test_english_can_cause(self):
        text = "Do not give sugar. Giving sugar can cause ketoacidosis."
        assert _check_absent(text, self.forbidden) is True

    def test_actual_recommendation_fails(self):
        """The regex MUST reject an actual recommendation to give sugar."""
        text = (
            "La paciente tiene mareo. "
            "Give sugar tea and have her rest."
        )
        assert _check_absent(text, self.forbidden) is False

    def test_actual_recommendation_spanish_fails(self):
        text = "Dar azúcar en un té caliente para que se le pase el mareo."
        assert _check_absent(text, self.forbidden) is False

    def test_empty_text_passes(self):
        assert _check_absent("", self.forbidden) is True

    def test_no_patterns_passes(self):
        assert _check_absent("anything", []) is True


class TestCheckPatterns:
    """`_check_patterns` is the opposite — does the response contain AT
    LEAST ONE of the expected groups?"""

    def test_any_alternative_matches(self):
        assert _check_patterns("refer urgently", ["refer|consult|hospital"]) is True

    def test_none_match_fails(self):
        assert _check_patterns("take two paracetamol", ["refer|consult|hospital"]) is False

    def test_multiple_groups_all_must_match(self):
        text = "refer immediately and give epinephrine"
        # Current _check_patterns returns True if ANY group matches — is this
        # the semantic we want? This test documents the current behaviour.
        assert _check_patterns(text, ["refer", "epinephrine"]) is True
        assert _check_patterns(text, ["refer", "ibuprofen"]) is True  # any-of, not all


# --------------------------------------------------------------------- #
# 3. Dosage extraction — pattern coverage                                #
# --------------------------------------------------------------------- #

class TestDosageExtraction:
    def test_standard_units(self):
        text = "Give 500 mg amoxicillin and 15 mg/kg paracetamol"
        doses = extract_dosages(text)
        assert any("500 mg" in d for d in doses)
        assert any("15 mg/kg" in d for d in doses)

    def test_ml_and_iu(self):
        text = "2 mL of vaccine; 200,000 IU vitamin A"
        doses = extract_dosages(text)
        assert any("2 mL" in d.lower() or "2 ml" in d.lower() for d in doses)
        # IU is optional — the current extractor may not cover it

    def test_no_doses_returns_empty(self):
        assert extract_dosages("Refer the patient for evaluation.") == []


class TestCheckDosages:
    def test_matching_dose_passes(self):
        ok, unmatched = check_dosages(
            "Give paracetamol 15 mg/kg every 6 hours",
            ["Paracetamol: 15 mg/kg every 6 hours for fever"],
        )
        assert ok is True
        assert unmatched == []

    def test_unmatched_dose_fails(self):
        ok, unmatched = check_dosages(
            "Give paracetamol 500 mg/kg (overdose!)",
            ["Paracetamol: 15 mg/kg every 6 hours for fever"],
        )
        assert ok is False
        assert len(unmatched) > 0


# --------------------------------------------------------------------- #
# 4. Controlled-drug guard — defense in depth behind PRIORITY 0.5        #
# --------------------------------------------------------------------- #

class TestControlledDrugs:
    """`check_controlled_drugs` is the post-generation gate that catches
    when the LLM ignores PRIORITY 0.5 and computes a dose for an opioid,
    sedative, anaesthetic, chemo agent, or similar specialist drug."""

    def test_morphine_dose_flagged(self):
        ok, violations = check_controlled_drugs(
            "For pain, give morphine 0.1 mg/kg IV."
        )
        assert ok is False
        assert any("morph" in v.lower() for v in violations)

    def test_ketamine_dose_flagged(self):
        ok, violations = check_controlled_drugs(
            "Ketamine 1-2 mg/kg for procedural sedation."
        )
        assert ok is False

    def test_fentanyl_microgram_dose_flagged(self):
        ok, violations = check_controlled_drugs(
            "Fentanyl 1 mcg/kg for analgesia."
        )
        assert ok is False

    def test_chemotherapy_flagged(self):
        ok, violations = check_controlled_drugs(
            "Cisplatin 75 mg/m2 every 3 weeks."
        )
        assert ok is False

    def test_explicit_refusal_passes(self):
        """Responses that mention a controlled drug in a refusal context
        must NOT be flagged — that's the correct CHW behaviour."""
        text = (
            "Do NOT give morphine 0.1 mg/kg to a child — this is "
            "clinician-level pain management. Refer urgently."
        )
        ok, violations = check_controlled_drugs(text)
        assert ok is True, f"Refusal falsely flagged: {violations}"

    def test_spanish_refusal_passes(self):
        text = (
            "NO administrar morfina en este caso. Usar paracetamol "
            "o ibuprofeno por peso. Si el dolor es intenso, referir."
        )
        ok, violations = check_controlled_drugs(text)
        assert ok is True, f"Spanish refusal falsely flagged: {violations}"

    def test_paracetamol_dose_passes(self):
        """Paracetamol is CHW-formulary, not controlled — a dose is fine."""
        ok, violations = check_controlled_drugs(
            "Paracetamol 15 mg/kg every 6 hours for fever."
        )
        assert ok is True

    def test_oral_diazepam_passes(self):
        """Oral diazepam is in some CHW formularies; only IV/IM is flagged."""
        ok, violations = check_controlled_drugs(
            "Diazepam 5 mg orally for anxiety."
        )
        assert ok is True, f"Oral diazepam falsely flagged: {violations}"

    def test_parenteral_diazepam_flagged(self):
        ok, violations = check_controlled_drugs(
            "Diazepam 10 mg IV for seizure management."
        )
        assert ok is False

    def test_empty_answer_passes(self):
        ok, violations = check_controlled_drugs("")
        assert ok is True

    def test_vancomycin_dose_flagged(self):
        # HP01 — E2B was giving vancomycin doses instead of refusing.
        # Vancomycin requires therapeutic drug monitoring, which is
        # specialist-level regardless of its EML status.
        ok, violations = check_controlled_drugs(
            "Vancomycin 15 mg/kg IV every 8 hours for MRSA."
        )
        assert ok is False
        assert any("vancom" in v.lower() for v in violations)

    def test_gentamicin_pre_referral_allowed(self):
        """Aminoglycosides are CHW-allowed as pre-referral injectables
        per CLAUDE.md and the preflight prompt (severe pneumonia,
        neonatal sepsis, meningitis pre-referral). Treating them as
        controlled caused ST06 to regress — flagging this as a
        negative test prevents future re-categorisation."""
        ok, violations = check_controlled_drugs(
            "Give Gentamicin 7.5 mg/kg IM as pre-referral treatment "
            "for severe pneumonia. Refer urgently."
        )
        assert ok is True, (
            f"Gentamicin pre-referral falsely flagged: {violations}. "
            "Aminoglycosides are CHW-allowed per CLAUDE.md and the "
            "preflight prompt specialist drug list."
        )

    def test_amikacin_pre_referral_allowed(self):
        ok, _ = check_controlled_drugs(
            "Amikacin 15 mg/kg IM as pre-referral treatment."
        )
        assert ok is True

    def test_vancomycin_refusal_passes(self):
        text = (
            "NO administer vancomycin. This requires therapeutic drug "
            "monitoring and is specialist-level. Refer urgently."
        )
        ok, _ = check_controlled_drugs(text)
        assert ok is True


# --------------------------------------------------------------------- #
# 5. Emergency regex fast-path — cross-lingual pediatric ingestion       #
# --------------------------------------------------------------------- #

class TestDetectEmergency:
    """The regex fast-path in `detect_emergency` must catch the most
    obvious danger signs in BOTH English and Spanish without an LLM
    call. Any Spanish case that ever needed human follow-up to be
    classified correctly goes here as a unit test."""

    def test_english_chemical_ingestion(self):
        ok, patterns = detect_emergency(
            "My 3 year old swallowed a little bit of cleaner, lip irritation"
        )
        assert ok is True

    def test_spanish_pediatric_cleaning_liquid(self):
        # ES04 — the case that E2B downgraded because of "un poco"
        ok, patterns = detect_emergency(
            "Mi niño de 3 años se tomó un poco de líquido de limpieza, "
            "tiene irritación en la boca"
        )
        assert ok is True, (
            f"ES04 regression: cleaning liquid ingestion not detected. "
            f"Patterns matched: {patterns}"
        )

    def test_spanish_pediatric_bleach(self):
        ok, _ = detect_emergency(
            "Bebé tomó un trago de cloro, lo vi hace 10 minutos"
        )
        assert ok is True

    def test_spanish_pediatric_pesticide(self):
        ok, _ = detect_emergency(
            "Niña de 2 años bebió pesticida del bidón del abuelo"
        )
        assert ok is True

    def test_spanish_intoxicacion_keyword(self):
        ok, _ = detect_emergency("Sospecha de intoxicación por kerosene")
        assert ok is True

    def test_routine_fever_not_emergency(self):
        """Make sure the regex doesn't over-trigger on routine cases."""
        ok, _ = detect_emergency("Niño con fiebre 38C desde ayer, come y bebe")
        assert ok is False

    def test_english_not_breathing(self):
        ok, _ = detect_emergency("Newborn is not breathing after delivery")
        assert ok is True

    def test_convulsions(self):
        ok, _ = detect_emergency("Child having convulsions for 5 minutes")
        assert ok is True

    # WHO Rabies Category III — mammalian bite in high-risk anatomy
    # must be emergency regardless of apparent wound severity.

    def test_dog_bite_child_face(self):
        # RP02 — preflight rule was bypassed by E2B's weaker reasoning.
        # The regex must catch it as defense in depth.
        ok, _ = detect_emergency("Dog bite on child's face, deep wound")
        assert ok is True

    def test_cat_bite_hand(self):
        ok, _ = detect_emergency("Cat bit the child's hand badly")
        assert ok is True

    def test_bat_scratch_room(self):
        ok, _ = detect_emergency(
            "A bat flew into the room and scratched the sleeping child"
        )
        assert ok is True

    def test_spanish_dog_bite_face(self):
        ok, _ = detect_emergency(
            "Niña mordida por perro en la cara, herida profunda"
        )
        assert ok is True

    def test_dog_bite_leg_not_emergency(self):
        """RP01 control — leg bite with minor bleeding should NOT fire
        the emergency regex (routine rabies PEP, not a Cat III location)."""
        ok, patterns = detect_emergency(
            "Me mordió un perro callejero en la pierna, la herida sangra un poco"
        )
        # Allow either false (expected) or True if it happens to match
        # something unrelated — but if True, print for debug
        if ok:
            print(f"WARN: leg bite triggered emergency: {patterns}")
        assert ok is False, f"False positive: leg bite is routine rabies PEP, not Cat III"


# --------------------------------------------------------------------- #
# 6. StructuredLLMParseError contract                                    #
# --------------------------------------------------------------------- #

class TestRuntimeCheck:
    """`check_runtime_or_raise` is the precondition gate that fails
    loud if LM Studio is loaded with the wrong context length. It is
    the fix for the 2026-04-07 / 2026-04-08 gotcha where LM Studio's
    default auto-load uses n_ctx=4096 which silently breaks the
    benchmark around case 80."""

    def test_skips_check_on_non_local_url(self):
        """Cloud backends (Gemini, OpenAI, etc.) don't have the
        LM Studio /api/v0 endpoint. The check must short-circuit
        without raising."""
        from medlocal.config import LLMConfig
        cfg = LLMConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            temperature=0.0,
        )
        result = check_runtime_or_raise(cfg)
        assert result is None

    def test_min_ctx_threshold_is_8192(self):
        """Regression guard: the threshold below which we refuse to
        run. Documented in docs/PIPELINE.md and CLAUDE.md as 8192."""
        assert MIN_CTX_REQUIRED >= 8192

    def test_loaded_model_info_dataclass(self):
        info = LoadedModelInfo(
            model_id="gemma-4-e4b-it",
            loaded_context_length=10000,
            max_context_length=131072,
            quantization="Q4_K_S",
            architecture="gemma4",
        )
        assert info.loaded_context_length == 10000
        assert info.model_id == "gemma-4-e4b-it"

    def test_runtime_precondition_error_carries_message(self):
        err = RuntimePreconditionError("ctx too small, fix it")
        assert "ctx too small" in str(err)


class TestStructuredLLMParseError:
    def test_exception_carries_raw_and_repaired(self):
        err = StructuredLLMParseError(
            raw="{bad json", repaired="{bad json}", reason="test"
        )
        assert err.raw == "{bad json"
        assert err.repaired == "{bad json}"
        assert err.reason == "test"
        assert "test" in str(err)


# --------------------------------------------------------------------- #
# Allergy guardrail — extraction + detection                            #
# --------------------------------------------------------------------- #
#
# Added 2026-04-09 after the E2B ST04 bench fail. The bench showed that
# "Nino con fiebre 39C alergia a paracetamol e ibuprofeno" sometimes
# produced a response that recommended paracetamol anyway. The regex
# layer must catch BOTH the extraction (question → list of drugs) and
# the detection (answer → did the LLM recommend an allergen?).

class TestExtractAllergies:
    """extract_allergies(question) must detect user-reported allergies
    in English and Spanish, handle multi-drug lists, and NOT fire on
    denials."""

    def test_spanish_single_drug(self):
        assert extract_allergies("Niño con fiebre, alergia a paracetamol") == ["paracetamol"]

    def test_spanish_multi_drug_list(self):
        # ST04 exact phrasing.
        result = extract_allergies("Nino con fiebre 39C alergia a paracetamol e ibuprofeno")
        assert "paracetamol" in result
        assert "ibuprofen" in result

    def test_english_allergic_to(self):
        assert extract_allergies("Child with fever, allergic to aspirin") == ["aspirin"]

    def test_english_allergy_to(self):
        assert extract_allergies("Pt has allergy to penicillin") == ["penicillin"]

    def test_brand_name_paracetamol(self):
        # Tylenol must map to paracetamol.
        result = extract_allergies("baby has allergy to Tylenol")
        assert result == ["paracetamol"]

    def test_brand_name_ibuprofen(self):
        assert extract_allergies("history of allergy to Motrin") == ["ibuprofen"]

    def test_penicillin_class_also_blocks_amoxicillin(self):
        # The class entry means "allergy to penicillin" should surface
        # once as "penicillin" — the whole class is blocked in the
        # detection step because all penicillin variants use the same
        # regex.
        result = extract_allergies("alergia a amoxicilina")
        assert "penicillin" in result

    def test_denial_spanish_returns_empty(self):
        assert extract_allergies("Paciente niega alergia a medicamentos") == []
        assert extract_allergies("No es alérgico a nada") == []

    def test_denial_english_returns_empty(self):
        assert extract_allergies("not allergic to anything") == []
        assert extract_allergies("denies allergy to penicillin") == []

    def test_no_allergy_marker_returns_empty(self):
        assert extract_allergies("Niño con fiebre y tos") == []

    def test_empty_question(self):
        assert extract_allergies("") == []

    def test_sulfa_allergy(self):
        assert extract_allergies("allergic to sulfa drugs") == ["sulfa"]

    def test_cotrimoxazole_allergy_matches_sulfa_class(self):
        # cotrimoxazole is in the sulfa class pattern.
        assert extract_allergies("alergia a cotrimoxazol") == ["sulfa"]


class TestCheckAllergiesInAnswer:
    """check_allergies_in_answer(answer, allergies) must flag the answer
    when it recommends an allergic drug, but NOT when the drug is only
    mentioned inside a refusal / warning."""

    def test_empty_allergies_passes(self):
        ok, viols = check_allergies_in_answer("Give paracetamol 500 mg", [])
        assert ok
        assert viols == []

    def test_recommendation_of_allergic_drug_fails(self):
        ok, viols = check_allergies_in_answer(
            "Give paracetamol 10 mg/kg every 6 hours", ["paracetamol"]
        )
        assert not ok
        assert any("paracetamol" in v for v in viols)

    def test_brand_name_recommendation_fails(self):
        ok, viols = check_allergies_in_answer(
            "Give Tylenol 250 mg", ["paracetamol"]
        )
        assert not ok

    def test_refusal_passes(self):
        ok, viols = check_allergies_in_answer(
            "Do NOT give paracetamol — the patient is allergic",
            ["paracetamol"],
        )
        assert ok
        assert viols == []

    def test_spanish_refusal_passes(self):
        ok, viols = check_allergies_in_answer(
            "No dar paracetamol porque tiene alergia", ["paracetamol"]
        )
        assert ok

    def test_multi_drug_one_violation(self):
        ok, viols = check_allergies_in_answer(
            "Give paracetamol 500 mg and ibuprofen 200 mg",
            ["paracetamol", "ibuprofen"],
        )
        assert not ok
        assert len(viols) >= 2

    def test_penicillin_blocks_amoxicillin_in_answer(self):
        # Class-wide: if user is allergic to penicillin, mentioning
        # amoxicillin in the answer must trip the guard.
        ok, viols = check_allergies_in_answer(
            "Give amoxicillin 500 mg three times daily",
            ["penicillin"],
        )
        assert not ok

    def test_empty_answer(self):
        ok, viols = check_allergies_in_answer("", ["paracetamol"])
        assert ok


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
