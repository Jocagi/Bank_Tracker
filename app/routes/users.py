from flask import render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from . import bp
from ..models import User
from .. import db


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Ingreso exitoso.', 'success')
            return redirect(url_for('main.index'))
        flash('Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('main.login'))


def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Acceso denegado: se requieren permisos de administrador.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)

    return decorated


@bp.route('/users')
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template('users.html', users=users)


@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'user')
        if not username or not password:
            flash('Usuario y contraseña obligatorios.', 'danger')
            return render_template('user_form.html')
        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya existe.', 'warning')
            return render_template('user_form.html')

        user = User(username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(user)
        db.session.commit()
        flash('Usuario creado.', 'success')
        return redirect(url_for('main.list_users'))
    return render_template('user_form.html')


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'user')
        if not username:
            flash('Usuario obligatorio.', 'danger')
            return render_template('user_form.html', user=user)
        if User.query.filter(User.username == username, User.id != user.id).first():
            flash('Otro usuario ya usa ese nombre.', 'warning')
            return render_template('user_form.html', user=user)

        user.username = username
        if password:
            user.password_hash = generate_password_hash(password)
        user.role = role
        db.session.commit()
        flash('Usuario actualizado.', 'success')
        return redirect(url_for('main.list_users'))
    return render_template('user_form.html', user=user)


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Usuario eliminado.', 'warning')
    return redirect(url_for('main.list_users'))
