def can_manage_event(user, event):
    """Return whether a user can perform event management actions."""
    return bool(
        user.is_authenticated
        and (event.organizer_id == user.id or user.is_superuser)
    )
