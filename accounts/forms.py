from django import forms


class EmailForm(forms.Form):
    email = forms.EmailField(label="البريد الإلكتروني", widget=forms.EmailInput(attrs={
        "autofocus": True, "autocomplete": "email", "dir": "ltr", "placeholder": "name@example.com"}))


class OTPForm(forms.Form):
    otp = forms.CharField(label="رمز التحقق", min_length=6, max_length=6, widget=forms.TextInput(attrs={
        "autofocus": True, "inputmode": "numeric", "autocomplete": "one-time-code", "dir": "ltr",
        "class": "otp-input", "pattern": "[0-9]{6}"}))
