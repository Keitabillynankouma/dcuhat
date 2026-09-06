# Raccourcis de developpement et d'exploitation DCUHAT.

.PHONY: aide install demarrer arreter migrer initialiser tests couverture logs sauvegarde front

aide:
	@echo "make install      - installe les dependances backend et frontend"
	@echo "make demarrer     - lance toute la pile Docker"
	@echo "make arreter      - arrete la pile"
	@echo "make migrer       - applique les migrations"
	@echo "make initialiser  - cree services, arborescence et compte admin"
	@echo "make tests        - lance la suite de tests backend"
	@echo "make front        - lance le serveur de developpement de l'interface"
	@echo "make sauvegarde   - sauvegarde base + stockage objet"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

demarrer:
	docker compose up -d --build

arreter:
	docker compose down

migrer:
	docker compose exec api python manage.py migrate

initialiser:
	docker compose exec api python manage.py initialiser_dcuhat

tests:
	cd backend && python manage.py test tests -v 2

couverture:
	cd backend && coverage run manage.py test tests && coverage report -m

front:
	cd frontend && npm run dev

logs:
	docker compose logs -f api worker

sauvegarde:
	./deploy/sauvegarde.sh
