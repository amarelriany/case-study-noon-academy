import os
import sqlite3
import math
from datetime import datetime
from flask import Flask, jsonify, request, render_template
from database import get_db_connection, init_db, seed_db, validate_phone
from prioritization import get_prioritized_queue, calculate_priority_for_student
from LLM import generate_why_explanation, summarize_notes, calculate_notes_sentiment_adjustment

app = Flask(__name__)

# DB initialization is handled on startup when run directly

@app.route('/')
def home():
    """Renders the dashboard SPA."""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Returns general config info (facilitator emails, campuses)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT facilitator_email FROM students ORDER BY facilitator_email")
    emails = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({
        "facilitator_emails": emails,
        "campuses": []
    })

@app.route('/api/queue', methods=['GET'])
def get_queue():
    """
    Returns the prioritized student queue and workload targets KPI.
    Query params: facilitator_email, status (default: all)
    """
    email = request.args.get('facilitator_email')
    status = request.args.get('status', 'all')
    
    conn = get_db_connection()
    # Get the global queue to calculate global targets
    global_queue = get_prioritized_queue(conn, facilitator_email=None)
    
    # Identify target students for intervention (risk score > 6.0)
    target_students = [s for s in global_queue if s['priority_score'] > 6.0]
    total_target_students = len(target_students)
    
    # 80% intervention rate target globally
    global_interventions_needed = math.ceil(total_target_students * 0.8)
    
    # Get distinct facilitators
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT facilitator_email FROM students WHERE facilitator_email IS NOT NULL AND facilitator_email != ''")
    all_facils = [r[0] for r in cursor.fetchall()]
    num_facils = len(all_facils) if all_facils else 1
    
    # Target per facilitator
    target_per_facil = math.ceil(global_interventions_needed / num_facils)
    
    workload_targets = {
        "global_target": global_interventions_needed,
        "target_per_facil": target_per_facil,
        "total_high_risk_failed": total_target_students
    }
    
    if email:
        # Calculate how many of the target students this facilitator has completed
        facil_target_students = [s for s in target_students if s['facilitator_email'] == email]
        completed_interventions = len([s for s in facil_target_students if s['queue_status'] in ['completed', 'ignored']])
        interventions_left = max(0, target_per_facil - completed_interventions)
        
        workload_targets["facilitator_completed"] = completed_interventions
        workload_targets["interventions_left"] = interventions_left
        
        all_queue = [s for s in global_queue if s['facilitator_email'] == email]
    else:
        completed_global = len([s for s in target_students if s['queue_status'] in ['completed', 'ignored']])
        workload_targets["interventions_left"] = max(0, global_interventions_needed - completed_global)
        all_queue = global_queue
    
    # Filter by queue status
    if status != 'all':
        all_queue = [s for s in all_queue if s['queue_status'] == status]
        
    # Assign sequential ranks for the final filtered view
    for idx, s in enumerate(all_queue, 1):
        s['priority_level'] = str(idx)
        
    conn.close()
    return jsonify({
        "queue": all_queue,
        "workload_targets": workload_targets
    })

