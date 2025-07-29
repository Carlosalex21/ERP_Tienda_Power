from woocommerce import API
from django.conf import settings
from .models import Producto, Variacionproducto

def get_wc_api():
    """
    Inicializa y devuelve un cliente de la API de WooCommerce
    usando la configuración de settings.py.
    """
    wc_config = settings.WOOCOMMERCE_CONFIG
    return API(
        url=wc_config["url"],
        consumer_key=wc_config["consumer_key"],
        consumer_secret=wc_config["consumer_secret"],
        wp_api=wc_config["wp_api"],
        version=wc_config["version"],
        timeout=wc_config["timeout"]
    )

def actualizar_stock_woocommerce(sku, nueva_cantidad):
    """
    Busca un producto en WooCommerce por su SKU y actualiza su cantidad de stock.

    Args:
        sku (str): El SKU del producto a actualizar.
        nueva_cantidad (int): La nueva cantidad de stock.

    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario.
    """
    if not sku:
        print(f"Intento de actualizar stock sin SKU. Abortado.")
        return False

    try:
        wcapi = get_wc_api()
        
        # 1. Buscar el producto en WooCommerce usando su SKU
        print(f"Buscando producto en WooCommerce con SKU: {sku}")
        productos_encontrados = wcapi.get("products", params={"sku": sku}).json()

        if not productos_encontrados:
            print(f"ADVERTENCIA: No se encontró ningún producto en WooCommerce con el SKU: {sku}")
            return False

        # El producto encontrado puede ser simple o una variante
        producto_wc = productos_encontrados[0]
        producto_id = producto_wc.get("id")
        
        # 2. Preparar los datos para la actualización
        data_para_actualizar = {
            "stock_quantity": nueva_cantidad
        }
        
        endpoint = f"products/{producto_id}"
        
        # Si el producto es una variante, el endpoint cambia
        if producto_wc.get("parent_id", 0) > 0:
            parent_id = producto_wc.get("parent_id")
            endpoint = f"products/{parent_id}/variations/{producto_id}"

        # 3. Enviar la petición de actualización a WooCommerce
        print(f"Actualizando stock para SKU {sku} (ID: {producto_id}) a la cantidad: {nueva_cantidad}")
        response = wcapi.put(endpoint, data_para_actualizar)

        if response.status_code == 200:
            print(f"ÉXITO: Stock para SKU {sku} actualizado correctamente en WooCommerce.")
            return True
        else:
            print(f"ERROR: Falló la actualización de stock para SKU {sku}. Respuesta de WooCommerce: {response.json()}")
            return False

    except Exception as e:
        print(f"ERROR CRÍTICO al intentar actualizar el stock en WooCommerce para SKU {sku}: {e}")
        return False
