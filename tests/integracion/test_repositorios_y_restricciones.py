"""Repositorios ORM y restricciones de la base de datos (criterio «Arquitectura y datos»)."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction

from drakon.aplicacion.casos_uso import DatosAuditoria, DatosEvidencia, DatosHallazgo
from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.infraestructura import contenedor as c
from drakon.infraestructura.persistencia.models import (
    AuditoriaModel, ControlModel, EvaluacionControlModel, HallazgoModel,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    call_command("inicializar", verbosity=0)
    return get_user_model().objects.create_user("auditor", password="Clave-segura-1")


def test_catalogo_cargado_con_93_controles(usuario):
    assert ControlModel.objects.count() == 93
    assert len(c.catalogo().listar("PERSONAS")) == 8


def test_cp12_persistencia_del_agregado_completo(usuario):
    call_command("cargar_empresa_abc", usuario="auditor", verbosity=0)
    a = c.auditorias().listar()[0]
    recargada = c.auditorias().obtener(a.id)
    assert len(recargada.evaluaciones) == 13
    assert [h.codigo for h in recargada.hallazgos] == ["H-01", "H-02", "H-03", "H-04"]
    assert all(h.recomendaciones for h in recargada.hallazgos)
    assert len(recargada.todas_las_evidencias) == 12
    ind = c.consultar_indicadores().ejecutar(a.id)
    assert (ind.cumplimiento_base, ind.indice_ponderado) == (33.3, 54.2)


def test_reseleccion_elimina_evaluaciones_retiradas(usuario):
    a = c.crear_auditoria().ejecutar(DatosAuditoria("Org", "Obj", "Alc", date(2026, 1, 1), date(2026, 1, 2)), usuario.id)
    ids = list(ControlModel.objects.values_list("id", flat=True)[:12])
    c.seleccionar_controles().ejecutar(a.id, ids)
    c.seleccionar_controles().ejecutar(a.id, ids[:10])
    assert EvaluacionControlModel.objects.filter(auditoria_id=a.id).count() == 10


def test_evidencia_con_archivo_se_guarda_en_bd(usuario):
    call_command("cargar_empresa_abc", usuario="auditor", verbosity=0)
    a = c.auditorias().listar()[0]
    c.cambiar_estado().ejecutar(a.id, "devolver")
    idc = ControlModel.objects.get(codigo_iso="5.1").id
    ev = c.registrar_evidencia().ejecutar(a.id, idc, DatosEvidencia(
        "Política firmada", "Documental", date(2026, 11, 12),
        archivo=ArchivoAdjunto("politica.pdf", "application/pdf", b"%PDF-1.4 prueba")))
    archivo = c.archivo_evidencia().ejecutar(a.id, ev.codigo)
    assert archivo.contenido == b"%PDF-1.4 prueba"


def test_informe_pdf_real(usuario):
    call_command("cargar_empresa_abc", usuario="auditor", cerrar=True, verbosity=0)
    a = c.auditorias().listar()[0]
    informe = c.informes().listar(a.id)[0]
    _, pdf = c.descargar_informe_pdf().ejecutar(informe.id)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


# ---------------- La base de datos rechaza datos inválidos aunque se salte el dominio
def _auditoria(usuario, **kw):
    datos = dict(organizacion="Org", objetivo="Obj", alcance="Alc", fecha_inicio=date(2026, 1, 10),
                 fecha_fin=date(2026, 1, 20), auditor=usuario)
    datos.update(kw)
    return AuditoriaModel.objects.create(**datos)


def test_check_fechas(usuario):
    with pytest.raises(IntegrityError), transaction.atomic():
        _auditoria(usuario, fecha_fin=date(2026, 1, 1))


def test_check_estado_auditoria(usuario):
    with pytest.raises(IntegrityError), transaction.atomic():
        _auditoria(usuario, estado="APROBADA")


def test_check_na_exige_justificacion_y_unique(usuario):
    a = _auditoria(usuario)
    ctrl = ControlModel.objects.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        EvaluacionControlModel.objects.create(auditoria=a, control=ctrl, estado="NO_APLICABLE", observacion="x")
    EvaluacionControlModel.objects.create(auditoria=a, control=ctrl)
    with pytest.raises(IntegrityError), transaction.atomic():
        EvaluacionControlModel.objects.create(auditoria=a, control=ctrl)


def test_check_hallazgo_completo(usuario):
    a = _auditoria(usuario)
    ev = EvaluacionControlModel.objects.create(auditoria=a, control=ControlModel.objects.first(),
                                               estado="NO_IMPLEMENTADO", observacion="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        HallazgoModel.objects.create(auditoria=a, evaluacion=ev, codigo="H-01", condicion="c", criterio="c",
                                     causa="", efecto_riesgo="e", severidad="ALTA")


def test_inicializar_carga_demo_solo_si_esta_vacia(monkeypatch):
    monkeypatch.setenv("DEMO_USUARIO", "demo")
    monkeypatch.setenv("DEMO_CLAVE", "Clave-segura-9")
    call_command("inicializar", verbosity=0)
    call_command("inicializar", verbosity=0)          # idempotente: no duplica
    assert AuditoriaModel.objects.count() == 1
