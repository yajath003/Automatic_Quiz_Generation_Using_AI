from flask import render_template, redirect, url_for, flash, request, Response
import csv
import io
from flask_login import login_required, current_user
from app.admin import admin_bp
from app import db
from app.models import Resource, User, Quiz, QuizAttempt, Assignment, AssignmentUser
from app.utils import allowed_file, extract_text_from_file
from sqlalchemy import desc
from datetime import datetime
from app.services.quiz_service import QuizService

quiz_service = QuizService()

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        flash('Access denied: Admins only.')
        return redirect(url_for('user.dashboard'))
    
    total_users = User.query.count()
    quizzes_generated = Quiz.query.count()
    resources_count = Resource.query.count()
    system_alerts = User.query.filter_by(is_flagged=True).count()

    activities = []
    
    # Quizzes created
    recent_quizzes = Quiz.query.order_by(desc(Quiz.created_at)).limit(10).all()
    for q in recent_quizzes:
        activities.append({
            'user': q.user,
            'action': f"Generated Quiz: {q.resource.title if q.resource else 'Unknown'}",
            'status': 'Created',
            'date': q.created_at,
            'type': 'quiz_created'
        })
        
    # Quiz attempts completed
    recent_attempts = QuizAttempt.query.filter(QuizAttempt.completed_at.isnot(None)).order_by(desc(QuizAttempt.completed_at)).limit(10).all()
    for a in recent_attempts:
        activities.append({
            'user': a.user,
            'action': f"Completed Quiz: {a.quiz.resource.title if a.quiz and a.quiz.resource else 'Unknown'}",
            'status': 'Completed',
            'date': a.completed_at,
            'type': 'quiz_completed'
        })
        
    # Resources uploaded
    recent_resources = Resource.query.order_by(desc(Resource.created_at)).limit(10).all()
    for r in recent_resources:
        activities.append({
            'user': r.author,
            'action': f"Uploaded Resource: {r.title}",
            'status': 'Uploaded',
            'date': r.created_at,
            'type': 'resource_uploaded'
        })
        
    activities.sort(key=lambda x: x['date'], reverse=True)
    recent_activities = activities[:10]

    return render_template('admin/dashboard.html', 
                           title='Admin Dashboard',
                           total_users=total_users,
                           quizzes_generated=quizzes_generated,
                           resources_count=resources_count,
                           system_alerts=system_alerts,
                           recent_activities=recent_activities)

@admin_bp.route('/resources')
@login_required
def resources():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    resources = Resource.query.filter_by(resource_type='admin_default').order_by(Resource.created_at.desc()).all()
    return render_template('admin/resources.html', title='Manage Resources', resources=resources)

@admin_bp.route('/resource/add', methods=['POST'])
@login_required
def add_resource():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    
    title = request.form.get('title')
    description = request.form.get('description')
    file = request.files.get('file')
    
    content = ""
    filename = None
    
    if file and file.filename != '' and allowed_file(file.filename):
        content = extract_text_from_file(file)
        if content is None:
            flash('Error extracting text from file.')
            return redirect(url_for('admin.resources'))
        filename = file.filename
    
    resource = Resource(
        title=title,
        description=description,
        content=content,
        file_name=filename,
        resource_type='admin_default',
        author=current_user
    )
    
    db.session.add(resource)
    db.session.commit()
    
    # Automate topic extraction
    quiz_service.process_resource_topics(resource.id)
    
    flash('Resource added successfully with automated topic extraction.')
    return redirect(url_for('admin.resources'))

