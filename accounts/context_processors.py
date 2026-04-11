def user_role(request):
    """
    Inject role flags into every template context so the sidebar and
    inline action buttons can show/hide based on the current user's role.
    """
    if not request.user.is_authenticated:
        return {'user_role': None, 'can_edit': False, 'can_delete': False}

    try:
        role = request.user.profile.role
    except Exception:
        role = 'viewer'

    return {
        'user_role':   role,
        'can_edit':    role in ('editor', 'admin'),
        'can_delete':  role == 'admin',
    }
