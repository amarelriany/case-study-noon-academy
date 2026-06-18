# **Diagnosis**

Facilitators spend too much time deciding which students to prioritize and what intervention to take, causing high-risk students to be missed. Student risk signals are scattered across attendance data, practice activity, quiz performance, and facilitator notes, requiring manual synthesis before action can be taken. As student volume grows, the absence of clear prioritization and workload management makes intervention coverage impossible to scale.

# **What’s found in the data**

- **Facilitator notes and behavioral metrics were internally consistent.** Notes in `facilitator_notes.csv` frequently aligned with attendance and engagement patterns in `student_daily_metrics.csv` through the shared `student_id`. For example, a note for S190 describing attendance dropping from 90 to 20 minutes matched the corresponding attendance record, making the two datasets suitable for joint analysis despite the synthetic nature of the data.
- while In `student_metadata.csv`, students are assigned to facilitators in contiguous ID ranges (e.g., `facilitator1@noon.com` manages S001–S020, `facilitator2@noon.com` manages S021–S040) which doesn’t align with both `facilitator_notes.csv` and `student_daily_metrics.csv` .
- The busiest facilitator handled 4× more students than the least busy facilitator & Three facilitators account for 40% of all intervention activity indicating there’s no workload management system
- **A significant number of students had no documented facilitator interaction despite having measurable engagement data.** This created an "invisibility" problem where students could decline for days without appearing in any facilitator workflow.

# What I built & why

- **Student Risk Engine** - Calculated a risk score based on weather students are declining or improving, practice completion, quiz performance, number of notes facilitator, to identify students most likely to fall behind before the next quiz.
- **Facilitator Action Queue** - Converted risk scores into a ranked daily intervention list so facilitators know exactly who to help first.
- **Recommendation Layer** - Generated the highest-impact next action and root cause for each student to reduce facilitator decision-making overhead.
- **AI Intelligence Layer** - Used LLMs to extract signals from facilitator notes and add risk score from 0.1 to 2, explain risk scores, and identify recurring patterns across struggling students.

---

# **What I cut and why**

- **Authentication and role-based access control:** I deferred authentication because it does not improve intervention coverage; given the two-day timeline, I prioritized risk identification and facilitator workflows over production infrastructure concerns.
- **One click or fully automated personalized messages:** since we don’t have a reliable way to find parents numbers yet.

# **What I'd build next**

- **Intervention outcome tracking:** I would add a feedback loop that records whether interventions were completed and measures their impact on subsequent student engagement and quiz performance. This would allow the system to learn which interventions are most effective for different risk patterns and continuously improve prioritization quality.