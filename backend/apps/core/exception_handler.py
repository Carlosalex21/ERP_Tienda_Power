from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    # Llama al manejador de excepciones predeterminado de DRF primero
    response = exception_handler(exc, context)

    # Si el manejador predeterminado de DRF devuelve una respuesta, la usamos.
    if response is not None:
        # Puedes personalizar el formato de la respuesta aquí
        # Por ejemplo, envolver los errores en un diccionario 'errors'
        if isinstance(response.data, dict) and 'detail' in response.data:
            response.data = {'error': response.data['detail']}
        elif isinstance(response.data, dict):
            response.data = {'errors': response.data}
        return response

    # Para excepciones no manejadas por DRF, devolvemos una respuesta genérica 500
    # y loggeamos el error.
    # Aquí podrías añadir logging del error 'exc'
    return Response(
        {'error': 'Ocurrió un error inesperado en el servidor.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )