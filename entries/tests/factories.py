import factory
from django.contrib.contenttypes.models import ContentType
from authors.tests.factories import AuthorFactory
from ..models import Entry, Comment, Like
import uuid


class EntryFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Entry instances"""
    class Meta:
        model = Entry

    author = factory.SubFactory(AuthorFactory)
    title = factory.Faker('sentence')
    description = factory.Faker('paragraph')
    content_type = 'text/plain'
    content = factory.Faker('text')
    visibility = 'PUBLIC'

    # Generate unique FQID for the entry
    serial = factory.LazyFunction(uuid.uuid4)
    url = factory.LazyAttribute(
        lambda obj: (
            f"{obj.author.host.rstrip('/')}/api/authors/"
            f"{obj.author.serial}/entries/{obj.serial}/"
        )
    )


class CommentFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Comment instances"""
    class Meta:
        model = Comment

    author = factory.SubFactory(AuthorFactory)
    entry = factory.SubFactory(EntryFactory)
    comment = factory.Faker('sentence')
    content_type = 'text/plain'

    # Generate unique FQID for the comment
    serial = factory.LazyFunction(uuid.uuid4)
    url = factory.LazyAttribute(
        lambda obj: (
            f"{obj.author.host.rstrip('/')}/api/authors/"
            f"{obj.author.serial}/commented/{obj.serial}/"
        )
    )


class LikeFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Like instances"""
    class Meta:
        model = Like

    author = factory.SubFactory(AuthorFactory)

    # By default, likes are for Entries, but this can be overridden in tests
    # to point to a Comment instead.
    content_object = factory.SubFactory(EntryFactory)
    object_id = factory.SelfAttribute('content_object.url')
    content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )

    # Generate unique FQID for the like
    serial = factory.LazyFunction(uuid.uuid4)
    url = factory.LazyAttribute(
        lambda obj: (
            f"{obj.author.host.rstrip('/')}/api/authors/"
            f"{obj.author.serial}/liked/{obj.serial}/"
        )
    )
