"""
Tipos de documento de identidad disponibles para elegir al registrar un
cliente, según el país fiscal del tenant -- mismo espíritu que
`apps.configuracion.core.tax_strategy.TaxStrategyRegistry` (una lista fija
por país, no texto libre que el cajero pueda escribir a su criterio).
"""
from __future__ import annotations

TIPOS_DOCUMENTO_POR_PAIS: dict[str, list[dict[str, str]]] = {
    'VE': [
        {'value': 'V', 'label': 'V - Cédula Venezolana'},
        {'value': 'E', 'label': 'E - Cédula Extranjero'},
        {'value': 'J', 'label': 'J - RIF Jurídico'},
        {'value': 'G', 'label': 'G - RIF Gubernamental'},
        {'value': 'P', 'label': 'P - Pasaporte'},
    ],
    'CO': [
        {'value': 'CC', 'label': 'CC - Cédula de Ciudadanía'},
        {'value': 'CE', 'label': 'CE - Cédula de Extranjería'},
        {'value': 'NIT', 'label': 'NIT - Persona Jurídica'},
        {'value': 'P', 'label': 'Pasaporte'},
    ],
    'PE': [
        {'value': 'DNI', 'label': 'DNI'},
        {'value': 'RUC', 'label': 'RUC - Persona Jurídica'},
        {'value': 'CE', 'label': 'CE - Carné de Extranjería'},
        {'value': 'P', 'label': 'Pasaporte'},
    ],
}

DEFAULT_PAIS = 'VE'


def obtener_tipos_documento(pais_codigo: str) -> list[dict[str, str]]:
    return TIPOS_DOCUMENTO_POR_PAIS.get((pais_codigo or '').upper(), TIPOS_DOCUMENTO_POR_PAIS[DEFAULT_PAIS])
