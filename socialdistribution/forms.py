from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model


class SignupForm(UserCreationForm):
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Your First Name',
            # remove 'class': 'w-full py-4 px-6 rounded-xl'
        })
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Your Last Name',
        })
    )

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Your Username',
        })
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Your password',
        })
    )
    password2 = forms.CharField(
        label="Repeat Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Repeat Password',
        })
    )

    class Meta:
        model = get_user_model()
        fields = (
            'first_name',
            'last_name',
            'username',
            'password1',
            'password2',
        )


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Your Username',
            'class': 'w-full py-4 px-6 rounded-xl',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Your password',
            'class': 'w-full py-4 px-6 rounded-xl',
        })
    )
