import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    SUPERVISOR = "supervisor", "مشرف"
    DEPT_MANAGER = "dept_manager", "مدير قسم"
    DIRECTOR = "director", "مدير الإدارة"
    EDU_ASSISTANT = "edu_assistant", "مساعد الشؤون التعليمية"
    ADMIN = "admin", "مسؤول النظام"


LEADERSHIP_ROLES = {Role.DEPT_MANAGER, Role.DIRECTOR, Role.EDU_ASSISTANT, Role.ADMIN}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("البريد الإلكتروني مطلوب")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("البريد الإلكتروني", unique=True)
    full_name = models.CharField("الاسم الكامل", max_length=150)
    role = models.CharField("الدور", max_length=20, choices=Role.choices, default=Role.SUPERVISOR)
    department = models.ForeignKey(
        "org.Department", verbose_name="القسم", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="members",
    )
    sector = models.ForeignKey(
        "org.Sector", verbose_name="القطاع", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="members",
    )
    phone = models.CharField("الجوال", max_length=20, blank=True)
    specialization = models.CharField("التخصص", max_length=100, blank=True)
    max_schools = models.PositiveSmallIntegerField(
        "الحد الأعلى للمدارس المسندة", null=True, blank=True,
        help_text="يُستخدم لحساب عبء الإسناد. اتركه فارغاً لعدم التحديد.",
    )
    is_active = models.BooleanField("نشط", default=True)
    is_staff = models.BooleanField("وصول للوحة الإدارة التقنية", default=False)
    date_joined = models.DateTimeField("تاريخ الإنشاء", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return (self.full_name or self.email).split(" ")[0]

    @property
    def is_supervisor(self):
        return self.role == Role.SUPERVISOR

    @property
    def is_leadership(self):
        return self.role in LEADERSHIP_ROLES or self.is_superuser


def _hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{code}".encode()).hexdigest()


class LoginCode(models.Model):
    """رمز تحقق لمرة واحدة يُرسل عبر البريد. لا يُخزّن الرمز نصاً صريحاً."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "رمز دخول"
        verbose_name_plural = "رموز الدخول"
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, user):
        """يُبطل الرموز السابقة ويُصدر رمزاً جديداً، ويعيد (الكائن، الرمز الصريح)."""
        now = timezone.now()
        cls.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        code = f"{secrets.randbelow(10**6):06d}"
        obj = cls.objects.create(
            user=user,
            code_hash=_hash_code(code),
            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES),
        )
        return obj, code

    @property
    def is_usable(self):
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < settings.OTP_MAX_ATTEMPTS
        )

    def verify(self, code: str) -> bool:
        if not self.is_usable:
            return False
        self.attempts += 1
        ok = secrets.compare_digest(self.code_hash, _hash_code((code or "").strip()))
        if ok:
            self.used_at = timezone.now()
        self.save(update_fields=["attempts", "used_at"])
        return ok
