"""Crée un agent en ligne de commande.

    python manage.py creer_agent --email=f.bah@lambayin.gov \
        --prenom=Fatou --nom=Bah --role=AGENT --service=CADASTRE

Sans `--mot-de-passe`, un mot de passe est généré et affiché une seule fois ;
l'agent devra le changer à sa première connexion.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string

from apps.accounts.models import Role, Service, User


class Command(BaseCommand):
    help = "Cree un compte agent."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--prenom", default="")
        parser.add_argument("--nom", default="")
        parser.add_argument("--role", default=Role.AGENT, choices=[r for r, _ in Role.choices])
        parser.add_argument("--service", default="", help="Code du service, ex. CADASTRE")
        parser.add_argument("--matricule", default="")
        parser.add_argument("--fonction", default="")
        parser.add_argument("--mot-de-passe", dest="mot_de_passe", default="")

    def handle(self, *args, **options):
        email = options["email"].lower()
        if User.objects.filter(email=email).exists():
            raise CommandError(f"Un compte existe deja pour {email}.")

        service = None
        if options["service"]:
            service = Service.objects.filter(code=options["service"].upper()).first()
            if service is None:
                codes = ", ".join(Service.objects.values_list("code", flat=True))
                raise CommandError(
                    f"Service inconnu : {options['service']}. Services existants : {codes}"
                )

        mot_de_passe = options["mot_de_passe"] or get_random_string(14)
        agent = User.objects.create_user(
            email=email,
            password=mot_de_passe,
            first_name=options["prenom"],
            last_name=options["nom"],
            role=options["role"],
            service=service,
            matricule=options["matricule"] or None,
            fonction=options["fonction"],
        )
        self.stdout.write(self.style.SUCCESS(f"Agent cree : {agent} ({agent.role})"))
        if not options["mot_de_passe"]:
            self.stdout.write(
                self.style.WARNING(f"Mot de passe provisoire : {mot_de_passe}")
            )
        self.stdout.write("Il sera demande a l'agent de le changer a la premiere connexion.")
