"""Flujo completo por HTTP: evaluación, evidencias, hallazgos y recomendaciones (CP-04 a CP-08)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from drakon.infraestructura.persistencia.models import (
    ArchivoEvidenciaModel, AuditoriaModel, ControlModel, EvaluacionControlModel, HallazgoModel,
)

pytestmark = pytest.mark.django_db
CODIGOS = ["5.1", "5.15", "5.18", "5.24", "6.3", "7.2", "8.5", "8.7", "8.8", "8.13", "8.15", "8.23", "8.31"]


@pytest.fixture
def auditoria(client):
    call_command("inicializar", verbosity=0)
    u = get_user_model().objects.create_user("ana", password="Clave-segura-1", first_name="Ana")
    client.force_login(u)
    client.post(reverse("auditoria_crear"), {"organizacion": "Empresa ABC", "objetivo": "Evaluar", "alcance": "TI",
                                             "fecha_inicio": "2026-11-09", "fecha_fin": "2026-11-20"})
    a = AuditoriaModel.objects.get()
    ids = [ControlModel.objects.get(codigo_iso=c).id for c in CODIGOS]
    client.post(reverse("controles_seleccion", args=[a.id]), {"controles": ids})
    client.post(reverse("auditoria_estado", args=[a.id]), {"accion": "iniciar"})
    return a, {c: i for c, i in zip(CODIGOS, ids)}


def evaluar(client, a, idc, estado, obs="Observación", na=""):
    return client.post(reverse("evaluar_control", args=[a.id, idc]),
                       {"estado": estado, "observacion": obs, "justificacion_na": na, "ir": "siguiente"}, follow=True)


def test_evaluar_inicio_lleva_al_primer_pendiente(client, auditoria):
    a, ids = auditoria
    r = client.get(reverse("evaluar_inicio", args=[a.id]))
    assert r.status_code == 302 and r["Location"].endswith(f"/evaluar/{ids['5.1']}/")
    pagina = client.get(r["Location"]).content.decode()
    assert "Políticas para la seguridad de la información" in pagina and "0 de 13 evaluados" in pagina


def test_cp04_evaluar_sin_observacion(client, auditoria):
    a, ids = auditoria
    r = evaluar(client, a, ids["5.18"], "PARCIAL", obs="")
    assert "obligatorio" in r.content.decode()
    assert EvaluacionControlModel.objects.get(auditoria=a, control_id=ids["5.18"]).estado == "PENDIENTE"


def test_cp05_no_aplicable_sin_justificacion(client, auditoria):
    a, ids = auditoria
    r = evaluar(client, a, ids["8.31"], "NO_APLICABLE")
    assert "exige justificación" in r.content.decode()
    evaluar(client, a, ids["8.31"], "NO_APLICABLE", na="No desarrolla software propio")
    assert EvaluacionControlModel.objects.get(auditoria=a, control_id=ids["8.31"]).estado == "NO_APLICABLE"


def test_cp06_implementado_sin_evidencia_avisa_y_bloquea_revision(client, auditoria):
    a, ids = auditoria
    r = evaluar(client, a, ids["5.1"], "IMPLEMENTADO")
    assert "Recuerde adjuntar al menos una evidencia" in r.content.decode()
    for c in CODIGOS[1:]:
        evaluar(client, a, ids[c], "NO_IMPLEMENTADO" if c != "8.31" else "NO_APLICABLE", na="N/A")
    r = client.post(reverse("auditoria_estado", args=[a.id]), {"accion": "revision"}, follow=True)
    assert "no tiene evidencias" in r.content.decode()


def test_evidencia_con_referencia_y_con_archivo(client, auditoria):
    a, ids = auditoria
    url = reverse("evidencia_agregar", args=[a.id, ids["5.1"]])
    r = client.post(url, {"descripcion": "Política v2", "fuente": "Documental", "fecha": "2026-11-12",
                          "referencia": "DOC-01", "es_simulada": "on"}, follow=True)
    assert "Evidencia EV-01 registrada" in r.content.decode()
    pdf = SimpleUploadedFile("politica.pdf", b"%PDF-1.4 contenido", content_type="application/pdf")
    r = client.post(url, {"descripcion": "Acta", "fuente": "Documental", "fecha": "2026-11-12", "archivo": pdf}, follow=True)
    assert "Evidencia EV-02 registrada" in r.content.decode()
    descarga = client.get(reverse("evidencia_archivo", args=[a.id, "EV-02"]))
    assert descarga.content == b"%PDF-1.4 contenido" and descarga["Content-Type"] == "application/pdf"


def test_evidencia_rechaza_archivo_disfrazado(client, auditoria):
    a, ids = auditoria
    falso = SimpleUploadedFile("malware.pdf", b"MZ\x90\x00 ejecutable", content_type="application/pdf")
    r = client.post(reverse("evidencia_agregar", args=[a.id, ids["5.1"]]),
                    {"descripcion": "x", "fuente": "Documental", "fecha": "2026-11-12", "archivo": falso})
    assert "no corresponde a un PDF" in r.content.decode()
    assert ArchivoEvidenciaModel.objects.count() == 0


def test_evidencia_sin_archivo_ni_referencia(client, auditoria):
    a, ids = auditoria
    r = client.post(reverse("evidencia_agregar", args=[a.id, ids["5.1"]]),
                    {"descripcion": "x", "fuente": "Documental", "fecha": "2026-11-12"})
    assert "Adjunte un archivo o indique una referencia" in r.content.decode()


def test_eliminar_evidencia(client, auditoria):
    a, ids = auditoria
    client.post(reverse("evidencia_agregar", args=[a.id, ids["5.1"]]),
                {"descripcion": "x", "fuente": "Documental", "fecha": "2026-11-12", "referencia": "R"})
    r = client.post(reverse("evidencia_eliminar", args=[a.id, "EV-01"]), {"id_control": ids["5.1"]}, follow=True)
    assert "Evidencia EV-01 eliminada" in r.content.decode()


def test_cp07_cp08_hallazgos_recomendaciones_y_cierre(client, auditoria):
    a, ids = auditoria
    for c in CODIGOS:
        estado = {"5.1": "IMPLEMENTADO", "8.31": "NO_APLICABLE"}.get(c, "NO_IMPLEMENTADO")
        evaluar(client, a, ids[c], estado, na="No aplica")
    client.post(reverse("evidencia_agregar", args=[a.id, ids["5.1"]]),
                {"descripcion": "Política", "fuente": "Documental", "fecha": "2026-11-12", "referencia": "DOC"})
    client.post(reverse("auditoria_estado", args=[a.id]), {"accion": "revision"})

    # El formulario prellena el criterio desde el catálogo
    pagina = client.get(reverse("hallazgo_nuevo", args=[a.id]) + f"?control={ids['8.8']}").content.decode()
    assert "ISO/IEC 27002:2022, control 8.8" in pagina

    base = {"severidad": "ALTA", "condicion": "Sin escaneos", "criterio": "ISO 27002 8.8", "efecto": "Explotación"}
    r = client.post(reverse("hallazgo_nuevo", args=[a.id]), dict(base, id_control=ids["8.8"], causa=""))
    assert "obligatorio" in r.content.decode() and HallazgoModel.objects.count() == 0      # CP-07

    for c in ("8.8", "5.24"):
        client.post(reverse("hallazgo_nuevo", args=[a.id]), dict(
            base, id_control=ids[c], causa="Sin responsable", recomendacion="Designar responsable",
            prioridad="ALTA", plazo_dias=60))
    client.post(reverse("hallazgo_nuevo", args=[a.id]), dict(base, id_control=ids["8.13"], causa="Sin procedimiento"))
    assert list(HallazgoModel.objects.values_list("codigo", flat=True)) == ["H-01", "H-02", "H-03"]

    r = client.post(reverse("auditoria_estado", args=[a.id]), {"accion": "cerrar"}, follow=True)
    assert "H-03 no tiene recomendación" in r.content.decode()                              # CP-08
    client.post(reverse("recomendacion_agregar", args=[a.id, "H-03"]),
                {"recomendacion": "Pruebas trimestrales", "prioridad": "MEDIA", "plazo_dias": 90})
    client.post(reverse("auditoria_estado", args=[a.id]), {"accion": "cerrar"})
    a.refresh_from_db()
    assert a.estado == "CERRADA"
    pagina = client.get(reverse("hallazgos", args=[a.id])).content.decode()
    assert "Nuevo hallazgo" not in pagina and "R-03" in pagina                              # solo lectura


def test_hallazgo_no_permite_controles_no_aplicables(client, auditoria):
    a, ids = auditoria
    evaluar(client, a, ids["8.31"], "NO_APLICABLE", na="No aplica")
    pagina = client.get(reverse("hallazgo_nuevo", args=[a.id])).content.decode()
    assert "Primero evalúa los controles" in pagina
