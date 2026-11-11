"""Agregado raíz Auditoría.

Contiene las evaluaciones de control, sus evidencias, los hallazgos y sus
recomendaciones. Todas las reglas que cruzan esas entidades se validan aquí,
de modo que la trazabilidad (RNF05) se garantiza en un solo lugar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .catalogo import Control
from .errores import DatoInvalido, NoEncontrado, ReglaDeNegocioViolada
from .valores import (
    MAX_CONTROLES,
    MIN_CONTROLES,
    MIN_HALLAZGOS_CIERRE,
    EstadoAuditoria,
    EstadoEvaluacion,
    Prioridad,
    Severidad,
)


def _texto(valor: str | None, campo: str, nombre: str, max_len: int | None = None) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise DatoInvalido(f"{nombre} es obligatorio.", campo)
    if max_len and len(valor) > max_len:
        raise DatoInvalido(f"{nombre} admite máximo {max_len} caracteres.", campo)
    return valor


# --------------------------------------------------------------------------
# Entidades hijas
# --------------------------------------------------------------------------
@dataclass
class Evidencia:
    codigo: str                      # EV-01, EV-02, ...
    descripcion: str
    fuente: str
    fecha: date
    es_simulada: bool = True
    referencia: str = ""             # URL o referencia documental
    archivo_id: str | None = None    # clave en el almacén de evidencias
    archivo_nombre: str = ""
    id: int | None = None


@dataclass
class Recomendacion:
    codigo: str                      # R-01, R-02, ...
    descripcion: str
    prioridad: Prioridad
    plazo_dias: int
    id: int | None = None


@dataclass
class Hallazgo:
    codigo: str                      # H-01, H-02, ...
    id_control: int
    condicion: str
    criterio: str
    causa: str
    efecto: str
    severidad: Severidad
    recomendaciones: list[Recomendacion] = field(default_factory=list)
    id: int | None = None


@dataclass
class EvaluacionControl:
    id_control: int
    codigo_control: str
    nombre_control: str = ""
    estado: EstadoEvaluacion = EstadoEvaluacion.PENDIENTE
    observacion: str = ""
    justificacion_na: str = ""
    evidencias: list[Evidencia] = field(default_factory=list)
    id: int | None = None

    @property
    def evaluada(self) -> bool:
        return self.estado != EstadoEvaluacion.PENDIENTE


# --------------------------------------------------------------------------
# Agregado raíz
# --------------------------------------------------------------------------
@dataclass
class Auditoria:
    organizacion: str
    objetivo: str
    alcance: str
    fecha_inicio: date
    fecha_fin: date
    id_auditor: int
    referentes: str = "ISO 19011:2018; ISO/IEC 27001:2022; ISO/IEC 27002:2022"
    estado: EstadoAuditoria = EstadoAuditoria.BORRADOR
    evaluaciones: list[EvaluacionControl] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    id: int | None = None

    # ---------------------------------------------------------------- RF01
    @classmethod
    def crear(cls, organizacion, objetivo, alcance, fecha_inicio, fecha_fin, id_auditor,
              referentes: str | None = None) -> "Auditoria":
        if fecha_inicio is None:
            raise DatoInvalido("La fecha de inicio es obligatoria.", "fecha_inicio")
        if fecha_fin is None:
            raise DatoInvalido("La fecha de cierre es obligatoria.", "fecha_fin")
        if fecha_fin < fecha_inicio:
            raise DatoInvalido("La fecha de cierre debe ser igual o posterior a la de inicio.", "fecha_fin")
        if not id_auditor:
            raise DatoInvalido("La auditoría debe tener un auditor responsable.", "id_auditor")
        aud = cls(
            organizacion=_texto(organizacion, "organizacion", "La organización", 120),
            objetivo=_texto(objetivo, "objetivo", "El objetivo"),
            alcance=_texto(alcance, "alcance", "El alcance"),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            id_auditor=id_auditor,
        )
        if referentes and referentes.strip():
            aud.referentes = referentes.strip()
        return aud

    def actualizar_datos(self, organizacion, objetivo, alcance, fecha_inicio, fecha_fin, referentes=None):
        self._exigir_estado(EstadoAuditoria.BORRADOR, EstadoAuditoria.EN_EJECUCION)
        nueva = Auditoria.crear(organizacion, objetivo, alcance, fecha_inicio, fecha_fin, self.id_auditor, referentes)
        self.organizacion, self.objetivo, self.alcance = nueva.organizacion, nueva.objetivo, nueva.alcance
        self.fecha_inicio, self.fecha_fin, self.referentes = nueva.fecha_inicio, nueva.fecha_fin, nueva.referentes

    # ---------------------------------------------------------------- RF02
    def seleccionar_controles(self, controles: list[Control]) -> None:
        """Define los controles que se evaluarán. Solo en borrador.

        Conserva las evaluaciones de controles que siguen seleccionados.
        El rango 10-15 se exige al pasar a ejecución (CP-03), no al guardar.
        """
        self._exigir_estado(EstadoAuditoria.BORRADOR)
        if len(controles) > MAX_CONTROLES:
            raise ReglaDeNegocioViolada(
                f"Se seleccionaron {len(controles)} controles; el máximo permitido es {MAX_CONTROLES}.",
                "controles",
            )
        ids = [c.id for c in controles]
        if len(set(ids)) != len(ids):
            raise ReglaDeNegocioViolada("Un control no puede seleccionarse dos veces.", "controles")
        actuales = {e.id_control: e for e in self.evaluaciones}
        self.evaluaciones = [
            actuales.get(c.id) or EvaluacionControl(id_control=c.id, codigo_control=c.codigo, nombre_control=c.nombre)
            for c in sorted(controles, key=lambda c: c.orden)
        ]

    @property
    def ids_controles(self) -> list[int]:
        return [e.id_control for e in self.evaluaciones]

    def iniciar_ejecucion(self) -> None:
        self._exigir_estado(EstadoAuditoria.BORRADOR)
        n = len(self.evaluaciones)
        if not MIN_CONTROLES <= n <= MAX_CONTROLES:
            raise ReglaDeNegocioViolada(
                f"Para iniciar la ejecución se requieren entre {MIN_CONTROLES} y {MAX_CONTROLES} "
                f"controles seleccionados; hay {n}.",
                "controles",
            )
        self.estado = EstadoAuditoria.EN_EJECUCION

    # ---------------------------------------------------------------- RF03
    def evaluar_control(self, id_control: int, estado: EstadoEvaluacion | str,
                        observacion: str, justificacion_na: str = "") -> EvaluacionControl:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION)
        estado = EstadoEvaluacion(estado)
        if estado == EstadoEvaluacion.PENDIENTE:
            raise DatoInvalido("Seleccione uno de los cuatro estados de evaluación.", "estado")
        ev = self.evaluacion(id_control)
        observacion = _texto(observacion, "observacion", "La observación del auditor")
        justificacion_na = (justificacion_na or "").strip()
        if estado == EstadoEvaluacion.NO_APLICABLE and not justificacion_na:
            raise DatoInvalido("Un control «No aplicable» exige justificación.", "justificacion_na")
        if estado != EstadoEvaluacion.NO_APLICABLE:
            justificacion_na = ""
        if estado == EstadoEvaluacion.NO_APLICABLE and self._hallazgos_de(id_control):
            raise ReglaDeNegocioViolada(
                "No se puede marcar como «No aplicable» un control que tiene hallazgos.", "estado"
            )
        ev.estado, ev.observacion, ev.justificacion_na = estado, observacion, justificacion_na
        return ev

    # ---------------------------------------------------------------- RF04
    def registrar_evidencia(self, id_control: int, descripcion: str, fuente: str, fecha: date,
                            es_simulada: bool = True, referencia: str = "",
                            archivo_id: str | None = None, archivo_nombre: str = "") -> Evidencia:
        evidencia = self.validar_evidencia(id_control, descripcion, fuente, fecha, es_simulada,
                                           referencia, archivo_id, archivo_nombre)
        self.evaluacion(id_control).evidencias.append(evidencia)
        return evidencia

    def validar_evidencia(self, id_control: int, descripcion: str, fuente: str, fecha: date,
                          es_simulada: bool = True, referencia: str = "",
                          archivo_id: str | None = None, archivo_nombre: str = "") -> Evidencia:
        """Valida y construye la evidencia sin agregarla (útil antes de guardar archivos)."""
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION)
        self.evaluacion(id_control)
        if fecha is None:
            raise DatoInvalido("La fecha de la evidencia es obligatoria.", "fecha")
        if not (referencia or "").strip() and not archivo_id:
            raise DatoInvalido("Adjunte un archivo o indique una referencia de la evidencia.", "referencia")
        evidencia = Evidencia(
            codigo=self._siguiente_codigo("EV", [e.codigo for e in self.todas_las_evidencias]),
            descripcion=_texto(descripcion, "descripcion", "La descripción de la evidencia"),
            fuente=_texto(fuente, "fuente", "La fuente de la evidencia", 200),
            fecha=fecha,
            es_simulada=es_simulada,
            referencia=(referencia or "").strip(),
            archivo_id=archivo_id,
            archivo_nombre=archivo_nombre or "",
        )
        return evidencia

    def eliminar_evidencia(self, codigo: str) -> Evidencia:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION)
        for ev in self.evaluaciones:
            for e in ev.evidencias:
                if e.codigo == codigo:
                    ev.evidencias.remove(e)
                    return e
        raise NoEncontrado(f"No existe la evidencia {codigo}.")

    @property
    def todas_las_evidencias(self) -> list[Evidencia]:
        return [e for ev in self.evaluaciones for e in ev.evidencias]

    def editar_evidencia(self, codigo: str, descripcion: str, fuente: str, fecha: date,
                         es_simulada: bool, referencia: str) -> Evidencia:
        """Actualiza los datos descriptivos de una evidencia (el archivo, si lo hay, se conserva)."""
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION)
        evidencia = self.evidencia(codigo)
        if fecha is None:
            raise DatoInvalido("La fecha de la evidencia es obligatoria.", "fecha")
        referencia = (referencia or "").strip()
        if not referencia and not evidencia.archivo_id:
            raise DatoInvalido("Adjunte un archivo o indique una referencia de la evidencia.", "referencia")
        evidencia.descripcion = _texto(descripcion, "descripcion", "La descripción de la evidencia")
        evidencia.fuente = _texto(fuente, "fuente", "La fuente de la evidencia", 200)
        evidencia.fecha, evidencia.es_simulada, evidencia.referencia = fecha, es_simulada, referencia
        return evidencia

    def evidencia(self, codigo: str) -> Evidencia:
        for e in self.todas_las_evidencias:
            if e.codigo == codigo:
                return e
        raise NoEncontrado(f"No existe la evidencia {codigo}.")

    def control_de_evidencia(self, codigo: str) -> int:
        for ev in self.evaluaciones:
            if any(e.codigo == codigo for e in ev.evidencias):
                return ev.id_control
        raise NoEncontrado(f"No existe la evidencia {codigo}.")

    # ---------------------------------------------------------- RF05 / RF06
    def _validar_control_para_hallazgo(self, id_control: int) -> None:
        ev = self.evaluacion(id_control)
        if not ev.evaluada:
            raise ReglaDeNegocioViolada("Evalúe el control antes de registrar un hallazgo.", "id_control")
        if ev.estado == EstadoEvaluacion.NO_APLICABLE:
            raise ReglaDeNegocioViolada("No se registran hallazgos sobre controles «No aplicable».", "id_control")

    @staticmethod
    def _datos_hallazgo(condicion, criterio, causa, efecto, severidad) -> dict:
        try:
            severidad = Severidad(severidad)
        except ValueError:
            raise DatoInvalido("Seleccione la severidad del hallazgo.", "severidad")
        return dict(
            condicion=_texto(condicion, "condicion", "La condición"),
            criterio=_texto(criterio, "criterio", "El criterio"),
            causa=_texto(causa, "causa", "La causa"),
            efecto=_texto(efecto, "efecto", "El efecto o riesgo"),
            severidad=severidad,
        )

    @staticmethod
    def _datos_recomendacion(descripcion, prioridad, plazo_dias) -> dict:
        try:
            prioridad = Prioridad(prioridad)
        except ValueError:
            raise DatoInvalido("Seleccione la prioridad de la recomendación.", "prioridad")
        try:
            plazo = int(plazo_dias)
        except (TypeError, ValueError):
            plazo = 0
        if plazo <= 0:
            raise DatoInvalido("El plazo sugerido debe ser un número de días mayor que cero.", "plazo_dias")
        return dict(descripcion=_texto(descripcion, "recomendacion", "La recomendación"),
                    prioridad=prioridad, plazo_dias=plazo)

    def registrar_hallazgo(self, id_control: int, condicion: str, criterio: str, causa: str,
                           efecto: str, severidad: Severidad | str,
                           recomendacion: str | None = None, prioridad: Prioridad | str | None = None,
                           plazo_dias: int | None = None) -> Hallazgo:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        self._validar_control_para_hallazgo(id_control)
        datos = self._datos_hallazgo(condicion, criterio, causa, efecto, severidad)
        if recomendacion and recomendacion.strip():
            self._datos_recomendacion(recomendacion, prioridad, plazo_dias)  # valida antes de agregar nada
        hallazgo = Hallazgo(codigo=self._siguiente_codigo("H", [h.codigo for h in self.hallazgos]),
                            id_control=id_control, **datos)
        self.hallazgos.append(hallazgo)
        if recomendacion and recomendacion.strip():
            self.agregar_recomendacion(hallazgo.codigo, recomendacion, prioridad, plazo_dias)
        return hallazgo

    def editar_hallazgo(self, codigo: str, id_control: int, condicion: str, criterio: str, causa: str,
                        efecto: str, severidad: Severidad | str) -> Hallazgo:
        """Corrige un hallazgo; conserva su código y sus recomendaciones."""
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        hallazgo = self.hallazgo(codigo)
        self._validar_control_para_hallazgo(id_control)
        for campo, valor in self._datos_hallazgo(condicion, criterio, causa, efecto, severidad).items():
            setattr(hallazgo, campo, valor)
        hallazgo.id_control = id_control
        return hallazgo

    def eliminar_hallazgo(self, codigo: str) -> Hallazgo:
        """Elimina el hallazgo y sus recomendaciones. Los demás códigos no cambian."""
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        hallazgo = self.hallazgo(codigo)
        self.hallazgos.remove(hallazgo)
        return hallazgo

    def agregar_recomendacion(self, codigo_hallazgo: str, descripcion: str,
                              prioridad: Prioridad | str | None, plazo_dias: int | None) -> Recomendacion:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        hallazgo = self.hallazgo(codigo_hallazgo)
        datos = self._datos_recomendacion(descripcion, prioridad, plazo_dias)
        rec = Recomendacion(
            codigo=self._siguiente_codigo("R", [r.codigo for h in self.hallazgos for r in h.recomendaciones]),
            **datos)
        hallazgo.recomendaciones.append(rec)
        return rec

    def editar_recomendacion(self, codigo: str, descripcion: str, prioridad: Prioridad | str,
                             plazo_dias: int) -> Recomendacion:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        _, rec = self.recomendacion(codigo)
        for campo, valor in self._datos_recomendacion(descripcion, prioridad, plazo_dias).items():
            setattr(rec, campo, valor)
        return rec

    def eliminar_recomendacion(self, codigo: str) -> Recomendacion:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION)
        hallazgo, rec = self.recomendacion(codigo)
        hallazgo.recomendaciones.remove(rec)
        return rec

    def recomendacion(self, codigo: str) -> tuple[Hallazgo, Recomendacion]:
        for h in self.hallazgos:
            for r in h.recomendaciones:
                if r.codigo == codigo:
                    return h, r
        raise NoEncontrado(f"No existe la recomendación {codigo}.")

    # -------------------------------------------------------- eliminación
    def verificar_eliminable(self) -> None:
        """Una auditoría cerrada es un registro de evidencia: no se elimina."""
        if self.estado == EstadoAuditoria.CERRADA:
            raise ReglaDeNegocioViolada("Una auditoría cerrada no se puede eliminar: es el soporte del informe emitido.")

    # ------------------------------------------------------- ciclo de vida
    def problemas_para_revision(self) -> list[str]:
        """Lo que impide pasar a revisión (CP-06). Vacío si se puede."""
        problemas = []
        for ev in self.evaluaciones:
            if not ev.evaluada:
                problemas.append(f"El control {ev.codigo_control} no ha sido evaluado.")
            elif ev.estado.exige_evidencia and not ev.evidencias:
                problemas.append(
                    f"El control {ev.codigo_control} está «{ev.estado.etiqueta}» y no tiene evidencias."
                )
        return problemas

    def problemas_para_cierre(self) -> list[str]:
        """Lo que impide cerrar la auditoría (CP-08). Vacío si se puede."""
        problemas = []
        if len(self.hallazgos) < MIN_HALLAZGOS_CIERRE:
            problemas.append(
                f"Se requieren al menos {MIN_HALLAZGOS_CIERRE} hallazgos documentados; hay {len(self.hallazgos)}."
            )
        for h in self.hallazgos:
            if not h.recomendaciones:
                problemas.append(f"El hallazgo {h.codigo} no tiene recomendación asociada.")
        return problemas

    def enviar_a_revision(self) -> None:
        self._exigir_estado(EstadoAuditoria.EN_EJECUCION)
        problemas = self.problemas_para_revision()
        if problemas:
            raise ReglaDeNegocioViolada("No se puede pasar a revisión: " + " ".join(problemas))
        self.estado = EstadoAuditoria.EN_REVISION

    def devolver_a_ejecucion(self) -> None:
        self._exigir_estado(EstadoAuditoria.EN_REVISION)
        self.estado = EstadoAuditoria.EN_EJECUCION

    def cerrar(self) -> None:
        self._exigir_estado(EstadoAuditoria.EN_REVISION)
        problemas = self.problemas_para_revision() + self.problemas_para_cierre()
        if problemas:
            raise ReglaDeNegocioViolada("No se puede cerrar la auditoría: " + " ".join(problemas))
        self.estado = EstadoAuditoria.CERRADA

    # ------------------------------------------------------------ consultas
    def evaluacion(self, id_control: int) -> EvaluacionControl:
        for ev in self.evaluaciones:
            if ev.id_control == id_control:
                return ev
        raise NoEncontrado("El control no está seleccionado en esta auditoría.", "id_control")

    def hallazgo(self, codigo: str) -> Hallazgo:
        for h in self.hallazgos:
            if h.codigo == codigo:
                return h
        raise NoEncontrado(f"No existe el hallazgo {codigo}.")

    def _hallazgos_de(self, id_control: int) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.id_control == id_control]

    @property
    def editable(self) -> bool:
        return self.estado != EstadoAuditoria.CERRADA

    # ------------------------------------------------------------- internos
    def _exigir_estado(self, *permitidos: EstadoAuditoria) -> None:
        if self.estado == EstadoAuditoria.CERRADA:
            raise ReglaDeNegocioViolada("La auditoría está cerrada y no admite cambios.")
        if self.estado not in permitidos:
            nombres = " o ".join(f"«{e.etiqueta}»" for e in permitidos)
            raise ReglaDeNegocioViolada(
                f"Esta acción solo se permite con la auditoría en estado {nombres} "
                f"(estado actual: «{self.estado.etiqueta}»)."
            )

    @staticmethod
    def _siguiente_codigo(prefijo: str, existentes: list[str]) -> str:
        numeros = [int(c.split("-")[1]) for c in existentes if c.startswith(prefijo + "-")]
        return f"{prefijo}-{(max(numeros, default=0) + 1):02d}"
