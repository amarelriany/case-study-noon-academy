// Noon Academy Facilitator Priority Workspace - JS Controller

// Global App State
let activeTab = 'workspace';
let studentsData = [];
let filteredStudents = [];
let selectedStudent = null;
let studentMetricsChart = null;
let adminNotesChart = null;
let currentSortField = null;
let currentSortDirection = 'asc';
let sidebarPinned = true;
let currentPage = 1;
let pageSize = 25;

// Initial Setup on DOM Load
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    
    // Load sidebar state from localStorage
    const savedPinned = localStorage.getItem('sidebarPinned');
    if (savedPinned !== null) {
        sidebarPinned = savedPinned === 'true';
    }
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed', !sidebarPinned);
        updatePinIcon();
    }
    
    loadQueueData();
    
});

// Switch Dashboard Tabs
function switchTab(tab) {
    activeTab = tab;
    document.getElementById('btn-tab-workspace').classList.toggle('active', tab === 'workspace');
    document.getElementById('btn-tab-admin').classList.toggle('active', tab === 'admin');
    
    document.getElementById('view-workspace').style.display = tab === 'workspace' ? 'block' : 'none';
    document.getElementById('view-admin').style.display = tab === 'admin' ? 'block' : 'none';
    
    // Update top header page title dynamically
    const pageTitle = document.getElementById('page-title');
    if (pageTitle) {
        pageTitle.textContent = tab === 'workspace' ? 'Facilitator Workspace' : 'Admin Insights';
    }
    
    if (tab === 'admin') {
        loadAdminMetrics();
    } else {
        loadQueueData();
    }
}

// Fetch general configuration (facilitators dropdown list)
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        
        const dropdown = document.getElementById('select-facilitator-filter');
        // Clear except first
        dropdown.innerHTML = '<option value="">All Facilitators</option>';
        
        data.facilitator_emails.forEach(email => {
            const opt = document.createElement('option');
            opt.value = email;
            opt.textContent = email;
            dropdown.appendChild(opt);
        });
    } catch (err) {
        console.error("Error loading config:", err);
    }
}

// Load Workspace queue data
async function loadQueueData() {
    const facilEmail = document.getElementById('select-facilitator-filter').value;
    const queueStatus = document.getElementById('select-status-filter').value;
    
    let url = `/api/queue?status=${queueStatus}`;
    if (facilEmail) {
        url += `&facilitator_email=${encodeURIComponent(facilEmail)}`;
    }
    
    try {
        const res = await fetch(url);
        const data = await res.json();
        
        studentsData = data.queue;
        filteredStudents = [...studentsData];
        currentPage = 1;
        
        renderWorkloadKPI(data.workload_targets, facilEmail);
        
        // Render table (queue is now embedded inside)
        filterStudentTable();
    } catch (err) {
        console.error("Error loading queue:", err);
    }
}

function renderWorkloadKPI(targets, facilEmail) {
    let banner = document.getElementById('kpi-banner');
    if (!banner) {
        const workspace = document.getElementById('view-workspace');
        banner = document.createElement('div');
        banner.id = 'kpi-banner';
        banner.className = 'table-card';
        banner.style.marginBottom = '1.5rem';
        banner.style.padding = '1rem 1.5rem';
        banner.style.display = 'flex';
        banner.style.alignItems = 'center';
        banner.style.justifyContent = 'space-between';
        banner.style.background = 'linear-gradient(to right, #f8fafc, #eff6ff)';
        banner.style.borderLeft = '4px solid var(--primary-glow)';
        workspace.insertBefore(banner, workspace.firstChild);
    }
    
    if (facilEmail) {
        banner.innerHTML = `
            <div>
                <h4 style="margin: 0; color: var(--text-title); font-size: 1.1rem;">
                    <i class="fa-solid fa-bullseye" style="color: var(--primary); margin-right: 0.5rem;"></i>Exam Prep Target: ${facilEmail}
                </h4>
                <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.9rem;">
                    Global Goal: 80% intervention for students with a risk score more than 6.<br>
                    Interventions needed before exam: <strong>${targets.target_per_facil}</strong> students.
                </p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 2rem; font-weight: 700; color: var(--primary); line-height: 1;">
                    <i class="fa-solid fa-list-check" style="font-size: 1.5rem; opacity: 0.7; margin-right: 0.3rem;"></i>${targets.interventions_left}
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase;">
                    Interventions Left
                </div>
            </div>
        `;
        banner.style.display = 'flex';
    } else {
        banner.innerHTML = `
            <div>
                <h4 style="margin: 0; color: var(--text-title); font-size: 1.1rem;">Global Exam Prep Target</h4>
                <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.9rem;">
                    Goal: 80% intervention for students with a risk score more than 6 (${targets.total_high_risk_failed} students total).<br>
                    Interventions needed per facilitator before exam: <strong>${targets.target_per_facil}</strong> students.
                </p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 2rem; font-weight: 700; color: var(--primary); line-height: 1;">
                    ${targets.interventions_left}
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase;">
                    Total Interventions Left
                </div>
            </div>
        `;
        banner.style.display = 'none';
    }
}

