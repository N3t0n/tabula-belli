import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.players.models import Player


class EmailSettingsTest(SimpleTestCase):
    def test_development_uses_console_backend_without_resend_key(self):
        result = self.run_settings_probe({'DJANGO_ENV': 'development'})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ['django.core.mail.backends.console.EmailBackend', ''],
        )

    def run_settings_probe(self, extra_env):
        project_root = Path(settings.BASE_DIR).parent
        env = {
            'PATH': os.environ.get('PATH', ''),
            'PYTHONPATH': str(settings.BASE_DIR),
            'SECRET_KEY': 'test-secret-key-for-settings-probe',
            'DJANGO_ENV': 'production',
            'ALLOWED_HOSTS': 'example.com',
            'CSRF_TRUSTED_ORIGINS': 'https://example.com',
            'DB_NAME': 'probe_db',
            'DB_USER': 'probe_user',
            'DB_PASSWORD': 'probe_password',
            'DB_HOST': 'localhost',
            'DB_PORT': '5432',
            'DB_SSLMODE': 'prefer',
            'DEFAULT_FROM_EMAIL': 'noreply@example.com',
        }
        env.update(extra_env)
        code = (
            'import os; '
            'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); '
            'from django.conf import settings; '
            'print(settings.EMAIL_BACKEND); '
            'print(settings.ANYMAIL["RESEND_API_KEY"])'
        )
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run(
                [sys.executable, '-c', code],
                cwd=cwd,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_production_uses_resend_backend_and_anymail_api_key(self):
        result = self.run_settings_probe({'RESEND_API_KEY': 'test_resend_key'})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ['anymail.backends.resend.EmailBackend', 'test_resend_key'],
        )

    def test_production_without_resend_api_key_fails_clearly(self):
        result = self.run_settings_probe({})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            'RESEND_API_KEY is required and cannot be empty',
            result.stderr,
        )


class FormspreeContactTest(TestCase):
    @override_settings(FORMSPREE_FORM_ID='abc123')
    def test_contact_get_uses_configured_formspree_action_and_post_method(self):
        response = self.client.get(reverse('contact'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'action="https://formspree.io/f/abc123"',
        )
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'js/contact.js')
        self.assertContains(response, 'data-contact-form')
        self.assertContains(response, 'role="status"')
        self.assertContains(response, 'aria-live="polite"')

    @override_settings(FORMSPREE_FORM_ID='')
    def test_contact_without_form_id_has_no_accidental_submission(self):
        response = self.client.get(reverse('contact'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'https://formspree.io/f/')
        self.assertContains(response, 'Contact is not configured yet.')
        self.assertContains(response, 'disabled')
        self.assertNotContains(response, 'js/contact.js')

    @override_settings(FORMSPREE_FORM_ID='abc123')
    def test_contact_form_does_not_send_django_csrf_token_to_formspree(self):
        response = self.client.get(reverse('contact'))

        self.assertNotContains(response, 'csrfmiddlewaretoken')

    @override_settings(FORMSPREE_FORM_ID='abc123')
    def test_contact_fields_remain_present(self):
        response = self.client.get(reverse('contact'))

        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="subject"')
        self.assertContains(response, 'name="message"')

    def test_django_contact_post_is_not_reachable(self):
        response = self.client.post(reverse('contact'), {
            'email': 'contact@example.com',
            'subject': 'Hello',
            'message': 'Message',
        })

        self.assertEqual(response.status_code, 405)

    def test_django_contact_no_longer_calls_send_mail(self):
        with patch('django.core.mail.send_mail') as send_mail:
            self.client.post(reverse('contact'), {
                'email': 'contact@example.com',
                'subject': 'Hello',
                'message': 'Message',
            })

        send_mail.assert_not_called()


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AllauthEmailTransportTest(TestCase):
    password = 'StrongTransportPass123!'

    def create_verified_user(self, username='transport-user',
                             email='transport@example.com'):
        user = Player.objects.create_user(
            username=username,
            email=email,
            password=self.password,
        )
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True,
        )
        return user

    def test_signup_verification_still_generates_email(self):
        response = self.client.post(reverse('account_signup'), {
            'username': 'transport-signup',
            'email': 'transport-signup@example.com',
            'password1': self.password,
            'password2': self.password,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_for_normal_user_still_generates_email(self):
        user = self.create_verified_user()

        response = self.client.post(reverse('account_reset_password'), {
            'email': user.email,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_public_demo_password_reset_still_generates_no_email(self):
        demo = self.create_verified_user(
            username=settings.PUBLIC_DEMO_USERNAME,
            email='public-demo-transport@example.com',
        )

        response = self.client.post(reverse('account_reset_password'), {
            'email': demo.email,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox, [])

    def test_email_change_still_uses_allauth_email_flow(self):
        user = self.create_verified_user()
        self.client.force_login(user)

        response = self.client.post(reverse('account_email'), {
            'email': 'transport-changed@example.com',
            'action_add': '1',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmailAddress.objects.filter(
            user=user,
            email='transport-changed@example.com',
            verified=False,
        ).exists())
        self.assertEqual(len(mail.outbox), 1)
