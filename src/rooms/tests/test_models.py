from datetime import datetime

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.test import TestCase

from src.rooms.models import Donation, Room

User = get_user_model()


class RoomTransactionModelTest(TestCase):
    fixtures = ['src/rooms/tests/fixtures.json', ]

    def setUp(self):
        self.user1 = User.objects.get(username='testuser')
        self.user2 = User.objects.get(username='testuser2')
        self.user3 = User.objects.get(username='testuser3')

        room1 = Room.objects.get(gift='gift1')
        room2 = Room.objects.get(gift='gift2')
        room3 = Room.objects.get(gift='gift3')

        room1.donate({'user': self.user1, 'amount': 500})
        room2.donate({'user': self.user1, 'amount': 300})
        room2.donate({'user': self.user2, 'amount': 200})
        room3.donate({'user': self.user1, 'amount': 200})
        room3.donate({'user': self.user2, 'amount': 200})
        room3.donate({'user': self.user3, 'amount': 200})

        self.room = Room.objects.get(receiver='receiver1')
        self.room2 = room2

    def test_creation(self):
        room = Room.objects.get(receiver='receiver1')
        self.assertEqual(room.price, 1000)
        self.assertEqual(room.description, 'test')
        self.assertEqual(room.to_collect, 500)

    def test_str(self):
        room = Room.objects.get(receiver='receiver1')
        self.assertEqual(str(room), 'receiver1 - gift1')

    """
    def test_save(self):
        before_score = self.room.score
        self.room.donate({'user': self.user1, 'amount': 5})
        after_score = self.room.score
        print(self.room.score)
        self.assertTrue(after_score > before_score)
    """

    def test_can_see(self):
        room4 = Room.objects.create(
            receiver='receiver3', creator=self.user1, gift='gift3',
            price=800, description='test', to_collect=800,
            visible=False, date_expires=datetime(2019, 6, 6)
        )
        room4.guests.add(self.user2)
        self.assertTrue(room4.can_see(self.user1))
        self.assertTrue(room4.can_see(self.user2))
        self.assertFalse(room4.can_see(self.user3))

    def test_percent_left(self):
        all_donations = (
            Donation.objects
            .filter(room=self.room)
            .aggregate(Sum('amount'))['amount__sum']
        )
        expected = (all_donations / self.room.price) * 100
        self.assertEqual(self.room.percent_left, expected)

    def test_percent_got(self):
        expected = 100 - self.room.percent_left
        self.assertEqual(self.room.percent_got, expected)

    def test_patrons_count(self):
        expected = (Donation.objects
                    .filter(room=self.room2)
                    .aggregate(Count('user'))['user__count'])
        self.assertEqual(self.room2.num_patrons, expected)

    def test_most_patrons(self):
        most_patrons = Room.get_visible.most_patrons()
        expected = Room.objects.get(receiver='receiver3')
        self.assertEqual(most_patrons[0], expected)

    def test_most_popular(self):
        most_collected = Room.get_visible.most_popular()
        expected = Room.objects.get(receiver='receiver3')
        self.assertEqual(most_collected[0], expected)

    def test_most_to_collect(self):
        most_to_collect = Room.get_visible.most_to_collect()
        expected = Room.objects.get(receiver='receiver1')
        self.assertEqual(most_to_collect[0], expected)

    def test_add_observer(self):
        num_observers = self.room.observers.count()
        self.room.add_observer(self.user1.id)
        num_observers += 1
        self.assertEqual(self.room.observers.count(), num_observers)
        self.assertTrue(self.user1 in self.room.observers.all())

    def test_donate(self):
        room = Room.objects.get(receiver='receiver1')
        beginning = room.to_collect
        donate_amount = 200

        room.donate({'user': self.user1, 'amount': donate_amount})
        rest = beginning - donate_amount
        self.assertEqual(room.to_collect, rest)

        room.donate({'user': self.user1, 'amount': rest})
        self.assertFalse(room.is_active)
        self.assertEqual(room.to_collect, 0)

    def test_get_visible(self):
        room3 = Room.objects.create(
            receiver='receiver3', creator=self.user1,
            gift='gift3', price=800, description='test',
            to_collect=800, visible=False,
            date_expires=datetime(2019, 6, 6)
        )
        query = Room.objects.get_visible(self.user3)
        self.assertFalse(room3 in query)
        room3.guests.add(self.user2)
        query = Room.objects.get_visible(self.user2)
        self.assertTrue(room3 in query)

    def test_get_patrons(self):
        room3 = Room.objects.get(receiver='receiver2')
        patrons = room3.get_patrons()
        ordered_patrons = ['testuser', 'testuser2']
        self.assertEqual(list(patrons), ordered_patrons)

    def test_remove_guest(self):
        user = User.objects.first()
        self.room.guests.add(user)
        self.assertTrue(self.room.guests.filter(id=user.id))
        self.room.guest_remove(user.username)
        self.assertFalse(self.room.guests.filter(id=user.id))

    def test_get_guests_dict(self):
        self.room.guests.add(self.user1, self.user2)
        expected = [self.user1.username, self.user2.username]
        guest_list = self.room.get_guests_dict()

        self.assertEqual(guest_list, expected)


class DonationModelTest(TestCase):
    fixtures = ['src/rooms/tests/fixtures.json']

    def setUp(self):
        self.user1 = User.objects.get(username='testuser')
        self.room1 = Room.objects.get(gift='gift1')
        self.room1.donate({'user': self.user1, 'amount': 500})

    def test_donation_exists(self):
        self.assertTrue(Donation.objects.exists())

    def test_donation_fields(self):
        donation = Donation.objects.first()
        self.assertEqual(donation.user, self.user1)
        self.assertEqual(donation.amount, 500)
        self.assertEqual(donation.room, self.room1)
        self.assertEqual(donation.date, datetime.now().date())

    def test_str(self):
        donation = Donation.objects.first()
        expected = f'{donation.room} - {donation.amount}'
        self.assertEqual(str(donation), expected)
