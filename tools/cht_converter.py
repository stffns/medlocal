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

CHT_RAW_BASE = "https://raw.githubusercontent.com/medic/cht-core/master/config/default/forms/app"
OUTPUT_DIR = Path("data/core/cht-workflows")

# Known clinical forms (skip administrative ones like replace_user, undo_death_report)
CLINICAL_FORMS = [
    "delivery",
    "pregnancy",
    "pregnancy_danger_sign",
    "pregnancy_danger_sign_follow_up",
    "pregnancy_facility_visit_reminder",
    "pregnancy_home_visit",
    "pnc_danger_sign_follow_up_baby",
    "pnc_danger_sign_follow_up_mother",
    "death_report",
]


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
        if any(kw in text_id_lower for kw in ["note", "message", "refer", "congratulate"]):
            result["messages"].append(text)
        elif any(kw in text_id_lower for kw in ["danger", "sign", "risk", "symptom"]):
            result["questions"].append({"ref": text_id, "text": text, "type": "danger_sign"})
        elif any(kw in text_id_lower for kw in ["label"]) and len(text) > 5:
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

    # Danger signs
    danger_signs = [q for q in parsed["questions"] if q["type"] == "danger_sign"]
    if danger_signs:
        lines.append("## Danger Signs to Check")
        lines.append("Ask about EACH of the following. If ANY is present, refer immediately.")
        lines.append("")
        for q in danger_signs:
            text = q["text"]
            if text and not text.startswith("["):
                lines.append(f"- {text}")
        lines.append("")

    # Assessment questions
    assessment = [q for q in parsed["questions"] if q["type"] == "assessment"]
    if assessment:
        lines.append("## Assessment Steps")
        lines.append("")
        for i, q in enumerate(assessment, 1):
            text = q["text"]
            if text and not text.startswith("[") and len(text) > 10:
                lines.append(f"{i}. {text}")
        lines.append("")

    # Decision logic
    if parsed["conditions"]:
        lines.append("## Decision Rules")
        lines.append("")
        for c in parsed["conditions"]:
            ref = c["ref"].split("/")[-1] if "/" in c["ref"] else c["ref"]
            lines.append(f"- **{ref}**: If any danger sign is present → REFER URGENTLY")
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
    args = parser.parse_args()

    if args.list:
        list_forms()
        return

    if args.form:
        forms = [args.form]
    elif args.all:
        forms = CLINICAL_FORMS
    else:
        forms = CLINICAL_FORMS

    converted = 0
    for form in forms:
        print(f"\nProcessing: {form}")
        path = convert_form(form)
        if path:
            converted += 1

    print(f"\nConverted {converted}/{len(forms)} forms to {OUTPUT_DIR}/")
    print("Next: run 'medlocal ingest data/core/cht-workflows/ --profile core' to ingest")


if __name__ == "__main__":
    main()
