"""Casos de uso probados con adaptadores en memoria (sin Django ni base de datos)."""

import io
import zipfile
from datetime import date

import pytest

from drakon.aplicacion.casos_uso import (
    TIPO_DOCX,
    CambiarEstadoAuditoria,
    ConsultarDashboard,
    CrearAuditoria,
    DatosAuditoria,
    DatosEvidencia,
    DatosHallazgo,
    DescargarInformePDF,
    DesvincularEvidenciaHallazgo,
    EvaluarControl,
    GenerarInforme,
    RegistrarEvidencia,
    RegistrarEvidenciaHallazgo,
    RegistrarHallazgo,
    SeleccionarControles,
    VincularEvidenciaHallazgo,
)
from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.dominio.errores import DatoInvalido
from tests.fakes import (
    DATOS_ABC,
    EJEMPLO_ABC,
    AlmacenMemoria,
    PDFFalso,
    RepoAuditoriasMemoria,
    RepoCatalogoMemoria,
    RepoInformesMemoria,
    UsuariosMemoria,
)


@pytest.fixture
def ctx():
    return dict(aud=RepoAuditoriasMemoria(), cat=RepoCatalogoMemoria(), inf=RepoInformesMemoria(), alm=AlmacenMemoria())


def flujo_abc(ctx):
    a = CrearAuditoria(ctx["aud"]).ejecutar(DatosAuditoria(**DATOS_ABC), id_auditor=7)
    ids = [ctx["cat"].por_codigo(c).id for c, _ in EJEMPLO_ABC]
    SeleccionarControles(ctx["aud"], ctx["cat"]).ejecutar(a.id, ids)
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(a.id, "iniciar")
    for codigo, estado in EJEMPLO_ABC:
        idc = ctx["cat"].por_codigo(codigo).id
        EvaluarControl(ctx["aud"]).ejecutar(
            a.id, idc, estado, "Obs", "No desarrolla software" if estado == "NO_APLICABLE" else ""
        )
        if estado in ("IMPLEMENTADO", "PARCIAL"):
            RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
                a.id, idc, DatosEvidencia("Soporte", "Documental", date(2026, 11, 10), referencia="DOC")
            )
    return a.id


def test_flujo_completo_y_informe(ctx):
    id_a = flujo_abc(ctx)
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(id_a, "revision")
    for codigo in ("8.8", "5.24", "8.13"):
        h = RegistrarHallazgo(ctx["aud"]).ejecutar(
            id_a,
            DatosHallazgo(
                ctx["cat"].por_codigo(codigo).id, "Cond", "Crit", "Causa", "Efecto", "ALTA", "Rec", "ALTA", 60
            ),
        )
        RegistrarEvidenciaHallazgo(ctx["aud"], ctx["alm"]).ejecutar(
            id_a, h.codigo, DatosEvidencia("Acta", "Entrevista", date(2026, 11, 13), referencia="ACTA")
        )
    CambiarEstadoAuditoria(ctx["aud"]).ejecutar(id_a, "cerrar")

    informe = GenerarInforme(ctx["aud"], ctx["cat"], ctx["inf"], UsuariosMemoria()).ejecutar(id_a)
    assert informe.version == 1
    assert informe.contenido["indicadores"]["cumplimiento_base"] == 33.3
    assert informe.contenido["auditoria"]["auditor"] == "Auditor 7"
    assert len(informe.contenido["hallazgos"]) == 3
    assert [e["descripcion"] for e in informe.contenido["hallazgos"][0]["evidencias"]] == ["Acta"]
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
            id_a, idc, DatosEvidencia("x", "y", date(2026, 11, 10), archivo=malo)
        )
    antes = len(ctx["alm"].archivos)
    with pytest.raises(DatoInvalido):  # falta descripción: no debe dejar archivo huérfano
        RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
            id_a,
            idc,
            DatosEvidencia("", "y", date(2026, 11, 10), archivo=ArchivoAdjunto("a.pdf", "application/pdf", b"%PDF")),
        )
    assert len(ctx["alm"].archivos) == antes


def test_evidencia_con_archivo_valido(ctx):
    id_a = flujo_abc(ctx)
    idc = ctx["cat"].por_codigo("5.1").id
    ev = RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
        id_a,
        idc,
        DatosEvidencia(
            "Política v2",
            "Documental",
            date(2026, 11, 10),
            archivo=ArchivoAdjunto("politica.pdf", "application/pdf", b"%PDF-1.4"),
        ),
    )
    assert ev.archivo_nombre == "politica.pdf"
    assert ctx["alm"].obtener(ev.archivo_id).contenido == b"%PDF-1.4"


