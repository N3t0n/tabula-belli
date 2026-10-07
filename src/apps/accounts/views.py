from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models.deletion import ProtectedError
from django.db import IntegrityError
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from allauth.account.views import (
    ConfirmEmailView,
    EmailView,
    PasswordChangeView,
    PasswordSetView,
)
import logging
import json

from apps.accounts.demo import DEMO_ACCOUNT_NOTICE, is_public_demo_user
from apps.accounts.forms import ProfileForm
from apps.accounts.deletion import (
    AccountDeletionBlocked, IN_PROGRESS_ERROR, SUPERUSER_ERROR,
    confirmation_token, delete_account, deletion_review,
)

logger = logging.getLogger(__name__)

def _is_htmx(request):
    return bool(request.headers.get('HX-Request'))


def _demo_context(user):
    return {
        'is_public_demo_account': is_public_demo_user(user),
    }


class PublicDemoAccountViewMixin:
    """Keep account screens visible while making the demo account read-only."""

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if is_public_demo_user(self.request.user):
            for field in form.fields.values():
                field.disabled = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_demo_context(self.request.user))
        return context

    def post(self, request, *args, **kwargs):
        if is_public_demo_user(request.user):
            messages.warning(request, DEMO_ACCOUNT_NOTICE)
            return redirect(request.path)
        return super().post(request, *args, **kwargs)


class PublicDemoEmailView(PublicDemoAccountViewMixin, EmailView):
    pass


class PublicDemoPasswordChangeView(
    PublicDemoAccountViewMixin, PasswordChangeView
):
    pass


class PublicDemoPasswordSetView(PublicDemoAccountViewMixin, PasswordSetView):
    pass


class PublicDemoConfirmEmailView(ConfirmEmailView):
    def post(self, request, *args, **kwargs):
        confirmation = self.get_object()
        if is_public_demo_user(confirmation.email_address.user):
            messages.warning(request, DEMO_ACCOUNT_NOTICE)
            return redirect('account_login')
        return super().post(request, *args, **kwargs)


class ProfileView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')

    def get(self, request):
        form = ProfileForm(instance=request.user)
        context = {'form': form, **_demo_context(request.user)}

        if request.META.get('HTTP_HX_REQUEST'):
            # If request comes from #profile-info (for update), return only info
            if request.META.get('HTTP_HX_TARGET') == 'profile-info':
                return render(request, 'accounts/profile_info.html', {
                    'user': request.user,
                    **_demo_context(request.user),
                })
            # Otherwise, it's for the modal, return form
            return render(request, 'accounts/profile_form.html', context)

        return render(request, 'accounts/profile.html', {
            'user': request.user,
            **context,
        })

    def post(self, request):
        if is_public_demo_user(request.user):
            messages.warning(request, DEMO_ACCOUNT_NOTICE)
            if _is_htmx(request):
                return JsonResponse(
                    {'success': False, 'error': DEMO_ACCOUNT_NOTICE},
                    status=403,
                    headers={'HX-Redirect': reverse('accounts:profile')},
                )
            return redirect('accounts:profile')

        if request.POST.get('_method', '').upper() == 'DELETE':
            return self.delete(request)

        form = ProfileForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            logger.info("Authenticated user updated their profile")

            if _is_htmx(request):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'profileUpdated': {'userId': request.user.id},
                    'modal-close': {}
                })
                return response

            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')
        else:
            if not _is_htmx(request):
                return render(request, 'accounts/profile.html', {
                    'user': request.user,
                    'form': form,
                    **_demo_context(request.user),
                }, status=400)

            response = render(request, 'accounts/profile_form.html', {
                'form': form,
                **_demo_context(request.user),
            }, status=400)
            response['HX-Reswap'] = 'outerHTML'
            return response

    def delete(self, request):
        # Legacy profile submissions lead to review, never bypass confirmation.
        if _is_htmx(request):
            return HttpResponse(status=200, headers={
                'HX-Redirect': reverse('accounts:delete'),
            })
        return redirect('accounts:delete')


class AccountDeleteView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')

    def get(self, request):
        review = deletion_review(request.user)
        return render(request, 'accounts/delete.html', {
            'review': review,
            'confirmation': confirmation_token(request.user, review),
            'in_progress_error': IN_PROGRESS_ERROR,
            'superuser_error': SUPERUSER_ERROR,
            **_demo_context(request.user),
        })

    def post(self, request):
        try:
            delete_account(request.user.pk, request.POST.get('confirmation', ''))
        except AccountDeletionBlocked as error:
            messages.error(request, str(error))
            if _is_htmx(request):
                return JsonResponse(
                    {'success': False, 'error': str(error)}, status=error.status,
                    headers={'HX-Redirect': reverse('accounts:delete')},
                )
            return redirect('accounts:delete')
        except (ProtectedError, IntegrityError):
            error = 'Your account could not be deleted. No changes were made. Please try again.'
            messages.error(request, error)
            logger.warning('Account deletion rolled back due to a protected relationship')
            if _is_htmx(request):
                return JsonResponse(
                    {'success': False, 'error': error}, status=409,
                    headers={'HX-Redirect': reverse('accounts:delete')},
                )
            return redirect('accounts:delete')

        logout(request)
        logger.info('User account deleted; event history retained without account links')
        if _is_htmx(request):
            return JsonResponse(
                {'success': True, 'message': 'Account deleted successfully'},
                headers={'HX-Redirect': '/'},
            )
        return redirect('/')
