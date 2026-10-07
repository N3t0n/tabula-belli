from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.conf import settings

from .policies import can_manage_event


class VerifiedUserRequiredMixin(LoginRequiredMixin):
    """
    Require users to have a verified email address.
    Inherits login check from LoginRequiredMixin.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if settings.ACCOUNT_EMAIL_VERIFICATION == 'none':
            return super().dispatch(request, *args, **kwargs)

        if not request.user.emailaddress_set.filter(verified=True).exists():
            messages.warning(
                request, "Please verify your email to access this feature.")
            return redirect('account_email')

        return super().dispatch(request, *args, **kwargs)


class EventManagementRequiredMixin(UserPassesTestMixin):

    def test_func(self):
        event = self.get_object()
        return can_manage_event(self.request.user, event)