// Filters the Main Table locally
function filterStudentTable() {
    const searchText = document.getElementById('input-search-students').value.toLowerCase().trim();
    filteredStudents = studentsData.filter(student => {
        return student.student_id.toLowerCase().includes(searchText);
    });
    
    currentPage = 1;
    
    // Re-apply sort if a sort field is active
    if (currentSortField) {
        const field = currentSortField;
        const dir = currentSortDirection;
        // Reset currentSortField so handleSort re-applies it in correct direction
        currentSortField = null;
        currentSortDirection = dir === 'asc' ? 'desc' : 'asc';
        handleSort(field);
    } else {
        renderStudentTable();
    }
}

// Handles column sorting
function handleSort(field) {
    if (currentSortField === field) {
        // Toggle direction
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortField = field;
        currentSortDirection = 'asc';
    }
    
    filteredStudents.sort((a, b) => {
        let valA = a[field];
        let valB = b[field];
        
        // Handle priority level sorting (sequential ranks)
        if (field === 'priority_level') {
            valA = parseInt(a[field], 10) || 9999;
            valB = parseInt(b[field], 10) || 9999;
        }
        
        
        // Handle null / N/A values for last_quiz_score
        if (field === 'last_quiz_score') {
            valA = a[field] !== null ? a[field] : -1;
            valB = b[field] !== null ? b[field] : -1;
        }
        
        // Handle standard numeric comparisons
        if (typeof valA === 'number' && typeof valB === 'number') {
            return currentSortDirection === 'asc' ? valA - valB : valB - valA;
        }
        
        // Fallback to string comparison
        valA = String(valA);
        valB = String(valB);
        if (valA < valB) return currentSortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return currentSortDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Update sort icons in DOM
    updateSortIcons();
    
    // Re-render table
    renderStudentTable();
}

function updateSortIcons() {
    const fields = [
        'priority_level', 'priority_score', 'student_id',
        'avg_daily_practice', 'last_quiz_score', 'notes_count'
    ];
    
    fields.forEach(field => {
        const icon = document.getElementById(`sort-icon-${field}`);
        if (icon) {
            if (currentSortField === field) {
                icon.className = currentSortDirection === 'asc' ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
                icon.style.opacity = '1';
                icon.style.color = '#3fae88';
            } else {
                icon.className = 'fa-solid fa-sort';
                icon.style.opacity = '0.5';
                icon.style.color = '';
            }
        }
    });
}

// Toggle Sidebar Pin/Unpin
function toggleSidebarPin() {
    sidebarPinned = !sidebarPinned;
    localStorage.setItem('sidebarPinned', sidebarPinned);
    
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed', !sidebarPinned);
        updatePinIcon();
    }
}

function updatePinIcon() {
    const icon = document.getElementById('pin-icon');
    if (icon) {
        if (sidebarPinned) {
            icon.style.transform = 'rotate(45deg)';
            icon.title = 'Unpin Sidebar';
        } else {
            icon.style.transform = 'rotate(0deg)';
            icon.title = 'Pin Sidebar';
        }
    }
}

// Mobile/Unpinned Drawer Toggle
function toggleSidebarDrawer() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Renders the Unified Priority + Student Table
function renderStudentTable() {
    const tbody = document.getElementById('student-table-body');
    tbody.innerHTML = '';
    
    const totalRecords = filteredStudents.length;
    
    if (totalRecords === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="text-center text-muted" style="padding:3rem;">
                    <i class="fa-solid fa-folder-open" style="font-size:2.5rem; margin-bottom:1rem;"></i>
                    <p>No student records match active search filters.</p>
                </td>
            </tr>
        `;
        document.getElementById('pagination-info-text').textContent = 'Showing 0-0 of 0 records';
        document.getElementById('pagination-page-indicator').textContent = 'Page 1 of 1';
        document.getElementById('btn-prev-page').disabled = true;
        document.getElementById('btn-next-page').disabled = true;
        return;
    }
    
    // Calculate page range
    let currentLimit = pageSize;
    if (pageSize === 'all') {
        currentLimit = totalRecords;
    }
    
    const totalPages = Math.ceil(totalRecords / currentLimit);
    if (currentPage > totalPages) {
        currentPage = totalPages;
    }
    if (currentPage < 1) {
        currentPage = 1;
    }
    
    const startIndex = (currentPage - 1) * currentLimit;
    const endIndex = Math.min(startIndex + currentLimit, totalRecords);
    
    const pageStudents = filteredStudents.slice(startIndex, endIndex);
    
    pageStudents.forEach(student => {
        const tr = document.createElement('tr');
        tr.id = `table-row-${student.student_id}`;
        
        // Use score to determine badge color class
        const score = student.priority_score || 0;
        const colorClass = score >= 8.0 ? 'critical' :
                           score > 6.0 ? 'high'     :
                           score >= 4.0 ? 'medium'   :
                                          'low';
        
        // Priority badge cell with sequential rank inside
        const priorityBadgeHtml = `<span class="priority-badge ${colorClass}">${student.priority_level || '-'}</span>`;
        
        // Priority score with coloured bar
        const scoreBarColor = `var(--color-${colorClass})`;
        const scoreHtml = `
            <div style="display:flex; align-items:center; gap:0.4rem;">
                <span style="font-weight:700; color:${scoreBarColor}; font-size:0.9rem;">${score}</span>
                <div style="flex:1; height:4px; background:var(--border-color); border-radius:2px; min-width:32px;">
                    <div style="width:${(score/10)*100}%; height:100%; background:${scoreBarColor}; border-radius:2px;"></div>
                </div>
            </div>
        `;
        
        const studentCellHtml = `
            <div>
                <strong>${student.student_id}</strong>
            </div>
        `;
        
        // Why snippet (truncated)
        const whyText = student.rule_based_why || '';
        const whyHtml = `<span style="font-size:0.75rem; color:var(--text-muted); max-width:180px; display:inline-block;" title="${whyText.replace(/"/g,'&quot;')}">${whyText.length > 60 ? whyText.slice(0,60) + '…' : whyText}</span>`;
        
        // Action buttons
        let actionsHtml = `
            <div style="display: inline-flex; justify-content: center; align-items: center; gap: 0.35rem; width: 100%;">
                <button class="btn-secondary" style="padding:0.4rem 0.8rem; font-size:0.8rem;" onclick="selectStudent('${student.student_id}')">
                    <i class="fa-solid fa-user-gear"></i> Open
                </button>
            </div>
        `;
        
        // Left border stripe via inline style on the row
        tr.style.borderLeft = `3px solid ${scoreBarColor}`;
        
        tr.innerHTML = `
            <td>${priorityBadgeHtml}</td>
            <td>${scoreHtml}</td>
            <td>${studentCellHtml}</td>
            <td class="text-center">${student.avg_daily_practice} q/d</td>
            <td class="text-center">${student.last_quiz_score !== null ? student.last_quiz_score : 'N/A'}</td>
            <td class="text-center"><span class="badge-count">${student.notes_count}</span></td>
            <td>${whyHtml}</td>
            <td class="text-center">${actionsHtml}</td>
        `;
        tbody.appendChild(tr);
    });
    
    // Update pagination controls
    document.getElementById('pagination-info-text').innerHTML = `Showing <strong>${startIndex + 1}-${endIndex}</strong> of <strong>${totalRecords}</strong> records`;
    document.getElementById('pagination-page-indicator').textContent = `Page ${currentPage} of ${totalPages || 1}`;
    
    document.getElementById('btn-prev-page').disabled = (currentPage === 1);
    document.getElementById('btn-next-page').disabled = (currentPage === totalPages || totalPages === 0);
}

