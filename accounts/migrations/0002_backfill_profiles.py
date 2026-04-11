"""
Data migration: create a UserProfile for every existing User that doesn't have one.
Superusers get role='admin'; everyone else gets role='viewer'.
"""
from django.db import migrations


def create_profiles(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('accounts', 'UserProfile')
    for user in User.objects.all():
        if not UserProfile.objects.filter(user=user).exists():
            role = 'admin' if user.is_superuser else 'viewer'
            UserProfile.objects.create(user=user, role=role)


def delete_profiles(apps, schema_editor):
    # Reverse: remove all profiles (safe for rollback in dev)
    apps.get_model('accounts', 'UserProfile').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_profiles, delete_profiles),
    ]
