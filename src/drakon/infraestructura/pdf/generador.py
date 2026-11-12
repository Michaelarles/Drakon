"""Adaptador GeneradorPDF con xhtml2pdf (Python puro, sin librerías del sistema)."""

from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from xhtml2pdf import pisa


class GeneradorPDFXhtml2pdf:
    plantilla = "drakon/informe_pdf.html"

    def generar(self, contenido_informe: dict) -> bytes:
        html = render_to_string(self.plantilla, {"inf": contenido_informe})
        salida = BytesIO()
        resultado = pisa.CreatePDF(html, dest=salida, encoding="utf-8", link_callback=self._ruta_local)
        if resultado.err:
            raise RuntimeError("No fue posible generar el PDF del informe.")
        return salida.getvalue()

    @staticmethod
    def _ruta_local(uri: str, rel: str | None = None) -> str:
        """Traduce /static/... a la ruta del archivo para que xhtml2pdf incruste el logo."""
        if uri.startswith(settings.STATIC_URL) or uri.startswith("/" + settings.STATIC_URL):
            relativo = uri.split(settings.STATIC_URL, 1)[1]
            return finders.find(relativo) or str(settings.STATIC_ROOT / relativo)
        return uri
