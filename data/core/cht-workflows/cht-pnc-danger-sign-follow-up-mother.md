# CHT Workflow: PNC danger sign follow-up - mother

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Danger Sign Follow-up - Mother
- Did
- Is she still experiencing any danger signs?
- Fever
- Severe headache
- Vaginal bleeding
- Foul smelling vaginal discharge
- Convulsions

## Assessment Steps

5. Delivery Report ID
6. What is the patient's name?
9. Date of Birth

## Decision Rules

- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **r_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **custom_woman_label_translator**: If any danger sign is present → REFER URGENTLY
- **custom_woman_label**: If any danger sign is present → REFER URGENTLY
- **custom_woman_start_label_translator**: If any danger sign is present → REFER URGENTLY
- **custom_woman_start_label**: If any danger sign is present → REFER URGENTLY
- **__still_experiencing_danger_sign**: If any danger sign is present → REFER URGENTLY
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- Please indicate which danger signs
- Great news! Please continue to closely monitor her.
- Please advise her to do so and accompany her if possible.

## When to Use This Workflow
- Postnatal danger sign assessment for mothers

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
