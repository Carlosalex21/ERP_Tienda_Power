from django.db import models  # noqa: F401

# Este app no define modelos propios: reutiliza `Producto`/`Factura` de
# `inventario`/`facturacion`. Existe únicamente como namespace aislado para
# los endpoints `AllowAny` del catálogo público.