@admin_bp.route('/resource/<int:resource_id>/delete', methods=['POST'])
@login_required
def delete_resource(resource_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    resource = Resource.query.get_or_404(resource_id)
    db.session.delete(resource)
    db.session.commit()
    flash('Resource deleted.')
    return redirect(url_for('admin.resources'))

@admin_bp.route('/resource/<int:resource_id>/toggle', methods=['POST'])
@login_required
def toggle_resource(resource_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    resource = Resource.query.get_or_404(resource_id)
    resource.is_active = not resource.is_active
    db.session.commit()
    flash('Resource status updated.')
    return redirect(url_for('admin.resources'))

@admin_bp.route('/users')
@login_required
def user_monitoring():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    users = User.query.all()
    return render_template('admin/user_monitoring.html', title='User Monitoring', users=users)

@admin_bp.route('/user/<int:user_id>/toggle_flag', methods=['POST'])
@login_required
def toggle_user_flag(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot flag yourself!")
        return redirect(url_for('admin.user_monitoring'))
    
    user.is_flagged = not user.is_flagged
    db.session.commit()
    status = "flagged" if user.is_flagged else "unflagged"
    flash(f"User {user.username} has been {status}.")
    return redirect(url_for('admin.user_monitoring'))

@admin_bp.route('/analytics')
@login_required
def analytics():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    
    from sqlalchemy import func
    from app.models import AssignmentAttempt
    
    # 1. Summary Cards
    stats = {
        'total_users': User.query.filter(User.role == 'user').count(),
        'total_resources': Resource.query.count(),
        'total_assignments': Assignment.query.count(),
        'total_attempts': QuizAttempt.query.count()
    }
    
    # 2. Score Distribution (Pie/Bar Chart data)
    distribution = { '0-40': 0, '40-60': 0, '60-80': 0, '80-100': 0 }
    attempts = QuizAttempt.query.join(Quiz).all()
    for a in attempts:
        if a.quiz and a.quiz.total_questions > 0:
            pct = (a.total_score / a.quiz.total_questions) * 100
            if pct < 40: distribution['0-40'] += 1
            elif pct < 60: distribution['40-60'] += 1
            elif pct < 80: distribution['60-80'] += 1
            else: distribution['80-100'] += 1
            
    # 3. Most Active Users
    active_users = db.session.query(
        User.username,
        func.count(QuizAttempt.id).label('attempt_count'),
        func.avg(QuizAttempt.total_score / Quiz.total_questions * 100).label('avg_score')
    ).join(User.attempts)\
     .join(QuizAttempt.quiz)\
     .group_by(User.id)\
     .order_by(desc('attempt_count'))\
     .limit(5).all()
     
    # 4. Resource Usage
    resource_usage = db.session.query(
        Resource.title,
        func.count(func.distinct(Assignment.id)).label('assign_count'),
        func.count(func.distinct(QuizAttempt.id)).label('attempt_count')
    ).outerjoin(Resource.quizzes)\
     .outerjoin(Quiz.assignments)\
     .outerjoin(Quiz.attempts)\
     .group_by(Resource.id)\
     .order_by(desc('attempt_count'))\
     .limit(5).all()
     
    # 5. Completion Rate
    total_assigned = AssignmentUser.query.count()
    completed_assigned = AssignmentUser.query.filter_by(status='completed').count()
    completion_rate = round((completed_assigned / total_assigned * 100), 1) if total_assigned > 0 else 0
    
    # 6. Recent Activity
    recent_activity = QuizAttempt.query.order_by(desc(QuizAttempt.started_at)).limit(10).all()
    
    return render_template(
        'admin/analytics.html', 
        title='System Analytics',
        stats=stats,
        distribution=distribution,
        active_users=active_users,
        resource_usage=resource_usage,
        completion_rate=completion_rate,
        total_assigned=total_assigned,
        completed_assigned=completed_assigned,
        recent_activity=recent_activity
    )

@admin_bp.route('/export/report')
@login_required
def export_report():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['System Report', '', '', ''])
    writer.writerow(['Date', db.func.current_timestamp(), '', ''])
    writer.writerow(['', '', '', ''])
    writer.writerow(['Metric', 'Count'])
    writer.writerow(['Total Users', User.query.count()])
    writer.writerow(['Total Quizzes', Quiz.query.count()])
    writer.writerow(['Total Resources', Resource.query.count()])
    writer.writerow(['Total Flagged Users', User.query.filter_by(is_flagged=True).count()])
    writer.writerow(['', '', '', ''])
    
    writer.writerow(['Recent User Activities (Last 20)', '', '', ''])
    writer.writerow(['User', 'Action', 'Status', 'Timestamp'])
    
    activities = []
    
    # Quizzes created
    recent_quizzes = Quiz.query.order_by(desc(Quiz.created_at)).limit(20).all()
    for q in recent_quizzes:
        activities.append([q.user.username if q.user else 'Unknown', f"Generated Quiz: {q.resource.title if q.resource else 'N/A'}", 'Created', q.created_at])
        
    # Quiz attempts
    recent_attempts = QuizAttempt.query.filter(QuizAttempt.completed_at.isnot(None)).order_by(desc(QuizAttempt.completed_at)).limit(20).all()
    for a in recent_attempts:
        activities.append([a.user.username if a.user else 'Unknown', f"Completed Quiz: {a.quiz.resource.title if a.quiz and a.quiz.resource else 'N/A'}", 'Completed', a.completed_at])
        
    # Resources
    recent_resources = Resource.query.order_by(desc(Resource.created_at)).limit(20).all()
    for r in recent_resources:
        activities.append([r.author.username if r.author else 'Unknown', f"Uploaded Resource: {r.title}", 'Uploaded', r.created_at])
        
    activities.sort(key=lambda x: x[3] if x[3] else '', reverse=True)
    for act in activities[:20]:
        writer.writerow(act)
        
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=admin_report.csv"}
    )
@admin_bp.route('/create_assignment/<int:resource_id>', methods=['POST'])
@login_required
def create_assignment(resource_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
        
    title = request.form.get('title')
    teacher_note = request.form.get('teacher_note')
    
    # 1. Trigger AI generation logic
    try:
        new_quiz_id = quiz_service.generate_custom_quiz(resource_id, teacher_note, current_user.id)
        
        # 2. Create the Assignment entry
        new_assignment = Assignment(
            quiz_id=new_quiz_id,
            admin_id=current_user.id,
            title=title,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_assignment)
        db.session.flush()

        # 3. Assign to all users (Legacy behavior)
        users = User.query.filter(User.role != 'admin').all()
        for user in users:
            au = AssignmentUser(assignment_id=new_assignment.id, user_id=user.id, status='pending')
            db.session.add(au)

        db.session.commit()
        
        flash(f"Assignment '{title}' created and sent to students!", "success")
    except Exception as e:
        flash(f"Error creating assignment: {str(e)}", "danger")
        
    return redirect(url_for('admin.resources'))
