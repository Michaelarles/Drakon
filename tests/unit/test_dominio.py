"""Pruebas del dominio puro (sin base de datos). Referencias a los casos CP del plan de pruebas."""

from datetime import date

import pytest

from drakon.dominio.auditoria import Auditoria
from drakon.dominio.errores import DatoInvalido, ReglaDeNegocioViolada
from drakon.dominio.indicadores import CalculadoraIndicadores
from drakon.dominio.valores import EstadoAuditoria, EstadoEvaluacion
from tests.fakes import DATOS_ABC, EJEMPLO_ABC, RepoCatalogoMemoria

CAT = RepoCatalogoMemoria()


def nueva(**cambios):
    datos = dict(DATOS_ABC, **cambios)
    return Auditoria.crear(id_auditor=1, **datos)


def en_ejecucion(n=13):
    a = nueva()
    a.seleccionar_controles([CAT.por_codigo(c) for c, _ in EJEMPLO_ABC[:n]])
    a.iniciar_ejecucion()
    return a


def evaluada_abc():
    a = en_ejecucion()
    for codigo, estado in EJEMPLO_ABC:
        c = CAT.por_codigo(codigo)
        a.evaluar_control(
            c.id,
            estado,
            f"Observación {codigo}",
            "Adquiere soluciones como servicio." if estado == "NO_APLICABLE" else "",
        )
        if EstadoEvaluacion(estado).exige_evidencia:
            a.registrar_evidencia(c.id, "Soporte", "Documental", date(2026, 11, 10), referencia="DOC-1")
    return a


# ---------------------------------------------------------------- CP-01/02
def test_cp01_crea_auditoria_en_borrador():
    a = nueva()
    assert a.estado == EstadoAuditoria.BORRADOR
    assert a.organizacion == "Empresa ABC (ficticia)"


def test_cp02_auditoria_sin_fecha_de_cierre():
    with pytest.raises(DatoInvalido) as e:
        nueva(fecha_fin=None)
    assert e.value.campo == "fecha_fin"


def test_fecha_fin_anterior_a_inicio():
    with pytest.raises(DatoInvalido) as e:
        nueva(fecha_fin=date(2026, 11, 1))
    assert e.value.campo == "fecha_fin"


@pytest.mark.parametrize("campo", ["organizacion", "objetivo", "alcance"])
def test_campos_obligatorios(campo):
    with pytest.raises(DatoInvalido) as e:
        nueva(**{campo: "   "})
    assert e.value.campo == campo


# ------------------------------------------------------------------- CP-03
@pytest.mark.parametrize("n", [9])
def test_cp03_menos_de_10_controles_bloquea_ejecucion(n):
    a = nueva()
    a.seleccionar_controles([CAT.por_codigo(c) for c, _ in EJEMPLO_ABC[:n]])
    with pytest.raises(ReglaDeNegocioViolada, match="entre 10 y 15"):
        a.iniciar_ejecucion()


def test_cp03_mas_de_15_controles_se_rechaza():
    a = nueva()
    with pytest.raises(ReglaDeNegocioViolada, match="máximo"):
        a.seleccionar_controles(CAT.listar()[:16])


def test_seleccion_ordena_por_codigo_y_conserva_evaluaciones():
    a = nueva()
    a.seleccionar_controles([CAT.por_codigo("8.13"), CAT.por_codigo("5.2"), CAT.por_codigo("5.10")])
    assert [e.codigo_control for e in a.evaluaciones] == ["5.2", "5.10", "8.13"]


# ------------------------------------------------------------------- CP-04
def test_cp04_evaluar_sin_observacion():
    a = en_ejecucion()
    with pytest.raises(DatoInvalido) as e:
        a.evaluar_control(CAT.por_codigo("5.18").id, "PARCIAL", "")
    assert e.value.campo == "observacion"


# ------------------------------------------------------------------- CP-05
def test_cp05_no_aplicable_exige_justificacion():
    a = en_ejecucion()
    c = CAT.por_codigo("8.31")
    with pytest.raises(DatoInvalido) as e:
        a.evaluar_control(c.id, "NO_APLICABLE", "No desarrolla software")
    assert e.value.campo == "justificacion_na"
    a.evaluar_control(c.id, "NO_APLICABLE", "No desarrolla software", "Adquiere SaaS")
    assert a.evaluacion(c.id).estado == EstadoEvaluacion.NO_APLICABLE


# ------------------------------------------------------------------- CP-06
def test_cp06_implementado_sin_evidencia_bloquea_revision():
    a = evaluada_abc()
    c = CAT.por_codigo("5.1")
    a.evaluacion(c.id).evidencias.clear()
    with pytest.raises(ReglaDeNegocioViolada, match="5.1"):
        a.enviar_a_revision()


def test_evidencia_requiere_archivo_o_referencia():
    a = en_ejecucion()
    with pytest.raises(DatoInvalido) as e:
        a.registrar_evidencia(CAT.por_codigo("5.1").id, "Política", "Documental", date(2026, 11, 10))
    assert e.value.campo == "referencia"


def test_codigos_de_evidencia_consecutivos():
    a = evaluada_abc()
    assert [e.codigo for e in a.todas_las_evidencias][:3] == ["EV-01", "EV-02", "EV-03"]


