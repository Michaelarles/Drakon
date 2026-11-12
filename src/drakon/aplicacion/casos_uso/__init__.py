"""Casos de uso (puertos de entrada). Cada clase representa una acción del usuario.

Orquestan: cargar agregado → invocar reglas del dominio → persistir.
No conocen Django ni la base de datos: solo los puertos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from drakon.aplicacion.puertos import (
    AlmacenEvidencias,
    ArchivoAdjunto,
    DirectorioUsuarios,
    GeneradorPDF,
    RepositorioAuditorias,
    RepositorioCatalogo,
    RepositorioInformes,
)
from drakon.dominio.auditoria import Auditoria, Evidencia, Hallazgo, Recomendacion
from drakon.dominio.catalogo import Control
from drakon.dominio.errores import DatoInvalido, NoEncontrado, ReglaDeNegocioViolada
from drakon.dominio.indicadores import CalculadoraIndicadores, Indicadores
from drakon.dominio.informe import Informe, construir_contenido
from drakon.dominio.valores import CategoriaControl, EstadoAuditoria, EstadoEvaluacion, Prioridad, Severidad

TAMANO_MAX_EVIDENCIA = 5 * 1024 * 1024  # 5 MB
TIPOS_EVIDENCIA = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
# Firmas («números mágicos») para no confiar solo en la extensión del archivo
FIRMAS_EVIDENCIA = {"application/pdf": b"%PDF", "image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff"}


# --------------------------------------------------------------------- RF01
@dataclass
class DatosAuditoria:
    organizacion: str
    objetivo: str
    alcance: str
    fecha_inicio: date | None
    fecha_fin: date | None
    referentes: str = ""


class CrearAuditoria:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, datos: DatosAuditoria, id_auditor: int) -> Auditoria:
        auditoria = Auditoria.crear(
            datos.organizacion,
            datos.objetivo,
            datos.alcance,
            datos.fecha_inicio,
            datos.fecha_fin,
            id_auditor,
            datos.referentes,
        )
        return self.auditorias.guardar(auditoria)


class ActualizarAuditoria:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, datos: DatosAuditoria) -> Auditoria:
        a = self.auditorias.obtener(id_auditoria)
        a.actualizar_datos(
            datos.organizacion, datos.objetivo, datos.alcance, datos.fecha_inicio, datos.fecha_fin, datos.referentes
        )
        return self.auditorias.guardar(a)


class EliminarAuditoria:
    def __init__(self, auditorias: RepositorioAuditorias, almacen: AlmacenEvidencias):
        self.auditorias, self.almacen = auditorias, almacen

    def ejecutar(self, id_auditoria: int) -> Auditoria:
        a = self.auditorias.obtener(id_auditoria)
        a.verificar_eliminable()
        archivos = [e.archivo_id for e in a.todas_las_evidencias if e.archivo_id]
        self.auditorias.eliminar(id_auditoria)
        for archivo_id in archivos:
            self.almacen.eliminar(archivo_id)
        return a


# --------------------------------------------------------------------- RF02
class SeleccionarControles:
    def __init__(self, auditorias: RepositorioAuditorias, catalogo: RepositorioCatalogo):
        self.auditorias, self.catalogo = auditorias, catalogo

    def ejecutar(self, id_auditoria: int, ids_controles: list[int]) -> Auditoria:
        a = self.auditorias.obtener(id_auditoria)
        controles = self.catalogo.obtener_varios(list(dict.fromkeys(ids_controles)))
        faltantes = set(ids_controles) - set(controles)
        if faltantes:
            raise NoEncontrado("Uno o más controles seleccionados no existen en el catálogo.", "controles")
        a.seleccionar_controles(list(controles.values()))
        return self.auditorias.guardar(a)


class CambiarEstadoAuditoria:
    ACCIONES = {
        "iniciar": Auditoria.iniciar_ejecucion,
        "revision": Auditoria.enviar_a_revision,
        "devolver": Auditoria.devolver_a_ejecucion,
        "cerrar": Auditoria.cerrar,
    }

    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, accion: str) -> Auditoria:
        if accion not in self.ACCIONES:
            raise DatoInvalido("Acción de estado no reconocida.", "accion")
        a = self.auditorias.obtener(id_auditoria)
        self.ACCIONES[accion](a)
        return self.auditorias.guardar(a)


# --------------------------------------------------------------------- RF03
class EvaluarControl:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(
        self, id_auditoria: int, id_control: int, estado: str, observacion: str, justificacion_na: str = ""
    ) -> Auditoria:
        a = self.auditorias.obtener(id_auditoria)
        try:
            estado = EstadoEvaluacion(estado)
        except ValueError:
            raise DatoInvalido("Seleccione uno de los cuatro estados de evaluación.", "estado") from None
        a.evaluar_control(id_control, estado, observacion, justificacion_na)
        return self.auditorias.guardar(a)


# --------------------------------------------------------------------- RF04
@dataclass
class DatosEvidencia:
    descripcion: str
    fuente: str
    fecha: date | None
    es_simulada: bool = True
    referencia: str = ""
    archivo: ArchivoAdjunto | None = None


class RegistrarEvidencia:
    def __init__(self, auditorias: RepositorioAuditorias, almacen: AlmacenEvidencias):
        self.auditorias, self.almacen = auditorias, almacen

    def ejecutar(self, id_auditoria: int, id_control: int, datos: DatosEvidencia) -> Evidencia:
        a = self.auditorias.obtener(id_auditoria)
        archivo_id, archivo_nombre = None, ""
        if datos.archivo is not None:
            self._validar_archivo(datos.archivo)
        # Valida en el dominio antes de guardar el archivo, para no dejar archivos huérfanos.
        a.validar_evidencia(
            id_control,
            datos.descripcion,
            datos.fuente,
            datos.fecha,
            datos.es_simulada,
            datos.referencia,
            "provisional" if datos.archivo else None,
        )
        if datos.archivo is not None:
            archivo_id = self.almacen.guardar(datos.archivo)
            archivo_nombre = datos.archivo.nombre
        evidencia = a.registrar_evidencia(
            id_control,
            datos.descripcion,
            datos.fuente,
            datos.fecha,
            datos.es_simulada,
            datos.referencia,
            archivo_id,
            archivo_nombre,
        )
        self.auditorias.guardar(a)
        return evidencia

    @staticmethod
    def _validar_archivo(archivo: ArchivoAdjunto) -> None:
        if archivo.tipo not in TIPOS_EVIDENCIA:
            raise DatoInvalido("Solo se admiten archivos PDF, PNG o JPG.", "archivo")
        if len(archivo.contenido) > TAMANO_MAX_EVIDENCIA:
            raise DatoInvalido("El archivo supera el tamaño máximo de 5 MB.", "archivo")
        if not archivo.contenido:
            raise DatoInvalido("El archivo está vacío.", "archivo")
        if not archivo.contenido.startswith(FIRMAS_EVIDENCIA[archivo.tipo]):
            raise DatoInvalido("El contenido del archivo no corresponde a un PDF, PNG o JPG válido.", "archivo")


class EliminarEvidencia:
    def __init__(self, auditorias: RepositorioAuditorias, almacen: AlmacenEvidencias):
        self.auditorias, self.almacen = auditorias, almacen

    def ejecutar(self, id_auditoria: int, codigo: str) -> None:
        a = self.auditorias.obtener(id_auditoria)
        evidencia = a.eliminar_evidencia(codigo)
        self.auditorias.guardar(a)
        if evidencia.archivo_id:
            self.almacen.eliminar(evidencia.archivo_id)


class EditarEvidencia:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, codigo: str, datos: DatosEvidencia) -> Evidencia:
        a = self.auditorias.obtener(id_auditoria)
        e = a.editar_evidencia(
            codigo, datos.descripcion, datos.fuente, datos.fecha, datos.es_simulada, datos.referencia
        )
        self.auditorias.guardar(a)
        return e


class ObtenerArchivoEvidencia:
    def __init__(self, auditorias: RepositorioAuditorias, almacen: AlmacenEvidencias):
        self.auditorias, self.almacen = auditorias, almacen

    def ejecutar(self, id_auditoria: int, codigo: str) -> ArchivoAdjunto:
        a = self.auditorias.obtener(id_auditoria)
        for e in a.todas_las_evidencias:
            if e.codigo == codigo and e.archivo_id:
                return self.almacen.obtener(e.archivo_id)
        raise NoEncontrado("La evidencia no tiene archivo adjunto.")


# --------------------------------------------------------------- RF05 / RF06
@dataclass
class DatosHallazgo:
    id_control: int
    condicion: str
    criterio: str
    causa: str
    efecto: str
    severidad: str
    recomendacion: str = ""
    prioridad: str | None = None
    plazo_dias: int | None = None


class RegistrarHallazgo:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, datos: DatosHallazgo) -> Hallazgo:
        a = self.auditorias.obtener(id_auditoria)
        h = a.registrar_hallazgo(
            datos.id_control,
            datos.condicion,
            datos.criterio,
            datos.causa,
            datos.efecto,
            datos.severidad,
            datos.recomendacion,
            datos.prioridad,
            datos.plazo_dias,
        )
        self.auditorias.guardar(a)
        return h


class AgregarRecomendacion:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(
        self, id_auditoria: int, codigo_hallazgo: str, descripcion: str, prioridad: str, plazo_dias: int | None
    ):
        a = self.auditorias.obtener(id_auditoria)
        r = a.agregar_recomendacion(codigo_hallazgo, descripcion, prioridad, plazo_dias)
        self.auditorias.guardar(a)
        return r


class EditarHallazgo:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, codigo: str, datos: DatosHallazgo) -> Hallazgo:
        a = self.auditorias.obtener(id_auditoria)
        h = a.editar_hallazgo(
            codigo, datos.id_control, datos.condicion, datos.criterio, datos.causa, datos.efecto, datos.severidad
        )
        self.auditorias.guardar(a)
        return h


class EliminarHallazgo:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, codigo: str) -> Hallazgo:
        a = self.auditorias.obtener(id_auditoria)
        h = a.eliminar_hallazgo(codigo)
        self.auditorias.guardar(a)
        return h


class EditarRecomendacion:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(
        self, id_auditoria: int, codigo: str, descripcion: str, prioridad: str, plazo_dias: int | None
    ) -> Recomendacion:
        a = self.auditorias.obtener(id_auditoria)
        r = a.editar_recomendacion(codigo, descripcion, prioridad, plazo_dias)
        self.auditorias.guardar(a)
        return r


class EliminarRecomendacion:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int, codigo: str) -> Recomendacion:
        a = self.auditorias.obtener(id_auditoria)
        r = a.eliminar_recomendacion(codigo)
        self.auditorias.guardar(a)
        return r


# --------------------------------------------------------- catálogo (RF02)
@dataclass
class DatosControl:
    codigo: str
    nombre: str
    categoria: str
    descripcion: str


class GuardarControl:
    """Crea un control nuevo (id_control None) o edita uno existente."""

    def __init__(self, catalogo: RepositorioCatalogo):
        self.catalogo = catalogo

    def ejecutar(self, datos: DatosControl, id_control: int | None = None) -> Control:
        try:
            categoria = CategoriaControl(datos.categoria)
        except ValueError:
            raise DatoInvalido("Seleccione la categoría del control.", "categoria") from None
        control = Control(
            codigo=datos.codigo, nombre=datos.nombre, categoria=categoria, descripcion=datos.descripcion, id=id_control
        )
        if id_control is not None:
            self.catalogo.obtener(id_control)  # NoEncontrado si no existe
        if self.catalogo.existe_codigo(control.codigo, excluir_id=id_control):
            raise ReglaDeNegocioViolada(f"Ya existe un control con el código {control.codigo}.", "codigo")
        return self.catalogo.guardar(control)


class EliminarControl:
    def __init__(self, catalogo: RepositorioCatalogo):
        self.catalogo = catalogo

    def ejecutar(self, id_control: int) -> Control:
        control = self.catalogo.obtener(id_control)
        if self.catalogo.en_uso(id_control):
            raise ReglaDeNegocioViolada(
                f"El control {control.codigo} está seleccionado en al menos una auditoría y no se puede eliminar."
            )
        self.catalogo.eliminar(id_control)
        return control


# --------------------------------------------------------------- RF07 / RF08
class ConsultarIndicadores:
    def __init__(self, auditorias: RepositorioAuditorias):
        self.auditorias = auditorias

    def ejecutar(self, id_auditoria: int) -> Indicadores:
        return CalculadoraIndicadores.de_auditoria(self.auditorias.obtener(id_auditoria))


class GenerarInforme:
    def __init__(
        self,
        auditorias: RepositorioAuditorias,
        catalogo: RepositorioCatalogo,
        informes: RepositorioInformes,
        usuarios: DirectorioUsuarios,
    ):
        self.auditorias, self.catalogo = auditorias, catalogo
        self.informes, self.usuarios = informes, usuarios

    def ejecutar(self, id_auditoria: int) -> Informe:
        a = self.auditorias.obtener(id_auditoria)
        if a.estado == EstadoAuditoria.BORRADOR:
            raise ReglaDeNegocioViolada("Inicie la ejecución y evalúe los controles antes de generar el informe.")
        controles = self.catalogo.obtener_varios(a.ids_controles)
        contenido = construir_contenido(a, controles, self.usuarios.nombre(a.id_auditor))
        version = self.informes.ultima_version(id_auditoria) + 1
        contenido["version"] = version
        contenido["preliminar"] = a.estado != EstadoAuditoria.CERRADA
        informe = Informe(
            id_auditoria=id_auditoria, version=version, fecha_generacion=datetime.now(UTC), contenido=contenido
        )
        return self.informes.guardar(informe)


class DescargarInformePDF:
    def __init__(self, informes: RepositorioInformes, pdf: GeneradorPDF):
        self.informes, self.pdf = informes, pdf

    def ejecutar(self, id_informe: int) -> tuple[Informe, bytes]:
        informe = self.informes.obtener(id_informe)
        contenido = dict(informe.contenido, fecha_generacion=informe.fecha_generacion.isoformat())
        return informe, self.pdf.generar(contenido)


# --------------------------------------------------------------------- RF09
@dataclass(frozen=True)
class Dashboard:
    total_auditorias: int
    por_estado: dict[str, int]
    indicadores: Indicadores
    recientes: list[tuple[Auditoria, Indicadores]]
    por_categoria: list[tuple[CategoriaControl, Indicadores]]

    @property
    def activas(self) -> int:
        return self.por_estado[EstadoAuditoria.EN_EJECUCION.value] + self.por_estado[EstadoAuditoria.EN_REVISION.value]


class ConsultarDashboard:
    def __init__(self, auditorias: RepositorioAuditorias, catalogo: RepositorioCatalogo | None = None):
        self.auditorias, self.catalogo = auditorias, catalogo

    def ejecutar(self, id_auditor: int | None = None, recientes: int = 5) -> Dashboard:
        todas = self.auditorias.listar(id_auditor)
        por_estado = {e.value: 0 for e in EstadoAuditoria}
        for a in todas:
            por_estado[a.estado.value] += 1
        return Dashboard(
            total_auditorias=len(todas),
            por_estado=por_estado,
            indicadores=CalculadoraIndicadores.consolidado(todas),
            recientes=[(a, CalculadoraIndicadores.de_auditoria(a)) for a in todas[:recientes]],
            por_categoria=self._por_categoria(todas),
        )

    def _por_categoria(self, auditorias: list[Auditoria]) -> list[tuple[CategoriaControl, Indicadores]]:
        """Cumplimiento por categoría ISO 27002 (organizacionales, personas, físicos, tecnológicos)."""
        if self.catalogo is None:
            return []
        evaluaciones = [e for a in auditorias for e in a.evaluaciones]
        controles = self.catalogo.obtener_varios(list({e.id_control for e in evaluaciones}))
        return [
            (
                cat,
                CalculadoraIndicadores.calcular(
                    [e for e in evaluaciones if e.id_control in controles and controles[e.id_control].categoria == cat]
                ),
            )
            for cat in CategoriaControl
        ]


__all__ = [
    "CrearAuditoria",
    "ActualizarAuditoria",
    "SeleccionarControles",
    "CambiarEstadoAuditoria",
    "EvaluarControl",
    "RegistrarEvidencia",
    "EliminarEvidencia",
    "ObtenerArchivoEvidencia",
    "RegistrarHallazgo",
    "AgregarRecomendacion",
    "ConsultarIndicadores",
    "GenerarInforme",
    "DescargarInformePDF",
    "ConsultarDashboard",
    "EliminarAuditoria",
    "EditarEvidencia",
    "EditarHallazgo",
    "EliminarHallazgo",
    "EditarRecomendacion",
    "EliminarRecomendacion",
    "GuardarControl",
    "EliminarControl",
    "DatosControl",
    "DatosAuditoria",
    "DatosEvidencia",
    "DatosHallazgo",
    "Prioridad",
    "Severidad",
]