// Selects a student to open details modal
async function selectStudent(studentId) {
    // Visually highlight active list items
    const allCards = document.querySelectorAll('.student-card');
    allCards.forEach(c => c.classList.remove('active'));
    const activeCard = document.getElementById(`queue-card-${studentId}`);
    if (activeCard) activeCard.classList.add('active');
    
    // Open loading modal immediately
    document.getElementById('modal-student-detail').classList.add('open');
    document.getElementById('detail-student-name').textContent = "Loading...";
    document.getElementById('detail-ai-why').textContent = "Running priority engine analysis...";
    document.getElementById('detail-notes-timeline').innerHTML = "";
    
    try {
        const res = await fetch(`/api/student/${studentId}`);
        const data = await res.json();
        
        selectedStudent = data;
        
        renderStudentDetailModal();
    } catch (err) {
        console.error("Error loading student details:", err);
    }
}

// Renders the loaded student detail data into the workspace Modal
function renderStudentDetailModal() {
    const meta = selectedStudent.metadata;
    const ai = selectedStudent.ai_analysis;
    
    document.getElementById('detail-student-name').textContent = `Student ${meta.student_id}`;
    
    // Setup badges
    const badge = document.getElementById('detail-priority-badge');
    const colorClass = meta.priority_score >= 8.0 ? 'critical' :
                       meta.priority_score > 6.0 ? 'high'     :
                       meta.priority_score >= 4.0 ? 'medium'   :
                                                    'low';
    badge.textContent = `${meta.priority_level} (${meta.priority_score}/10)`;
    badge.className = `priority-badge ${colorClass}`;
    

    
    // Update stats
    document.getElementById('detail-stat-quiz').textContent = meta.last_quiz_score !== null ? meta.last_quiz_score : 'N/A';

    document.getElementById('detail-stat-practice').textContent = meta.avg_daily_practice;
    
    document.getElementById('detail-profile-id').textContent = meta.student_id;
    document.getElementById('detail-profile-facilitator').textContent = meta.facilitator_email;
    document.getElementById('detail-profile-priority').textContent = `${meta.priority_level} (Score: ${meta.priority_score})`;
    document.getElementById('detail-profile-status').textContent = meta.queue_status.toUpperCase();
    document.getElementById('detail-profile-suggested-action').textContent = meta.suggested_action || 'N/A';
    
    // AI Section
    document.getElementById('detail-ai-why').innerHTML = `
        <strong>Intervention Triggers:</strong><br>
        ${ai.why_prioritized}
    `;
    
    // Render Historical Metrics
    const metricsTbody = document.getElementById('detail-metrics-tbody');
    metricsTbody.innerHTML = '';
    
    if (selectedStudent.metrics && selectedStudent.metrics.length > 0) {
        selectedStudent.metrics.forEach(metric => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${metric.date}</td>
                <td class="text-center">${metric.session_attended_min !== null ? metric.session_attended_min : '-'}</td>
                <td class="text-center">${metric.practice_questions}</td>
                <td class="text-center">${metric.last_quiz_score !== null ? metric.last_quiz_score : '-'}</td>
            `;
            metricsTbody.appendChild(tr);
        });
    } else {
        metricsTbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No historical metrics available.</td></tr>`;
    }
    
    // Notes History Timeline
    renderNotesTimeline();
}

// Renders the notes inside the timeline
function renderNotesTimeline() {
    const timeline = document.getElementById('detail-notes-timeline');
    timeline.innerHTML = '';
    
    const notes = selectedStudent.notes;
    
    if (notes.length === 0) {
        timeline.innerHTML = `
            <div class="text-center text-muted" style="padding:1.5rem;">
                <i class="fa-solid fa-ghost" style="font-size:1.5rem; margin-bottom:0.5rem;"></i>
                <p style="font-size:0.8rem;">No tracking notes written for this student yet.</p>
            </div>
        `;
        return;
    }
    
    notes.forEach(note => {
        const el = document.createElement('div');
        el.className = 'timeline-item';
        el.innerHTML = `
            <div class="timeline-header">
                <span>By ${note.facilitator_email}</span>
                <span>${note.date}</span>
            </div>
            <div class="timeline-text">${note.note_text}</div>
        `;
        timeline.appendChild(el);
    });
}

// Submit a new facilitator note
async function submitQuickNote() {
    const input = document.getElementById('input-new-note');
    const noteText = input.value.trim();
    if (!noteText) return;
    
    const studentId = selectedStudent.metadata.student_id;
    
    try {
        const res = await fetch(`/api/student/${studentId}/note`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ note_text: noteText })
        });
        
        if (res.ok) {
            input.value = '';
            // Reload student details to see new note and updated priority score
            const reloadRes = await fetch(`/api/student/${studentId}`);
            selectedStudent = await reloadRes.json();
            renderStudentDetailModal();
            loadQueueData(); // Refresh main lists
        } else {
            const err = await res.json();
            alert("Error: " + err.error);
        }
    } catch (err) {
        console.error("Error submitting note:", err);
    }
}

