# CHT Workflow: Pregnancy danger sign follow-up

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Danger Sign Follow-up
- Did
- Is she still experiencing any danger signs?
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

5. What is the patient's name?
8. Date of Birth

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

- Great news! Please closely monitor her until her next scheduled ANC check-up at the health facility.
- The mother should visit the health facility immediately if she is experiencing any of these danger signs.
- Please advise her to do so and accompany her if possible.
- Please indicate which danger signs

## When to Use This Workflow
- Follow-up within 3 days after danger sign referral

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
