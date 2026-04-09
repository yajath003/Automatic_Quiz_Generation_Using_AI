from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    is_flagged = db.Column(db.Boolean, default=False)

    resources = db.relationship('Resource', back_populates='author', cascade="all, delete-orphan")
    quizzes = db.relationship('Quiz', back_populates='user', cascade="all, delete-orphan")
    attempts = db.relationship('QuizAttempt', back_populates='user', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


class Resource(db.Model):
    __tablename__ = "resource"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)
    file_name = db.Column(db.String(255))
    resource_type = db.Column(db.String(20), default='user_upload')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_active = db.Column(db.Boolean, default=True)

    author = db.relationship('User', back_populates='resources')
    topics = db.relationship('ResourceTopic', back_populates='resource', cascade="all, delete-orphan")
    questions = db.relationship('GeneratedQuestion', back_populates='resource', cascade="all, delete-orphan")
    quizzes = db.relationship('Quiz', back_populates='resource', cascade="all, delete-orphan")


class ResourceTopic(db.Model):
    __tablename__ = "resource_topic"

    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id'), nullable=False)
    topic_name = db.Column(db.String(255), nullable=False)
    topic_content = db.Column(db.Text)

    resource = db.relationship('Resource', back_populates='topics')
    questions = db.relationship('GeneratedQuestion', back_populates='topic')



class GeneratedQuestion(db.Model):
    __tablename__ = "generated_question"

    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('resource_topic.id'), nullable=True)

    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text)
    correct_answer = db.Column(db.String(255))
    bloom_level = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    question_type = db.Column(db.String(50))
    explanation = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    resource = db.relationship('Resource', back_populates='questions')
    topic = db.relationship('ResourceTopic', back_populates='questions')
    
    def get_options(self):
        import json
        if not self.options:
            return {}
        try:
            # First try parsing it as a JSON string
            parsed = json.loads(self.options)
            if isinstance(parsed, dict):
                return parsed
        except:
            pass
        # Fallback to manual extraction or matching if it's not proper JSON
        return {
            "A": getattr(self, "option_a", "N/A"),
            "B": getattr(self, "option_b", "N/A"),
            "C": getattr(self, "option_c", "N/A"),
            "D": getattr(self, "option_d", "N/A")
        }



quiz_questions = db.Table(
    'quiz_questions',
    db.Column('quiz_id', db.Integer, db.ForeignKey('quiz.id'), primary_key=True),
    db.Column('question_id', db.Integer, db.ForeignKey('generated_question.id'), primary_key=True)
)



class Quiz(db.Model):
    __tablename__ = "quiz"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id', ondelete="CASCADE"), nullable=False)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    total_questions = db.Column(db.Integer, nullable=False)
    mode = db.Column(db.String(50))
    bloom_level = db.Column(db.String(50))
    difficulty = db.Column(db.String(50))
    teacher_note = db.Column(db.Text, nullable=True)
    passing_score = db.Column(db.Float, default=0.0)

    user = db.relationship('User', back_populates='quizzes')
    resource = db.relationship('Resource', back_populates='quizzes')

    questions = db.relationship(
        'GeneratedQuestion',
        secondary=quiz_questions,
        lazy='subquery',
        backref='quizzes'
    )

    attempts = db.relationship('QuizAttempt', back_populates='quiz', cascade="all, delete-orphan")


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempt"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'assignment_id', name='uq_user_assignment'),
    )

    started_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    completed_at = db.Column(db.DateTime)
    total_score = db.Column(db.Float, default=0.0)
    time_taken = db.Column(db.Integer)
    is_submitted = db.Column(db.Boolean, default=False)

    quiz = db.relationship('Quiz', back_populates='attempts')
    user = db.relationship('User', back_populates='attempts')

    answers = db.relationship('AttemptAnswer', back_populates='attempt', cascade="all, delete-orphan")


class AttemptAnswer(db.Model):
    __tablename__ = "attempt_answer"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('generated_question.id'), nullable=False)

    selected_answer = db.Column(db.String(255))
    is_correct = db.Column(db.Boolean, default=False)
    response_time = db.Column(db.Integer, default=0)

    attempt = db.relationship('QuizAttempt', back_populates='answers')
    question = db.relationship('GeneratedQuestion')


class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'))
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(100))
    instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    due_date = db.Column(db.DateTime)
    
    # New Fields for Preview / Classroom functionality
    status = db.Column(db.String(20), default='published') # draft, published
    target_type = db.Column(db.String(20), default='all') # all, class, users
    target_class_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=True)
    target_user_ids = db.Column(db.Text, nullable=True) # Comma separated for manually chosen users
    results_released = db.Column(db.Boolean, default=False)

    quiz = db.relationship('Quiz', backref='assignments')
    admin = db.relationship('User', backref='managed_assignments')
    results = db.relationship('AssignmentAttempt', backref='assignment', lazy=True, cascade="all, delete-orphan")
    assigned_users = db.relationship('AssignmentUser', back_populates='assignment', cascade="all, delete-orphan")
    
    # Relationship to classroom (if assigned to a class)
    target_class = db.relationship('Classroom', backref='assignments', lazy=True)


class Classroom(db.Model):
    __tablename__ = "classroom"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    admin = db.relationship('User', backref='created_classes', foreign_keys=[created_by_admin_id])
    members = db.relationship('ClassMembership', back_populates='classroom', cascade="all, delete-orphan")


class ClassMembership(db.Model):
    __tablename__ = "class_membership"
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'user_id', name='uq_class_user'),
    )

    classroom = db.relationship('Classroom', back_populates='members')
    user = db.relationship('User', backref='class_memberships')


class AssignmentUser(db.Model):
    __tablename__ = "assignment_users"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, completed

    assignment = db.relationship('Assignment', back_populates='assigned_users')
    user = db.relationship('User', backref='assigned_quizzes')


class AssignmentAttempt(db.Model):
    __tablename__ = "assignment_attempts"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    quiz_attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempt.id'))
    score = db.Column(db.Float)
    time_taken = db.Column(db.Integer) # in seconds
    completed_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_submitted = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='assigned_attempts')
    quiz_attempt = db.relationship('QuizAttempt', backref='assignment_attempt')
