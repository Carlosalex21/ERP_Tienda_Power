"""
Pruebas sin base de datos de las piezas transversales: paginación, formato de
errores y validación de archivos subidos.
"""
import io
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.response import StandardResultsSetPagination, errores_desde_payload
from apps.core.uploads import validar_archivo_subido


def _request(query=''):
    return Request(APIRequestFactory().get(f'/x/{query}'))


class PaginacionTests(SimpleTestCase):

    def test_sin_parametros_devuelve_la_lista_completa(self):
        """Antes cortaba en 20 sin avisar: un negocio con 42 productos veía 20."""
        datos = list(range(42))
        paginador = StandardResultsSetPagination()
        pagina = paginador.paginate_queryset(datos, _request())
        self.assertEqual(len(pagina), 42)
        meta = json.loads(json.dumps(paginador.get_paginated_response(pagina).data['meta']))
        self.assertEqual(meta['pagination']['count'], 42)
        self.assertFalse(meta['pagination']['truncated'])

    def test_con_page_size_pagina_normalmente(self):
        paginador = StandardResultsSetPagination()
        pagina = paginador.paginate_queryset(list(range(42)), _request('?page=2&page_size=20'))
        self.assertEqual(pagina, list(range(20, 40)))
        pag = paginador.get_paginated_response(pagina).data['meta']['pagination']
        self.assertEqual((pag['page'], pag['total_pages'], pag['count']), (2, 3, 42))

    def test_solo_page_usa_el_tamano_por_defecto(self):
        paginador = StandardResultsSetPagination()
        pagina = paginador.paginate_queryset(list(range(42)), _request('?page=3'))
        self.assertEqual(pagina, [40, 41])

    def test_lista_vacia(self):
        paginador = StandardResultsSetPagination()
        self.assertEqual(paginador.paginate_queryset([], _request()), [])

    def test_el_tope_de_lista_completa_se_avisa(self):
        paginador = StandardResultsSetPagination()
        paginador.LISTA_COMPLETA_MAX = 10
        pagina = paginador.paginate_queryset(list(range(25)), _request())
        self.assertEqual(len(pagina), 10)
        self.assertTrue(paginador.get_paginated_response(pagina).data['meta']['pagination']['truncated'])


class ErroresTests(SimpleTestCase):

    def test_error_suelto_de_una_vista_es_global(self):
        self.assertEqual(
            errores_desde_payload({'error': 'El pago supera el saldo.'}),
            [{'code': 'error', 'detail': 'El pago supera el saldo.', 'field': None}],
        )

    def test_error_de_campo_conserva_el_campo(self):
        errores = errores_desde_payload({'numero_control': ['Este campo es requerido.']})
        self.assertEqual(errores[0]['field'], 'numero_control')

    def test_lineas_anidadas_dejan_la_ruta_y_no_el_dict(self):
        errores = errores_desde_payload({'detalles': [{}, {'cantidad': ['Debe ser mayor a 0.']}]})
        self.assertEqual(len(errores), 1)
        self.assertEqual(errores[0]['field'], 'detalles.1.cantidad')
        self.assertNotIn('{', errores[0]['detail'])

    def test_detalle_simple_de_drf(self):
        self.assertEqual(errores_desde_payload({'detail': 'No encontrado.'})[0]['field'], None)


def _imagen(formato='PNG', nombre='comprobante.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buffer, formato)
    return SimpleUploadedFile(nombre, buffer.getvalue())


class SubidasTests(SimpleTestCase):

    def test_imagen_valida_pasa(self):
        archivo = validar_archivo_subido(_imagen())
        self.assertEqual(archivo.read(4), b'\x89PNG')  # se rebobinó

    def test_extension_no_permitida(self):
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(SimpleUploadedFile('virus.html', b'<script>alert(1)</script>'))

    def test_html_disfrazado_de_imagen(self):
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(SimpleUploadedFile('foto.png', b'<script>alert(1)</script>'))

    def test_svg_no_se_acepta_como_imagen(self):
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(SimpleUploadedFile('logo.svg', b'<svg onload="alert(1)"></svg>'))

    def test_demasiado_pesado(self):
        grande = SimpleUploadedFile('foto.png', b'x' * (2 * 1024 * 1024))
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(grande, max_mb=1)

    def test_archivo_vacio_y_ausente(self):
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(SimpleUploadedFile('foto.png', b''))
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(None)

    def test_pdf_solo_si_se_permite(self):
        pdf = SimpleUploadedFile('recibo.pdf', b'%PDF-1.4 contenido')
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(pdf)
        pdf.seek(0)
        validar_archivo_subido(pdf, permitir_pdf=True)

    def test_pdf_falso(self):
        with self.assertRaises(serializers.ValidationError):
            validar_archivo_subido(SimpleUploadedFile('recibo.pdf', b'no soy pdf'), permitir_pdf=True)