@app.route('/api/student/<student_id>', methods=['GET'])
def get_student_detail(student_id):
    """
    Returns full details for a student:
    - Metadata
    - Historical notes
    - Metrics (daily logs)
    - AI-generated why explanation, notes summary, and WhatsApp/SMS templates
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch metadata
    cursor.execute("""
        SELECT s.*, q.status as queue_status, q.notes as queue_notes
        FROM students s
        LEFT JOIN queue_status q ON s.student_id = q.student_id
        WHERE s.student_id = ?
    """, (student_id,))
    student_row = cursor.fetchone()
    
    if not student_row:
        conn.close()
        return jsonify({"error": "Student not found"}), 404
        
    student = dict(student_row)
    
    # 2. Fetch daily metrics
    cursor.execute("""
        SELECT * FROM daily_metrics 
        WHERE student_id = ? 
        ORDER BY date ASC
    """, (student_id,))
    metrics = [dict(row) for row in cursor.fetchall()]
    
    # 3. Fetch notes
    cursor.execute("""
        SELECT * FROM facilitator_notes 
        WHERE student_id = ? 
        ORDER BY date DESC
    """, (student_id,))
    notes = [dict(row) for row in cursor.fetchall()]
    
    # 4. Fetch intervention logs
    cursor.execute("""
        SELECT * FROM facilitator_actions 
        WHERE student_id = ? 
        ORDER BY created_at DESC
    """, (student_id,))
    actions = [dict(row) for row in cursor.fetchall()]
    
    # Calculate current priorities
    metrics_desc = sorted(metrics, key=lambda x: x['date'], reverse=True)
    priority_info = calculate_priority_for_student(student, metrics_desc, len(notes))
    
    # Calculate sequential rank globally
    global_queue = get_prioritized_queue(conn)
    rank = next((idx for idx, s in enumerate(global_queue, 1) if s['student_id'] == student_id), 1)
    priority_info['priority_level'] = str(rank)
    
    # 5. Integrate AI content
    cached_summary = student.get('ai_summary')
    cached_why = student.get('ai_why')
    if cached_summary and cached_why:
        ai_summary = cached_summary
        ai_why = cached_why
    else:
        try:
            # Summarize notes
            ai_summary = summarize_notes(student_id, notes)
            
            # Explaining why this student is in the queue
            ai_why = generate_why_explanation(
                student_id=student_id,
                priority_score=priority_info['priority_score'],
                avg_practice=priority_info['avg_daily_practice'],
                avg_session=priority_info['avg_daily_session_min'],
                notes_count=priority_info['notes_count'],
                notes_summary_text=ai_summary
            )
            
            # Draft messages
            recent_perf_desc = f"{priority_info['avg_daily_practice']} أسئلة باليوم وحضور {priority_info['avg_daily_session_min']} دقيقة"
            parent_draft = draft_arabic_message(
                student_id=student_id,
                recent_performance=recent_perf_desc,
                message_type='parent_whatsapp'
            )
            
            student_draft = draft_arabic_message(
                student_id=student_id,
                recent_performance=recent_perf_desc,
                message_type='student_whatsapp'
            )

            # Update cache in the database
            cursor.execute("""
                UPDATE students 
                SET ai_summary = ?, ai_why = ?
                WHERE student_id = ?
            """, (ai_summary, ai_why, student_id))
            conn.commit()
            
        except Exception as e:
            ai_summary = f"AI summary unavailable: {e}"
            ai_why = f"AI why unavailable: {e}"

    conn.close()
    
    return jsonify({
        "metadata": {
            **student,
            "priority_score": priority_info['priority_score'],
            "priority_level": priority_info['priority_level'],
            "suggested_action": priority_info['suggested_action'],
            "avg_daily_practice": priority_info['avg_daily_practice'],
            "avg_daily_session_min": priority_info['avg_daily_session_min'],
            "last_quiz_score": priority_info['last_quiz_score'],
            "queue_status": student['queue_status'] or 'pending',
            "queue_notes": student['queue_notes'] or ''
        },
        "metrics": metrics,
        "notes": notes,
        "actions_log": actions,
        "ai_analysis": {
            "summary": ai_summary,
            "why_prioritized": ai_why
        }
    })

@app.route('/api/student/<student_id>/note', methods=['POST'])
def add_note(student_id):
    """Adds a new note for a student."""
    data = request.get_json() or {}
    note_text = data.get('note_text', '').strip()
    facil_email = data.get('facilitator_email', '').strip()
    
    if not note_text:
        return jsonify({"error": "Note text cannot be empty"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify student exists and get details
    cursor.execute("SELECT facilitator_email FROM students WHERE student_id = ?", (student_id,))
    student_row = cursor.fetchone()
    if not student_row:
        conn.close()
        return jsonify({"error": "Student not found"}), 404
        
    if not facil_email:
        facil_email = student_row['facilitator_email']
        
    note_id = f"N_{student_id}_{int(datetime.now().timestamp())}"
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("""
        INSERT INTO facilitator_notes (note_id, student_id, facilitator_email, date, note_text)
        VALUES (?, ?, ?, ?, ?)
    """, (note_id, student_id, facil_email, date_str, note_text))
    
    # Also log it as an action
    cursor.execute("""
        INSERT INTO facilitator_actions (student_id, action_type, notes, created_at)
        VALUES (?, 'facilitator_note', ?, ?)
    """, (student_id, f"Added note: {note_text[:50]}...", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    # Re-calculate and update AI notes priority adjustment
    cursor.execute("SELECT * FROM facilitator_notes WHERE student_id = ?", (student_id,))
    notes_list = [dict(row) for row in cursor.fetchall()]
    try:
        ai_adjustment = calculate_notes_sentiment_adjustment(student_id, notes_list)
    except Exception as e:
        print(f"Error calculating sentiment adjustment for S{student_id}: {e}")
        ai_adjustment = 0.0
        
    cursor.execute("UPDATE students SET ai_notes_adjustment = ? WHERE student_id = ?", (ai_adjustment, student_id))
    
    # Invalidate AI analysis cache since new notes have been added
    cursor.execute("""
            UPDATE students 
            SET ai_summary = NULL, ai_why = NULL
            WHERE student_id = ?
    """, (student_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "note_id": note_id})



@app.route('/api/student/<student_id>/action', methods=['POST'])
def submit_intervention_action(student_id):
    """Marks a student queue status as 'completed' or 'ignored', moving them out of active queue."""
    data = request.get_json() or {}
    status = data.get('status') # 'completed', 'ignored', 'pending'
    notes = data.get('notes', '').strip()
    action_type = data.get('action_type', 'other') # 'call_parent', 'one_on_one', etc.
    
    if status not in ['completed', 'ignored', 'pending']:
        return jsonify({"error": "Invalid status. Must be 'completed', 'ignored', or 'pending'"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if student exists
    cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Student not found"}), 404
        
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        INSERT OR REPLACE INTO queue_status (student_id, status, updated_at, notes)
        VALUES (?, ?, ?, ?)
    """, (student_id, status, now_str, notes))
    
    # Log the action history
    cursor.execute("""
        INSERT INTO facilitator_actions (student_id, action_type, notes, created_at)
        VALUES (?, ?, ?, ?)
    """, (student_id, action_type, f"Queue status set to '{status}'. Notes: {notes}", now_str))
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "status": status})

