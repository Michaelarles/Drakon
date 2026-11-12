"""Adaptador AlmacenEvidencias que guarda los archivos en PostgreSQL.

Evita el disco efímero de Render. Para cambiar a S3 o Supabase Storage basta con
otro adaptador que implemente el mismo puerto y registrarlo en contenedor.py.
"""

from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.dominio.errores import NoEncontrado
from drakon.infraestructura.persistencia.models import ArchivoEvidenciaModel


class AlmacenEvidenciasBD:
    """Guarda los archivos en PostgreSQL. Evita el disco efímero de Render."""

    def guardar(self, archivo: ArchivoAdjunto) -> str:
        m = ArchivoEvidenciaModel.objects.create(
            nombre=archivo.nombre, tipo=archivo.tipo, tamano=len(archivo.contenido), datos=archivo.contenido
        )
        return str(m.id)

    def obtener(self, archivo_id: str) -> ArchivoAdjunto:
        try:
            m = ArchivoEvidenciaModel.objects.get(pk=archivo_id)
        except ArchivoEvidenciaModel.DoesNotExist:
            raise NoEncontrado("El archivo de evidencia no existe.") from None
        return ArchivoAdjunto(nombre=m.nombre, tipo=m.tipo, contenido=bytes(m.datos))

    def eliminar(self, archivo_id: str) -> None:
        ArchivoEvidenciaModel.objects.filter(pk=archivo_id).delete()
