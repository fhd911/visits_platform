from django.contrib.auth.backends import BaseBackend

from .models import LoginCode, User


class EmailOTPBackend(BaseBackend):
    """مصادقة بالبريد + رمز التحقق."""

    def authenticate(self, request, email=None, otp=None, **kwargs):
        if not email or not otp:
            return None
        try:
            user = User.objects.get(email__iexact=email.strip(), is_active=True)
        except User.DoesNotExist:
            return None
        latest = LoginCode.objects.filter(user=user).first()
        if latest and latest.verify(otp):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None
