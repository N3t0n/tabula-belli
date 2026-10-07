from django.conf import settings


DEMO_ACCOUNT_NOTICE = (
    'Profile and account settings are read-only for this shared demo account. '
    'Create your own account to update profile details, email or password.'
)


def is_public_demo_user(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and user.username == settings.PUBLIC_DEMO_USERNAME
    )
