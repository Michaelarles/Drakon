"""Agregado Informe: instantánea inmutable de los resultados de una auditoría (RF08)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .auditoria import Auditoria
from .catalogo import Control
from .indicadores import ADVERTENCIA, CalculadoraIndicadores


@dataclass(frozen=True)
class Informe:
    id_auditoria: int
    version: int
    fecha_generacion: datetime
    contenido: dict = field(default_factory=dict)
    id: int | None = None


def construir_contenido(auditoria: Auditoria, controles: dict[int, Control], auditor: str) -> dict:
    """Arma el contenido del informe solo con datos registrados (condición 16.1)."""
    ind = CalculadoraIndicadores.de_auditoria(auditoria)
    nombre_control = {e.id_control: f"{e.codigo_control} {controles[e.id_control].nombre}"
                      if e.id_control in controles else e.codigo_control
                      for e in auditoria.evaluaciones}
    aplicables = ind.aplicables
    base_txt = f"{ind.cumplimiento_base:.1f}".replace(".", ",") if ind.cumplimiento_base is not None else "sin datos"
    severidades = ind.hallazgos_por_severidad
    resumen = (
        f"De los {aplicables} controles aplicables evaluados, {ind.implementados} "
        f"({base_txt} %) están implementados, {ind.parciales} parcialmente y "
        f"{ind.no_implementados} no implementados. Se documentaron {ind.total_hallazgos} hallazgos "
        f"({severidades.get('ALTA', 0)} de severidad alta, {severidades.get('MEDIA', 0)} media y "
        f"{severidades.get('BAJA', 0)} baja). {ADVERTENCIA}"
    )
    return {
        "auditoria": {
            "id": auditoria.id,
            "organizacion": auditoria.organizacion,
            "objetivo": auditoria.objetivo,
            "alcance": auditoria.alcance,
            "fecha_inicio": auditoria.fecha_inicio.isoformat(),
            "fecha_fin": auditoria.fecha_fin.isoformat(),
            "auditor": auditor,
            "referentes": auditoria.referentes,
            "estado": auditoria.estado.etiqueta,
        },
        "controles": [
            {
                "codigo": e.codigo_control,
                "nombre": controles[e.id_control].nombre if e.id_control in controles else e.nombre_control,
                "categoria": controles[e.id_control].categoria.etiqueta if e.id_control in controles else "",
                "criterio": controles[e.id_control].descripcion if e.id_control in controles else "",
                "estado": e.estado.etiqueta,
                "estado_clave": e.estado.value,
                "observacion": e.observacion,
                "justificacion_na": e.justificacion_na,
                "evidencias": [ev.codigo for ev in e.evidencias],
            }
            for e in auditoria.evaluaciones
        ],
        "indicadores": ind.como_dict(),
        "resumen": resumen,
        "hallazgos": [
            {
                "codigo": h.codigo,
                "control": nombre_control.get(h.id_control, ""),
                "severidad": h.severidad.etiqueta,
                "condicion": h.condicion,
                "criterio": h.criterio,
                "causa": h.causa,
                "efecto": h.efecto,
                "recomendaciones": [
                    {"codigo": r.codigo, "descripcion": r.descripcion,
                     "prioridad": r.prioridad.etiqueta, "plazo_dias": r.plazo_dias}
                    for r in h.recomendaciones
                ],
            }
            for h in auditoria.hallazgos
        ],
        "evidencias": [
            {
                "codigo": ev.codigo,
                "control": e.codigo_control,
                "descripcion": ev.descripcion,
                "fuente": ev.fuente,
                "fecha": ev.fecha.isoformat(),
                "simulada": ev.es_simulada,
                "referencia": ev.referencia or ev.archivo_nombre,
            }
            for e in auditoria.evaluaciones for ev in e.evidencias
        ],
        "limitaciones": ADVERTENCIA,
    }
