import re

from django.core.management.base import BaseCommand
from apps.tenants.models import Domain

# `localhost`/`127.0.0.1` quedaron sembrados en `Domain` desde el bootstrap
# de desarrollo (ver migración 0003) -- Let's Encrypt directamente RECHAZA
# pedir un certificado para una IP desnuda o para "localhost" (no es un
# nombre público resoluble), así que `sync_tenant_domains.sh` reventaba
# certbot en cada corrida al toparse con estas entradas. Un dominio real de
# tenant siempre tiene un punto (`<subdominio>.<base>`); filtramos por eso
# en vez de una lista fija de nombres a excluir, para no tener que acordarse
# de mantenerla si aparece otro alias de desarrollo similar.
_ES_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _es_dominio_publico_valido(dominio: str) -> bool:
    return "." in dominio and dominio != "localhost" and not dominio.endswith(".localhost") and not _ES_IP.match(dominio)


class Command(BaseCommand):
    """Imprime un dominio por línea, sin nada más -- pensado para que
    `deploy/scripts/sync_tenant_domains.sh` lo consuma directo, a diferencia
    de `inspect_domains` (que es para leer a ojo, con formato decorado)."""

    help = "Lista, uno por línea, los dominios públicos reales de tenants (para el cron de certificados)."

    def handle(self, *args, **options):
        dominios = Domain.objects.order_by("domain").values_list("domain", flat=True)
        for dominio in dominios:
            if _es_dominio_publico_valido(dominio):
                self.stdout.write(dominio)
