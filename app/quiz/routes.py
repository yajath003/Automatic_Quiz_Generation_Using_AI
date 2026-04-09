from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app.quiz import quiz_bp
from app import db
from app.models import Quiz, QuizAttempt, AttemptAnswer, GeneratedQuestion, Resource, AssignmentUser
from datetime import datetime
import json

from app.services.quiz_service import QuizService

quiz_service = QuizService()


def is_attempt_completed(user_id, assignment_id):
    if not assignment_id:
        return False
    attempt = QuizAttempt.query.filter_by(
        user_id=user_id,
        assignment_id=assignment_id,
        is_submitted=True
    ).first()
    return attempt is not None


@quiz_bp.route('/start', methods=['POST'])
@login_required
def start():
    resource_id = request.form.get('resource_id')
    retry_quiz_id = request.form.get('retry_quiz_id')
    assignment_id = None

    if retry_quiz_id:
        original_quiz = Quiz.query.get_or_404(retry_quiz_id)
        
        # Check if user owns the quiz OR if it's assigned to them
        is_owner = original_quiz.user_id == current_user.id
        assignment_user = AssignmentUser.query.join(AssignmentUser.assignment).filter(
            AssignmentUser.user_id == current_user.id,
            AssignmentUser.assignment.has(quiz_id=retry_quiz_id)
        ).first()
        is_assigned = assignment_user is not None
        
        if not (is_owner or is_assigned):
            flash('Permission denied.')
            return redirect(url_for('user.dashboard'))
            
        assignment_id = assignment_user.assignment_id if assignment_user else None
        
        if assignment_id:
            # STEP 4 — DEBUG LOG
            all_attempts = QuizAttempt.query.filter_by(
                user_id=current_user.id,
                assignment_id=assignment_id
            ).all()
            print("[(id, is_submitted)]", [(a.id, a.is_submitted) for a in all_attempts])

            # STEP 2 — REPLACE LOGIC
            attempt = QuizAttempt.query.filter_by(
                user_id=current_user.id,
                assignment_id=assignment_id,
                is_submitted=True
            ).first()

            if attempt:
                flash("You have already attempted this assignment.")
                return redirect(url_for('user.dashboard'))
                

        quiz = original_quiz
    else:
        resource = Resource.query.get_or_404(resource_id)
        questions = GeneratedQuestion.query.filter_by(
            resource_id=resource.id
        ).order_by(
            GeneratedQuestion.created_at.desc()
        ).limit(10).all()

        if not questions:
            flash('No questions found for this resource. Please generate some first.')
            return redirect(url_for('ai_engine.process'))

        quiz = Quiz(
            user_id=current_user.id,
            resource_id=resource.id,
            total_questions=len(questions),
            mode='practice',
            bloom_level='mixed',
            difficulty='mixed'
        )

        quiz.questions.extend(questions)
        db.session.add(quiz)
        db.session.commit()

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=current_user.id,
        assignment_id=assignment_id,
        started_at=datetime.utcnow(),  # ✅ ensure started_at is set
        is_submitted=False
    )

    db.session.add(attempt)
    db.session.commit()

    session['current_question'] = 0
    session['quiz_answers'] = {}
    session['quiz_start_time'] = datetime.utcnow().isoformat()

    return redirect(url_for('quiz.attempt', attempt_id=attempt.id))