// Mark student queue status as completed or ignored
async function markIntervention(status) {
    const studentId = selectedStudent.metadata.student_id;
    const notes = document.getElementById('textarea-intervention-notes').value.trim();
    const actionType = document.getElementById('select-intervention-type').value;
    
    try {
        const res = await fetch(`/api/student/${studentId}/action`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                status: status,
                notes: notes,
                action_type: status === 'ignored' ? 'ignored' : actionType
            })
        });
        
        if (res.ok) {
            document.getElementById('textarea-intervention-notes').value = '';
            closeStudentDetailModal();
            loadQueueData(); // Refresh dashboard
        } else {
            const err = await res.json();
            alert("Error: " + err.error);
        }
    } catch (err) {
        console.error("Error submitting intervention status:", err);
    }
}

// Close Student Detail Modal
function closeStudentDetailModal() {
    document.getElementById('modal-student-detail').classList.remove('open');
    const activeCard = document.querySelector('.student-card.active');
    if (activeCard) activeCard.classList.remove('active');
}

// Render student metrics timeline chart (Removed)
function renderStudentMetricsChart(metrics) {
    // Visualizations removed
}



// Add Student Modal controls
function openAddStudentModal() {
    document.getElementById('modal-add-student').classList.add('open');
}

function closeAddStudentModal() {
    document.getElementById('modal-add-student').classList.remove('open');
    document.getElementById('form-add-student').reset();
    document.getElementById('add-student-error-box').style.display = 'none';
}