def test_dashboard_por_categoria(ctx):
    flujo_abc(ctx)
    dash = ConsultarDashboard(ctx["aud"], ctx["cat"]).ejecutar()
    por_cat = {c.value: i for c, i in dash.por_categoria}
    assert por_cat["FISICO"].cumplimiento_base == 100.0  # 7.2 implementado
    assert por_cat["PERSONAS"].cumplimiento_base == 0.0  # 6.3 parcial
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
    RegistrarEvidencia(ctx["aud"], ctx["alm"]).ejecutar(
        id_a,
        idc,
        DatosEvidencia(
            "Política", "Documental", date(2026, 11, 10), archivo=ArchivoAdjunto("p.pdf", "application/pdf", b"%PDF-1")
        ),
    )
    assert ctx["alm"].archivos
    EliminarAuditoria(ctx["aud"], ctx["alm"]).ejecutar(id_a)
    assert not ctx["alm"].archivos and ctx["aud"].listar() == []


# ------------------------------------------- evidencias que respaldan hallazgos
def docx_minimo() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def con_hallazgo(ctx):
    id_a = flujo_abc(ctx)
    RegistrarHallazgo(ctx["aud"]).ejecutar(
        id_a, DatosHallazgo(ctx["cat"].por_codigo("8.8").id, "Cond", "Crit", "Causa", "Efecto", "ALTA")
    )
    return id_a


@pytest.mark.parametrize(
    "archivo",
    [
        ArchivoAdjunto("acta.docx", TIPO_DOCX, docx_minimo()),
        ArchivoAdjunto("captura.png", "image/png", b"\x89PNG\r\n\x1a\n"),
        ArchivoAdjunto("informe.pdf", "application/pdf", b"%PDF-1.7"),
    ],
)
def test_hallazgo_acepta_word_imagen_y_pdf(ctx, archivo):
    id_a = con_hallazgo(ctx)
    ev = RegistrarEvidenciaHallazgo(ctx["aud"], ctx["alm"]).ejecutar(
        id_a, "H-01", DatosEvidencia("Soporte", "Documental", date(2026, 11, 13), archivo=archivo)
    )
    a = ctx["aud"].obtener(id_a)
    assert a.hallazgo("H-01").codigos_evidencia == [ev.codigo]
    assert ctx["alm"].obtener(ev.archivo_id).contenido == archivo.contenido


@pytest.mark.parametrize(
    "archivo",
    [
        ArchivoAdjunto("falso.docx", TIPO_DOCX, b"PK\x03\x04 no es un zip"),
        ArchivoAdjunto("vacio.docx", TIPO_DOCX, b""),
        ArchivoAdjunto("hoja.xlsx", "application/vnd.ms-excel", b"PK\x03\x04"),
        ArchivoAdjunto("grande.pdf", "application/pdf", b"%PDF" + b"0" * (5 * 1024 * 1024)),
    ],
)
def test_hallazgo_rechaza_archivos_invalidos_sin_dejar_huerfanos(ctx, archivo):
    id_a = con_hallazgo(ctx)
    with pytest.raises(DatoInvalido):
        RegistrarEvidenciaHallazgo(ctx["aud"], ctx["alm"]).ejecutar(
            id_a, "H-01", DatosEvidencia("Soporte", "Documental", date(2026, 11, 13), archivo=archivo)
        )
    assert ctx["alm"].archivos == {} and ctx["aud"].obtener(id_a).hallazgo("H-01").codigos_evidencia == []


def test_docx_sin_documento_de_word_se_rechaza(ctx):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("otro.txt", "hola")
    id_a = con_hallazgo(ctx)
    with pytest.raises(DatoInvalido, match="no corresponde"):
        RegistrarEvidenciaHallazgo(ctx["aud"], ctx["alm"]).ejecutar(
            id_a,
            "H-01",
            DatosEvidencia(
                "Soporte", "Documental", date(2026, 11, 13), archivo=ArchivoAdjunto("x.docx", TIPO_DOCX, buf.getvalue())
            ),
        )


def test_vincular_y_desvincular_evidencia_existente(ctx):
    id_a = con_hallazgo(ctx)
    VincularEvidenciaHallazgo(ctx["aud"]).ejecutar(id_a, "H-01", "EV-01")
    assert ctx["aud"].obtener(id_a).hallazgo("H-01").codigos_evidencia == ["EV-01"]
    DesvincularEvidenciaHallazgo(ctx["aud"]).ejecutar(id_a, "H-01", "EV-01")
    assert ctx["aud"].obtener(id_a).hallazgo("H-01").codigos_evidencia == []