# ------------------------------------------------------------------- CP-07
def test_cp07_hallazgo_sin_causa_y_codigo_automatico():
    a = evaluada_abc()
    c = CAT.por_codigo("8.8")
    with pytest.raises(DatoInvalido) as e:
        a.registrar_hallazgo(c.id, "Sin escaneos", "ISO 27002 8.8", "", "Explotación", "ALTA")
    assert e.value.campo == "causa"
    h = a.registrar_hallazgo(c.id, "Sin escaneos", "ISO 27002 8.8", "Sin responsable", "Explotación", "ALTA")
    assert h.codigo == "H-01"


def test_no_hay_hallazgos_sobre_no_aplicables():
    a = evaluada_abc()
    with pytest.raises(ReglaDeNegocioViolada):
        a.registrar_hallazgo(CAT.por_codigo("8.31").id, "x", "x", "x", "x", "BAJA")


# ------------------------------------------------------------------- CP-08
def test_cp08_cierre_exige_tres_hallazgos_con_recomendacion():
    a = evaluada_abc()
    a.enviar_a_revision()
    for codigo in ("8.8", "5.24"):
        a.registrar_hallazgo(CAT.por_codigo(codigo).id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    with pytest.raises(ReglaDeNegocioViolada, match="al menos 3"):
        a.cerrar()
    a.registrar_hallazgo(CAT.por_codigo("8.13").id, "c", "cr", "ca", "ef", "MEDIA")  # sin recomendación
    with pytest.raises(ReglaDeNegocioViolada, match="H-03"):
        a.cerrar()
    a.agregar_recomendacion("H-03", "Pruebas trimestrales", "MEDIA", 90)
    a.cerrar()
    assert a.estado == EstadoAuditoria.CERRADA


def test_cp13_auditoria_cerrada_es_de_solo_lectura():
    a = evaluada_abc()
    a.enviar_a_revision()
    for codigo in ("8.8", "5.24", "8.13"):
        a.registrar_hallazgo(CAT.por_codigo(codigo).id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    a.cerrar()
    with pytest.raises(ReglaDeNegocioViolada, match="cerrada"):
        a.registrar_hallazgo(CAT.por_codigo("8.15").id, "c", "cr", "ca", "ef", "MEDIA")


# ------------------------------------------------------------------- CP-09
def test_cp09_indicadores_ejemplo_abc():
    ind = CalculadoraIndicadores.de_auditoria(evaluada_abc())
    assert (ind.implementados, ind.parciales, ind.no_implementados, ind.no_aplicables) == (4, 5, 3, 1)
    assert ind.aplicables == 12
    assert ind.cumplimiento_base == 33.3
    assert ind.indice_ponderado == 54.2


def test_indicador_sin_aplicables_es_sin_datos():
    ind = CalculadoraIndicadores.de_auditoria(en_ejecucion())
    assert ind.cumplimiento_base is None and ind.pendientes == 13


# ------------------------------------------------- CRUD: editar y eliminar
def test_editar_hallazgo_conserva_codigo_y_recomendaciones():
    a = evaluada_abc()
    h = a.registrar_hallazgo(CAT.por_codigo("8.8").id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    a.editar_hallazgo("H-01", CAT.por_codigo("8.15").id, "Nueva condición", "cr", "ca", "ef", "MEDIA")
    assert (h.codigo, h.condicion, h.severidad.value, len(h.recomendaciones)) == ("H-01", "Nueva condición", "MEDIA", 1)
    with pytest.raises(ReglaDeNegocioViolada):
        a.editar_hallazgo("H-01", CAT.por_codigo("8.31").id, "c", "cr", "ca", "ef", "MEDIA")  # no aplicable
    with pytest.raises(DatoInvalido):
        a.editar_hallazgo("H-01", CAT.por_codigo("8.8").id, "c", "", "ca", "ef", "MEDIA")


def test_eliminar_hallazgo_y_recomendacion():
    a = evaluada_abc()
    a.registrar_hallazgo(CAT.por_codigo("8.8").id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    a.registrar_hallazgo(CAT.por_codigo("5.24").id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    a.editar_recomendacion("R-02", "Otra", "BAJA", 30)
    assert a.recomendacion("R-02")[1].plazo_dias == 30
    a.eliminar_recomendacion("R-02")
    assert a.hallazgo("H-02").recomendaciones == []
    a.eliminar_hallazgo("H-01")
    assert [h.codigo for h in a.hallazgos] == ["H-02"]


def test_editar_evidencia_y_registrar_hallazgo_invalido_no_deja_rastro():
    a = evaluada_abc()
    a.editar_evidencia("EV-01", "Política firmada", "Documental", date(2026, 11, 13), False, "DOC-9")
    assert a.evidencia("EV-01").referencia == "DOC-9" and a.evidencia("EV-01").es_simulada is False
    with pytest.raises(DatoInvalido):
        a.registrar_hallazgo(CAT.por_codigo("8.8").id, "c", "cr", "ca", "ef", "ALTA", "Rec", None, 60)
    assert a.hallazgos == []  # la recomendación inválida no deja un hallazgo a medias


def test_auditoria_cerrada_no_se_elimina():
    a = evaluada_abc()
    a.enviar_a_revision()
    for codigo in ("8.8", "5.24", "8.13"):
        a.registrar_hallazgo(CAT.por_codigo(codigo).id, "c", "cr", "ca", "ef", "ALTA", "Rec", "ALTA", 60)
    a.verificar_eliminable()
    a.cerrar()
    with pytest.raises(ReglaDeNegocioViolada, match="cerrada"):
        a.verificar_eliminable()
