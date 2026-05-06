from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import JsonResponse
from http import HTTPStatus

from models import Cliente
from .serializers import ClienteSerializer

class ClienteList(APIView):
    """
    Lista todos los clientes activos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        clientes = Cliente.objects.filter(activo=True).order_by("id")
        serializer = ClienteSerializer(clientes, many=True)
        return Response({"clientes": serializer.data}, status=HTTPStatus.OK)


class ObtenerclienteAPIView(APIView):
    """
    Obtiene los detalles de un cliente específico por ID.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            cliente = Cliente.objects.get(id=id)
            serializer = ClienteSerializer(cliente)
            return JsonResponse({"estado": "ok", "mensaje": serializer.data}, status=status.HTTP_200_OK)
        except Cliente.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)


class ClienteCreateUpdateDelete(APIView):
    """
    Maneja la creación, actualización y desactivación lógica de clientes.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClienteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            cliente = Cliente.objects.get(id=id)
        except Cliente.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Cliente no encontrado"}, status=HTTPStatus.NOT_FOUND)

        serializer = ClienteSerializer(cliente, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            cliente = Cliente.objects.get(id=id, activo=True)
            cliente.activo = False
            cliente.save()
            return JsonResponse({"estado": "eliminado", "mensaje": "Cliente inactivo"}, status=HTTPStatus.OK)
        except Cliente.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Cliente no encontrado"}, status=HTTPStatus.NOT_FOUND)