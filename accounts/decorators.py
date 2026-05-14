from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


def _get_role(user):
    """Safely read the user's role; default to 'viewer' if profile is missing."""
    try:
        return user.profile.role
    except Exception:
        return 'viewer'


def login_required(view_func):
    """Redirect to login page if the user is not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return view_func(request, *args, **kwargs)
    return wrapper


def editor_required(view_func):
    """Require login + editor or admin role.  Viewers get a 403 message."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if _get_role(request.user) not in ('editor', 'admin'):
            messages.error(
                request,
                "Huna ruhusa ya kufanya kitendo hiki. "
                "Unahitaji nafasi ya Editor au Admin."
            )
            return redirect(request.META.get('HTTP_REFERER', '/'))
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """Require login + admin role.  Editors and Viewers get a 403 message."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if _get_role(request.user) != 'admin':
            messages.error(
                request,
                "Huna ruhusa ya kufuta. Unahitaji nafasi ya Admin."
            )
            return redirect(request.META.get('HTTP_REFERER', '/'))
        return view_func(request, *args, **kwargs)
    return wrapper
