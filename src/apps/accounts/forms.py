from django import forms
from allauth.account.forms import (
    AddEmailForm, ChangePasswordForm, ResetPasswordForm, ResetPasswordKeyForm, SetPasswordForm,
    SignupForm, UserTokenForm,
)
from allauth.account.adapter import get_adapter

from apps.accounts.demo import is_public_demo_user
from apps.players.models import Player
from cities_light.models import Region, City, Country


class TermsSignupForm(SignupForm):
    terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must accept the terms to create an account.'},
    )


class ProfileForm(forms.ModelForm):

    class Meta:
        model = Player
        fields = ['username', 'first_name', 'last_name',
                  'country', 'region', 'city', 'favorite_games']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['region'].queryset = Region.objects.none()
        self.fields['city'].queryset = City.objects.none()

        if self.is_bound:
            country_id = self.data.get('country')
            region_id = self.data.get('region')

            if country_id:
                try:
                    self.fields['region'].queryset = Region.objects.filter(
                        country_id=country_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass

            if country_id and region_id:
                try:
                    self.fields['city'].queryset = City.objects.filter(
                        country_id=country_id,
                        region_id=region_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass
            elif country_id:
                try:
                    self.fields['city'].queryset = City.objects.filter(
                        country_id=country_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass

        elif self.instance.pk:
            if self.instance.country:
                self.fields['region'].queryset = Region.objects.filter(
                    country=self.instance.country
                ).order_by('name')

            if self.instance.region:
                self.fields['city'].queryset = City.objects.filter(
                    region=self.instance.region
                ).order_by('name')
            elif self.instance.country:
                self.fields['city'].queryset = City.objects.filter(
                    country=self.instance.country
                ).order_by('name')

        if is_public_demo_user(self.instance):
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get('city')

        if city:
            cleaned_data['country'] = city.country
            cleaned_data['region'] = city.region

        return cleaned_data


class AccountInputStyleMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs['class'] = 'form-control'


class StyledAddEmailForm(AccountInputStyleMixin, AddEmailForm):
    pass


class StyledChangePasswordForm(AccountInputStyleMixin, ChangePasswordForm):
    pass


class StyledSetPasswordForm(AccountInputStyleMixin, SetPasswordForm):
    pass


class StyledResetPasswordKeyForm(AccountInputStyleMixin, ResetPasswordKeyForm):
    pass


class PublicDemoResetPasswordForm(AccountInputStyleMixin, ResetPasswordForm):
    """Preserve allauth's anti-enumeration response without emailing demo."""

    def clean_email(self):
        email = super().clean_email()
        self.users = [
            user for user in self.users if not is_public_demo_user(user)
        ]
        return email

    def save(self, request, **kwargs):
        if not self.users:
            return self.cleaned_data['email']
        return super().save(request, **kwargs)


class PublicDemoUserTokenForm(AccountInputStyleMixin, UserTokenForm):
    """Reject any existing password reset token for the public demo user."""

    def clean(self):
        cleaned_data = super().clean()
        if is_public_demo_user(self.reset_user):
            raise get_adapter().validation_error('invalid_password_reset')
        return cleaned_data
