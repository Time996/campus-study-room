-- Reference schema for MySQL 8.0. Generated from studyroom/models.py.
-- Create/select a database first, then run this on an empty database.
-- Alternatively run: python -m flask --app run:app init-db
-- InnoDB is required for the room-row reservation lock.

CREATE TABLE buildings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	UNIQUE (code)
)CHARSET=utf8mb4 ENGINE=InnoDB;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_role CHECK (`role` IN ('student', 'staff')), 
	UNIQUE (email)
)CHARSET=utf8mb4 ENGINE=InnoDB;

CREATE TABLE rooms (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	building_id INTEGER NOT NULL, 
	room_number VARCHAR(30) NOT NULL, 
	floor VARCHAR(20) NOT NULL, 
	capacity INTEGER NOT NULL, 
	features VARCHAR(255) NOT NULL, 
	is_available BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_building_room UNIQUE (building_id, room_number), 
	CONSTRAINT ck_room_capacity CHECK (capacity > 0 AND capacity <= 100), 
	FOREIGN KEY(building_id) REFERENCES buildings (id)
)CHARSET=utf8mb4 ENGINE=InnoDB;

CREATE TABLE reservations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	room_id INTEGER NOT NULL, 
	start_at DATETIME NOT NULL, 
	end_at DATETIME NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reservation_time CHECK (start_at < end_at), 
	CONSTRAINT ck_reservation_status CHECK (status IN ('active', 'cancelled')), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id)
)CHARSET=utf8mb4 ENGINE=InnoDB;
CREATE INDEX ix_conflicts ON reservations (room_id, status, start_at, end_at);
CREATE INDEX ix_user_reservations ON reservations (user_id, start_at);

CREATE TABLE room_hours (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	room_id INTEGER NOT NULL, 
	weekday INTEGER NOT NULL, 
	open_time TIME NOT NULL, 
	close_time TIME NOT NULL, 
	is_closed BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_room_weekday UNIQUE (room_id, weekday), 
	CONSTRAINT ck_weekday CHECK (weekday >= 0 AND weekday <= 6), 
	CONSTRAINT ck_hours_order CHECK (open_time < close_time), 
	FOREIGN KEY(room_id) REFERENCES rooms (id)
)CHARSET=utf8mb4 ENGINE=InnoDB;
