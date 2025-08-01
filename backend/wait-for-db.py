import os
import socket
import time
from urllib.parse import urlparse

# Obtiene la URL de la base de datos de las variables de entorno
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("La variable de entorno DATABASE_URL no está configurada.")
    exit(1)

# Extrae el host y el puerto de la URL
parsed_url = urlparse(database_url)
db_host = parsed_url.hostname
db_port = parsed_url.port or 5432

print(f"Esperando a que la base de datos en {db_host}:{db_port} esté disponible...")

# Bucle de espera (máximo 30 segundos)
timeout = 30
start_time = time.time()
while time.time() - start_time < timeout:
    try:
        # Intenta crear una conexión al host y puerto de la BD
        with socket.create_connection((db_host, db_port), timeout=2):
            print("¡La base de datos está lista!")
            exit(0)  # Sale con éxito
    except (socket.timeout, ConnectionRefusedError, OSError):
        # Si falla, espera 1 segundo y vuelve a intentarlo
        print("La base de datos aún no está lista, reintentando en 1 segundo...")
        time.sleep(1)

print("Error: No se pudo conectar a la base de datos después de 30 segundos.")
exit(1) # Sale con error