@quiz_bp.route('/attempt/<int:attempt_id>', methods=['GET', 'POST'])
@login_required
def attempt(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash('Permission denied.')
        return redirect(url_for('user.dashboard'))

    if attempt.completed_at:
        return redirect(url_for('quiz.result', attempt_id=attempt.id))

    quiz = attempt.quiz
    questions = quiz.questions
    total_questions = len(questions)

    current_index = session.get('current_question', 0)

    if current_index >= total_questions:
        return redirect(url_for('quiz.submit', attempt_id=attempt.id))

    current_question = questions[current_index]

    if request.method == 'POST':
        action = request.form.get('action')

        user_answer = (
            request.form.getlist('answer')
            if current_question.question_type == 'MSQ'
            else request.form.get('answer')
        )

        answers = session.get('quiz_answers', {})
        answers[str(current_question.id)] = user_answer
        session['quiz_answers'] = answers
        session.modified = True  # Ensure session is saved

        if action == 'next':
            session['current_question'] = current_index + 1
            if session['current_question'] >= total_questions:
                return redirect(url_for('quiz.submit', attempt_id=attempt.id))
            return redirect(url_for('quiz.attempt', attempt_id=attempt.id))

        elif action == 'submit':
            return redirect(url_for('quiz.submit', attempt_id=attempt.id))

    return render_template(
        'quiz/attempt.html',
        quiz=quiz,
        attempt=attempt,
        question=current_question,
        index=current_index,
        total=total_questions
    )


@quiz_bp.route('/submit/<int:attempt_id>')
@login_required
def submit(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash('Permission denied.')
        return redirect(url_for('user.dashboard'))

    answers = session.get('quiz_answers', {})

    # ✅ Calculate total time taken properly
    start_time_iso = session.get('quiz_start_time')
    time_taken = 0

    if start_time_iso:
        start_time = datetime.fromisoformat(start_time_iso)
        time_taken = int((datetime.utcnow() - start_time).total_seconds())

    attempt.time_taken = time_taken
    db.session.commit()

    # ✅ Submit answers
    quiz_service.submit_quiz(attempt.id, answers)

    # ✅ Set completed_at AFTER submit_quiz is executed and mark as submitted
    attempt.completed_at = datetime.utcnow()
    attempt.is_submitted = True
    db.session.commit()

    # Trigger Quiz Result Email (Only for Practice Quizzes)
    if not attempt.assignment_id:
        from app.tasks.email_tasks import send_quiz_result_email
        send_quiz_result_email.delay(
            current_user.email,
            "Practice Quiz",
            attempt.total_score
        )

    session.pop('current_question', None)
    session.pop('quiz_answers', None)
    session.pop('quiz_start_time', None)

    return redirect(url_for('quiz.result', attempt_id=attempt.id))


@quiz_bp.route('/result/<int:attempt_id>')
@login_required
def result(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash('Permission denied.')
        return redirect(url_for('user.dashboard'))

    # Check if this is an assignment and if results are released
    if attempt.assignment_id:
        from app.models import Assignment
        assignment = Assignment.query.get(attempt.assignment_id)
        if assignment and not assignment.results_released:
            return render_template("quiz/waiting_result.html")

    formatted_time = "0m 0s"

    if attempt.time_taken:
        minutes = attempt.time_taken // 60
        seconds = attempt.time_taken % 60
        formatted_time = f"{minutes}m {seconds}s"

    # Calculate correct count from stored answers
    correct_count = AttemptAnswer.query.filter_by(
        attempt_id=attempt.id, 
        is_correct=True
    ).count()

    return render_template(
        'quiz/result.html',
        attempt=attempt,
        correct_count=correct_count,
        formatted_time=formatted_time
    )


@quiz_bp.route('/generate_explanations/<int:attempt_id>')
@login_required
def generate_explanations(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        return jsonify({"error": "Permission denied"}), 403

    if not attempt.completed_at:
        return jsonify({"error": "Quiz not completed"}), 400

    # Call AI analysis
    analysis_data = quiz_service.analyze_attempt_with_ai(attempt_id)

    # Return structured JSON for frontend
    return jsonify(analysis_data)


@quiz_bp.route('/analysis/<int:attempt_id>')
@login_required
def analysis(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)

    if attempt.user_id != current_user.id:
        flash("Permission denied.", "danger")
        return redirect(url_for('user.dashboard'))

    results = quiz_service.analyze_attempt_with_ai(attempt_id)

    formatted_time = "0m 0s"
    if attempt.time_taken:
        minutes = attempt.time_taken // 60
        seconds = attempt.time_taken % 60
        formatted_time = f"{minutes}m {seconds}s"

    if not results:
        flash("Analysis not available. Ensure the quiz is completed.", "warning")
        return redirect(url_for('quiz.result', attempt_id=attempt_id))

    return render_template(
        'quiz/analysis.html',
        title="Quiz Analysis",
        attempt=attempt,
        analysis_data=results,
        formatted_time=formatted_time
    )


@quiz_bp.route('/performance')
@login_required
def performance():
    from app.models import Assignment
    attempts = QuizAttempt.query.filter_by(
        user_id=current_user.id
    ).order_by(
        QuizAttempt.completed_at.desc()
    ).all()

    # Calculate stats with released results only (practice or released assignments)
    valid_attempts = db.session.query(QuizAttempt).outerjoin(Assignment, QuizAttempt.assignment_id == Assignment.id).filter(
        QuizAttempt.user_id == current_user.id,
        QuizAttempt.completed_at.isnot(None),
        db.or_(
            QuizAttempt.assignment_id.is_(None),
            Assignment.results_released == True
        )
    ).all()

    total_quizzes = len(valid_attempts)

    avg_score = 0
    if total_quizzes > 0:
        avg_score = sum(a.total_score for a in valid_attempts if a.total_score is not None) / total_quizzes

    # Fetch assignments separately since QuizAttempt lacks assignment property direction
    assignment_ids = [a.assignment_id for a in attempts if a.assignment_id]
    assignments_dict = {}
    if assignment_ids:
        assignments = Assignment.query.filter(Assignment.id.in_(assignment_ids)).all()
        assignments_dict = {a.id: a for a in assignments}

    return render_template(
        'quiz/performance.html',
        attempts=attempts,
        total_quizzes=total_quizzes,
        avg_score=avg_score,
        assignments=assignments_dict
    )


@quiz_bp.route('/my_quizzes')
@login_required
def my_quizzes():
    attempts = QuizAttempt.query.filter_by(
        user_id=current_user.id
    ).order_by(
        QuizAttempt.completed_at.desc()
    ).all()

    return render_template(
        'quiz/my_quizzes.html',
        attempts=attempts
    )