from django import template

register = template.Library()


@register.filter
def pct(valor):
    """33.3 -> '33,3 %'; None -> 'sin datos'."""
    if valor is None:
        return "sin datos"
    return f"{valor:.1f}".replace(".", ",") + " %"


@register.filter
def chip(clave):
    """Clase CSS para el estado de evaluación/auditoría o la severidad."""
    return "chip-" + str(getattr(clave, "value", clave)).lower().replace("_", "-")


@register.filter
def get(dic, clave):
    return dic.get(clave, 0) if dic else 0


@register.filter
def ancho(valor):
    """Porcentaje para CSS con punto decimal (la localización usaría coma y rompería el estilo)."""
    try:
        v = max(0.0, min(100.0, float(valor)))
    except (TypeError, ValueError):
        v = 0.0
    return f"{v:.1f}"


@register.filter
def restar(a, b):
    return (a or 0) - (b or 0)


@register.filter
def tipo_archivo(nombre):
    """Clase de archivo por su extensión: 'imagen', 'pdf', 'word' o '' (sin archivo)."""
    nombre = (nombre or "").lower()
    if nombre.endswith((".png", ".jpg", ".jpeg")):
        return "imagen"
    if nombre.endswith(".pdf"):
        return "pdf"
    if nombre.endswith(".docx"):
        return "word"
    return ""


@register.filter
def lista(dic, clave):
    """Valor de un diccionario de listas; lista vacía si no existe la clave."""
    return dic.get(clave, []) if dic else []
