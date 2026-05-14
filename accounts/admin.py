from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Role'
    fields = ('role',)


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_active')
    list_filter  = ('is_active', 'profile__role')

    @admin.display(description='Role')
    def get_role(self, obj):
        try:
            return obj.profile.get_role_display()
        except Exception:
            return '—'

    def save_formset(self, request, form, formset, change):
        """Sync is_staff flag when role changes via the admin."""
        super().save_formset(request, form, formset, change)
        try:
            profile = form.instance.profile
            form.instance.is_staff = profile.role == 'admin'
            form.instance.save(update_fields=['is_staff'])
        except Exception:
            pass


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
