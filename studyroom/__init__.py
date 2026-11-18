import os
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
import click
from flask import Flask, abort, g, redirect, request, session, url_for, render_template
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from .db import create_database
from .models import Base, User
from .services import seed_demo


def tr(en, zh):
    return zh if session.get('lang') == 'zh' else en


def safe_next(value):
    if not value or not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        return None
    if any(c in value for c in ('\\', '\r', '\n')):
        return None
    try:
        u = urlsplit(value)
    except ValueError:
        return None
    return value if not u.netloc and not u.scheme else None


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))
        return fn(*args, **kwargs)
    return wrapped


def staff_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user['role'] != 'staff':
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    default_path = Path(app.instance_path) / 'study_rooms.sqlite3'
    default_url = 'sqlite:///' + default_path.as_posix()
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
                      DATABASE_URL=os.environ.get('DATABASE_URL') or default_url,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE') == '1',
                      AUTO_INIT_DEMO=os.environ.get('AUTO_INIT_DEMO', '1') != '0')
    if test_config:
        app.config.update(test_config)
    fresh_demo = (app.config['AUTO_INIT_DEMO'] and app.config['DATABASE_URL'] == default_url
                  and not default_path.exists())
    engine, factory = create_database(app.config['DATABASE_URL'])
    app.extensions['study_engine'] = engine
    app.extensions['study_sessions'] = factory
    if fresh_demo:
        Base.metadata.create_all(engine)
        seed_demo(factory)
    from .auth import bp as auth_bp
    from .views import bp as views_bp
    from .admin import bp as admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def security_and_user():
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            sent = request.form.get('csrf_token', '')
            if not secrets.compare_digest(token, sent):
                abort(400, 'Invalid CSRF token')
        g.user = None
        user_id = session.get('user_id')
        if isinstance(user_id, int):
            with factory() as db:
                user = db.get(User, user_id)
                if user:
                    g.user = {'id': user.id, 'name': user.name, 'email': user.email, 'role': user.role}
                else:
                    session.pop('user_id', None)

    @app.context_processor
    def template_context():
        return {'current_user': g.get('user'), 'csrf_token': session.get('_csrf_token', ''),
                '_': tr, 'language': session.get('lang', 'en'),
                'database_kind': 'SQLite' if engine.dialect.name == 'sqlite' else 'MySQL'}

    @app.post('/language')
    def language():
        session['lang'] = 'zh' if session.get('lang') != 'zh' else 'en'
        return redirect(safe_next(request.form.get('next')) or url_for('views.index'))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template('error.html', title='403', message=tr('You do not have permission to open this page.', '你没有权限访问这个页面。')), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template('error.html', title='404', message=tr('This page could not be found.', '页面不存在。')), 404

    @app.errorhandler(SQLAlchemyError)
    def database_unavailable(_error):
        app.logger.error('Database unavailable; check connection and initialization.')
        return render_template('error.html', title=tr('Database unavailable', '数据库未连接'),
                               message=tr('Check DATABASE_URL, ensure the database exists, and run the setup command in README.',
                                          '请检查 DATABASE_URL，确认数据库已创建，并按 README 运行初始化命令。')), 503

    @app.cli.command('init-db')
    def init_db():
        Base.metadata.create_all(engine)
        click.echo('Database tables initialized.')

    @app.cli.command('seed-demo')
    def seed():
        if seed_demo(factory):
            click.echo('Demo records added. See README for demo credentials.')
        else:
            click.echo('Database is not empty; no demo data was inserted.')

    @app.cli.command('create-staff')
    @click.option('--name', prompt='Staff name')
    @click.option('--email', prompt='Staff email')
    @click.password_option(prompt='Password', confirmation_prompt=True)
    def create_staff(name, email, password):
        from sqlalchemy.exc import IntegrityError
        from werkzeug.security import generate_password_hash
        name, email = name.strip(), email.strip().lower()
        if not 2 <= len(name) <= 100 or len(email) > 255 or '@' not in email or '.' not in email.rsplit('@', 1)[-1] or ' ' in email or not 8 <= len(password) <= 128:
            raise click.ClickException('Check name, email and password length (8 to 128 characters).')
        try:
            with factory() as db:
                db.add(User(name=name, email=email, password_hash=generate_password_hash(password), role='staff'))
                db.commit()
        except IntegrityError as exc:
            raise click.ClickException('This email is already registered.') from exc
        click.echo('Staff account created.')

    return app
