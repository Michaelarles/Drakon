"""Inyección de dependencias: conecta cada puerto con su adaptador.

Es el único lugar donde se decide qué implementación usa cada caso de uso.
Para cambiar el almacenamiento de evidencias o el generador de PDF, se cambia aquí.
"""

from functools import cache

from drakon.aplicacion import casos_uso as cu
from drakon.infraestructura.evidencias.almacen_bd import AlmacenEvidenciasBD
from drakon.infraestructura.pdf.generador import GeneradorPDFXhtml2pdf
from drakon.infraestructura.persistencia.repositorios import (
    DirectorioUsuariosDjango,
    RepositorioAuditoriasDjango,
    RepositorioCatalogoDjango,
    RepositorioInformesDjango,
)


@cache
def auditorias():
    return RepositorioAuditoriasDjango()


@cache
def catalogo():
    return RepositorioCatalogoDjango()


@cache
def informes():
    return RepositorioInformesDjango()


@cache
def almacen():
    return AlmacenEvidenciasBD()


@cache
def pdf():
    return GeneradorPDFXhtml2pdf()


def crear_auditoria():
    return cu.CrearAuditoria(auditorias())


def actualizar_auditoria():
    return cu.ActualizarAuditoria(auditorias())


def seleccionar_controles():
    return cu.SeleccionarControles(auditorias(), catalogo())


def cambiar_estado():
    return cu.CambiarEstadoAuditoria(auditorias())


def evaluar_control():
    return cu.EvaluarControl(auditorias())


def registrar_evidencia():
    return cu.RegistrarEvidencia(auditorias(), almacen())


def eliminar_evidencia():
    return cu.EliminarEvidencia(auditorias(), almacen())


def archivo_evidencia():
    return cu.ObtenerArchivoEvidencia(auditorias(), almacen())


def registrar_hallazgo():
    return cu.RegistrarHallazgo(auditorias())


def agregar_recomendacion():
    return cu.AgregarRecomendacion(auditorias())


def consultar_indicadores():
    return cu.ConsultarIndicadores(auditorias())


def generar_informe():
    return cu.GenerarInforme(auditorias(), catalogo(), informes(), DirectorioUsuariosDjango())


def descargar_informe_pdf():
    return cu.DescargarInformePDF(informes(), pdf())


def consultar_dashboard():
    return cu.ConsultarDashboard(auditorias(), catalogo())


def eliminar_auditoria():
    return cu.EliminarAuditoria(auditorias(), almacen())


def editar_evidencia():
    return cu.EditarEvidencia(auditorias())


def editar_hallazgo():
    return cu.EditarHallazgo(auditorias())


def eliminar_hallazgo():
    return cu.EliminarHallazgo(auditorias())


def editar_recomendacion():
    return cu.EditarRecomendacion(auditorias())


def eliminar_recomendacion():
    return cu.EliminarRecomendacion(auditorias())


def guardar_control():
    return cu.GuardarControl(catalogo())


def eliminar_control():
    return cu.EliminarControl(catalogo())
