"""Prepara la base de datos: roles, catálogo ISO 27002 y superusuario.

Es idempotente: se puede ejecutar en cada despliegue sin duplicar datos.
"""
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from drakon.infraestructura.persistencia.models import AuditoriaModel, ControlModel

FIXTURE = Path(__file__).resolve().parents[6] / "fixtures" / "controles_iso27002.json"


class Command(BaseCommand):
    help = "Crea los roles «auditor» y «admin», carga el catálogo de controles y el superusuario."

    @transaction.atomic
    def handle(self, *args, **opts):
        auditor, _ = Group.objects.get_or_create(name="auditor")
        admin, _ = Group.objects.get_or_create(name="admin")
        permisos = Permission.objects.filter(content_type__app_label="persistencia",
                                             codename__endswith="controlmodel")
        admin.permissions.set(permisos)

        datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
        nuevos = 0
        for d in datos:
            _, creado = ControlModel.objects.update_or_create(
                codigo_iso=d["codigo"],
                defaults=dict(nombre=d["nombre"], categoria=d["categoria"], descripcion=d["descripcion"]),
            )
            nuevos += creado
        self.stdout.write(f"Catálogo: {len(datos)} controles ({nuevos} nuevos).")

        usuario = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        clave = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if usuario and clave:
            User = get_user_model()
            u, creado = User.objects.get_or_create(username=usuario, defaults={
                "email": os.environ.get("DJANGO_SUPERUSER_EMAIL", ""), "is_staff": True, "is_superuser": True})
            if creado:
                u.set_password(clave)
                u.save()
                self.stdout.write(f"Superusuario «{usuario}» creado.")
            u.groups.add(admin, auditor)
        # Datos de demostración (Render gratuito no tiene consola): solo si no hay auditorías.
        demo_usuario, demo_clave = os.environ.get("DEMO_USUARIO"), os.environ.get("DEMO_CLAVE")
        if demo_usuario and demo_clave and not AuditoriaModel.objects.exists():
            call_command("cargar_empresa_abc", usuario=demo_usuario, clave=demo_clave, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Inicialización completa."))
