from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Time, UniqueConstraint, column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='student')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    reservations: Mapped[list['Reservation']] = relationship(back_populates='user')
    __table_args__ = (CheckConstraint(column("role").in_(["student", "staff"]), name="ck_user_role"), {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'})


class Building(Base):
    __tablename__ = 'buildings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    rooms: Mapped[list['Room']] = relationship(back_populates='building')
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}


class Room(Base):
    __tablename__ = 'rooms'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey('buildings.id'), nullable=False)
    room_number: Mapped[str] = mapped_column(String(30), nullable=False)
    floor: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[str] = mapped_column(String(255), default='', nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    building: Mapped['Building'] = relationship(back_populates='rooms')
    hours: Mapped[list['RoomHours']] = relationship(back_populates='room', cascade='all, delete-orphan')
    reservations: Mapped[list['Reservation']] = relationship(back_populates='room')
    __table_args__ = (
        UniqueConstraint('building_id', 'room_number', name='uq_building_room'),
        CheckConstraint('capacity > 0 AND capacity <= 100', name='ck_room_capacity'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class RoomHours(Base):
    __tablename__ = 'room_hours'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # Monday=0
    open_time = mapped_column(Time, nullable=False)
    close_time = mapped_column(Time, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    room: Mapped['Room'] = relationship(back_populates='hours')
    __table_args__ = (
        UniqueConstraint('room_id', 'weekday', name='uq_room_weekday'),
        CheckConstraint('weekday >= 0 AND weekday <= 6', name='ck_weekday'),
        CheckConstraint('open_time < close_time', name='ck_hours_order'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class Reservation(Base):
    __tablename__ = 'reservations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='active', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    user: Mapped['User'] = relationship(back_populates='reservations')
    room: Mapped['Room'] = relationship(back_populates='reservations')
    __table_args__ = (
        CheckConstraint('start_at < end_at', name='ck_reservation_time'),
        CheckConstraint("status IN ('active', 'cancelled')", name='ck_reservation_status'),
        Index('ix_conflicts', 'room_id', 'status', 'start_at', 'end_at'),
        Index('ix_user_reservations', 'user_id', 'start_at'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )
