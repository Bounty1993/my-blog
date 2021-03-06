from django.conf import settings
from django.db import models
from django.db.models import Count, F, Q, Sum


class VisibleManager(models.QuerySet):
    def get_visible(self, user):
        """
        Method should be used to get all visible rooms for the user.
        Room is visible if (one of is true):
            room's attribute is_visible == True,
            the creator of room is the user,
            the user is in room's guests
        """
        visible_query = self.filter(visible=True)
        room_created = user.rooms.all()
        room_guests = user.guest_rooms.all()
        return (visible_query | room_created | room_guests).distinct()

    def summarise_for_list(self):
        """method used for optimalisation"""
        return self.prefetch_related('observers').prefetch_related('patrons')

    def search(self, field):
        """General method used for searching in views"""
        return self.filter(
            Q(receiver__icontains=field) |
            Q(gift__icontains=field) |
            Q(description__icontains=field)
        )

    def most_popular(self):
        popular = (self
                   .annotate(collected=F('price')-F('to_collect'))
                   .order_by('-collected')
                   )
        return popular

    def most_patrons(self):
        num_patrons = (self
                       .annotate(patrons_number=Count('patrons'))
                       .exclude(patrons_number=0)
                       .order_by('-patrons_number')
                       )
        return num_patrons

    def most_to_collect(self):
        return self.order_by('-to_collect')


class Room(models.Model):
    receiver = models.CharField('odbiorca', max_length=50)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        related_name='rooms',
        null=True,
        blank=True,
    )
    gift = models.CharField('Cel', max_length=50)
    gift_url = models.URLField('Adres internetowy celu', blank=True)
    price = models.DecimalField('Cena', max_digits=11, decimal_places=2)
    description = models.CharField('Opis', max_length=250, blank=True)
    to_collect = models.DecimalField(
        'Do zebrania', max_digits=11, decimal_places=2
    )
    visible = models.BooleanField('Widoczny dla wszystkich?')
    created = models.DateField(auto_now_add=True)
    date_expires = models.DateField('Data wygaśnięcia')
    is_active = models.BooleanField(default=True)
    score = models.FloatField(default=0)
    guests = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='guest_rooms',
    )
    patrons = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        through='Donation'
    )
    observers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='observed_rooms'
    )

    objects = VisibleManager.as_manager()
    get_visible = VisibleManager.as_manager()

    class Meta:
        ordering = ['-date_expires']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def percent_left(self):
        return (self.to_collect / self.price) * 100

    @property
    def percent_got(self):
        return 100 - self.percent_left

    @property
    def num_patrons(self):
        return self.patrons.count()

    def __str__(self):
        return f'{self.receiver} - {self.gift}'

    """
    def get_absolute_url(self):
        return reverse('rooms:detail', kwargs={'pk': self.id})
    """

    def can_see(self, user):
        """
        Verify is user can see the room.
        Is room is not visible and user is not in guests and is
        not a creator then us used cannot see
        """
        if self.visible:
            return True
        can_see = list(self.guests.all()) if self.guests.exists() else []
        can_see.append(self.creator)
        if user in can_see:
            return True
        return False

    def update_score(self):
        # It needs more development - unfortunately...
        # Problem is a recursion when signals
        patrons_rank = self.patrons.count() * 2
        observers_rank = self.observers.count()
        collected_rank = self.collected() / 1000
        total_rank = patrons_rank + observers_rank + collected_rank
        self.score = total_rank

    def is_visible(self):
        """True if room is visible for everyone else false"""
        return self.visible

    def add_observer(self, user_id):
        """used to add observer"""
        try:
            self.observers.add(user_id)
        except ValueError:
            return {'is_valid': 'false'}
        return {'is_valid': 'true'}

    def donate(self, data):
        """
        method is responsible for making donation. If donation is
        bigger than amount to collect the room's attribute is_visible
        will be change to not active. It is not a problem if amount
        is bigger than to collect attribute.
        :param data: dictionary for making donations
            {'user': int - required - user who makes the donation,
             'amount': decimal - required - amount of the donation,
             'date': date - optional - when donation will be made
             'comment': string - optional - comment for donation}
        :return: self or dict({'error': reason of error})
        """
        try:
            user = data['user']
            amount = data['amount']
        except KeyError:
            return {'error': 'Brak wszystkich danych'}
        date = data.get('date', None)
        comment = data.get('comment', amount)
        actual_amount = amount if amount < self.to_collect else self.to_collect
        full_collection = self.to_collect <= amount
        if full_collection:
            self.to_collect = 0
            self.is_active = False
        else:
            self.to_collect -= amount
        donation = Donation(
            user=user,
            room=self,
            date=date,
            amount=actual_amount,
            comment=comment
        )
        donation.save()
        self.save()
        return self

    def get_patrons(self):
        """
        :return: list of patrons in format [username1, username2, ...]
        """
        patrons = (
            self.donations.values_list('user__username', flat=True)
            .annotate(total_amount=Sum('amount'))
            .order_by('-total_amount')
        )
        return patrons

    def guest_remove(self, guest_name):
        guest = self.guests.filter(username=guest_name)
        if guest.count() != 1:
            return {'error': 'Nie ma takiego użytkownika'}
        self.guests.remove(guest.first())
        return self.get_guests_dict()

    def get_guests_dict(self):
        """guests as a list"""
        guests = self.guests.values_list('username', flat=True)
        guests_list = [guest for guest in guests]
        return guests_list

    def collected(self):
        """money which has been already collected"""
        return self.price - self.to_collect

    def all_likes(self):
        posts = self.posts
        likes_per_post = posts.data_with_likes()
        all_likes = likes_per_post.aggregate(Sum('all_likes'))
        return all_likes

    def all_comments(self):
        """
        method should not be used for all rooms because it
        will cause a lot of duplicated queries. Use only number
        for single room is needed.
        :return: number of all comments and threads for the room
        """
        posts = self.posts
        num_threads = (
            posts
            .annotate(num_threads=Count('threads'))
            .aggregate(Sum(F'num_threads'))
        )
        return num_threads


class DonationQuerySet(models.QuerySet):

    def resume(self):   # will be change
        return 'wiadomość'

    def get_chart_data(self):
        categories = [1, 2, 3, 4, 5]
        data = self.values('date').annotate(amount__sum=Sum('amount'))
        chart_data = {
            'categories': [x['date'] for x in data],
            'data': [int(x['amount__sum']) for x in data]
        }
        return chart_data


class Donation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name='donations'
    )
    date = models.DateField(auto_now=True)
    amount = models.DecimalField(max_digits=11, decimal_places=2)
    comment = models.CharField(max_length=250, blank=True)

    objects = DonationQuerySet.as_manager()

    class Meta:
        ordering = ['date', ]
        get_latest_by = ['date', ]

    def __str__(self):
        return f'{self.room} - {self.amount}'


class Message(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    subject = models.CharField('Tytuł', max_length=150)
    content = models.CharField('Treść', max_length=255)

    def __str__(self):
        return f'{self.receiver} - {self.subject}'
