from datetime import datetime, time
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, abort
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from . import staff_required, tr
from .models import Building, Room, RoomHours, Reservation
from .services import BookingError, lock_for_admin

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.get('/')
@staff_required
def dashboard():
    factory = current_app.extensions['study_sessions']
    with factory() as db:
        rooms = db.scalars(select(Room).options(joinedload(Room.building)).order_by(Room.room_number)).unique().all()
        bookings = db.scalars(select(Reservation).options(joinedload(Reservation.user), joinedload(Reservation.room).joinedload(Room.building))
                              .order_by(Reservation.start_at.desc(), Reservation.id.desc())).unique().all()
        active = [b for b in bookings if b.status == 'active']
        report = []
        for room in rooms:
            items = [b for b in active if b.room_id == room.id]
            hours = sum((b.end_at - b.start_at).total_seconds() / 3600 for b in items)
            report.append((room, len(items), hours))
        report.sort(key=lambda v: (-v[1], v[0].room_number))
        return render_template('admin/dashboard.html', rooms=rooms, bookings=bookings, active=len(active),
                               cancelled=len(bookings)-len(active), report=report)


def _fields(form):
    number = form.get('room_number', '').strip()
    floor = form.get('floor', '').strip()
    features = form.get('features', '').strip()
    try:
        building_id = int(form.get('building_id', ''))
        capacity = int(form.get('capacity', ''))
    except ValueError:
        raise ValueError('invalid')
    if not number or len(number) > 30 or not floor or len(floor) > 20 or len(features) > 255 or not 1 <= capacity <= 100:
        raise ValueError('invalid')
    return {'room_number': number, 'floor': floor, 'features': features,
            'building_id': building_id, 'capacity': capacity, 'is_available': form.get('is_available') == '1'}


@bp.route('/rooms/new', methods=['GET', 'POST'])
@staff_required
def add_room():
    factory = current_app.extensions['study_sessions']
    if request.method == 'POST':
        try:
            fields = _fields(request.form)
            with factory() as db:
                if db.get(Building, fields['building_id']) is None:
                    raise ValueError('invalid')
                room = Room(**fields); db.add(room); db.flush()
                db.add_all([RoomHours(room_id=room.id, weekday=i, open_time=time(8), close_time=time(22), is_closed=False) for i in range(7)])
                db.commit()
            flash(tr('Room created.', '房间已创建。'), 'success')
            return redirect(url_for('admin.dashboard'))
        except IntegrityError:
            flash(tr('That room number already exists in the building.', '此楼宇已有相同房间号。'), 'error')
        except ValueError:
            flash(tr('Check the room information and capacity.', '请检查房间信息和容量。'), 'error')
    with factory() as db:
        buildings = db.scalars(select(Building).order_by(Building.name)).all()
        return render_template('admin/room_form.html', room=None, buildings=buildings)


@bp.route('/rooms/<int:room_id>/edit', methods=['GET', 'POST'])
@staff_required
def edit_room(room_id):
    factory = current_app.extensions['study_sessions']
    if request.method == 'POST':
        try:
            fields = _fields(request.form)
            with factory() as db:
                room = lock_for_admin(db, room_id)
                if db.get(Building, fields['building_id']) is None:
                    raise ValueError('invalid')
                for key, value in fields.items(): setattr(room, key, value)
                db.commit()
            flash(tr('Room updated.', '房间信息已更新。'), 'success')
            return redirect(url_for('admin.dashboard'))
        except IntegrityError:
            flash(tr('That room number already exists in the building.', '此楼宇已有相同房间号。'), 'error')
        except ValueError:
            flash(tr('Check the room information and capacity.', '请检查房间信息和容量。'), 'error')
        except BookingError:
            abort(404)
    with factory() as db:
        room = db.get(Room, room_id)
        if not room: abort(404)
        buildings = db.scalars(select(Building).order_by(Building.name)).all()
        return render_template('admin/room_form.html', room=room, buildings=buildings)


@bp.route('/rooms/<int:room_id>/hours', methods=['GET', 'POST'])
@staff_required
def edit_hours(room_id):
    factory = current_app.extensions['study_sessions']
    if request.method == 'POST':
        try:
            day = int(request.form.get('weekday', '-1'))
            opening = datetime.strptime(request.form.get('open', ''), '%H:%M').time()
            closing = datetime.strptime(request.form.get('close', ''), '%H:%M').time()
            if not 0 <= day <= 6 or opening >= closing:
                raise ValueError
            with factory() as db:
                room = lock_for_admin(db, room_id)
                rule = db.scalar(select(RoomHours).where(RoomHours.room_id == room.id, RoomHours.weekday == day))
                if rule is None:
                    rule = RoomHours(room_id=room.id, weekday=day); db.add(rule)
                rule.open_time = opening; rule.close_time = closing; rule.is_closed = request.form.get('is_closed') == '1'
                db.commit()
            flash(tr('Opening hours updated. Existing reservations remain unchanged.', '开放时间已更新，已有预约保持不变。'), 'success')
            return redirect(url_for('admin.edit_hours', room_id=room_id))
        except ValueError:
            flash(tr('Closing time must be later than opening time.', '关闭时间须晚于开放时间。'), 'error')
        except BookingError:
            abort(404)
    with factory() as db:
        room = db.scalar(select(Room).where(Room.id == room_id).options(joinedload(Room.building), selectinload(Room.hours)))
        if not room: abort(404)
        rules = {h.weekday: h for h in room.hours}
        hours = [rules.get(i) or {'weekday': i, 'open_time': time(8), 'close_time': time(22), 'is_closed': True} for i in range(7)]
        return render_template('admin/hours.html', room=room, hours=hours)

@bp.route('/buildings/new', methods=['GET', 'POST'])
@staff_required
def add_building():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        if not name or len(name) > 100 or not code or len(code) > 20:
            flash(tr('Enter a building name and code.', '请输入楼宇名称和代码。'), 'error')
        else:
            try:
                with current_app.extensions['study_sessions']() as db:
                    db.add(Building(name=name, code=code)); db.commit()
                flash(tr('Building created.', '楼宇已创建。'), 'success')
                return redirect(url_for('admin.dashboard'))
            except IntegrityError:
                flash(tr('The building name or code already exists.', '楼宇名称或代码已存在。'), 'error')
    return render_template('admin/building_form.html')