async function submitNewStudent(e) {
    e.preventDefault();
    
    const id = document.getElementById('add-student-id').value.trim();
    const facil = document.getElementById('add-student-facil').value.trim();
    
    const errBox = document.getElementById('add-student-error-box');
    errBox.style.display = 'none';
    
    try {
        const res = await fetch('/api/student/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                student_id: id,
                facilitator_email: facil
            })
        });
        
        if (res.ok) {
            closeAddStudentModal();
            loadQueueData();
            alert("New student registered successfully! Enrolled in the priority queue.");
        } else {
            const err = await res.json();
            errBox.textContent = `Error: ${err.error}`;
            errBox.style.display = 'block';
        }
    } catch (err) {
        console.error("Error creating student:", err);
        errBox.textContent = "Error: Failed to connect to server.";
        errBox.style.display = 'block';
    }
}

// Admin Dashboard stats loaders
async function loadAdminMetrics() {
    try {
        const res = await fetch('/api/admin/metrics');
        const data = await res.json();
        
        // Overview cards
        document.getElementById('admin-val-total-students').textContent = data.overall.total_students;
        document.getElementById('admin-val-total-notes').textContent = data.overall.total_notes;
        document.getElementById('admin-val-invisibility').textContent = `${data.overall.invisibility_index_pct}%`;
        
        const interventionsLeftEl = document.getElementById('admin-val-interventions-left');
        if (interventionsLeftEl) {
            interventionsLeftEl.textContent = data.overall.interventions_left;
        }
        
        // Highlighting note clustering risk
        const indexEl = document.getElementById('admin-val-invisibility');
        if (data.overall.invisibility_index_pct > 50) {
            indexEl.style.color = 'var(--color-critical)';
        } else {
            indexEl.style.color = 'var(--color-low)';
        }
        

        
        // Facilitators activity
        const facilTbody = document.getElementById('admin-facil-table-body');
        facilTbody.innerHTML = '';
        
        data.facilitator_activity.forEach(facil => {
            const tr = document.createElement('tr');
            const noteCount = facil.total_notes_written;
            
            let status = `<span class="priority-badge low">ACTIVE</span>`;
            if (noteCount < 10) {
                status = `<span class="priority-badge critical">INACTIVE</span>`;
            } else if (noteCount < 30) {
                status = `<span class="priority-badge high">MODERATE</span>`;
            }
            
            tr.innerHTML = `
                <td><strong>${facil.facilitator_email}</strong></td>
                <td class="text-center">${noteCount}</td>
                <td>${status}</td>
            `;
            facilTbody.appendChild(tr);
        });
        
        // Issues impact matrix
        const issuesTbody = document.getElementById('admin-issues-table-body');
        issuesTbody.innerHTML = '';
        
        data.main_issues_impact.forEach(issue => {
            const tr = document.createElement('tr');
            
            let impactClass = 'low';
            let impactText = 'Monitoring';
            if (issue.count > 40) {
                impactClass = 'critical';
                impactText = 'Critical Risk';
            } else if (issue.count > 15) {
                impactClass = 'high';
                impactText = 'High Action';
            }
            
            tr.innerHTML = `
                <td><strong>${issue.issue}</strong></td>
                <td class="text-center"><span class="badge-count" style="background:var(--primary-glow);">${issue.count}</span></td>
                <td><span class="priority-badge ${impactClass}">${impactText}</span></td>
            `;
            issuesTbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading admin metrics:", err);
    }
}

// Renders the notes distribution chart (Removed)
function renderNotesDistributionChart(buckets) {
    // Visualizations removed
}

// Exports filtered students to CSV format
function exportToCSV() {
    if (filteredStudents.length === 0) {
        alert("No student data available to export.");
        return;
    }
    
    const headers = ['Student ID', 'Avg Practice q/d', 'Last Quiz Score', 'Notes Count', 'Risk Score', 'Priority Level', 'Why / AI Analysis'];
    const rows = filteredStudents.map(s => [
        s.student_id,
        s.avg_daily_practice,
        s.last_quiz_score !== null ? s.last_quiz_score : 'N/A',
        s.notes_count,
        s.priority_score,
        s.priority_level,
        s.rule_based_why || ''
    ]);
    
    // Construct CSV file
    const csvRows = [headers.join(','), ...rows.map(r => r.map(val => `"${String(val).replace(/"/g, '""')}"`).join(','))];
    const csvContent = "data:text/csv;charset=utf-8," + csvRows.join('\n');
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `noon_student_priority_queue_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Client-side Pagination Controls
function changePageSize() {
    const sizeVal = document.getElementById('select-page-size').value;
    if (sizeVal === 'all') {
        pageSize = 'all';
    } else {
        pageSize = parseInt(sizeVal, 10);
    }
    currentPage = 1;
    renderStudentTable();
}

function prevPage() {
    if (currentPage > 1) {
        currentPage--;
        renderStudentTable();
    }
}

function nextPage() {
    const totalRecords = filteredStudents.length;
    const currentLimit = pageSize === 'all' ? totalRecords : pageSize;
    const totalPages = Math.ceil(totalRecords / currentLimit);
    if (currentPage < totalPages) {
        currentPage++;
        renderStudentTable();
    }
}
