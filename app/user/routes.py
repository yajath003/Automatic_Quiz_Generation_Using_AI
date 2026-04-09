from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.user import user_bp
from app import db
from app.models import Resource, ResourceTopic, QuizAttempt, Assignment, AssignmentAttempt, AssignmentUser
from app.utils import allowed_file, extract_text_from_file

from app.services.quiz_service import QuizService
quiz_service = QuizService()

@user_bp.route('/dashboard')
@login_required
def dashboard():
    admin_resources = Resource.query.filter_by(resource_type='admin_default', is_active=True).order_by(Resource.created_at.desc()).all()
    my_resources = Resource.query.filter_by(resource_type='user_upload', created_by=current_user.id).order_by(Resource.created_at.desc()).all()
    
    from app.models import Assignment
    # Fetch completed attempts that are either practice OR released assignments
    valid_attempts = db.session.query(QuizAttempt).outerjoin(Assignment, QuizAttempt.assignment_id == Assignment.id).filter(
        QuizAttempt.user_id == current_user.id,
        QuizAttempt.completed_at.isnot(None),
        db.or_(
            QuizAttempt.assignment_id.is_(None),
            Assignment.results_released == True
        )
    ).all()
    
    total_completed = len(valid_attempts)
    avg_score = 0
    if total_completed > 0:
        avg_score = sum(a.total_score for a in valid_attempts if a.total_score is not None) / total_completed
        
    recent_quizzes = db.session.query(QuizAttempt).outerjoin(Assignment, QuizAttempt.assignment_id == Assignment.id).filter(
        QuizAttempt.user_id == current_user.id,
        QuizAttempt.completed_at.isnot(None),
        db.or_(
            QuizAttempt.assignment_id.is_(None),
            Assignment.results_released == True
        )
    ).order_by(QuizAttempt.completed_at.desc()).limit(5).all()
    
    # Assignments explicitly assigned to this user through AssignmentUser
    assignments_raw = db.session.query(Assignment).join(AssignmentUser).filter(AssignmentUser.user_id == current_user.id).order_by(Assignment.created_at.desc()).all()
    
    assignments_with_status = []
    for assignment in assignments_raw:
        # Check for attempt data
        attempt_data = AssignmentAttempt.query.filter_by(assignment_id=assignment.id, user_id=current_user.id).first()
        is_attempted = attempt_data.is_submitted if attempt_data else False
        assignments_with_status.append({
            'assignment': assignment,
            'status': attempt_data,
            'is_attempted': is_attempted,
            'admin_name': assignment.admin.username if assignment.admin else "Admin"
        })
    
    return render_template('user/dashboard.html', 
                           title='User Dashboard', 
                           admin_resources=admin_resources, 
                           my_resources=my_resources,
                           total_completed=total_completed,
                           avg_score=avg_score,
                           recent_quizzes=recent_quizzes,
                           assignments=assignments_with_status)

@user_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        file = request.files.get('file')
        
        if not file or file.filename == '':
            flash('No file selected.')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            content = extract_text_from_file(file)
            if content is None:
                flash('Error extracting text from file.')
                return redirect(request.url)
            
            resource = Resource(
                title=title,
                description=description,
                content=content,
                file_name=file.filename,
                resource_type='user_upload',
                author=current_user
            )
            
            db.session.add(resource)
            db.session.commit() # Save to DB so we have an ID for the background process
            
            # Use unifying QuizService automatic topic extraction (replaces old legacy extractor)
            quiz_service.process_resource_topics(resource.id)
            
            flash('Resource uploaded and topics extracted successfully.')
            return redirect(url_for('user.dashboard'))
            
    return render_template('user/upload.html', title='Upload Resource')

@user_bp.route('/resource/<int:resource_id>/delete', methods=['POST'])
@login_required
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    if resource.author != current_user:
        flash('Permission denied.')
        return redirect(url_for('user.dashboard'))
        
    db.session.delete(resource)
    db.session.commit()
    flash('Resource deleted.')
    return redirect(url_for('user.dashboard'))

@user_bp.route('/profile')
@login_required
def profile():
    return render_template('user/profile.html', user=current_user)

