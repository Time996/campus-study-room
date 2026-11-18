from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from . import safe_next, tr
from .models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirmation = request.form.get('confirm_password', '')
        if not 2 <= len(name) <= 100 or len(email) > 255 or '@' not in email or '.' not in email.rsplit('@', 1)[-1] or ' ' in email:
            flash(tr('Please enter a valid name and email address.', '请输入有效的姓名和邮箱。'), 'error')
        elif len(password) < 8 or len(password) > 128:
            flash(tr('Password must be 8 to 128 characters.', '密码长度须为 8 至 128 个字符。'), 'error')
        elif password != confirmation:
            flash(tr('Passwords do not match.', '两次输入的密码不一致。'), 'error')
        else:
            factory = current_app.extensions['study_sessions']
            try:
                with factory() as db:
                    user = User(name=name, email=email, password_hash=generate_password_hash(password), role='student')
                    db.add(user); db.commit(); uid = user.id
                session.clear(); session['user_id'] = uid
                flash(tr('Account created. Welcome!', '账号创建成功，欢迎！'), 'success')
                return redirect(url_for('views.index'))
            except IntegrityError:
                flash(tr('This email is already registered.', '该邮箱已注册。'), 'error')
    return render_template('auth/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    target = safe_next(request.values.get('next'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        factory = current_app.extensions['study_sessions']
        with factory() as db:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None and check_password_hash(user.password_hash, password):
                uid = user.id
            else:
                uid = None
        if uid is None:
            flash(tr('Incorrect email or password.', '邮箱或密码不正确。'), 'error')
        else:
            lang = session.get('lang')
            session.clear(); session['user_id'] = uid
            if lang: session['lang'] = lang
            flash(tr('Welcome back!', '欢迎回来！'), 'success')
            return redirect(target or url_for('views.index'))
    return render_template('auth/login.html', next_url=target or '')


@bp.post('/logout')
def logout():
    lang = session.get('lang')
    session.clear()
    if lang: session['lang'] = lang
    flash(tr('You are signed out.', '你已退出登录。'), 'success')
    return redirect(url_for('views.index'))
