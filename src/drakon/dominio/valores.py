"""Objetos de valor del dominio: estados, severidades y categorías."""

from enum import Enum


class EstadoAuditoria(str, Enum):
    BORRADOR = "BORRADOR"
    EN_EJECUCION = "EN_EJECUCION"
    EN_REVISION = "EN_REVISION"
    CERRADA = "CERRADA"

    @property
    def etiqueta(self) -> str:
        return {
            "BORRADOR": "Borrador",
            "EN_EJECUCION": "En ejecución",
            "EN_REVISION": "En revisión",
            "CERRADA": "Cerrada",
        }[self.value]


class EstadoEvaluacion(str, Enum):
    """Estados de evaluación de un control (sección 10.1 del documento orientador).

    PENDIENTE representa un control seleccionado que aún no se ha evaluado.
    """

    PENDIENTE = "PENDIENTE"
    IMPLEMENTADO = "IMPLEMENTADO"
    PARCIAL = "PARCIAL"
    NO_IMPLEMENTADO = "NO_IMPLEMENTADO"
    NO_APLICABLE = "NO_APLICABLE"

    @property
    def etiqueta(self) -> str:
        return {
            "PENDIENTE": "Sin evaluar",
            "IMPLEMENTADO": "Implementado",
            "PARCIAL": "Parcialmente implementado",
            "NO_IMPLEMENTADO": "No implementado",
            "NO_APLICABLE": "No aplicable",
        }[self.value]

    @property
    def exige_evidencia(self) -> bool:
        return self in (EstadoEvaluacion.IMPLEMENTADO, EstadoEvaluacion.PARCIAL)


class Severidad(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"

    @property
    def etiqueta(self) -> str:
        return self.value.capitalize()


class Prioridad(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"

    @property
    def etiqueta(self) -> str:
        return self.value.capitalize()


class CategoriaControl(str, Enum):
    ORGANIZACIONAL = "ORGANIZACIONAL"
    PERSONAS = "PERSONAS"
    FISICO = "FISICO"
    TECNOLOGICO = "TECNOLOGICO"

    @property
    def etiqueta(self) -> str:
        return {
            "ORGANIZACIONAL": "Organizacionales (5)",
            "PERSONAS": "Personas (6)",
            "FISICO": "Físicos (7)",
            "TECNOLOGICO": "Tecnológicos (8)",
        }[self.value]


# Rango de controles por auditoría definido en el alcance del proyecto.
MIN_CONTROLES = 10
MAX_CONTROLES = 15
# Mínimo de hallazgos para cerrar una auditoría (escenario de validación).
MIN_HALLAZGOS_CIERRE = 3
