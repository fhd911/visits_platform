from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import EmailForm, OTPForm
from .models import LoginCode, User

SESSION_KEY = "otp_email"


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = EmailForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            last = LoginCode.objects.filter(user=user).first()
            recent = last and last.created_at > timezone.now() - timedelta(seconds=settings.OTP_RESEND_SECONDS)
            if not recent:
                _, code = LoginCode.issue(user)
                send_mail(
                    "رمز الدخول إلى بوابة الزيارات",
                    f"رمز التحقق الخاص بك: {code}\nصالح لمدة {settings.OTP_TTL_MINUTES} دقائق.\n"
                    "إذا لم تطلب الرمز فتجاهل هذه الرسالة.",
                    None, [user.email],
                )
        # رسالة موحّدة لا تكشف وجود الحساب
        request.session[SESSION_KEY] = email
        messages.info(request, "إن كان البريد مسجلاً فقد أُرسل إليه رمز التحقق.")
        return redirect("accounts:verify")
    return render(request, "accounts/login.html", {"form": form})


def verify_view(request):
    email = request.session.get(SESSION_KEY)
    if not email:
        return redirect("accounts:login")
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, email=email, otp=form.cleaned_data["otp"])
        if user:
            request.session.pop(SESSION_KEY, None)
            login(request, user, backend="accounts.backends.EmailOTPBackend")
            return redirect("home")
        form.add_error("otp", "الرمز غير صحيح أو منتهي الصلاحية.")
    return render(request, "accounts/verify.html", {"form": form, "email": email})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
