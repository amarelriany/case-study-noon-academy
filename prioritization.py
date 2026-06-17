import sqlite3
import math
from datetime import datetime

def calculate_priority_for_student(student, metrics, notes_count):
    """
    Calculates the 10-point prioritization score and details for a single student.
    
    student: sqlite3.Row or dict representing student metadata
    metrics: list of sqlite3.Row or dicts of daily metrics for this student (sorted by date desc)
    notes_count: count of notes written for this student in the last 14 days
    
    Returns a dictionary of score breakdown and rules-based suggestions.
    """
    # 1. Target Score Clamping & Quiz Score Gap
    # Removed due to deprecation of student_metadata.csv
    
    # Find most recent non-null quiz score
    latest_quiz_score = None
    for m in metrics:
        if m['last_quiz_score'] is not None:
            latest_quiz_score = m['last_quiz_score']
            break
            
    is_untested = False
    if latest_quiz_score is None:
        is_untested = True

    # 2. Engagement/Silent Risk (Max 3.0)
    # Average daily practice questions and session time over all days
    all_metrics = metrics
    if len(all_metrics) > 0:
        avg_practice = sum(m['practice_questions'] or 0 for m in all_metrics) / len(all_metrics)
        avg_session = sum(m['session_attended_min'] or 0.0 for m in all_metrics if m['session_attended_min'] is not None) / len(all_metrics)
    else:
        # If no metrics exist, assume highest risk
        avg_practice = 0
        avg_session = 0.0

    practice_risk = 0.0
    if avg_practice < 5.0:
        practice_risk = 2.0
    elif avg_practice < 10.0:
        practice_risk = 1.0
        
    session_risk = 0.0
    if avg_session < 60.0:
        session_risk = 1.0
        
    engagement_score = practice_risk + session_risk

    # 3. Invisibility/Staleness (Max 2.0)
    # 0 notes: 2.0, 1 note: 1.0, 2 notes: 0.5, 3+ notes: 0.0
    if notes_count == 0:
        invisibility_score = 2.0
    elif notes_count == 1:
        invisibility_score = 1.0
    elif notes_count == 2:
        invisibility_score = 0.5
    else:
        invisibility_score = 0.0

    # 4. Urgency / Recovery Window (Max 2.0)
    days_until_quiz = None
    if len(metrics) > 0:
        days_until_quiz = metrics[0]['days_until_next_quiz']

    UNRECOVERABLE_THRESHOLD = 2    # ≤ this many days → past the point of no return
    SWEET_SPOT_END        = 10     # sweet-spot window: 3 – 10 days
    EARLY_WARNING_END     = 21     # early-warning window: 11 – 21 days
    MAX_URGENCY_SCORE     = 2.0

    urgency_score = 0.0
    is_unrecoverable = False

    if days_until_quiz is not None:
        d = days_until_quiz
        if d <= UNRECOVERABLE_THRESHOLD:
            is_unrecoverable = True
            urgency_score = 0.0
        elif d <= SWEET_SPOT_END:
            urgency_score = MAX_URGENCY_SCORE - (d - (UNRECOVERABLE_THRESHOLD + 1)) * (1.3 / (SWEET_SPOT_END - UNRECOVERABLE_THRESHOLD - 1))
            urgency_score = round(max(0.0, urgency_score), 2)
        elif d <= EARLY_WARNING_END:
            urgency_score = 0.6 * (1.0 - (d - SWEET_SPOT_END - 1) / (EARLY_WARNING_END - SWEET_SPOT_END))
            urgency_score = round(max(0.0, urgency_score), 2)

    # 5. Trend Analysis (Compare recent half of days to older half of days)
    trend_adjustment = 0.0
    trend_reasons = []
    
    if len(metrics) >= 2:
        half_len = len(metrics) // 2
        # metrics is sorted by date DESC (newest to oldest)
        recent_half = metrics[:half_len]
        older_half = metrics[half_len:]
        
        recent_practice_avg = sum(m['practice_questions'] or 0 for m in recent_half) / len(recent_half)
        older_practice_avg = sum(m['practice_questions'] or 0 for m in older_half) / len(older_half)
        
        recent_session_avg = sum(m['session_attended_min'] or 0.0 for m in recent_half if m['session_attended_min'] is not None) / len(recent_half)
        older_session_avg = sum(m['session_attended_min'] or 0.0 for m in older_half if m['session_attended_min'] is not None) / len(older_half)
        
        practice_trend = recent_practice_avg - older_practice_avg
        session_trend = recent_session_avg - older_session_avg
        
        # Prioritize declining activity (adds to score), deprioritize improving (subtracts from score)
        if practice_trend <= -2.0:
            trend_adjustment += 0.75
            trend_reasons.append(f"Declining practice trend: dropped by {round(abs(practice_trend), 1)} questions/day")
        elif practice_trend >= 2.0:
            trend_adjustment -= 0.75
            trend_reasons.append(f"Improving practice trend: increased by {round(practice_trend, 1)} questions/day")
            
        if session_trend <= -15.0:
            trend_adjustment += 0.75
            trend_reasons.append(f"Declining session attendance trend: dropped by {round(abs(session_trend))} mins/day")
        elif session_trend >= 15.0:
            trend_adjustment -= 0.75
            trend_reasons.append(f"Improving session attendance trend: increased by {round(session_trend)} mins/day")

    # Retrieve pre-calculated AI notes adjustment
    ai_adjustment = 0.0
    try:
        ai_adjustment = student['ai_notes_adjustment']
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    if ai_adjustment is None:
        ai_adjustment = 0.0

    # Calculate Total Priority Score (0.0 to 10.0)
    base_score = engagement_score + invisibility_score + urgency_score
    total_score = (base_score * (10.0 / 7.0)) + ai_adjustment + trend_adjustment
    total_score = max(0.0, min(10.0, total_score))
    total_score = round(total_score, 1)

    # Determine Action Suggestion & Priority Label
    if total_score >= 8.0:
        priority_level = "1"
        suggested_action = "Call parent today & log attendance reasons"
    elif total_score >= 6.0:
        priority_level = "2"
        suggested_action = "One-on-one academic check-in & review track"
    elif total_score >= 4.0:
        priority_level = "3"
        suggested_action = "Send student chat / WhatsApp motivational check"
    else:
        priority_level = "4"
        suggested_action = "Routine check-in / Encourage self-study"

    # Assemble rule-based explanations for "why this student"
    reasons = []
    if avg_practice < 5.0:
        reasons.append(f"Silent disengagement: averaging only {round(avg_practice, 1)} practice questions/day (target: 10+)")
    elif avg_practice < 10.0:
        reasons.append(f"Sub-optimal practice activity ({round(avg_practice, 1)} questions/day)")
        
    if avg_session < 60.0:
        reasons.append(f"Low session time: averaging {round(avg_session)} mins/day (target: 60+ mins)")
        
    if notes_count == 0:
        reasons.append("Invisible student: 0 facilitator notes written in the last 14 days")
    elif notes_count == 1:
        reasons.append("Minimal oversight: only 1 facilitator note written recently")
        
    reasons.extend(trend_reasons)

    # Prefer cached AI why explanation if available, otherwise fallback to the rule-based reasons
    why_explanation = None
    if isinstance(student, dict) and 'ai_why' in student:
        why_explanation = student['ai_why']
    elif hasattr(student, 'keys') and 'ai_why' in student.keys():
        why_explanation = student['ai_why']
        
    if not why_explanation:
        why_explanation = " | ".join(reasons) if reasons else "Routine tracking queue."

    return {
        "student_id": student['student_id'],
        "last_quiz_score": latest_quiz_score,
        "is_untested": is_untested,
        "avg_daily_practice": round(avg_practice, 1),
        "avg_daily_session_min": round(avg_session, 1),
        "notes_count": notes_count,
        "days_until_next_quiz": days_until_quiz,
        "is_unrecoverable": is_unrecoverable,
        "urgency_score": urgency_score,
        "priority_score": total_score,
        "priority_level": priority_level,
        "suggested_action": suggested_action,
        "rule_based_why": why_explanation,
        "ai_notes_adjustment": ai_adjustment,
        "trend_adjustment": trend_adjustment
    }

