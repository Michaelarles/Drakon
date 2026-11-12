"""Cálculo de indicadores (RF07). Única fuente de verdad para dashboard e informe.

Fórmulas documentadas:
  - Cumplimiento base   = implementados / aplicables × 100
  - Índice ponderado    = (implementados + 0,5 × parciales) / aplicables × 100
  - aplicables          = evaluados − no aplicables (los pendientes no cuentan)
Si no hay controles aplicables, el indicador es None («sin datos»).
El indicador es descriptivo: no constituye certificación.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .auditoria import Auditoria, EvaluacionControl, Hallazgo
from .valores import EstadoEvaluacion, Severidad

PESO_PARCIAL = 0.5

FORMULA_BASE = "Implementados / aplicables × 100"
FORMULA_PONDERADA = "(Implementados + 0,5 × parciales) / aplicables × 100"
ADVERTENCIA = (
    "El indicador es descriptivo y no constituye certificación ni sustituye el juicio profesional del auditor."
)


@dataclass(frozen=True)
class Indicadores:
    total: int
    implementados: int
    parciales: int
    no_implementados: int
    no_aplicables: int
    pendientes: int
    cumplimiento_base: float | None
    indice_ponderado: float | None
    hallazgos_por_severidad: dict[str, int] = field(default_factory=dict)

    @property
    def aplicables(self) -> int:
        return self.implementados + self.parciales + self.no_implementados

    @property
    def total_hallazgos(self) -> int:
        return sum(self.hallazgos_por_severidad.values())

    def como_dict(self) -> dict:
        return {
            "total": self.total,
            "implementados": self.implementados,
            "parciales": self.parciales,
            "no_implementados": self.no_implementados,
            "no_aplicables": self.no_aplicables,
            "pendientes": self.pendientes,
            "aplicables": self.aplicables,
            "cumplimiento_base": self.cumplimiento_base,
            "indice_ponderado": self.indice_ponderado,
            "hallazgos_por_severidad": dict(self.hallazgos_por_severidad),
            "total_hallazgos": self.total_hallazgos,
            "formula_base": FORMULA_BASE,
            "formula_ponderada": FORMULA_PONDERADA,
            "advertencia": ADVERTENCIA,
        }


class CalculadoraIndicadores:
    @staticmethod
    def calcular(evaluaciones: list[EvaluacionControl], hallazgos: list[Hallazgo] | None = None) -> Indicadores:
        c = Counter(e.estado for e in evaluaciones)
        impl, parc = c[EstadoEvaluacion.IMPLEMENTADO], c[EstadoEvaluacion.PARCIAL]
        noimp = c[EstadoEvaluacion.NO_IMPLEMENTADO]
        aplicables = impl + parc + noimp
        base = round(100.0 * impl / aplicables, 1) if aplicables else None
        ponderado = round(100.0 * (impl + PESO_PARCIAL * parc) / aplicables, 1) if aplicables else None
        sev = Counter(h.severidad for h in (hallazgos or []))
        return Indicadores(
            total=len(evaluaciones),
            implementados=impl,
            parciales=parc,
            no_implementados=noimp,
            no_aplicables=c[EstadoEvaluacion.NO_APLICABLE],
            pendientes=c[EstadoEvaluacion.PENDIENTE],
            cumplimiento_base=base,
            indice_ponderado=ponderado,
            hallazgos_por_severidad={s.value: sev[s] for s in Severidad},
        )

    @classmethod
    def de_auditoria(cls, auditoria: Auditoria) -> Indicadores:
        return cls.calcular(auditoria.evaluaciones, auditoria.hallazgos)

    @classmethod
    def consolidado(cls, auditorias: list[Auditoria]) -> Indicadores:
        """Indicadores agregados de varias auditorías (dashboard, RF09)."""
        evaluaciones = [e for a in auditorias for e in a.evaluaciones]
        hallazgos = [h for a in auditorias for h in a.hallazgos]
        return cls.calcular(evaluaciones, hallazgos)
