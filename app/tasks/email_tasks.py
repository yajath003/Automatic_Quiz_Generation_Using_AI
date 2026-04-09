from app import celery, db
from app.utils.mail_service import send_email
from app.models import User, Assignment, AssignmentUser
from datetime import datetime, timedelta

@celery.task
def send_welcome_email(user_email, username):
    subject = "Welcome to AI Quiz Platform"
    body = f"""Hello {username},

Welcome to the AI-Powered Quiz Generation Platform.

You can now upload study resources, attempt quizzes, and track your learning progress.

Good luck with your learning journey!"""
    send_email(subject, user_email, body)

@celery.task
def send_assignment_notification(user_email, assignment_title, due_date):
    subject = "New Quiz Assignment"
    body = f"""Hello,

A new quiz has been assigned to you.

Assignment: {assignment_title}
Due Date: {due_date}

Please log in to attempt it."""
    send_email(subject, user_email, body)

@celery.task
def send_quiz_result_email(user_email, assignment_title, score):
    subject = "Quiz Attempt Completed"
    body = f"""Hello,

You have completed the assignment.

Assignment: {assignment_title}
Score: {score}

Check your dashboard for detailed explanations."""
    send_email(subject, user_email, body)

@celery.task
def send_deadline_reminder(user_email, assignment_title, due_date):
    subject = "Assignment Deadline Reminder"
    body = f"""Hello,

Reminder that your assignment is due soon.

Assignment: {assignment_title}
Due Date: {due_date}

Please complete it before the deadline."""
    send_email(subject, user_email, body)

@celery.task(name="app.tasks.email_tasks.check_upcoming_deadlines")
def check_upcoming_deadlines():
    # Check assignments due within the next 24 hours
    now = datetime.utcnow()
    reminder_window = now + timedelta(hours=24)
    
    upcoming_assignments = Assignment.query.filter(
        Assignment.due_date > now,
        Assignment.due_date <= reminder_window,
        Assignment.status == 'active'
    ).all()
    
    for assignment in upcoming_assignments:
        pending_users = AssignmentUser.query.filter_by(
            assignment_id=assignment.id,
            status='pending'
        ).all()
        
        for au in pending_users:
            send_deadline_reminder.delay(
                au.user.email,
                assignment.title,
                assignment.due_date.strftime('%Y-%m-%d %H:%M')
            )
@celery.task(name="app.tasks.email_tasks.send_results_release_email")
def send_results_release_email(assignment_id):
    # Fetch all users assigned to the assignment
    from app.models import Assignment, AssignmentUser
    assignment = Assignment.query.get(assignment_id)
    if not assignment:
        return
        
    members = AssignmentUser.query.filter_by(assignment_id=assignment_id).all()
    for member in members:
        if member.user:
            subject = "Results Released"
            body = f"""Hello,
            
Your results for assignment '{assignment.title}' are now available. Login to view your score."""
            send_email(subject, member.user.email, body)

@celery.task(name="app.tasks.email_tasks.check_past_deadlines_and_release_results")
def check_past_deadlines_and_release_results():
    from app.models import Assignment
    now = datetime.utcnow()
    
    past_assignments = Assignment.query.filter(
        Assignment.due_date < now,
        Assignment.results_released == False,
        Assignment.status == 'published'
    ).all()
    
    for assignment in past_assignments:
        try:
            assignment.results_released = True
            db.session.commit()
            send_results_release_email.delay(assignment.id)
        except Exception as e:
            db.session.rollback()
