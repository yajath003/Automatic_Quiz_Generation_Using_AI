from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Quiz, Assignment, AssignmentAttempt, User, QuizAttempt, AttemptAnswer, GeneratedQuestion, Resource
import csv
from io import StringIO
from datetime import datetime

admin_assignments_bp = Blueprint('admin_assignments', __name__)

@admin_assignments_bp.route('/publish/<int:quiz_id>', methods=['POST'])
@login_required
def publish_assignment(quiz_id):
    if not current_user.is_admin():
        flash("Permission denied.", "danger")
        return redirect(url_for('user.dashboard'))

    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if already published
    existing = Assignment.query.filter_by(quiz_id=quiz.id).first()
    if existing:
        flash("This quiz is already published as an assignment.", "info")
        return redirect(url_for('quiz.result', attempt_id=quiz.attempts[0].id if quiz.attempts else 0))

    # Create Assignment
    due_date_str = request.form.get('due_date')
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash("Invalid date format.", "warning")

    assignment = Assignment(
        quiz_id=quiz.id,
        admin_id=current_user.id,
        title=quiz.resource.title, # Default title
        due_date=due_date,
        status='active'
    )
    
    db.session.add(assignment)
    db.session.commit()
    
    # Optional: notify students or create AssignmentAttempt records immediately
    # if assigned_to_all is True. For now, we'll let students see it on their dashboard.
    
    flash("Quiz published to students successfully!", "success")
    
    # Redirect back to where we came from (likely quiz result)
    return redirect(request.referrer or url_for('user.dashboard'))

@admin_assignments_bp.route('/export_report/<int:assign_id>')
@login_required
def export_report(assign_id):
    if not current_user.is_admin():
        flash("Permission denied.", "danger")
        return redirect(url_for('user.dashboard'))

    assignment = Assignment.query.get_or_404(assign_id)
    
    # Query data: Student Name, Score, Time, Status
    # Fetch all attempts for this specific assignment
    attempts = AssignmentAttempt.query.filter_by(assignment_id=assign_id).all()

    def generate():
        data = StringIO()
        writer = csv.writer(data)
        writer.writerow(['Student Name', 'Total Score (%)', 'Hard Questions Correct', 'Time Taken (seconds)', 'Completion Date'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for a in attempts:
            user = User.query.get(a.user_id)
            # Calculate how many 'Hard' questions were correct
            hard_correct = 0
            if a.quiz_attempt_id:
                hard_correct = db.session.query(db.func.count(AttemptAnswer.id)).join(
                    GeneratedQuestion, AttemptAnswer.question_id == GeneratedQuestion.id
                ).filter(
                    AttemptAnswer.attempt_id == a.quiz_attempt_id,
                    AttemptAnswer.is_correct == True,
                    GeneratedQuestion.difficulty == 'Hard'
                ).scalar()

            writer.writerow([
                user.username, 
                a.score, 
                hard_correct,
                a.time_taken, 
                a.completed_at.strftime('%Y-%m-%d %H:%M')
            ])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    response = Response(generate(), mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename=f"assignment_{assign_id}_report.csv")
    return response
@admin_assignments_bp.route('/manage')
@login_required
def manage():
    if not current_user.is_admin():
        flash("Permission denied.", "danger")
        return redirect(url_for('user.dashboard'))

    assignments_raw = Assignment.query.filter_by(admin_id=current_user.id).all()
    
    assignments = []
    for a in assignments_raw:
        completion_count = AssignmentAttempt.query.filter_by(assignment_id=a.id).count()
        attempts = AssignmentAttempt.query.filter_by(assignment_id=a.id).all()
        
        avg_score = 0
        if attempts:
            avg_score = sum(att.score for att in attempts) / len(attempts)
            
        assignments.append({
            'id': a.id,
            'title': a.title or a.quiz.resource.title,
            'resource_name': a.quiz.resource.title,
            'completion_count': completion_count,
            'average_score': round(avg_score, 1),
            'status': a.status
        })

    return render_template('admin/manage_assignments.html', assignments=assignments)

@admin_assignments_bp.route('/close/<int:assign_id>', methods=['POST'])
@login_required
def close_assignment(assign_id):
    if not current_user.is_admin():
        flash("Permission denied.", "danger")
        return redirect(url_for('user.dashboard'))

    assignment = Assignment.query.get_or_404(assign_id)
    if assignment.admin_id != current_user.id:
        flash("You can only close your own assignments.", "danger")
        return redirect(url_for('admin_assignments.manage'))

    assignment.status = 'closed'
    db.session.commit()
    flash("Assignment closed successfully.", "info")
    return redirect(url_for('admin_assignments.manage'))
