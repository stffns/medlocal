# CHT Workflow: Pregnancy danger sign

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Danger Sign Check
- Vaginal bleeding
- Fits
- Severe abdominal pain
- Severe headache
- Very pale
- Fever
- Reduced or no fetal movements
- Breaking of water
- Getting tired easily
- Swelling of face and hands
- Breathlessness

## Assessment Steps

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
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- Great news! Please closely monitor her until her next scheduled pregnancy visit.
- Please refer to the health facility immediately. Accompany her if possible.
- Please complete the follow-up task within 3 days.

## When to Use This Workflow
- When a pregnant woman reports or presents with danger signs

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
