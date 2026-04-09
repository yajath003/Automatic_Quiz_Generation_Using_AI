from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

from app.admin import routes, routes_assignments, routes_classroom
