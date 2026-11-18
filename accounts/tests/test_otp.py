from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import LoginCode, Role, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OTPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sup@x.com", full_name="مشرف", role=Role.SUPERVISOR)

    def test_code_not_stored_in_plain_text(self):
        obj, code = LoginCode.issue(self.user)
        self.assertEqual(len(code), 6)
        self.assertNotEqual(obj.code_hash, code)

    def test_verify_once(self):
        obj, code = LoginCode.issue(self.user)
        self.assertTrue(obj.verify(code))
        self.assertFalse(obj.verify(code))

    def test_expired_code_rejected(self):
        obj, code = LoginCode.issue(self.user)
        obj.expires_at = timezone.now() - timedelta(seconds=1)
        obj.save()
        self.assertFalse(obj.verify(code))

    def test_attempts_limited(self):
        obj, code = LoginCode.issue(self.user)
        for _ in range(5):
            self.assertFalse(obj.verify("000000" if code != "000000" else "111111"))
        self.assertFalse(obj.verify(code))

    def test_new_code_invalidates_old(self):
        old, old_code = LoginCode.issue(self.user)
        LoginCode.issue(self.user)
        old.refresh_from_db()
        self.assertFalse(old.verify(old_code))

    def test_full_login_flow(self):
        r = self.client.post(reverse("accounts:login"), {"email": "SUP@x.com"})
        self.assertRedirects(r, reverse("accounts:verify"))
        self.assertEqual(len(mail.outbox), 1)
        code = [w for w in mail.outbox[0].body.split() if w.isdigit() and len(w) == 6][0]
        r = self.client.post(reverse("accounts:verify"), {"otp": "999999" if code != "999999" else "888888"})
        self.assertContains(r, "الرمز غير صحيح")
        # الرمز ما زال صالحاً بعد محاولة خاطئة واحدة
        r = self.client.post(reverse("accounts:verify"), {"otp": code})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        r = self.client.get(reverse("home"))
        self.assertRedirects(r, reverse("operations:today"), fetch_redirect_response=False)

    def test_unknown_email_does_not_leak(self):
        r = self.client.post(reverse("accounts:login"), {"email": "nobody@x.com"}, follow=True)
        self.assertContains(r, "إن كان البريد مسجلاً")
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_throttled(self):
        self.client.post(reverse("accounts:login"), {"email": "sup@x.com"})
        self.client.post(reverse("accounts:login"), {"email": "sup@x.com"})
        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse("accounts:login"), {"email": "sup@x.com"})
        self.assertEqual(len(mail.outbox), 0)

    def test_pages_require_login(self):
        r = self.client.get(reverse("operations:today"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])
