from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import datetime, timedelta

from apps.rrhh.models import Horario, DiaFestivo, Asistencia, Descanso
from apps.rrhh.api.serializers import HorarioSerializer, DiaFestivoSerializer, AsistenciaSerializer

class HorarioDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, pk=1):
        try:
            horario = Horario.objects.get(pk=pk)
            serializer = HorarioSerializer(horario)
            return Response(serializer.data)
        except Horario.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk=1):
        horario, created = Horario.objects.update_or_create(
            pk=pk,
            defaults=request.data
        )
        serializer = HorarioSerializer(horario)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

class DiaFestivoListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    queryset = DiaFestivo.objects.all().order_by('fecha')
    serializer_class = DiaFestivoSerializer

class DiaFestivoDetailView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    queryset = DiaFestivo.objects.all()
    serializer_class = DiaFestivoSerializer

class AttendanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        today = timezone.localdate()
        start_of_month = today.replace(day=1)
        
        asistencia_hoy = Asistencia.objects.filter(usuario=request.user, fecha=today).first()
        current_status = asistencia_hoy.estado_actual if asistencia_hoy else 'out'

        asistencias_mes = Asistencia.objects.filter(usuario=request.user, fecha__range=[start_of_month, today])
        festivos_mes = DiaFestivo.objects.filter(fecha__range=[start_of_month, today]).count()

        summary = {
            "total_working_days": 22,
            "absent_days": asistencias_mes.filter(estado='Ausente').count(),
            "present_days": asistencias_mes.filter(estado='Presente').count(),
            "half_days": asistencias_mes.filter(estado='Medio Día').count(),
            "late_days": asistencias_mes.filter(llegada_tarde=True).count(),
            "holidays": festivos_mes,
        }

        log_serializer = AsistenciaSerializer(asistencias_mes, many=True)
        data = {"current_status": current_status, "summary": summary, "log": log_serializer.data}
        return Response(data)

class ClockInView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        now = timezone.now()
        local_date = timezone.localdate()
        horario = Horario.objects.first()
        es_tarde = False
        if horario:
            hora_entrada_limite = datetime.combine(now.date(), horario.hora_entrada_oficial)
            hora_entrada_limite = timezone.make_aware(hora_entrada_limite)
            limite_con_margen = hora_entrada_limite + timedelta(minutes=horario.margen_tardanza_minutos)
            if now > limite_con_margen:
                es_tarde = True

        asistencia, created = Asistencia.objects.get_or_create(
            usuario=request.user,
            fecha=local_date,
            defaults={'hora_entrada': now, 'estado_actual': 'in', 'llegada_tarde': es_tarde}
        )
        if not created:
            asistencia.hora_entrada = now
            asistencia.estado_actual = 'in'
            asistencia.llegada_tarde = es_tarde
            asistencia.save()
        return Response(status=status.HTTP_200_OK)

class ClockOutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        Asistencia.objects.filter(usuario=request.user, fecha=timezone.localdate()).update(
            hora_salida=timezone.now(),
            estado_actual='out'
        )
        return Response(status=status.HTTP_200_OK)

class BreakView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        start_break = request.data.get('start', True)
        asistencia = Asistencia.objects.get(usuario=request.user, fecha=timezone.localdate())
        
        if start_break:
            Descanso.objects.create(asistencia=asistencia, inicio_descanso=timezone.now())
            asistencia.estado_actual = 'break'
        else:
            ultimo_descanso = asistencia.descansos.filter(fin_descanso__isnull=True).last()
            if ultimo_descanso:
                ultimo_descanso.fin_descanso = timezone.now()
                ultimo_descanso.save()
            asistencia.estado_actual = 'in'
        asistencia.save()
        return Response(status=status.HTTP_200_OK)
