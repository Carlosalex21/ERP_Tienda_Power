# Variables de ruta
PYTHON = ./env/bin/python
MANAGE = backend/manage.py

run:
	$(PYTHON) $(MANAGE) runserver

migrate:
	$(PYTHON) $(MANAGE) migrate_schemas --shared

shell:
	$(PYTHON) $(MANAGE) shell