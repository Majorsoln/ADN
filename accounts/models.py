from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'Viewer — Kuona tu'),
        ('editor', 'Editor — Kuona, Kuongeza, Kuhariri'),
        ('admin',  'Admin — Mamlaka Yote'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    # ── Convenience properties ─────────────────────────────────────────────────

    @property
    def is_viewer(self):
        """All authenticated users can at least view."""
        return True

    @property
    def is_editor(self):
        """Editor and Admin can add and edit."""
        return self.role in ('editor', 'admin')

    @property
    def is_admin(self):
        """Only Admin has full access including delete and Django admin."""
        return self.role == 'admin'