@app.route('/api/student/add', methods=['POST'])
def add_new_student():
    """Adds a new student with minimal fields."""
    data = request.get_json() or {}
    
    student_id = data.get('student_id', '').strip()
    facilitator_email = data.get('facilitator_email', '').strip()
    
    # Validations
    if not student_id or not facilitator_email:
        return jsonify({"error": "ID and Facilitator Email are required"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Unique ID validation
    cursor.execute("SELECT student_id FROM students WHERE student_id = ?", (student_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": f"Student ID '{student_id}' already exists in the system"}), 400
        
    cursor.execute("""
        INSERT INTO students (
            student_id, facilitator_email
        ) VALUES (?, ?)
    """, (student_id, facilitator_email))
    
    # Queue init
    cursor.execute("""
        INSERT INTO queue_status (student_id, status, updated_at)
        VALUES (?, 'pending', ?)
    """, (student_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    # Log addition
    cursor.execute("""
        INSERT INTO facilitator_actions (student_id, action_type, notes, created_at)
        VALUES (?, 'student_added', ?, ?)
    """, (student_id, "Student manually registered in database", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    # Invalidate cached issues impact matrix
    cursor.execute("DELETE FROM system_cache WHERE cache_key = 'main_issues_impact'")
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True, 
        "student_id": student_id
    })

@app.route('/api/admin/metrics', methods=['GET'])
def get_admin_metrics():
    """
    Returns high-level statistics for the admin dashboard.
    - Campus-level performance (highlighting C04 and C05)
    - Invisibility index (notes distribution, showing clustering)
    - Facilitator metrics
    - Main issues impact categorizations
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total overview
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM facilitator_notes")
    total_notes = cursor.fetchone()[0]
    
    # Campus averages removed due to deprecation of student_metadata.csv
    # 3. Notes clustering / Invisibility Index
    # Find how many notes each student has
    cursor.execute("""
        SELECT s.student_id, COUNT(n.note_id) as note_count
        FROM students s
        LEFT JOIN facilitator_notes n ON s.student_id = n.student_id
        GROUP BY s.student_id
    """)
    notes_distribution = cursor.fetchall()
    
    notes_count_buckets = {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0}
    
    for row in notes_distribution:
        cnt = row['note_count']
        if cnt >= 4:
            notes_count_buckets["4+"] += 1
        else:
            notes_count_buckets[str(cnt)] += 1

    # Invisibility rate: percent of students with 0 notes
    invisible_students_count = notes_count_buckets["0"]
    invisibility_index_pct = (invisible_students_count / total_students) * 100 if total_students > 0 else 0
    
    # 4. Facilitator activity
    cursor.execute("""
        SELECT facilitator_email, COUNT(note_id) as total_notes_written
        FROM facilitator_notes
        GROUP BY facilitator_email
        ORDER BY total_notes_written DESC
    """)
    facil_activity = [dict(row) for row in cursor.fetchall()]
    
    # 5. Main Issues Impact Categorization (Dynamic via AI, Cached)
    # We load all ranked students and analyze their issues using LLM, caching results
    import json
    cursor.execute("SELECT cache_value FROM system_cache WHERE cache_key = 'main_issues_impact'")
    cached_row = cursor.fetchone()
    if cached_row:
        issues_impact = json.loads(cached_row['cache_value'])
        all_ranked = get_prioritized_queue(conn)
    else:
        all_ranked = get_prioritized_queue(conn)
        try:
            student_data_list = []
            for s in all_ranked:
                cursor.execute("SELECT note_text FROM facilitator_notes WHERE student_id = ?", (s['student_id'],))
                notes = [row['note_text'] for row in cursor.fetchall()]
                student_data_list.append({
                    "student_id": s['student_id'],
                    "avg_daily_practice": s['avg_daily_practice'],
                    "avg_daily_session_min": s['avg_daily_session_min'],
                    "notes": notes
                })
            from LLM import analyze_common_issues
            issues_impact = analyze_common_issues(student_data_list)
            issues_impact.sort(key=lambda x: -x['count'])
            # Save to cache
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT OR REPLACE INTO system_cache (cache_key, cache_value, updated_at) VALUES ('main_issues_impact', ?, ?)", (json.dumps(issues_impact), now_str))
            conn.commit()
        except Exception as e:
            print(f"Error calling LLM for issues impact: {e}. Falling back to rule-based categorization.")
            issues_buckets = {
                "Silent Disengagement (Ghost)": 0,
                "Zero Practice Activity (Practice < 1/day)": 0,
                "Transportation & Attendance (Session < 30 mins)": 0
            }
            for s in all_ranked:
                if s['avg_daily_practice'] < 5.0 and s['avg_daily_session_min'] < 60.0 and s['notes_count'] == 0:
                    issues_buckets["Silent Disengagement (Ghost)"] += 1
                if s['avg_daily_practice'] < 1.0:
                    issues_buckets["Zero Practice Activity (Practice < 1/day)"] += 1
                if s['avg_daily_session_min'] < 30.0:
                    issues_buckets["Transportation & Attendance (Session < 30 mins)"] += 1
            issues_impact = [{"issue": k, "count": v} for k, v in issues_buckets.items()]
            issues_impact.sort(key=lambda x: -x['count'])



    target_students = [s for s in all_ranked if s['priority_score'] > 6.0]
    total_target_students = len(target_students)
    global_interventions_needed = math.ceil(total_target_students * 0.8)
    completed_global = len([s for s in target_students if s['queue_status'] in ['completed', 'ignored']])
    interventions_left = max(0, global_interventions_needed - completed_global)

    conn.close()
    
    return jsonify({
        "overall": {
            "total_students": total_students,
            "total_notes": total_notes,
            "invisible_students": invisible_students_count,
            "invisibility_index_pct": round(invisibility_index_pct, 1),
            "interventions_left": interventions_left
        },
        "campus_performance": [],
        "notes_distribution": {
            "buckets": notes_count_buckets,
            "description": "Demonstrates facilitator attention clustering around a small group of students while 62.5% remain invisible."
        },
        "facilitator_activity": facil_activity,
        "main_issues_impact": issues_impact
    })

if __name__ == '__main__':
    # Ensure DB is initialized and seeded before handling requests when run directly
    with app.app_context():
        init_db()
        seed_db()
        # Pre-calculate AI adjustments and cache text
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check which students need AI calculations (those with no ai_why)
        cursor.execute("""
            SELECT student_id 
            FROM students 
            WHERE ai_why IS NULL
        """)
        ids_to_process = [row['student_id'] for row in cursor.fetchall()]

        if ids_to_process:
            print(f"Calculating AI cache for {len(ids_to_process)} students. This may take a moment...")
            
            # Fetch all needed data sequentially
            tasks_data = []
            for s_id in ids_to_process:
                cursor.execute("SELECT * FROM students WHERE student_id = ?", (s_id,))
                student = dict(cursor.fetchone())
                
                cursor.execute("SELECT * FROM daily_metrics WHERE student_id = ? ORDER BY date DESC", (s_id,))
                metrics_desc = [dict(row) for row in cursor.fetchall()]
                
                cursor.execute("SELECT * FROM facilitator_notes WHERE student_id = ? ORDER BY date DESC", (s_id,))
                s_notes = [dict(row) for row in cursor.fetchall()]
                
                tasks_data.append({
                    "s_id": s_id,
                    "student": student,
                    "metrics_desc": metrics_desc,
                    "s_notes": s_notes
                })

            # Define a pure function for the LLM calls (No DB usage here)
            def fetch_ai_for_student(data):
                s_id = data["s_id"]
                s_notes = data["s_notes"]
                student = data["student"]
                metrics_desc = data["metrics_desc"]
                
                try:
                    adj = calculate_notes_sentiment_adjustment(s_id, s_notes)
                    ai_summary = summarize_notes(s_id, s_notes)
                    priority_info = calculate_priority_for_student(student, metrics_desc, len(s_notes))
                    
                    ai_why = generate_why_explanation(
                        student_id=s_id,
                        priority_score=priority_info['priority_score'],
                        avg_practice=priority_info['avg_daily_practice'],
                        avg_session=priority_info['avg_daily_session_min'],
                        notes_count=priority_info['notes_count'],
                        notes_summary_text=ai_summary
                    )
                    
                    return {
                        "s_id": s_id,
                        "adj": adj,
                        "ai_summary": ai_summary,
                        "ai_why": ai_why
                    }
                except Exception as e:
                    print(f"Error calling LLM for student {s_id}: {e}")
                    return None

            import concurrent.futures
            
            results = []
            completed_count = 0
            total_tasks = len(tasks_data)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                # Map executes threads concurrently
                for res in executor.map(fetch_ai_for_student, tasks_data):
                    if res:
                        results.append(res)
                    completed_count += 1
                    print(f"AI student calculation progress: {completed_count}/{total_tasks} students processed...")
            
            # Now sequential DB update in main thread (Guarantees no DB lock!)
            for res in results:
                cursor.execute("""
                    UPDATE students 
                    SET ai_notes_adjustment = ?, ai_summary = ?, ai_why = ?
                    WHERE student_id = ?
                """, (res["adj"], res["ai_summary"], res["ai_why"], res["s_id"]))
            conn.commit()
            print("All AI caching completed and saved to the database.")
        else:
            print("AI adjustments already cached in database.")
            
        # Pre-calculate and cache Admin Insights (Main Issues Impact Matrix) if not already cached
        cursor.execute("SELECT cache_value FROM system_cache WHERE cache_key = 'main_issues_impact'")
        cached_row = cursor.fetchone()
        if not cached_row:
            print("Running AI analysis for admin insights (main issues impact matrix)...")
            try:
                all_ranked = get_prioritized_queue(conn)
                student_data_list = []
                for s in all_ranked:
                    cursor.execute("SELECT note_text FROM facilitator_notes WHERE student_id = ?", (s['student_id'],))
                    notes = [row['note_text'] for row in cursor.fetchall()]
                    student_data_list.append({
                        "student_id": s['student_id'],
                        "avg_daily_practice": s['avg_daily_practice'],
                        "avg_daily_session_min": s['avg_daily_session_min'],
                        "notes": notes
                    })
                from LLM import analyze_common_issues
                issues_impact = analyze_common_issues(student_data_list)
                issues_impact.sort(key=lambda x: -x['count'])
                
                # Save to cache
                import json
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("INSERT OR REPLACE INTO system_cache (cache_key, cache_value, updated_at) VALUES ('main_issues_impact', ?, ?)", (json.dumps(issues_impact), now_str))
                conn.commit()
                print("Admin insights AI analysis completed and saved to database.")
            except Exception as e:
                print(f"Error during startup AI analysis for admin insights: {e}")
        else:
            print("Admin insights already cached in database.")
            
        conn.close()

    app.run(debug=True, port=5000)
