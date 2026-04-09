from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.ai_engine import ai_bp
from app.models import Resource, ResourceTopic
from app.services.quiz_service import QuizService
import logging

logger = logging.getLogger(__name__)

quiz_service = QuizService()

@ai_bp.route('/process', methods=['GET', 'POST'])
@login_required
def process():
    if request.method == 'POST':
        resource_id = request.form.get('resource_id')
        
        params = {
            'topic_mode': request.form.get('topic_mode'),
            'topic_ids': request.form.getlist('topics'),
            'num_questions': request.form.get('num_questions', 5),
            'difficulty': request.form.get('difficulty', 'medium'),
            'bloom_level': request.form.get('bloom_level', 'understand'),
            'question_type': request.form.get('question_type', 'MCQ'),
            'teacher_note': request.form.get('teacher_note'),
            'passing_score': request.form.get('passing_score', 0)
        }

        try:
            quiz_id = quiz_service.generate_quiz(
                resource_id=int(resource_id), 
                user_id=current_user.id, 
                **params
            )
            
            flash(f"Quiz generated successfully!", "success")
            return redirect(url_for('quiz.start', retry_quiz_id=quiz_id))

        except PermissionError:
            flash("Permission denied.", "danger")
            return redirect(url_for('user.dashboard'))
        except Exception as e:
            logger.error(f"Quiz generation failed: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('ai_engine.process'))

    admin_resources = Resource.query.filter_by(resource_type='admin_default', is_active=True).all()
    my_resources = Resource.query.filter_by(resource_type='user_upload', created_by=current_user.id).all()

    return render_template(
        "ai_engine/generate.html",
        title="Generate Quiz",
        resources=admin_resources + my_resources
    )

@ai_bp.route('/api/topics/<int:resource_id>')
@login_required
def get_topics(resource_id):
    logger.info(f"API Trigger: Fetching topics for resource_id={resource_id}")
    try:
        topics = quiz_service.get_topics(resource_id)
        logger.info(f"API success: Found {len(topics)} topics for resource_id={resource_id}")
        
        # Ensure we always return topics key with list
        return jsonify({"topics": [{"id": t.id, "name": t.topic_name} for t in topics]})
    except Exception as e:
        logger.error(f"API Failure for resource_id {resource_id}: {e}")
        # Level 3 fallback on API level to NEVER return empty or break UI
        fallback_topics = [
            {"id": 0, "name": "General Concepts"},
            {"id": -1, "name": "Basics & Foundations"},
            {"id": -2, "name": "Examples & Applications"}
        ]
        return jsonify({"topics": fallback_topics})
