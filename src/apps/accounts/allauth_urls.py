from django.urls import path, re_path

from apps.accounts.views import (
    PublicDemoConfirmEmailView,
    PublicDemoEmailView,
    PublicDemoPasswordChangeView,
    PublicDemoPasswordSetView,
)


urlpatterns = [
    path('email/', PublicDemoEmailView.as_view(), name='account_email'),
    path(
        'password/change/',
        PublicDemoPasswordChangeView.as_view(),
        name='account_change_password',
    ),
    path(
        'password/set/',
        PublicDemoPasswordSetView.as_view(),
        name='account_set_password',
    ),
    re_path(
        r'^confirm-email/(?P<key>[-:\w]+)/$',
        PublicDemoConfirmEmailView.as_view(),
        name='account_confirm_email',
    ),
]
