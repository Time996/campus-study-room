from datetime import datetime, time, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload
from .models import User, Building, Room, RoomHours, Reservation
from werkzeug.security import generate_password_hash


class BookingError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def parse_slot(day, start, end, now=None):
    try:
        if not all(isinstance(v, str) for v in (day, start, end)):
            raise ValueError
        if len(day) != 10 or len(start) != 5 or len(end) != 5:
            raise ValueError
        start_at = datetime.strptime(day + ' ' + start, '%Y-%m-%d %H:%M')
        end_at = datetime.strptime(day + ' ' + end, '%Y-%m-%d %H:%M')
        if start_at.strftime('%Y-%m-%d %H:%M') != day + ' ' + start or end_at.strftime('%H:%M') != end:
            raise ValueError
    except ValueError:
        raise BookingError('invalid')
    if start_at >= end_at:
        raise BookingError('order')
    if start_at < (now or datetime.now()):
        raise BookingError('past')
    return start_at, end_at


def slot_is_open(room, start_at, end_at):
    if not room.is_available:
        return False
    rule = next((h for h in room.hours if h.weekday == start_at.weekday()), None)
    return bool(rule and not rule.is_closed and start_at.date() == end_at.date()
                and rule.open_time <= start_at.time() and end_at.time() <= rule.close_time)


def search_rooms(db, start_at, end_at, building_id=None, capacity=1, available_only=False):
    stmt = select(Room).options(joinedload(Room.building), selectinload(Room.hours)).order_by(Room.room_number)
    if building_id:
        stmt = stmt.where(Room.building_id == building_id)
    stmt = stmt.where(Room.capacity >= capacity)
    rooms = db.scalars(stmt).unique().all()
    occupied = set(db.scalars(select(Reservation.room_id).where(
        Reservation.status == 'active', Reservation.start_at < end_at, Reservation.end_at > start_at
    )).all())
    result = []
    for room in rooms:
        status = 'closed' if not slot_is_open(room, start_at, end_at) else ('booked' if room.id in occupied else 'available')
        if not available_only or status == 'available':
            result.append((room, status))
    return result


def _locked_room(db, room_id):
    # SQLite has no SELECT FOR UPDATE: serialize writers before checking overlap.
    # MySQL/InnoDB locks the room row. All reservation and availability writers
    # in this application acquire this same lock before making a change.
    if db.get_bind().dialect.name == 'sqlite':
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    return db.scalar(select(Room).where(Room.id == room_id).with_for_update())


def create_reservation(factory, user_id, room_id, start_at, end_at, now=None):
    if start_at >= end_at or start_at.date() != end_at.date():
        raise BookingError('order')
    if start_at < (now or datetime.now()):
        raise BookingError('past')
    with factory() as db:
        try:
            room = _locked_room(db, room_id)
            if room is None or db.get(User, user_id) is None:
                raise BookingError('notfound')
            if not slot_is_open(room, start_at, end_at):
                raise BookingError('closed')
            conflict = db.scalar(select(Reservation.id).where(
                Reservation.room_id == room_id, Reservation.status == 'active',
                Reservation.start_at < end_at, Reservation.end_at > start_at
            ).limit(1))
            if conflict is not None:
                raise BookingError('conflict')
            booking = Reservation(user_id=user_id, room_id=room_id, start_at=start_at,
                                  end_at=end_at, status='active')
            db.add(booking)
            db.commit()
            return booking.id
        except Exception:
            db.rollback()
            raise


def cancel_reservation(factory, booking_id, actor_id, is_staff):
    with factory() as db:
        try:
            # Determine the room, then acquire its lock and reread the reservation.
            initial = db.get(Reservation, booking_id)
            if initial is None:
                raise BookingError('notfound')
            room_id = initial.room_id
            # End the read transaction before acquiring SQLite's write lock.
            db.rollback()
            _locked_room(db, room_id)
            booking = db.get(Reservation, booking_id)
            if booking is None:
                raise BookingError('notfound')
            if not is_staff and booking.user_id != actor_id:
                raise BookingError('forbidden')
            if booking.status != 'active':
                raise BookingError('already_cancelled')
            booking.status = 'cancelled'
            db.commit()
        except Exception:
            db.rollback()
            raise


def lock_for_admin(db, room_id):
    room = _locked_room(db, room_id)
    if room is None:
        raise BookingError('notfound')
    return room


def seed_demo(factory):
    # Seed only an entirely empty project database; never overwrite user data.
    with factory() as db:
        for model in (User, Building, Room, RoomHours, Reservation):
            if db.scalar(select(func.count()).select_from(model)):
                return False
        student = User(name='Alex Chen', email='student@example.edu',
                       password_hash=generate_password_hash('Student123!'), role='student')
        staff = User(name='Morgan Lee', email='staff@example.edu',
                     password_hash=generate_password_hash('Staff123!'), role='staff')
        library = Building(name='Library', code='LB')
        union = Building(name='Student Union', code='SU')
        science = Building(name='Science Center', code='SC')
        db.add_all([student, staff, library, union, science]); db.flush()
        data = [(library,'L101','1',4,'Whiteboard,Power outlets'),
                (library,'L204','2',6,'Display,Whiteboard'),
                (library,'L310','3',8,'Display,Power outlets'),
                (union,'U105','1',4,'Whiteboard,Power outlets'),
                (union,'U208','2',8,'Display,Whiteboard'),
                (science,'S302','3',6,'Display,Power outlets')]
        rooms=[]
        for building, number, floor, capacity, features in data:
            room=Room(building_id=building.id, room_number=number, floor=floor,
                      capacity=capacity, features=features, is_available=True)
            db.add(room); db.flush(); rooms.append(room)
            for weekday in range(7):
                db.add(RoomHours(room_id=room.id, weekday=weekday, open_time=time(8), close_time=time(22), is_closed=False))
        tomorrow=(datetime.now()+timedelta(days=1)).date()
        db.add(Reservation(user_id=student.id, room_id=rooms[1].id,
                           start_at=datetime.combine(tomorrow,time(10)),
                           end_at=datetime.combine(tomorrow,time(11,30)),status='active'))
        db.commit()
        return True
