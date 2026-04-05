# CHT Workflow: Pregnancy home visit

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Heart condition
- Asthma
- High blood pressure
- Diabetes
- None of the above
- Risk Factors
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
- New Risk Factors
- Heart condition
- Asthma
- High blood pressure
- Diabetes
- New Danger Signs
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

5. What is the patient's name?
8. Date of Birth
12. Pregnancy Summary
13. Current Weeks Pregnant: **
14. Current Weeks Pregnant: **unknown**
15. Expected Date of Delivery(EDD): **
16. Expected Date of Delivery(EDD): **unknown**
17. Do you want to start this pregnancy visit?
18. Is the gestational age above correct?
19. Update Pregnancy
20. Date of miscarriage
21. Date of abortion
22. What would you like to do?
23. Update Pregnancy
24. How would you like to update gestational age?
25. Please enter the new current weeks pregnant.
26. Please enter the new EDD.
27. **Previous**
28. Unknown weeks pregnant
29. EDD: unknown
31. ANC Visits at Health Facility (Past)
32. Did the woman complete the health facility ANC visit scheduled for
33. Would you like to report any additional unreported health facility ANC visits?
35. Please enter the date if you know it.
36. ANC Visits at Health Facility (Upcoming)
37. Safe Pregnancy Practices
40. Unknown weeks pregnant.
41. Please attend ANC on:
42. Request the following services:
45. Iron folate
46. The WHO recommends routine ANC visits at 12, 20, 26, 30, 34, 36, 38, 40 weeks.
47. Follow-up Tasks
48. The following tasks will appear:
50. Please conduct the next pregnancy home visit in
51. Please conduct the next pregnancy home visit in 2 weeks.

## Decision Rules

- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **risk_factors_ctx**: If any danger sign is present → REFER URGENTLY
- **risk_factor_extra_ctx**: If any danger sign is present → REFER URGENTLY
- **r_risk_factor_present**: If any danger sign is present → REFER URGENTLY
- **r_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **__has_risk_factors_not_previously_reported**: If any danger sign is present → REFER URGENTLY
- **__additional_high_risk_condition_to_report**: If any danger sign is present → REFER URGENTLY
- **__additional_high_risk_condition**: If any danger sign is present → REFER URGENTLY
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- You have reported the woman has had a miscarriage. If she has not been seen by a care provider, please refer to the health facility.
- You have reported the woman has had an abortion. If she has not been seen by a care provider, please refer to the health facility.
- You have reported the woman has refused care.
- You have reported the woman has moved out of the area.
- Submitting this form will end the pregnancy. You will not receive any additional tasks.
- You can still submit pregnancy visits from the profile until the EDD is reached.
- Click Submit to confirm.
- Click "< Prev" to go back.
- **Please confirm the new information and then click Next.**
- If this seems incorrect, click "< Prev" to update the pregnancy information.

## When to Use This Workflow
- Routine pregnancy home visit by CHW

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
