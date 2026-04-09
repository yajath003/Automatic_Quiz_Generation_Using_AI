from app import create_app, celery
from celery.schedules import crontab

# Create the flask app instance
# This also initializes and configures the 'celery' instance defined in app/__init__.py
flask_app = create_app()

# Ensure tasks run inside Flask app context
class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask

# Import tasks explicitly so Celery registers them on the shared instance
import app.tasks.email_tasks

# Celery Beat schedule (scheduled tasks)
celery.conf.beat_schedule = {
    "check-deadlines-every-hour": {
        "task": "app.tasks.email_tasks.check_upcoming_deadlines",
        "schedule": crontab(minute=0),
    },
    "auto-release-results-every-hour": {
        "task": "app.tasks.email_tasks.check_past_deadlines_and_release_results",
        "schedule": crontab(minute=0),
    },
}

if __name__ == "__main__":
    celery.start()