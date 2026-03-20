#!/bin/sh
set -e
echo "Container role: ${APP_ROLE:-web}"
if [ "$APP_ROLE" = "web" ] || [ -z "$APP_ROLE" ]; then
  echo "Running Django migrations..."
  python manage.py migrate --noinput
  echo "Collecting static files..."
  python manage.py collectstatic --no-input --clear
  echo "Creating or updating superuser if needed..."
  if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
username = '$DJANGO_SUPERUSER_USERNAME'
email = '$DJANGO_SUPERUSER_EMAIL'
password = '$DJANGO_SUPERUSER_PASSWORD'
try:
    user = User.objects.get(email=email)
    # User exists, check if password needs updating
    if not user.check_password(password):
        user.set_password(password)
        user.email = email
        user.save()
        print(f'Superuser "{username}" password and email updated.')
    else:
        print(f'Superuser "{username}" already exists with correct credentials.')
except User.DoesNotExist:
    # User doesn't exist, create it
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f'Superuser "{username}" created successfully.')
EOF
  else
    echo "Superuser environment variables not set. Skipping superuser creation."
  fi
else
  echo "Skipping migrate & collectstatic for role: $APP_ROLE"
fi
echo "Starting main process: $@"
exec "$@"
