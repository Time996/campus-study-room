import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from urllib.parse import urlencode
from sqlalchemy import select
from werkzeug.security import check_password_hash
from studyroom import create_app
from studyroom.models import Base, User, Room, Reservation
from studyroom.services import BookingError, create_reservation, seed_demo


class StudyRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = (Path(self.temp.name) / 'test.sqlite').as_posix()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only', 'DATABASE_URL': 'sqlite:///' + path, 'AUTO_INIT_DEMO': False})
        Base.metadata.create_all(self.app.extensions['study_engine'])
        self.assertTrue(seed_demo(self.app.extensions['study_sessions']))
        self.client = self.app.test_client()
        self.day = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')

    def tearDown(self):
        self.app.extensions['study_engine'].dispose()
        self.temp.cleanup()

    def csrf(self, client=None):
        client = client or self.client
        with client.session_transaction() as s:
            return s['_csrf_token']

    def visit(self, client=None):
        client = client or self.client
        return client.get('/')

    def login(self, email='student@example.edu', password='Student123!', client=None):
        client = client or self.client
        client.get('/auth/login')
        return client.post('/auth/login', data={'csrf_token': self.csrf(client), 'email': email, 'password': password}, follow_redirects=True)

    def test_home_search_and_validation(self):
        result=self.visit()
        self.assertEqual(result.status_code,200)
        self.assertIn(b'L101',result.data)
        q=urlencode({'day':self.day,'start':'10:00','end':'11:00','capacity':'8'})
        result=self.client.get('/?'+q)
        self.assertIn(b'L310',result.data)
        self.assertNotIn(b'L101',result.data)
        bad=self.client.get('/?'+urlencode({'day':self.day,'start':'11:00','end':'10:00'}))
        self.assertIn(b'End time must be later',bad.data)

    def test_registration_password_hash_and_duplicate_email(self):
        self.client.get('/auth/register')
        data={'csrf_token':self.csrf(),'name':'Test Student','email':'test@example.edu','password':'Example123!','confirm_password':'Example123!'}
        self.assertEqual(self.client.post('/auth/register',data=data).status_code,302)
        with self.app.extensions['study_sessions']() as db:
            user=db.scalar(select(User).where(User.email=='test@example.edu'))
            self.assertNotEqual(user.password_hash,'Example123!')
            self.assertTrue(check_password_hash(user.password_hash,'Example123!'))
            self.assertEqual(user.role,'student')
        other=self.app.test_client();other.get('/auth/register');data['csrf_token']=self.csrf(other)
        self.assertIn(b'already registered',other.post('/auth/register',data=data).data)

    def test_csrf_and_staff_access(self):
        self.visit()
        self.assertEqual(self.client.post('/auth/login',data={'email':'student@example.edu','password':'Student123!'}).status_code,400)
        self.login()
        self.assertEqual(self.client.get('/admin/').status_code,403)
        self.assertEqual(self.client.post('/admin/buildings/new',data={'csrf_token':self.csrf(),'name':'X','code':'X'}).status_code,403)
        other=self.app.test_client();self.login('staff@example.edu','Staff123!',other)
        self.assertEqual(other.get('/admin/').status_code,200)

    def test_book_overlap_cancel_and_ownership(self):
        self.visit();self.login()
        with self.app.extensions['study_sessions']() as db:
            r=db.scalar(select(Room).where(Room.room_number=='L101'));room_id=r.id
            other=db.scalar(select(User).where(User.email=='staff@example.edu'));staff_id=other.id
        payload={'csrf_token':self.csrf(),'day':self.day,'start':'10:00','end':'11:00'}
        self.assertEqual(self.client.post(f'/rooms/{room_id}/book',data=payload).status_code,302)
        with self.app.extensions['study_sessions']() as db:
            booking=db.scalar(select(Reservation).where(Reservation.room_id==room_id,Reservation.start_at>=datetime.fromisoformat(self.day)));booking_id=booking.id
        overlap={'csrf_token':self.csrf(),'day':self.day,'start':'10:30','end':'11:30'}
        r=self.client.post(f'/rooms/{room_id}/book',data=overlap,follow_redirects=True)
        self.assertIn(b'already reserved',r.data)
        edge={'csrf_token':self.csrf(),'day':self.day,'start':'11:00','end':'12:00'}
        self.assertEqual(self.client.post(f'/rooms/{room_id}/book',data=edge).status_code,302)
        foreign=self.app.test_client();foreign.get('/auth/register');foreign.post('/auth/register',data={'csrf_token':self.csrf(foreign),'name':'Another User','email':'another@example.edu','password':'Another123!','confirm_password':'Another123!'},follow_redirects=True)
        self.assertIn(b'cannot cancel another',foreign.post(f'/bookings/{booking_id}/cancel',data={'csrf_token':self.csrf(foreign)},follow_redirects=True).data)
        with self.app.extensions['study_sessions']() as db:self.assertEqual(db.get(Reservation,booking_id).status,'active')
        self.client.post(f'/bookings/{booking_id}/cancel',data={'csrf_token':self.csrf()})
        with self.app.extensions['study_sessions']() as db:self.assertEqual(db.get(Reservation,booking_id).status,'cancelled')
        self.assertEqual(self.client.post(f'/rooms/{room_id}/book',data=payload).status_code,302)

    def test_staff_room_and_hours_management(self):
        self.login('staff@example.edu','Staff123!')
        response=self.client.post('/admin/buildings/new',data={'csrf_token':self.csrf(),'name':'Arts Hall','code':'AH'})
        self.assertEqual(response.status_code,302)
        with self.app.extensions['study_sessions']() as db:
            from studyroom.models import Building
            b=db.scalar(select(Building).where(Building.code=='AH')); bid=b.id
        response=self.client.post('/admin/rooms/new',data={'csrf_token':self.csrf(),'room_number':'A101','floor':'1','building_id':str(bid),'capacity':'6','features':'Whiteboard','is_available':'1'})
        self.assertEqual(response.status_code,302)
        with self.app.extensions['study_sessions']() as db:room=db.scalar(select(Room).where(Room.room_number=='A101'));rid=room.id
        weekday=datetime.strptime(self.day,'%Y-%m-%d').weekday()
        self.client.post(f'/admin/rooms/{rid}/hours',data={'csrf_token':self.csrf(),'weekday':str(weekday),'open':'08:00','close':'22:00','is_closed':'1'})
        response=self.client.post(f'/rooms/{rid}/book',data={'csrf_token':self.csrf(),'day':self.day,'start':'12:00','end':'13:00'},follow_redirects=True)
        self.assertIn(b'outside its opening hours',response.data)

    def test_staff_cli_and_safe_redirect(self):
        result = self.app.test_cli_runner().invoke(args=['create-staff', '--name', 'New Staff', '--email', 'newstaff@example.edu'], input='Secure123!\nSecure123!\n')
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.extensions['study_sessions']() as db:
            created = db.scalar(select(User).where(User.email == 'newstaff@example.edu'))
            self.assertEqual(created.role, 'staff')
            self.assertTrue(check_password_hash(created.password_hash, 'Secure123!'))
        from studyroom import safe_next
        self.assertIsNone(safe_next('//evil.example/path'))
        self.assertIsNone(safe_next('/\\evil.example'))
        self.assertEqual(safe_next('/bookings'), '/bookings')

    def test_mysql_schema_and_lock_statement_compile(self):
        from sqlalchemy.dialects import mysql
        from sqlalchemy.schema import CreateTable
        dialect = mysql.dialect()
        for table in Base.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(dialect=dialect))
            self.assertIn('ENGINE=InnoDB', ddl)
        statement = str(select(Room).where(Room.id == 1).with_for_update().compile(dialect=dialect))
        self.assertIn('FOR UPDATE', statement)

    def test_concurrent_bookings_do_not_overlap_in_sqlite(self):
        factory=self.app.extensions['study_sessions']
        with factory() as db:
            room_id=db.scalar(select(Room.id).where(Room.room_number=='L101'))
            user_id=db.scalar(select(User.id).where(User.email=='student@example.edu'))
        start=datetime.strptime(self.day+' 14:00','%Y-%m-%d %H:%M');end=start+timedelta(hours=1); barrier=Barrier(2)
        def attempt():
            barrier.wait()
            try:create_reservation(factory,user_id,room_id,start,end);return 'booked'
            except BookingError as e:return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:attempt(),range(2)))
        self.assertCountEqual(outcomes,['booked','conflict'])


if __name__=='__main__':
    unittest.main(verbosity=2)
