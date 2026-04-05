# CHT Workflow: Delivery

*Decision support workflow from Community Health Toolkit (CHT)*
*Used by 40,000+ community health workers in 15 countries*

## Danger Signs to Check
Ask about EACH of the following. If ANY is present, refer immediately.

- Postnatal Danger Sign Check - Woman
- Fever
- Severe headache
- Vaginal bleeding
- Foul smelling vaginal discharge
- Convulsions
- Danger signs
- Please conduct a danger sign follow-up for the mother in 3 days.
- Please conduct a danger sign follow-up for the baby in 3 days.

## Assessment Steps

5. What is the patient's name?
8. Date of Birth
9. Household ID
11. Health Facility ID
14. What is the outcome for the woman?
15. Death Information - Woman
16. Date of death
17. What was the place of death?
18. Did the woman deliver any babies before she died?
19. Delivery Outcome
20. How many babies were delivered?
21. How many babies are alive?
22. Date of delivery
23. Where did delivery take place?
24. Please specify other
25. How did she deliver?
26. Who conducted the delivery?
27. Please specify other
28. Death Information - Baby
29. Date of death
30. Place of death
31. Was this a stillbirth?
33. Health Facility ID
34. Baby's Condition
35. What is the condition of baby?
36. Birth weight
37. Birth length
38. What vaccines have they received?
39. Is the child exclusively breastfeeding?
40. Were they initiated on breastfeeding within on hour of delivery?
41. Infected umbilical cord
42. Convulsions
43. Difficulty feeding or drinking
44. Vomits everything
45. Drowsy or unconscious
46. Body stiffness
47. Yellow skin color
48. Blue skin color (hypothermia)
50. Health Facility ID
51. Safe Postnatal Practices
52. Lactating mothers need to eat more than usual to feed their baby well. Ask the woman to eat a variety of foods, especially extra fluids, fruits, and vegetables.
53. For the first 6 months, give the baby breastmilk only.
54. To keep the baby warm, use kangaroo mother care, wrap the baby with clothes and cover the head, and keep the baby in a warm room.
55. Always sleep with the baby under a long-lasting insecticide treated net (LLIN).
56. Keep the baby's umbilical cord clean and dry.
58. Which PNC visits have taken place so far?
59. Any additional PNC visits, please report the number of visits below to be counted in the total.
61. Pregnancy Outcome
62. Woman's Condition
63. Alive and well
64. Alive and unwell
66. Date of Death:
67. Place of Death:
68. Delivery Details
69. Date of Delivery:
70. Place of Delivery:
71. Number of babies delivered:
72. Number of babies deceased:
73. Severe headache
74. Vaginal bleeding
75. Foul smelling vaginal discharge
76. Convulsions
78. PNC visits completed so far:
83. Additional PNC visits completed:
84. Mom is alive and unwell
85. Follow-up Tasks
86. The following tasks will appear:

## Decision Rules

- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **r_pnc_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **r_baby_danger_sign_present**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up**: If any danger sign is present → REFER URGENTLY
- **t_danger_signs_referral_follow_up_date**: If any danger sign is present → REFER URGENTLY
- **infected_umbilical_cord**: If any danger sign is present → REFER URGENTLY
- **convulsion**: If any danger sign is present → REFER URGENTLY
- **difficulty_feeding**: If any danger sign is present → REFER URGENTLY
- **vomit**: If any danger sign is present → REFER URGENTLY
- **drowsy**: If any danger sign is present → REFER URGENTLY
- **stiff**: If any danger sign is present → REFER URGENTLY
- **yellow_skin**: If any danger sign is present → REFER URGENTLY
- **fever**: If any danger sign is present → REFER URGENTLY
- **blue_skin**: If any danger sign is present → REFER URGENTLY
- **r_baby_danger_sign_present_joined**: If any danger sign is present → REFER URGENTLY
- **r_baby_danger_sign_present_any**: If any danger sign is present → REFER URGENTLY
- **__has_danger_sign**: If any danger sign is present → REFER URGENTLY

## Instructions for Health Worker

- Does the woman have any of the following danger signs?
- After reporting a death, the person's profile will be locked. If reported in error, you may undo the death report from the profile.
- If babies were delivered, you will have the chance to report on them Next >.
- Maximum 300 characters allowed.
- Additional notes about baby's death
- Sections will repeat if multiple babies were delivered. Please fill out one section per baby.
- Please counsel the family and refer the child to the nearest health center where the baby can be immunized.
- Does the baby have any of the following danger signs?
- The WHO recommends PNC visits within 24 hours and on 3 days, 7 days, and 6 weeks from date of delivery.
- To finish, be sure to click the Submit button.

## When to Use This Workflow
- During or immediately after delivery

Source: Community Health Toolkit (CHT) — medic/cht-core reference app (MIT License)
