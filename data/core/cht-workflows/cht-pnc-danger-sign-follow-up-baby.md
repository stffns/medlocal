# CHT Workflow: PNC danger sign follow-up - baby

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Danger Sign Follow-up - Baby
- Was the baby taken to the health facility as recommended?
- Is the baby still experiencing any danger signs?
- Infected umbilical cord
- Convulsions
- Difficulty feeding or drinking
- Vomits everything
- Drowsy or unconscious
- Body stiffness
- Yellow skin color
- Fever
- Blue skin color (hypothermia)

## Assessment Steps

3. Delivery Report ID
4. What is the patient's name?
7. Date of Birth

## Decision Rules

- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **r_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **__still_experiencing_danger_sign**: If any danger sign is present → REFER URGENTLY
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- Please confirm if the baby has any of the following danger signs.
- Great news! Please continue to closely monitor the baby.
- The baby should be taken to the health facility immediately if experiencing any of these danger signs.
- Please advise the caregiver to do so and accompany them if possible.

## When to Use This Workflow
- Postnatal danger sign assessment for newborns

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
