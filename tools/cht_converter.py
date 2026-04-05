"""CHT Workflow Converter — transforms CHT XForm decision trees into MedLocal protocols.

Downloads CHT reference app forms from GitHub, parses the XForm XML,
and generates structured markdown protocols for ingestion into vstash.

Usage:
    python tools/cht_converter.py                    # Convert all default forms
    python tools/cht_converter.py --form pregnancy   # Convert specific form
    python tools/cht_converter.py --list             # List available forms
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

OUTPUT_DIR = Path("data/core/cht-workflows")

# Sources: CHT default + PIH Malawi (real deployment with IMCI, TB, HIV, etc.)
SOURCES = {
    "default": {
        "base_url": "https://raw.githubusercontent.com/medic/cht-core/master/config/default/forms/app",
        "forms": [
            "delivery", "pregnancy", "pregnancy_danger_sign",
            "pregnancy_danger_sign_follow_up", "pregnancy_home_visit",
            "pnc_danger_sign_follow_up_baby", "pnc_danger_sign_follow_up_mother",
        ],
    },
    "malawi": {
        "base_url": "https://raw.githubusercontent.com/medic/cht-pih-malawi-app/main/forms/app",
        "forms": [
            "under_5_screening", "over_5_screening", "danger_signs_screening",
            "immunization", "delivery", "delivery_check",
            "newborn_postnatal_follow_up", "postnatal_follow_up",
            "pregnancy", "pregnancy_follow_up",
            "fp_screening", "fp_follow_up",
            "hiv_screening", "hiv_home_visit",
            "tb_screening", "tb_home_visit", "tb_contact_tracing",
            "sputum_collection", "tb_results",
            "daily_follow_up", "referral_follow_up",
            "discharge_instructions",
        ],
    },
}

# Legacy — used if no --source specified
CHT_RAW_BASE = SOURCES["default"]["base_url"]
CLINICAL_FORMS = SOURCES["default"]["forms"]


def download_form(form_name: str) -> str | None:
    """Download XForm XML from CHT GitHub."""
    url = f"{CHT_RAW_BASE}/{form_name}.xml"
    print(f"  Downloading {url}...")
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR: {resp.status_code}")
        return None
    return resp.text


def parse_xform(xml_text: str, form_name: str) -> dict:
    """Parse XForm XML and extract decision tree structure."""
    # Aggressively strip all XML namespaces for simple parsing
    xml_text = re.sub(r'xmlns[:\w]*="[^"]*"', "", xml_text)
    # Remove ALL namespace prefixes from tags: <jr:foo> -> <foo>
    xml_text = re.sub(r"<(/?)[\w]+:", r"<\1", xml_text)
    # Remove ALL namespace prefixes from attributes: odk:foo="bar" -> foo="bar"
    xml_text = re.sub(r" [\w]+:([\w-]+)=", r" \1=", xml_text)

    root = ET.fromstring(xml_text)

    result = {
        "name": form_name,
        "title": "",
        "questions": [],
        "conditions": [],
        "messages": [],
    }

    # Extract title
    title_el = root.find(".//title")
    if title_el is not None and title_el.text:
        result["title"] = title_el.text.strip()

    # Extract labels from itext (internationalization) — this is where CHT stores all text
    for text_el in root.iter("text"):
        text_id = text_el.attrib.get("id", "")
        value_el = text_el.find("value")
        if value_el is None or not value_el.text:
            continue
        text = re.sub(r"<[^>]+>", "", value_el.text).strip()  # Strip HTML tags
        if not text or len(text) < 3:
            continue

        text_id_lower = text_id.lower()
        # Skip non-clinical fields
        if any(skip in text_id_lower for skip in [
            "patient_name", "patient_id", "date_of_birth", "name", "dob",
            "sex", "uuid", "source", "contact", "phone", "select_contact",
            "inputs:", "yes_no", "translation", "translator", "label_translator",
        ]):
            continue
        if any(kw in text_id_lower for kw in ["note", "message", "refer", "congratulate", "summary"]):
            if len(text) > 15:
                result["messages"].append(text)
        elif any(kw in text_id_lower for kw in ["danger", "sign", "risk", "symptom", "bleeding",
                 "fever", "pain", "seizure", "fits", "pale", "swelling", "breathing"]):
            result["questions"].append({"ref": text_id, "text": text, "type": "danger_sign"})
        elif "label" in text_id_lower and len(text) > 10:
            result["questions"].append({"ref": text_id, "text": text, "type": "assessment"})

    # Extract calculations (decision logic)
    for bind in root.iter("bind"):
        calc = bind.attrib.get("calculate", "")
        ref = bind.attrib.get("nodeset", bind.attrib.get("ref", ""))
        if calc and ("danger" in ref.lower() or "risk" in ref.lower()):
            result["conditions"].append({"ref": ref, "logic": calc})

    return result


def _get_text(el) -> str:
    """Get text content from element, handling mixed content."""
    if el.text:
        return el.text.strip()
    # Check for value child
    for child in el:
        if child.tag == "output" and child.attrib.get("value"):
            return f"[{child.attrib['value']}]"
        if child.text:
            return child.text.strip()
    return ""


def _find_parent(root, child):
    """Find parent of an element (ElementTree doesn't track parents)."""
    for parent in root.iter():
        for c in parent:
            if c is child:
                return parent
    return None


def generate_protocol(parsed: dict) -> str:
    """Convert parsed XForm data into MedLocal protocol markdown."""
    name = parsed["name"].replace("_", " ").title()
    title = parsed["title"] or name

    lines = [f"# CHT Workflow: {title}"]
    lines.append("")
    lines.append(f"*Decision support workflow from Community Health Toolkit (CHT)*")
    lines.append(f"*Used by 40,000+ community health workers in 15 countries*")
    lines.append("")

    # Danger signs — deduplicated
    danger_signs = [q for q in parsed["questions"] if q["type"] == "danger_sign"]
    if danger_signs:
        lines.append("## Danger Signs to Check")
        lines.append("Ask about EACH of the following. If ANY is present, refer immediately.")
        lines.append("")
        seen = set()
        for q in danger_signs:
            text = q["text"]
            if text and not text.startswith("[") and text.lower() not in seen:
                seen.add(text.lower())
                lines.append(f"- {text}")
        lines.append("")

    # Assessment questions — deduplicated, skip generic labels
    assessment = [q for q in parsed["questions"] if q["type"] == "assessment"]
    if assessment:
        seen = set()
        useful = []
        for q in assessment:
            text = q["text"]
            if (text and not text.startswith("[") and len(text) > 10
                    and text.lower() not in seen
                    and text.lower() not in ("yes", "no", "select one")):
                seen.add(text.lower())
                useful.append(text)
        if useful:
            lines.append("## Assessment Steps")
            lines.append("")
            for i, text in enumerate(useful, 1):
                lines.append(f"{i}. {text}")
            lines.append("")

    # Decision logic — simplified
    if parsed["conditions"]:
        lines.append("## Decision Rule")
        lines.append("")
        lines.append("- If ANY danger sign above is present → **REFER URGENTLY** to health facility")
        lines.append("- Accompany the patient if possible")
        lines.append("- Complete follow-up within 3 days")
        lines.append("")

    # Messages/instructions
    useful_msgs = [m for m in parsed["messages"] if len(m) > 20 and not m.startswith("[")]
    if useful_msgs:
        lines.append("## Instructions for Health Worker")
        lines.append("")
        for msg in useful_msgs[:10]:  # Limit to avoid noise
            lines.append(f"- {msg}")
        lines.append("")

    # Source
    lines.append("## When to Use This Workflow")
    workflow_map = {
        "pregnancy": "During antenatal care visits for pregnant women",
        "pregnancy_danger_sign": "When a pregnant woman reports or presents with danger signs",
        "pregnancy_danger_sign_follow_up": "Follow-up within 3 days after danger sign referral",
        "delivery": "During or immediately after delivery",
        "pnc_danger_sign_follow_up_baby": "Postnatal danger sign assessment for newborns",
        "pnc_danger_sign_follow_up_mother": "Postnatal danger sign assessment for mothers",
        "pregnancy_home_visit": "Routine pregnancy home visit by CHW",
        "pregnancy_facility_visit_reminder": "Remind pregnant woman about facility visits",
        "death_report": "Reporting a maternal or neonatal death",
    }
    context = workflow_map.get(parsed["name"], "Clinical assessment workflow")
    lines.append(f"- {context}")
    lines.append("")

    lines.append("Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)")
    lines.append("")

    return "\n".join(lines)


def convert_form(form_name: str) -> Path | None:
    """Download, parse, and convert a single CHT form."""
    xml = download_form(form_name)
    if not xml:
        return None

    parsed = parse_xform(xml, form_name)

    # Skip if no useful content
    if not parsed["questions"] and not parsed["messages"]:
        print(f"  Skipping {form_name} — no clinical content")
        return None

    protocol = generate_protocol(parsed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"cht-{form_name.replace('_', '-')}.md"
    out_path.write_text(protocol)
    print(f"  -> {out_path} ({len(protocol)} chars)")
    return out_path


def list_forms():
    """List available clinical forms."""
    print("Available CHT clinical forms:")
    for f in CLINICAL_FORMS:
        print(f"  - {f}")


def main():
    parser = argparse.ArgumentParser(description="Convert CHT XForm workflows to MedLocal protocols")
    parser.add_argument("--form", help="Convert specific form (e.g., pregnancy_danger_sign)")
    parser.add_argument("--list", action="store_true", help="List available forms")
    parser.add_argument("--all", action="store_true", help="Convert all clinical forms")
    parser.add_argument("--source", choices=list(SOURCES.keys()), default=None,
                        help="Source app (default, malawi, or all)")
    args = parser.parse_args()

    if args.list:
        for src_name, src in SOURCES.items():
            print(f"\n{src_name} ({len(src['forms'])} forms):")
            for f in src['forms']:
                print(f"  - {f}")
        return

    # Determine which sources to process
    if args.source:
        sources_to_run = {args.source: SOURCES[args.source]}
    elif args.all:
        sources_to_run = SOURCES
    else:
        sources_to_run = {"default": SOURCES["default"]}

    total_converted = 0
    total_forms = 0

    for src_name, src in sources_to_run.items():
        print(f"\n{'='*50}")
        print(f"  Source: {src_name}")
        print(f"{'='*50}")

        global CHT_RAW_BASE
        CHT_RAW_BASE = src["base_url"]

        if args.form:
            forms = [args.form]
        else:
            forms = src["forms"]

        total_forms += len(forms)
        for form in forms:
            print(f"\nProcessing: {form}")
            path = convert_form(form)
            if path:
                total_converted += 1

    print(f"\nConverted {total_converted}/{total_forms} forms to {OUTPUT_DIR}/")
    print("Next: run 'medlocal ingest data/core/cht-workflows/ --profile core' to ingest")


if __name__ == "__main__":
    main()
