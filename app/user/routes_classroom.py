from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.user import user_bp
from app import db
from app.models import Classroom, ClassMembership

@user_bp.route('/classrooms')
@login_required
def list_classrooms():
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
        
    # Get all active classrooms
    all_classrooms = Classroom.query.order_by(Classroom.created_at.desc()).all()
    
    # Get user's current memberships to cross-reference
    my_memberships = ClassMembership.query.filter_by(user_id=current_user.id).all()
    my_class_ids = [m.class_id for m in my_memberships]
    
    # Partition them for the UI
    joined_classrooms = [c for c in all_classrooms if c.id in my_class_ids]
    available_classrooms = [c for c in all_classrooms if c.id not in my_class_ids]
    
    # Fetch assignments linked to joined classes
    class_assignments = []
    if my_class_ids:
        from app.models import Assignment
        # Show both class and all target types?
        class_assignments = Assignment.query.filter(
            Assignment.target_type == 'class',
            Assignment.target_class_id.in_(my_class_ids)
        ).all()
        
    return render_template('user/classrooms/list.html', 
                           title='My Classrooms',
                           joined_classrooms=joined_classrooms,
                           available_classrooms=available_classrooms,
                           class_assignments=class_assignments)

@user_bp.route('/classrooms/<int:class_id>/join', methods=['POST'])
@login_required
def join_classroom(class_id):
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
        
    classroom = Classroom.query.get_or_404(class_id)
    
    # Double check they aren't already in it
    existing = ClassMembership.query.filter_by(class_id=class_id, user_id=current_user.id).first()
    if existing:
        flash("You are already a member of this classroom.", "info")
        return redirect(url_for('user.list_classrooms'))
        
    membership = ClassMembership(class_id=classroom.id, user_id=current_user.id)
    db.session.add(membership)
    db.session.commit()
    
    flash(f"Successfully joined {classroom.name}!", "success")
    return redirect(url_for('user.list_classrooms'))

@user_bp.route('/classrooms/<int:class_id>/leave', methods=['POST'])
@login_required
def leave_classroom(class_id):
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
        
    classroom = Classroom.query.get_or_404(class_id)
    membership = ClassMembership.query.filter_by(class_id=class_id, user_id=current_user.id).first_or_404()
    
    db.session.delete(membership)
    db.session.commit()
    
    flash(f"You have left {classroom.name}.", "info")
    return redirect(url_for('user.list_classrooms'))
