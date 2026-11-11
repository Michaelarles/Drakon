"""Casos de uso probados con adaptadores en memoria (sin Django ni base de datos)."""
from datetime import date

import pytest

from drakon.aplicacion.casos_uso import (
    CambiarEstadoAuditoria, ConsultarDashboard, CrearAuditoria, DatosAuditoria, DatosEvidencia,
    DatosHallazgo, DescargarInformePDF, EvaluarControl, GenerarInforme, RegistrarEvidencia,
    RegistrarHallazgo, SeleccionarControles,
)
from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.dominio.errores import DatoInvalido
from tests.fakes import (
    DATOS_ABC, EJEMPLO_ABC, AlmacenMemoria, PDFFalso, RepoAuditoriasMemoria, RepoCatalogoMemoria,
    RepoInformesMemoria, UsuariosMemoria,
)


@pytest.fixture
def ctx():
    return dict(aud=RepoAuditoriasMemoria(), cat=RepoCatalogoMemoria(), inf=RepoInformesMemoria(),
                alm=AlmacenMemoria())


def flujo_abc(ctx):
    a = CrearAuditoria(ctx["aud"]).ejecutar(DatosAuditoria(**DATOS_ABC), id_auditor=7)
    ids = [ctx["cat"].por_codigo(c).id for c, _ in EJEMPLO_ABC]
    SeleccionarControles(ctx["aud"], ctx["cat"]).ejecutar(a.id, ids)
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(a.id, "iniciar")
    for codigo, estado in EJEMPLO_ABC:
        idc = ctx["cat"].por_codigo(codigo).id
        EvaluarControl(ctx["aud"]).ejecutar(a.id, idc, estado, "Obs",
                                           "No desarrolla software" if estado == "NO_APLICABLE" else "")
        if estado in ("IMPLEMENTADO", "PARCIAL"):
            RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
                a.id, idc, DatosEvidencia("Soporte", "Documental", date(2026, 11, 10), referencia="DOC"))
    return a.id


def test_flujo_completo_y_informe(ctx):
    id_a = flujo_abc(ctx)
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(id_a, "revision")
    for codigo in ("8.8", "5.24", "8.13"):
        RegistrarHallazgo(ctx["aud"]).ejecutar(id_a, DatosHallazgo(
            ctx["cat"].por_codigo(codigo).id, "Cond", "Crit", "Causa", "Efecto", "ALTA", "Rec", "ALTA", 60))
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(id_a, "cerrar")

    informe = GenerarInforme(ctx["aud"], ctx["cat"], ctx["inf"], UsuariosMemoria()).ejecutar(id_a)
    assert informe.version == 1
    assert informe.contenido["indicadores"]["cumplimiento_base"] == 33.3
    assert informe.contenido["auditoria"]["auditor"] == "Auditor 7"
    assert len(informe.contenido["hallazgos"]) == 3
    assert informe.contenido["preliminar"] is False
    _, pdf = DescargarInformePDF(ctx["inf"], PDFFalso()).ejecutar(informe.id)
    assert pdf.startswith(b"%PDF")


def test_cp11_dashboard_coincide_con_informe(ctx):
    id_a = flujo_abc(ctx)
    informe = GenerarInforme(ctx["aud"], ctx["cat"], ctx["inf"], UsuariosMemoria()).ejecutar(id_a)
    dash = ConsultarDashboard(ctx["aud"]).ejecutar()
    assert dash.indicadores.cumplimiento_base == informe.contenido["indicadores"]["cumplimiento_base"]
    assert dash.por_estado["EN_EJECUCION"] == 1


def test_evidencia_con_archivo_invalido_no_se_guarda(ctx):
    id_a = flujo_abc(ctx)
    idc = ctx["cat"].por_codigo("5.1").id
    malo = ArchivoAdjunto("virus.exe", "application/x-msdownload", b"MZ")
    with pytest.raises(DatoInvalido):
        RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
            id_a, idc, DatosEvidencia("x", "y", date(2026, 11, 10), archivo=malo))
    antes = len(ctx["alm"].archivos)
    with pytest.raises(DatoInvalido):  # falta descripción: no debe dejar archivo huérfano
        RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
            id_a, idc, DatosEvidencia("", "y", date(2026, 11, 10),
                                      archivo=ArchivoAdjunto("a.pdf", "application/pdf", b"%PDF")))
    assert len(ctx["alm"].archivos) == antes


def test_evidencia_con_archivo_valido(ctx):
    id_a = flujo_abc(ctx)
    idc = ctx["cat"].por_codigo("5.1").id
    ev = RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
        id_a, idc, DatosEvidencia("Política v2", "Documental", date(2026, 11, 10),
                                  archivo=ArchivoAdjunto("politica.pdf", "application/pdf", b"%PDF-1.4")))
    assert ev.archivo_nombre == "politica.pdf"
    assert ctx["alm"].obtener(ev.archivo_id).contenido == b"%PDF-1.4"


def test_dashboard_por_categoria(ctx):
    flujo_abc(ctx)
    dash = ConsultarDashboard(ctx["aud"], ctx["cat"]).ejecutar()
    por_cat = {c.value: i for c, i in dash.por_categoria}
    assert por_cat["FISICO"].cumplimiento_base == 100.0       # 7.2 implementado
    assert por_cat["PERSONAS"].cumplimiento_base == 0.0       # 6.3 parcial
    assert por_cat["ORGANIZACIONAL"].cumplimiento_base == 50.0
    assert dash.activas == 1


def test_crud_catalogo(ctx):
    from drakon.aplicacion.casos_uso import DatosControl, EliminarControl, GuardarControl
    from drakon.dominio.errores import ReglaDeNegocioViolada
    nuevo = GuardarControl(ctx["cat"]).ejecutar(DatosControl("9.1", "Control propio", "TECNOLOGICO", "Criterio"))
    assert ctx["cat"].obtener(nuevo.id).nombre == "Control propio"
    with pytest.raises(ReglaDeNegocioViolada, match="Ya existe"):
        GuardarControl(ctx["cat"]).ejecutar(DatosControl("5.1", "Duplicado", "TECNOLOGICO", "x"))
    GuardarControl(ctx["cat"]).ejecutar(DatosControl("9.1", "Renombrado", "TECNOLOGICO", "Criterio"), nuevo.id)
    assert ctx["cat"].obtener(nuevo.id).nombre == "Renombrado"
    ctx["cat"].usados = {ctx["cat"].por_codigo("5.1").id}
    with pytest.raises(ReglaDeNegocioViolada, match="no se puede eliminar"):
        EliminarControl(ctx["cat"]).ejecutar(ctx["cat"].por_codigo("5.1").id)
    EliminarControl(ctx["cat"]).ejecutar(nuevo.id)
    assert nuevo.id not in ctx["cat"].obtener_varios([nuevo.id])


def test_eliminar_auditoria_borra_archivos(ctx):
    from drakon.aplicacion.casos_uso import EliminarAuditoria
    id_a = flujo_abc(ctx)
    idc = ctx["cat"].por_codigo("5.1").id
    RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(id_a, idc, DatosEvidencia(
        "Política", "Documental", date(2026, 11, 10), archivo=ArchivoAdjunto("p.pdf", "application/pdf", b"%PDF-1")))
    assert ctx["alm"].archivos
    EliminarAuditoria(ctx["aud"], ctx["alm"]).ejecutar(id_a)
    assert not ctx["alm"].archivos and ctx["aud"].listar() == []
