from django.contrib import admin

from . import models

for modelo in (
    models.Edificio, models.Unidad, models.Cargo, models.Recibo, models.Contrato,
    models.Liquidacion, models.PeriodoCondominio, models.MedioPago,
):
    admin.site.register(modelo)
