import os
from decimal import Decimal
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import black, gray

# Asumiendo que tus modelos están en 'erp.models'
from erp.models import Factura, Detallefactura, Cliente, Variacionproducto

def generar_factura_pdf(factura_id):
    """
    Genera un PDF de factura optimizado para una impresora de tickets de 80mm.
    Con altura dinámica y columnas alineadas.
    """
    try:
        factura = Factura.objects.get(id=factura_id)
        # Usamos select_related para optimizar la consulta a la base de datos
        detalles = Detallefactura.objects.filter(factura=factura).select_related('producto', 'variante')
        cliente = factura.cliente
    except (Factura.DoesNotExist, Cliente.DoesNotExist):
        return None, "Factura o Cliente no encontrado"
    except Exception as e:
        return None, f"Error inesperado: {str(e)}"

    # --- 1. CONFIGURACIÓN DEL DOCUMENTO ---
    # Ancho estándar para tickets de 80mm
    PAGE_WIDTH = 80 * mm
    # Altura inicial (se ajustará al final)
    PAGE_HEIGHT = 200 * mm # Una altura base grande, la recortaremos

    # Márgenes y posiciones de las columnas
    MARGIN_X = 5 * mm
    COL_POS = {
        "producto": MARGIN_X,
        "cant": 45 * mm,
        "precio": 55 * mm,
        "total": 65 * mm,
    }
    
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="factura_{factura.correlativo}.pdf"'
    
    c = canvas.Canvas(response, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    
    # Inicia la posición Y desde arriba
    y = PAGE_HEIGHT - (10 * mm)

    try:
        # --- 2. ENCABEZADO DE LA EMPRESA ---
        # (Ajusta la ruta a tu logo)
        logo_path = os.path.join("./img/logo-power.jpg")
        if os.path.exists(logo_path):
             c.drawImage(logo_path, (PAGE_WIDTH - 40*mm) / 2, y - 15*mm, width=40*mm, height=15*mm, preserveAspectRatio=True)
             y -= 20 * mm
            
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(PAGE_WIDTH / 2, y, "Power Nutricion Deportiva Excelente, S.L.")
        y -= 4 * mm
        c.setFont("Helvetica", 8)
        c.drawCentredString(PAGE_WIDTH / 2, y, "B-55450688")
        y -= 4 * mm
        c.drawCentredString(PAGE_WIDTH / 2, y, "Calle miguel de prado, 4 BJ 47002, Valladolid")
        y -= 4 * mm
        c.drawCentredString(PAGE_WIDTH / 2, y, "Tel: 641 00 89 57")
        y -= 7 * mm

        # --- 3. DATOS DE LA FACTURA Y CLIENTE ---
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN_X, y, f"Factura Simplificada: {factura.correlativo}")
        y -= 4 * mm
        c.drawString(MARGIN_X, y, f"Fecha: {factura.fecha_operacion.strftime('%d/%m/%Y %H:%M')}")
        y -= 6 * mm
        c.drawString(MARGIN_X, y, f"Cliente: {cliente.nombre}")
        y -= 4 * mm
        c.drawString(MARGIN_X, y, f"Documento: {cliente.documento}")
        y -= 7 * mm

        # --- 4. DETALLES DE PRODUCTOS ---
        # Línea de separación
        c.setStrokeColor(black)
        c.setLineWidth(0.5)
        c.line(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y)
        y -= 4 * mm

        # Encabezados de la tabla
        c.setFont("Helvetica-Bold", 8)
        c.drawString(COL_POS["producto"], y, "Descripción")
        c.drawRightString(COL_POS["cant"], y, "Cant")
        c.drawRightString(COL_POS["precio"], y, "P.U.")
        c.drawRightString(COL_POS["total"], y, "Total")
        y -= 5 * mm

        # Items
        c.setFont("Helvetica", 8)
        for d in detalles:
            # LÓGICA CORREGIDA PARA VARIANTES
            if d.variante:
                nombre_item = f"{d.producto.nombre} - {d.variante.nombre}"
            else:
                nombre_item = d.producto.nombre
            
            # Limitar longitud del nombre para que no se solape
            # Puedes usar textobject para un auto-wrap más avanzado si es necesario
            c.drawString(COL_POS["producto"], y, nombre_item[:30])
            c.drawRightString(COL_POS["cant"], y, str(d.cantidad))
            c.drawRightString(COL_POS["precio"], y, f"{d.precio_unitario:.2f}")
            c.drawRightString(COL_POS["total"], y, f"{d.total_linea:.2f}")
            y -= 4 * mm
            # Si hay descuento en la línea, mostrarlo
            if d.descuento and d.descuento > 0:
                c.setFont("Helvetica-Oblique", 7)
                c.drawString(COL_POS["producto"] + 2*mm, y, f"  (Desc. {d.descuento:.0f}%)")
                c.setFont("Helvetica", 8)
                y -= 4 * mm

        # --- 5. TOTALES ---
        y -= 2 * mm
        c.line(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y)
        y -= 5 * mm

        c.setFont("Helvetica", 8)
        c.drawString(40 * mm, y, "Subtotal:")
        c.drawRightString(PAGE_WIDTH - MARGIN_X, y, f"{factura.subtotal:.2f} €")
        y -= 4 * mm
        
        c.drawString(40 * mm, y, "IVA:")
        c.drawRightString(PAGE_WIDTH - MARGIN_X, y, f"{factura.iva_total:.2f} €")
        y -= 4 * mm
        
        # El descuento total se calcula como la diferencia entre el precio original y el subtotal
        total_sin_descuento = sum(item.cantidad * item.precio_unitario for item in detalles)
        descuento_total = total_sin_descuento - factura.subtotal
        if descuento_total > 0.01:
            c.drawString(40 * mm, y, "Descuento:")
            c.drawRightString(PAGE_WIDTH - MARGIN_X, y, f"-{descuento_total:.2f} €")
            y -= 4 * mm

        c.setFont("Helvetica-Bold", 10)
        c.drawString(40 * mm, y, "TOTAL:")
        c.drawRightString(PAGE_WIDTH - MARGIN_X, y, f"{factura.total:.2f} €")
        y -= 8 * mm

        # --- 6. PIE DE PÁGINA ---
        c.setFont("Helvetica", 8)
        c.drawCentredString(PAGE_WIDTH / 2, y, "¡Gracias por su compra!")
        y -= 4 * mm
        c.drawCentredString(PAGE_WIDTH / 2, y, "IVA INCLUIDO")
        
        # --- 7. AJUSTE FINAL DE LA ALTURA DE LA PÁGINA ---
        # Se calcula la altura real del contenido y se ajusta el tamaño de la página.
        final_height = PAGE_HEIGHT - y + (5 * mm) # Se añade un pequeño margen inferior
        c.setPageSize((PAGE_WIDTH, final_height))

        c.showPage()
        c.save()
        return response, None

    except Exception as e:
        print(f"Error generando el PDF: {str(e)}")
        return None, f"Error generando el PDF: {str(e)}"
