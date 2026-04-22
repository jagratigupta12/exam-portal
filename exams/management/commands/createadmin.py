from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create superuser automatically'

    def handle(self, *args, **kwargs):
        if not User.objects.filter(username='examadmin').exists():
            User.objects.create_superuser(
                username='examadmin',
                email='admin@exam.com',
                password='Exam@5678'
            )
            self.stdout.write('✅ Superuser created!')
        else:
            self.stdout.write('✅ Superuser already exists!')