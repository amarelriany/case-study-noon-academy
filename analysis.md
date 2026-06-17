# **Diagnosis**

facilitators waste a lot of time in:

- Thinking what students to prioritize & what actions to take
- Facilitators don't have clear operational targets or workload management so they achieve the 80% intervention goal
- Risk Signals Are Fragmented Across Multiple Sources

# **What’s found in the data**

- **Facilitator notes are strongly grounded in operational data.** Notes in `facilitator_notes.csv` consistently match behavioral signals in `student_daily_metrics.csv` through the shared `student_id`. For example, a note for **S190** states *"ليلى حضورها نزل فجأة من ٩٠ دقيقة الى ٢٠ دقيقة"*, and the corresponding metrics record shows `session_attended_min = 20` on **2025-10-07**, followed by continued attendance decline in subsequent days.
- **Facilitator assignment appears to follow a synthetic sequential pattern rather than a real operational distribution.** In `student_metadata.csv`, students are assigned to facilitators in contiguous ID blocks (e.g., `facilitator1@noon.com` manages **S001–S020**, `facilitator2@noon.com` manages **S021–S040**, etc.). This suggests the dataset was generated with evenly partitioned workloads and may not reflect the imbalance or complexity of real facilitator assignments.
- The busiest facilitator handled 4× more students than the least busy facilitator & Three facilitators account for 40% of all intervention activity indicating there’s no workload management system
- **20 failing students received no documented intervention**, while facilitator effort was unevenly distributed across the student population, indicating a prioritization problem rather than a lack of intervention capacity.

# What I built & why

- **Reliable Data Foundation** - Built the MVP using only `facilitator_notes.csv` and `student_daily_metrics.csv` because they were the only datasets with verifiable cross-file consistency.
- **Student Risk Engine** - Calculated a risk score from attendance trends, practice completion, quiz performance, and facilitator observations to identify students most likely to fall behind before the next quiz.
- **Facilitator Action Queue** - Converted risk scores into a ranked daily intervention list so facilitators know exactly who to help first.
- **Recommendation Layer** - Generated the highest-impact next action and root cause for each student to reduce facilitator decision-making overhead.
- **AI Intelligence Layer** - Used LLMs to extract signals from facilitator notes, explain risk scores, and identify recurring patterns across struggling students.

---

# **What I cut and why**

- Using any column in **student_metadata.csv** since their are no common identical columns between it and **facilitator_notes.csv** or **student_daily_metrics.csv** which means I avoided using target score, or messaging parents

# **What I'd build next**

- **Metadata recovery and validation layer:** I would build a metadata reconciliation step that flags unreliable fields, validates student identity and contact data, and separates usable routing fields from synthetic or missing attributes. This would let the system safely support parent outreach, personalized messages, and facilitator-level reporting without inventing names, phone numbers, or ownership data.