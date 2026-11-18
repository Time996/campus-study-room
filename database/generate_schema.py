from pathlib import Path
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable, CreateIndex
from studyroom.models import Base
out=['-- Reference schema for MySQL 8.0. Generated from studyroom/models.py.', '-- Create/select a database first, then run this on an empty database.', '-- Alternatively run: python -m flask --app run:app init-db', '-- InnoDB is required for the room-row reservation lock.', '']
dialect=mysql.dialect()
for table in Base.metadata.sorted_tables:
 out.append(str(CreateTable(table).compile(dialect=dialect)).strip()+';')
 for idx in table.indexes:out.append(str(CreateIndex(idx).compile(dialect=dialect)).strip()+';')
 out.append('')
Path('database/schema.sql').write_text('\n'.join(out),encoding='utf-8')
print('Generated MySQL schema for:', ', '.join(t.name for t in Base.metadata.sorted_tables))
