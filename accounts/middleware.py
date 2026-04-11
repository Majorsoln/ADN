from django.conf import settings
from django.shortcuts import redirect


# URLs that unauthenticated users are allowed to access
_EXEMPT = (
    '/accounts/login/',
    '/accounts/logout/',
    '/admin/',          # Django admin handles its own auth
    '/static/',
    '/media/',
)


class LoginRequiredMiddleware:
    """
    Global login guard — runs on every request BEFORE any view is called.
    Redirects anonymous users to the login page unless the URL is explicitly
    exempt (login page itself, admin, static/media files).

    This complements the per-view @login_required decorators and ensures that
    any view accidentally left without a decorator is still protected.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            # Allow exempt URLs (login page, admin, static files)
            if not any(path.startswith(prefix) for prefix in _EXEMPT):
                return redirect(f"{settings.LOGIN_URL}?next={path}")
        return self.get_response(request)
