"""L'administration Django est le premier outil de l'administrateur de la
plateforme : la création d'un agent doit y être sûre."""

from django.urls import reverse

from apps.accounts.admin import FormulaireCreationAgent
from apps.accounts.models import Role, User

from .base import BaseDCUHATTest


class TestCreationAgent(BaseDCUHATTest):
    def test_le_mot_de_passe_est_hache_et_non_stocke_en_clair(self):
        formulaire = FormulaireCreationAgent(
            data={
                "email": "f.bah@dcuhat.test",
                "first_name": "Fatou",
                "last_name": "Bah",
                "role": Role.AGENT,
                "service": str(self.service_cadastre.id),
                "password1": "MotDePasseSolide2026",
                "password2": "MotDePasseSolide2026",
            }
        )
        self.assertTrue(formulaire.is_valid(), formulaire.errors)
        agent = formulaire.save()
        self.assertNotEqual(agent.password, "MotDePasseSolide2026")
        self.assertTrue(agent.check_password("MotDePasseSolide2026"))
        self.assertTrue(agent.must_change_password)

    def test_mot_de_passe_trop_faible_refuse(self):
        formulaire = FormulaireCreationAgent(
            data={
                "email": "x@dcuhat.test",
                "role": Role.AGENT,
                "password1": "motdepasse",
                "password2": "motdepasse",
            }
        )
        self.assertFalse(formulaire.is_valid())
        self.assertIn("password2", formulaire.errors)

    def test_commande_creer_agent(self):
        from io import StringIO

        from django.core.management import call_command

        sortie = StringIO()
        call_command(
            "creer_agent",
            "--email=m.sylla@dcuhat.test",
            "--prenom=Mariama",
            "--nom=Sylla",
            "--role=AGENT",
            "--service=CADASTRE",
            stdout=sortie,
        )
        agent = User.objects.get(email="m.sylla@dcuhat.test")
        self.assertEqual(agent.service, self.service_cadastre)
        self.assertIn("Mot de passe provisoire", sortie.getvalue())

    def test_le_role_admin_ouvre_l_administration(self):
        """Un agent promu ADMIN par l'API doit pouvoir entrer dans /admin/."""
        self.agent_cadastre.role = Role.ADMIN
        self.agent_cadastre.save(update_fields=["role", "updated_at"])
        self.agent_cadastre.refresh_from_db()
        self.assertTrue(self.agent_cadastre.is_staff)
        self.assertTrue(self.agent_cadastre.is_superuser)

    def test_page_d_ajout_de_l_admin_repond(self):
        self.client.force_login(self.admin)
        reponse = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "password1")
