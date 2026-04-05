# CHT Workflow: Pregnancy registration

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Risk Factors
- Is this
- Has
- If "None of the above" selected, cannot select any other option.
- Does
- Select all that apply.
- If "None of the above" selected, cannot select any other option.
- Does
- Select all that apply.
- Are there additional factors that could make this pregnancy high-risk?
- max characters = 100
- If yes, please describe.
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
- Risk Factors
- First pregnancy
- Previous miscarriages or stillbirths
- Previous difficulties in childbirth
- Has delivered four or more children
- Last baby born less than one year ago
- Heart condition
- Asthma
- High blood pressure
- Diabetes
- Danger Signs
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
- Please conduct a danger sign follow-up in 3 days.

## Assessment Steps

7. What is the patient's name?
10. Date of Birth
14. Gestational Age
15. How would you like to report the pregnancy?
16. Please enter the start date of the LMP.
17. Would you like to report the pregnancy in weeks or months?
19. Please enter the expected date of delivery.
20. You selected "No information is known."
21. Why do you want to register
22. ANC Visits at Health Facility (Past)
23. How many times has
24. Please enter the date if you know it.
25. ANC Visits at Health Facility (Scheduled)
26. Safe Pregnancy Practices
29. Unknown weeks pregnant.
30. Please attend ANC on:
31. Request the following services:
34. Iron folate
35. The WHO recommends routine ANC visits at 12, 20, 26, 30, 34, 36, 38, 40 weeks.
36. Follow-up Tasks
37. The following tasks will appear:
39. Please conduct the next pregnancy home visit in
40. Please conduct the next pregnancy home visit in 2 weeks.

## Decision Rules

- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **r_risk_factor_present**: If any danger sign is present → REFER URGENTLY
- **r_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **__has_risk_factors**: If any danger sign is present → REFER URGENTLY
- **__additional_high_risk_condition_to_report**: If any danger sign is present → REFER URGENTLY
- **__additional_high_risk_condition**: If any danger sign is present → REFER URGENTLY
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- Registering a pregnancy will help you to provide timely guidance and support to the pregnant woman.
- You entered an LMP of: **
- You entered the EDD: **
- The estimated date of delivery is: **
- If this seems incorrect, click "< Prev" and update the pregnancy information.
- Please enter the dates if you have them.
- Each "Visit" section below asks about one individual visit. Please complete all sections.
- The WHO recommends ANC visits at 12, 20, 26, 30, 34, 36, 38, 40 weeks.
- Great news! Please closely monitor her until her next scheduled pregnancy visit.
- Please refer to the health facility immediately. Accompany her if possible.

## When to Use This Workflow
- During antenatal care visits for pregnant women

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
