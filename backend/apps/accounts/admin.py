from django import forms
from django.contrib import admin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password

from .models import Device, Service, User


class FormulaireCreationAgent(forms.ModelForm):
    """Création d'un agent depuis l'administration.

    Le mot de passe doit passer par `set_password` : un `ModelForm` brut
    écrirait la valeur en clair dans la colonne, ce qui rendrait le compte
    inutilisable et exposerait le mot de passe.
    """

    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            "email", "first_name", "last_name", "matricule", "role",
            "service", "fonction", "phone",
        ]

    def clean_password2(self):
        mot1 = self.cleaned_data.get("password1")
        mot2 = self.cleaned_data.get("password2")
        if mot1 and mot2 and mot1 != mot2:
            raise forms.ValidationError("Les deux mots de passe ne correspondent pas.")
        validate_password(mot2)
        return mot2

    def save(self, commit=True):
        agent = super().save(commit=False)
        agent.set_password(self.cleaned_data["password2"])
        agent.must_change_password = True
        if commit:
            agent.save()
        return agent


class FormulaireModificationAgent(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Mot de passe",
        help_text=(
            "Les mots de passe ne sont pas stockés en clair. Utilisez le lien "
            "« Modifier le mot de passe » pour en définir un nouveau."
        ),
    )

    class Meta:
        model = User
        fields = [
            "email", "password", "first_name", "last_name", "matricule", "role",
            "service", "fonction", "phone", "is_active", "is_staff",
            "must_change_password", "storage_quota_bytes", "totp_enabled",
        ]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]
    search_fields = ["name", "code"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = FormulaireModificationAgent
    add_form = FormulaireCreationAgent

    list_display = ["email", "nom_complet", "role", "service", "is_active"]
    list_filter = ["role", "service", "is_active", "totp_enabled"]
    search_fields = ["email", "first_name", "last_name", "matricule"]
    ordering = ["last_name", "first_name"]
    readonly_fields = ["last_login", "created_at", "updated_at"]

    fieldsets = [
        ("Identité", {"fields": ["email", "password", "first_name", "last_name", "matricule"]}),
        ("Affectation", {"fields": ["role", "service", "fonction", "phone"]}),
        (
            "Accès",
            {
                "fields": [
                    "is_active", "is_staff", "must_change_password",
                    "totp_enabled", "storage_quota_bytes",
                ]
            },
        ),
        ("Suivi", {"fields": ["last_login", "created_at", "updated_at"]}),
    ]
    add_fieldsets = [
        (
            "Nouvel agent",
            {
                "fields": [
                    "email", "first_name", "last_name", "matricule", "role",
                    "service", "fonction", "phone", "password1", "password2",
                ]
            },
        )
    ]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
            self.fieldsets_courants = self.add_fieldsets
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else self.readonly_fields


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["label", "user", "last_sync_at", "is_revoked"]
    list_filter = ["is_revoked"]
