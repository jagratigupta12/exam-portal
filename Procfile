web: python manage.py migrate && python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='examadmin').exists():
    User.objects.create_superuser('examadmin', '', 'Exam@5678')
    print('Superuser created!')
else:
    print('Superuser already exists!')
" && gunicorn exam_portal.wsgi