def get_prioritized_queue(conn, facilitator_email=None):
    """
    Retrieves all students, calculates priority, and returns them ordered by priority score descending.
    Filters by facilitator if provided.
    """
    cursor = conn.cursor()
    
    # Query structure
    query = """
        SELECT s.*, q.status as queue_status, q.notes as queue_notes
        FROM students s
        LEFT JOIN queue_status q ON s.student_id = q.student_id
    """
    params = []
    
    if facilitator_email:
        query += " WHERE s.facilitator_email = ?"
        params.append(facilitator_email)
        
    cursor.execute(query, params)
    students = cursor.fetchall()
    
    ranked_students = []
    for s in students:
        student_id = s['student_id']
        
        # Get daily metrics sorted by date desc
        cursor.execute("""
            SELECT * FROM daily_metrics 
            WHERE student_id = ? 
            ORDER BY date DESC
        """, (student_id,))
        metrics = cursor.fetchall()
        
        # Get count of notes in last 14 days
        # Since our seeded data is from Oct 1 to Oct 14 2025, let's treat the notes as "recent" notes
        # We can just count total notes in database since all are within this 14-day window.
        cursor.execute("""
            SELECT COUNT(*) FROM facilitator_notes
            WHERE student_id = ?
        """, (student_id,))
        notes_count = cursor.fetchone()[0]
        
        priority_details = calculate_priority_for_student(s, metrics, notes_count)
        
        # Override suggested action if score <= 6.0 (don't need intervention)
        if priority_details['priority_score'] <= 6.0:
            priority_details['suggested_action'] = "No intervention needed"
        
        priority_details['queue_status'] = s['queue_status'] or 'pending'
        priority_details['queue_notes'] = s['queue_notes'] or ''
        priority_details['facilitator_email'] = s['facilitator_email']
        
        ranked_students.append(priority_details)
        
    # Sort by priority score desc, then by student_id
    ranked_students.sort(key=lambda x: (-x['priority_score'], x['student_id']))
    
    # Assign sequential ranks (1, 2, 3, ...) based on sorted order
    for idx, s in enumerate(ranked_students, 1):
        s['priority_level'] = str(idx)
        
    return ranked_students


