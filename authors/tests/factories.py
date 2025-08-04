import factory
from django.contrib.auth import get_user_model
import uuid
from ..models import RemoteNode

Author = get_user_model()


class AuthorFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Author instances"""

    class Meta:
        model = Author
        skip_postgeneration_save = True

    # Basic fields
    username = factory.Sequence(lambda n: f"testuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")

    # Set host to test server host to ensure these are local authors
    host = "http://testserver/"

    # Generate URL based on serial
    url = factory.LazyAttribute(
        lambda obj: f"http://testserver/api/authors/{obj.serial}/")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return
        # Use a default password if one isn't provided
        password = extracted if extracted else "testpass123"
        obj.set_password(password)
        # The object has been saved once already, but we need to save it
        # again to persist the hashed password.
        obj.save()

    # Author-specific fields
    serial = factory.LazyFunction(uuid.uuid4)
    display_name = factory.Faker('name')
    github = factory.LazyAttribute(
        lambda obj: f"http://github.com/{obj.username}")
    profile_image = "https://example.com/profile.jpg"

    # Active user
    is_active = True


class FollowFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Follow instances"""

    class Meta:
        model = 'authors.Follow'

    # Create two different authors by default
    follower = factory.SubFactory(AuthorFactory)
    following = factory.SubFactory(AuthorFactory)

    # Default status is pending
    status = 'PENDING'

    @classmethod
    def create_accepted(cls, **kwargs):
        """Create an accepted follow relationship"""
        return cls.create(status='ACCEPTED', **kwargs)

    @classmethod
    def create_rejected(cls, **kwargs):
        """Create a rejected follow relationship"""
        return cls.create(status='REJECTED', **kwargs)

    @classmethod
    def create_friendship(cls, author1=None, author2=None):
        """Create a mutual friendship (both follow each other)"""
        if author1 is None:
            author1 = AuthorFactory()
        if author2 is None:
            author2 = AuthorFactory()

        # Create both follow relationships as accepted
        follow1 = cls.create_accepted(follower=author1, following=author2)
        follow2 = cls.create_accepted(follower=author2, following=author1)

        return follow1, follow2


class RemoteNodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RemoteNode

    host = factory.Faker('url')
    outgoing_username = factory.Faker("user_name")
    outgoing_password = factory.Faker("password")
    incoming_username = factory.Faker("user_name")
    incoming_password = factory.Faker("password")
    is_active = True


class RemoteAuthorFactory(factory.django.DjangoModelFactory):
    """Factory for creating test Author instances"""

    class Meta:
        model = Author
        skip_postgeneration_save = True

    # Basic fields
    username = factory.Sequence(lambda n: f"remoteuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")

    # Set host to remote server host to ensure these are local authors
    host = "https://remote.example.com"

    # Generate URL based on serial
    url = factory.LazyAttribute(
        lambda obj: f"{obj.host.rstrip('/')}/api/authors/{obj.serial}/")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return
        # Use a default password if one isn't provided
        password = extracted if extracted else "testpass123"
        obj.set_password(password)
        # The object has been saved once already, but we need to save it
        # again to persist the hashed password.
        obj.save()

    # Author-specific fields
    serial = factory.LazyFunction(uuid.uuid4)
    display_name = factory.Faker('name')
    github = factory.LazyAttribute(
        lambda obj: f"http://github.com/{obj.username}")
    profile_image = "https://example.com/profile.jpg"

    # Active user
    is_active = True
