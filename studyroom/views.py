from datetime import datetime, timedelta
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from . import login_required, tr
from .models import Building, Room, Reservation
from .services import BookingError, parse_slot, search_rooms, create_reservation, cancel_reservation

bp = Blueprint('views', __name__)


def problem(code):
    messages = {
        'invalid': ('Please enter a valid date and time.', '请输入有效的日期和时间。'),
        'order': ('End time must be later than start time on the same day.', '结束时间须晚于开始时间，且须在同一天。'),
        'past': ('Choose a future start time.', '请选择未来的开始时间。'),
        'closed': ('The room is unavailable or outside its opening hours.', '房间不可用或预约时间超出开放时间。'),
        'conflict': ('This room is already reserved for part of that time.', '该房间在部分时段已有预约。'),
        'notfound': ('The room or reservation does not exist.', '房间或预约不存在。'),
        'forbidden': ('You cannot cancel another user’s reservation.', '不能取消其他用户的预约。'),
        'already_cancelled': ('This reservation has already been cancelled.', '此预约已取消。'),
    }
    return tr(*messages.get(code, messages['invalid']))


@bp.get('/')
def index():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    data = {'day': request.args.get('day', tomorrow), 'start': request.args.get('start', '10:00'),
            'end': request.args.get('end', '11:00'), 'building': request.args.get('building', ''),
            'capacity': request.args.get('capacity', '1'), 'available_only': request.args.get('available_only') == '1'}
    rooms = []; error = None
    factory = current_app.extensions['study_sessions']
    with factory() as db:
        buildings = db.scalars(select(Building).order_by(Building.name)).all()
        try:
            start_at, end_at = parse_slot(data['day'], data['start'], data['end'])
            building_id = int(data['building']) if data['building'] else None
            capacity = int(data['capacity'])
            if capacity < 1 or capacity > 100 or (building_id is not None and building_id < 1):
                raise ValueError
            rooms = search_rooms(db, start_at, end_at, building_id, capacity, data['available_only'])
        except BookingError as e:
            error = problem(e.code)
        except ValueError:
            error = problem('invalid')
        return render_template('index.html', rooms=rooms, buildings=buildings, filters=data, error=error)


@bp.route('/rooms/<int:room_id>/book', methods=['GET', 'POST'])
@login_required
def book(room_id):
    day = request.values.get('day', '')
    start = request.values.get('start', '')
    end = request.values.get('end', '')
    factory = current_app.extensions['study_sessions']
    try:
        start_at, end_at = parse_slot(day, start, end)
        if request.method == 'POST':
            create_reservation(factory, g.user['id'], room_id, start_at, end_at)
            flash(tr('Your room is booked.', '预约成功。'), 'success')
            return redirect(url_for('views.my_bookings'))
        with factory() as db:
            room = db.scalar(select(Room).where(Room.id == room_id).options(joinedload(Room.building), selectinload(Room.hours)))
            if not room:
                raise BookingError('notfound')
            matches = search_rooms(db, start_at, end_at, room.building_id, room.capacity)
            status = next((status for row, status in matches if row.id == room_id), 'closed')
            if status != 'available':
                raise BookingError('conflict' if status == 'booked' else 'closed')
            return render_template('book.html', room=room, day=day, start=start, end=end)
    except BookingError as e:
        flash(problem(e.code), 'error')
        return redirect(url_for('views.index', day=day, start=start, end=end))


@bp.get('/bookings')
@login_required
def my_bookings():
    factory = current_app.extensions['study_sessions']
    with factory() as db:
        bookings = db.scalars(select(Reservation).where(Reservation.user_id == g.user['id'])
                              .options(joinedload(Reservation.room).joinedload(Room.building))
                              .order_by(Reservation.start_at.desc(), Reservation.id.desc())).all()
        return render_template('bookings.html', bookings=bookings)


@bp.post('/bookings/<int:booking_id>/cancel')
@login_required
def cancel(booking_id):
    try:
        cancel_reservation(current_app.extensions['study_sessions'], booking_id, g.user['id'], g.user['role'] == 'staff')
        flash(tr('Reservation cancelled.', '预约已取消。'), 'success')
    except BookingError as e:
        flash(problem(e.code), 'error')
    return redirect(url_for('admin.dashboard') if request.form.get('return_to') == 'admin' and g.user['role'] == 'staff' else url_for('views.my_bookings'))
