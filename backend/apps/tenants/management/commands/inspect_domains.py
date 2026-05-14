from django.core.management.base import BaseCommand
from apps.tenants.models import Domain, Client

class Command(BaseCommand):
    help = 'Inspects all tenants and their associated domains.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Inspeccionando Tenants y Dominios..."))

        clients = Client.objects.all()
        if not clients.exists():
            self.stdout.write(self.style.WARNING("No se encontraron tenants (Clients)."))
            return

        for client in clients:
            self.stdout.write("-" * 20)
            self.stdout.write(self.style.HTTP_INFO(f"Tenant: {client.nombre_empresa} (schema: {client.schema_name})"))

            domains = Domain.objects.filter(tenant=client)
            if domains.exists():
                for domain in domains:
                    self.stdout.write(f"  - Dominio: '{domain.domain}' (is_primary: {domain.is_primary})")
            else:
                self.stdout.write(self.style.WARNING("  - Este tenant no tiene ningún dominio asociado."))

        self.stdout.write("-" * 20)
        self.stdout.write(self.style.SUCCESS("Inspección completa."))