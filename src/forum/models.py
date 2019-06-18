from django.conf import settings
from django.db import models
from django.db.models import Sum, F, Q, Count
from django.forms.models import model_to_dict
from django.db.models.functions import Coalesce
from src.rooms.models import Room


class PostQuerySet(models.QuerySet):
    def get_visible(self):
        return self.filter(room__visible=True)

    def search(self, field):
        queryset = self.filter(
            Q(room__gift__icontains=field) |
            Q(author__username__icontains=field) |
            Q(subject__icontains=field) |
            Q(content__icontains=field) |
            Q(threads__subject__icontains=field) |
            Q(threads__content__icontains=field)
        ).distinct()
        return queryset

    def summarise(self):
        all_comments = []
        for post in self.prefetch_related('threads').prefetch_related('author'):
            post_detail = {
                'id': post.id,
                'author': post.author,
                'subject': post.subject,
                'content': post.content,
                'likes': post.get_likes(),
                'date': post.date,
                'threads': post.threads.count(),
            }
            all_comments.append(post_detail)
        all_comments = self.annotate(likes=Coalesce(Sum('opinions__likes'), 0))
        return all_comments

    def data_with_likes(self):
        posts_with_likes = (
            self.annotate(all_likes=Coalesce(Sum(F('threads__opinions__likes') + F('opinions__likes')), 0))
        )
        ordered_posts = posts_with_likes.order_by('-all_likes')
        return ordered_posts


class Post(models.Model):
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE,
        related_name='posts'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET('Konto usunięte')
    )
    subject = models.CharField('Tytuł', max_length=100)
    content = models.CharField('Treść', max_length=500)
    date = models.DateTimeField(auto_now_add=True)

    visible = PostQuerySet.as_manager()
    objects = models.Manager()

    def __str__(self):
        return self.subject

    @property
    def score(self):
        all_likes = self.all_likes
        if not all_likes:
            all_likes = 0
        num_threads = self.threads.count()
        return all_likes + num_threads

    def get_likes(self):
        likes = self.opinions.aggregate(likes__sum=Coalesce(Sum('likes'), 0))
        return likes['likes__sum']

    def add_like(self, user):
        Opinion.objects.create(
            post=self,
            user=user,
            likes=1
        )

    def add_dislike(self, user):
        Opinion.objects.create(
            post=self,
            user=user,
            likes=-1
        )


class ThreadQuerySet(models.QuerySet):
    def get_all_children(self):
        node = []
        for thread in self.filter(parent__isnull=True):
            data = thread.show_children()
            node.append(data)
        return node

    def get_main(self, post_id):
        main_threads = self.filter(post_id=post_id, parent__isnull=True)
        threads_dict = {}
        for num, thread in enumerate(main_threads):
            one_thread_dict = {str(num): thread.summarise()}
            threads_dict.update(one_thread_dict)
        return threads_dict

    def get_secondary(self, thread_id):
        threads = self.filter(parent_id=thread_id)
        threads_dict = {}
        for num, thread in enumerate(threads):
            one_thread_dict = {num: thread.summarise()}
            threads_dict.update(one_thread_dict)
        return threads_dict


class Thread(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='threads')
    subject = models.CharField('Tytuł', max_length=100)
    content = models.CharField('Treść', max_length=500)
    date = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='children'
    )

    objects = ThreadQuerySet.as_manager()

    def has_parent(self):
        if self.parent:
            return True
        return False

    def summarise(self):
        summary = model_to_dict(self)
        summary['author'] = self.author.username
        summary['date'] = self.date.strftime('%d.%m.%y %H:%M')
        thread_parent = self.parent.id if self.parent else None
        summary.update({
            'children_count': self.children.count(),
            'thread_parent': thread_parent
        })
        return summary

    def get_likes(self):
        likes = self.opinions.aggregate(likes__sum=Coalesce(Sum('likes'), 0))
        return likes['likes__sum']

    def show_children(self):
        all_threads = []
        if not self.children.all():
            return all_threads
        for thread in self.children.all():
            all_threads.append({thread: thread.show_children()})
        return all_threads

    def add_like(self, user):
        Opinion.objects.create(
            thread=self,
            user=user,
            likes=1
        )

    def add_dislike(self, user):
        Opinion.objects.create(
            thread=self,
            user=user,
            likes=-1
        )


class Opinion(models.Model):
    LIKE = 1
    DISLIKE = -1
    OPINION_CHOICES = [
        (LIKE, 'like'),
        (DISLIKE, 'dislike'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        null=True,
        related_name='opinions',
    )
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        null=True,
        related_name='opinions'
    )
    likes = models.IntegerField(choices=OPINION_CHOICES)
    date = models.DateField(auto_now_add=True)
