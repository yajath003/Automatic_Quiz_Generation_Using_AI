from flask import Blueprint

ai_bp = Blueprint('ai_engine', __name__)

from app.ai_engine import routes
