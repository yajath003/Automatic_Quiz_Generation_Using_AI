from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.admin import admin_bp
from app import db
from app.models import Classroom, ClassMembership, User

@admin_bp.route('/classrooms')
@login_required
def list_classrooms():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
    
    classrooms = Classroom.query.order_by(Classroom.created_at.desc()).all()
    # Attach member counts
    for c in classrooms:
        c.member_count = ClassMembership.query.filter_by(class_id=c.id).count()
        
    return render_template('admin/classrooms/list.html', title='Manage Classrooms', classrooms=classrooms)

@admin_bp.route('/classrooms/create', methods=['POST'])
@login_required
def create_classroom():
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
        
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash("Classroom name is required.", "danger")
        return redirect(url_for('admin.list_classrooms'))
        
    new_class = Classroom(
        name=name,
        description=description,
        created_by_admin_id=current_user.id
    )
    db.session.add(new_class)
    db.session.commit()
    
    flash(f"Classroom '{name}' created successfully!", "success")
    return redirect(url_for('admin.list_classrooms'))

@admin_bp.route('/classrooms/<int:class_id>')
@login_required
def view_classroom(class_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
        
    classroom = Classroom.query.get_or_404(class_id)
    memberships = ClassMembership.query.filter_by(class_id=class_id).all()
    
    return render_template('admin/classrooms/view.html', title=f"Classroom: {classroom.name}", classroom=classroom, memberships=memberships)

@admin_bp.route('/classrooms/<int:class_id>/remove_user/<int:user_id>', methods=['POST'])
@login_required
def remove_classroom_user(class_id, user_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
        
    membership = ClassMembership.query.filter_by(class_id=class_id, user_id=user_id).first_or_404()
    user_name = membership.user.username
    
    db.session.delete(membership)
    db.session.commit()
    
    flash(f"User '{user_name}' removed from classroom.", "success")
    return redirect(url_for('admin.view_classroom', class_id=class_id))

@admin_bp.route('/classrooms/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_classroom(class_id):
    if current_user.role != 'admin':
        return redirect(url_for('user.dashboard'))
        
    classroom = Classroom.query.get_or_404(class_id)
    name = classroom.name
    
    db.session.delete(classroom)
    db.session.commit()
    
    flash(f"Classroom '{name}' deleted.", "success")
    return redirect(url_for('admin.list_classrooms'))
