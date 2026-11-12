"""Pruebas de aceptación por HTTP (CP-01, CP-02, CP-03, CP-13 y salud)."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from drakon.infraestructura.persistencia.models import AuditoriaModel, ControlModel

pytestmark = pytest.mark.django_db

DATOS = {
    "organizacion": "Empresa ABC",
    "objetivo": "Evaluar controles",
    "alcance": "Servidores y red",
    "fecha_inicio": "2026-11-09",
    "fecha_fin": "2026-11-20",
    "referentes": "",
}


@pytest.fixture
def cliente(client):
    call_command("inicializar", verbosity=0)
    u = get_user_model().objects.create_user("ana", password="Clave-segura-1")
    client.force_login(u)
    return client


def test_salud(client):
    r = client.get("/salud/")
    assert r.status_code == 200 and r.json()["estado"] == "ok"


def test_requiere_autenticacion(client):
    r = client.get(reverse("auditoria_lista"))
    assert r.status_code == 302 and "/ingresar/" in r["Location"]


def test_cp01_crear_auditoria_valida(cliente):
    r = cliente.post(reverse("auditoria_crear"), DATOS)
    assert r.status_code == 302
    a = AuditoriaModel.objects.get()
    assert a.estado == "BORRADOR"
    lista = cliente.get(reverse("auditoria_lista")).content.decode()
    assert "Empresa ABC" in lista and "Borrador" in lista


def test_cp02_fecha_de_cierre_vacia(cliente):
    r = cliente.post(reverse("auditoria_crear"), dict(DATOS, fecha_fin=""))
    assert r.status_code == 200
    assert "obligatorio" in r.content.decode()
    assert AuditoriaModel.objects.count() == 0


def test_cp03_seleccion_fuera_de_rango(cliente):
    cliente.post(reverse("auditoria_crear"), DATOS)
    a = AuditoriaModel.objects.get()
    ids = list(ControlModel.objects.values_list("id", flat=True))
    cliente.post(reverse("controles_seleccion", args=[a.id]), {"controles": ids[:9]})
    r = cliente.post(reverse("auditoria_estado", args=[a.id]), {"accion": "iniciar"}, follow=True)
    assert "entre 10 y 15" in r.content.decode()
    r = cliente.post(reverse("controles_seleccion", args=[a.id]), {"controles": ids[:16]}, follow=True)
    assert "máximo permitido es 15" in r.content.decode()
    cliente.post(reverse("controles_seleccion", args=[a.id]), {"controles": ids[:12]})
    cliente.post(reverse("auditoria_estado", args=[a.id]), {"accion": "iniciar"})
    a.refresh_from_db()
    assert a.estado == "EN_EJECUCION"


def test_cp13_auditor_no_ve_auditoria_ajena_ni_admin(cliente, client):
    call_command("cargar_empresa_abc", usuario="otro", clave="Clave-segura-2", verbosity=0)
    a = AuditoriaModel.objects.get()
    assert cliente.get(reverse("auditoria_detalle", args=[a.id])).status_code == 403
    r = cliente.get("/admin/persistencia/controlmodel/")
    assert r.status_code == 302  # sin is_staff no entra al admin del catálogo


def test_dashboard_y_catalogo(cliente):
    assert cliente.get(reverse("dashboard")).status_code == 200
    r = cliente.get(reverse("catalogo") + "?categoria=FISICO")
    assert r.status_code == 200 and "7.14" in r.content.decode()


def test_dashboard_aviso_naranja_y_graficos(cliente):
    from drakon.infraestructura.persistencia.models import AuditoriaModel as A

    call_command("cargar_empresa_abc", usuario="ana", verbosity=0)
    html = cliente.get(reverse("dashboard")).content.decode()
    assert "Hola, ana" in html or "Hola, Ana" in html
    assert "ya está lista para cerrarse" in html
    assert "33,3 %" in html and "54,2 %" in html
    assert "width:33.3%" in html  # CSS con punto decimal aunque la interfaz use coma
    assert A.objects.count() == 1


def test_cp10_generar_informe_desde_la_interfaz(cliente):
    call_command("cargar_empresa_abc", usuario="ana", cerrar=False, verbosity=0)
    a = AuditoriaModel.objects.get()
    r = cliente.post(reverse("informe_generar", args=[a.id]), follow=True)
    assert "Informe versión 1 generado" in r.content.decode()
    from drakon.infraestructura.persistencia.models import InformeModel

    pdf = cliente.get(reverse("informe_pdf", args=[InformeModel.objects.get().id]))
    assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")


def test_404_con_marca(cliente, settings):
    settings.DEBUG = False
    r = cliente.get("/no-existe/")
    assert r.status_code == 404 and "No encontramos esta página" in r.content.decode()


def test_catalogo_con_categoria_invalida_no_se_rompe(cliente):
    r = cliente.get(reverse("catalogo") + "?categoria=XX&q=acceso")
    assert r.status_code == 200 and "Control de acceso" in r.content.decode()


def test_403_con_marca(cliente):
    r = cliente.get(reverse("control_nuevo"))
    assert r.status_code == 403 and "No tienes permiso" in r.content.decode()


def test_admin_con_identidad_drakon(client):
    call_command("inicializar", verbosity=0)
    admin = get_user_model().objects.create_superuser("root", "r@x.co", "Clave-segura-1")
    client.force_login(admin)
    html = client.get("/admin/").content.decode()
    assert "Volver a DRAKON" in html and "#F47721" in html and "dark_mode.css" not in html


def test_login_muestra_escena_del_dragon(client):
    r = client.get(reverse("login"))
    html = r.content.decode()
    assert r.status_code == 200
    assert "Ingresa a DRAKON" in html and "dragon_hd.png" in html and "login.css" in html


def test_login_sin_recordarme_expira_al_cerrar_navegador(client):
    get_user_model().objects.create_user("leo", password="Clave-segura-1")
    r = client.post(reverse("login"), {"username": "leo", "password": "Clave-segura-1"})
    assert r.status_code == 302
    assert client.session.get_expire_at_browser_close()


def test_login_con_recordarme_mantiene_la_sesion(client):
    get_user_model().objects.create_user("eva", password="Clave-segura-1")
    r = client.post(reverse("login"), {"username": "eva", "password": "Clave-segura-1", "recordarme": "1"})
    assert r.status_code == 302
    assert not client.session.get_expire_at_browser_close()


def test_login_credenciales_invalidas(client):
    r = client.post(reverse("login"), {"username": "nadie", "password": "x"})
    assert r.status_code == 200 and "Usuario o contraseña incorrectos" in r.content.decode()
