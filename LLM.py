import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GPT_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None
if client: print("OpenAI API configured successfully.")

def _call_llm(prompt):
    if not client: raise RuntimeError("OpenAI API not configured.")
    return client.chat.completions.create(model='gpt-4o-mini', messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip()

def generate_why_explanation(student_id, priority_score, avg_practice, avg_session, notes_count, notes_summary_text):
    return _call_llm(f"""You are an AI educational analyst at Noon Academy. Explain in a short, empathetic paragraph (2-3 sentences) why this student is flagged.
Student ID: {student_id}
Priority Score: {priority_score}/10
Avg Practice: {avg_practice} q/day (target >=10)
Avg Session: {avg_session} mins (target >=60)
Notes: {notes_count}
Summarized Notes: "{notes_summary_text}"
Focus on silent disengagement if low practice/session but no notes. Be concise. Do NOT use greetings (Dear Team, Hello).""")

def summarize_notes(student_id, notes_list):
    if not notes_list: return "No notes written yet. This student is currently invisible to the tracking system."
    notes_fmt = "\n".join([f"- [{n['date']}]: {n['note_text']}" for n in notes_list])
    return _call_llm(f"Summarize these facilitator notes for student '{student_id}' in one short, cohesive English paragraph (max 3 sentences). Focus on main obstacles and interventions.\nNotes:\n{notes_fmt}")

def calculate_notes_sentiment_adjustment(student_id, notes_list):
    if not notes_list: return 0.0
    notes_fmt = "\n".join([f"- [{n['date']}]: {n['note_text']}" for n in notes_list])
    try: return max(-2.0, min(2.0, float(_call_llm(f"Analyze notes for student {student_id}. Output ONLY a float between -2.0 (highly resolved/stable) and +2.0 (critical new risk) to adjust priority score.\nNotes:\n{notes_fmt}"))))
    except: return 0.0

def analyze_common_issues(student_data_list):
    if not client:
        raise RuntimeError("OpenAI API not configured.")
    
    import json
    
    # Format the data for the LLM concisely
    formatted_data = []
    for s in student_data_list:
        notes_str = " | ".join(s["notes"]) if s["notes"] else "No notes"
        formatted_data.append(
            f"Student {s['student_id']}: Practice={s['avg_daily_practice']} q/d, "
            f"Session={s['avg_daily_session_min']} min. Notes: {notes_str}"
        )
    
    data_input = "\n".join(formatted_data)
    
    prompt = f"""You are an educational data analyst. You are given a list of students, their daily metrics, and notes from their facilitators (written in Arabic/English).
Analyze the data and identify the most common recurring issues or root causes affecting student engagement, attendance, or practice activity.

Group the students into 3 to 5 distinct categories of issues. Each student can be associated with the primary issue they are facing.
Provide a clear, descriptive title for each issue (written in English, with brief Arabic examples in parentheses if relevant, e.g. "Gaming & Late Nights (سهر على الألعاب)"), and the count of students that fall into that category.

Ensure that the sum of counts makes sense relative to the total number of students.
Return ONLY a valid JSON array of objects, with no markdown styling (do NOT wrap in ```json ... ```), matching this structure:
[
  {{"issue": "Issue Name (Arabic translation/examples)", "count": 15}}
]

Data:
{data_input}
"""

    response = _call_llm(prompt)
    
    # Strip markdown code blocks if any
    if response.startswith("```"):
        response = response.strip("`").strip()
        if response.startswith("json"):
            response = response[4:].strip()
            
    return json.loads(response)
