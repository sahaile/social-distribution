from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from authors.models import RemoteNode


class Command(BaseCommand):
    help = 'Creates or updates a RemoteNode with specified credentials.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            type=str,
            required=True,
            help='The base URL of the remote node.')
        parser.add_argument(
            '--outgoing-user',
            type=str,
            required=True,
            help='Username for connecting TO the remote node.')
        parser.add_argument(
            '--outgoing-pass',
            type=str,
            required=True,
            help='Password for connecting TO the remote node.')
        parser.add_argument(
            '--incoming-user',
            type=str,
            required=True,
            help='Username for the remote node to connect TO US.')
        parser.add_argument(
            '--incoming-pass',
            type=str,
            required=True,
            help='Password for the remote node to connect TO US.')

    def handle(self, *args, **options):
        host = options['host']
        if not host.endswith('/'):
            host += '/'

        try:
            node, created = RemoteNode.objects.update_or_create(
                host=host,
                defaults={
                    'outgoing_username': options['outgoing_user'],
                    'outgoing_password': options['outgoing_pass'],
                    'incoming_username': options['incoming_user'],
                    'incoming_password': make_password(
                        options['incoming_pass']
                    ),
                    'is_active': True
                }
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully created RemoteNode for host: {host}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully updated RemoteNode for host: {host}"))

        except Exception as e:
            raise CommandError(
                f"Error creating or updating RemoteNode for host {host}: {e}")
