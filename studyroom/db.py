from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def create_database(url):
    options = {'pool_pre_ping': True}
    if url.startswith('sqlite:'):
        options['connect_args'] = {'timeout': 15, 'check_same_thread': False}
        if url in ('sqlite://', 'sqlite:///:memory:'):
            options['poolclass'] = StaticPool
    else:
        options['pool_recycle'] = 1800
    engine = create_engine(url, **options)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
