import os
from celery import Celery
from django.conf import settings

# Establece la configuración de Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# Crea una instancia de Celery
# El nombre 'backend' es el nombre de tu proyecto Django
app = Celery('backend')

# Carga la configuración de Celery desde el archivo settings.py de Django
# El prefijo 'CELERY_' indica que Celery buscará variables que comiencen con ese prefijo
# en tu settings.py (ej. CELERY_BROKER_URL, CELERY_RESULT_BACKEND).
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descubre automáticamente las tareas en todas las aplicaciones de Django
# que tengan un archivo 'tasks.py'.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

