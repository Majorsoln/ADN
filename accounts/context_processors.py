from django.conf import settings


def user_role(request):
    """
    Inject role flags and company info into every template context.
    """
    if not request.user.is_authenticated:
        return {
            'user_role':  None,
            'can_edit':   False,
            'can_delete': False,
            'company':    getattr(settings, 'COMPANY', {}),
        }

    try:
        role = request.user.profile.role
    except Exception:
        role = 'viewer'

    return {
        'user_role':   role,
        'can_edit':    role in ('editor', 'admin'),
        'can_delete':  role == 'admin',
        'company':     getattr(settings, 'COMPANY', {}),
    }
