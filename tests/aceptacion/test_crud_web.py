"""CRUD completo por HTTP: crear, consultar, editar y eliminar cada entidad, con sus reglas."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from drakon.infraestructura.persistencia.models import (
    AuditoriaModel, ControlModel, EvidenciaModel, HallazgoModel, RecomendacionModel,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def abc(client):
    """Auditoría Empresa ABC en revisión, con 4 hallazgos, a nombre de «ana»."""
    call_command("inicializar", verbosity=0)
    call_command("cargar_empresa_abc", usuario="ana", clave="Clave-segura-1", verbosity=0)
    client.force_login(get_user_model().objects.get(username="ana"))
    return AuditoriaModel.objects.get()


def test_editar_hallazgo(client, abc):
    url = reverse("hallazgo_editar", args=[abc.id, "H-01"])
    assert "Editar hallazgo H-01" in client.get(url).content.decode()
    h = HallazgoModel.objects.get(codigo="H-01")
    r = client.post(url, {"id_control": h.evaluacion.control_id, "severidad": "MEDIA", "condicion": "Condición corregida",
                          "criterio": h.criterio, "causa": h.causa, "efecto": h.efecto_riesgo}, follow=True)
    assert "Hallazgo H-01 actualizado" in r.content.decode()
    h.refresh_from_db()
    assert (h.condicion, h.severidad, h.recomendaciones.count()) == ("Condición corregida", "MEDIA", 1)


def test_eliminar_hallazgo_pide_confirmacion(client, abc):
    url = reverse("hallazgo_eliminar", args=[abc.id, "H-04"])
    assert "¿Eliminar el hallazgo H-04?" in client.get(url).content.decode()
    assert HallazgoModel.objects.count() == 4                        # un GET nunca borra
    client.post(url)
    assert list(HallazgoModel.objects.values_list("codigo", flat=True)) == ["H-01", "H-02", "H-03"]
    assert RecomendacionModel.objects.count() == 3


def test_editar_y_eliminar_recomendacion(client, abc):
    client.post(reverse("recomendacion_editar", args=[abc.id, "R-01"]),
                {"recomendacion": "Escaneos quincenales", "prioridad": "ALTA", "plazo_dias": 30})
    r = RecomendacionModel.objects.get(codigo="R-01")
    assert (r.descripcion, r.plazo_dias) == ("Escaneos quincenales", 30)
    client.post(reverse("recomendacion_eliminar", args=[abc.id, "R-01"]))
    pagina = client.post(reverse("auditoria_estado", args=[abc.id]), {"accion": "cerrar"}, follow=True).content.decode()
    assert "H-01 no tiene recomendación" in pagina                  # la regla de cierre se mantiene


def test_editar_evidencia(client, abc):
    client.post(reverse("auditoria_estado", args=[abc.id]), {"accion": "devolver"})
    url = reverse("evidencia_editar", args=[abc.id, "EV-01"])
    assert "Editar evidencia EV-01" in client.get(url).content.decode()
    client.post(url, {"descripcion": "Política v3", "fuente": "Documental", "fecha": "2026-11-14", "referencia": "DOC-3"})
    e = EvidenciaModel.objects.get(codigo="EV-01")
    assert (e.descripcion, e.referencia, e.es_simulada) == ("Política v3", "DOC-3", False)
    r = client.post(url, {"descripcion": "x", "fuente": "Documental", "fecha": "2026-11-14", "referencia": ""})
    assert "Indique una referencia" in r.content.decode()


def test_evidencia_no_se_edita_en_revision(client, abc):
    r = client.post(reverse("evidencia_editar", args=[abc.id, "EV-01"]),
                    {"descripcion": "x", "fuente": "Documental", "fecha": "2026-11-14", "referencia": "R"})
    assert "solo se modifican con la auditoría en ejecución" in r.content.decode()


def test_eliminar_auditoria_y_bloqueo_si_esta_cerrada(client, abc):
    url = reverse("auditoria_eliminar", args=[abc.id])
    assert "¿Eliminar la auditoría" in client.get(url).content.decode()
    client.post(reverse("auditoria_estado", args=[abc.id]), {"accion": "cerrar"})
    r = client.post(url, follow=True)
    assert "no se puede eliminar" in r.content.decode() and AuditoriaModel.objects.count() == 1


def test_eliminar_auditoria_en_curso(client, abc):
    client.post(reverse("auditoria_eliminar", args=[abc.id]))
    assert AuditoriaModel.objects.count() == 0 and HallazgoModel.objects.count() == 0


def test_otro_auditor_no_puede_editar_ni_eliminar(client, abc):
    intruso = get_user_model().objects.create_user("intruso", password="Clave-segura-2")
    client.force_login(intruso)
    assert client.post(reverse("hallazgo_eliminar", args=[abc.id, "H-01"])).status_code == 403
    assert client.post(reverse("auditoria_eliminar", args=[abc.id])).status_code == 403
    assert HallazgoModel.objects.count() == 4


def test_crud_catalogo_solo_admin(client, abc):
    assert client.get(reverse("control_nuevo")).status_code == 403              # ana es auditora
    admin = get_user_model().objects.create_user("admin1", password="Clave-segura-3")
    admin.groups.add(Group.objects.get(name="admin"))
    client.force_login(admin)
    r = client.post(reverse("control_nuevo"), {"codigo": "9.1", "nombre": "Control propio",
                                               "categoria": "TECNOLOGICO", "descripcion": "Criterio propio"}, follow=True)
    assert "Control 9.1 creado" in r.content.decode()
    nuevo = ControlModel.objects.get(codigo_iso="9.1")
    r = client.post(reverse("control_nuevo"), {"codigo": "5.1", "nombre": "x", "categoria": "TECNOLOGICO", "descripcion": "x"})
    assert "Ya existe un control con el código 5.1" in r.content.decode()
    client.post(reverse("control_editar", args=[nuevo.id]), {"codigo": "9.1", "nombre": "Renombrado",
                                                             "categoria": "PERSONAS", "descripcion": "Criterio"})
    nuevo.refresh_from_db()
    assert (nuevo.nombre, nuevo.categoria) == ("Renombrado", "PERSONAS")
    en_uso = ControlModel.objects.get(codigo_iso="8.8")
    r = client.post(reverse("control_eliminar", args=[en_uso.id]), follow=True)
    assert "no se puede eliminar" in r.content.decode() and ControlModel.objects.filter(pk=en_uso.id).exists()
    client.post(reverse("control_eliminar", args=[nuevo.id]))
    assert not ControlModel.objects.filter(pk=nuevo.id).exists()
