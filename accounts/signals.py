from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a UserProfile for every new User."""
    if created:
        from accounts.models import UserProfile
        # Superusers get admin role automatically
        role = 'admin' if instance.is_superuser else 'viewer'
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})


@receiver(post_save, sender=User)
def sync_admin_flags(sender, instance, **kwargs):
    """Keep is_staff in sync with admin role (required for Django admin access)."""
    try:
        profile = instance.profile
        needs_staff = profile.role == 'admin'
        if instance.is_staff != needs_staff:
            User.objects.filter(pk=instance.pk).update(is_staff=needs_staff)
    except Exception:
        pass
