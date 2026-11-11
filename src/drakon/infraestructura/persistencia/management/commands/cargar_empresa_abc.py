"""Carga la auditoría simulada de Empresa ABC (datos ficticios del documento de ejemplo).

Usa los mismos casos de uso que la interfaz web, así que también sirve como prueba
de humo del flujo completo. Uso:
    python manage.py cargar_empresa_abc --usuario auditor1 [--cerrar]
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from drakon.aplicacion.casos_uso import DatosAuditoria, DatosEvidencia, DatosHallazgo
from drakon.infraestructura import contenedor as c
from drakon.infraestructura.persistencia.models import ControlModel

EVALUACIONES = [
    ("5.1", "IMPLEMENTADO", "Política vigente, aprobada por la gerencia y revisada en 2026.", "Política de seguridad v2.0", "Documental"),
    ("5.15", "IMPLEMENTADO", "Matriz de roles y permisos aprobada; accesos por perfil.", "Matriz de roles y permisos", "Documental"),
    ("5.18", "PARCIAL", "Altas y bajas gestionadas; la revisión de accesos no es periódica.", "Entrevista al líder de TI", "Entrevista"),
    ("5.24", "NO_IMPLEMENTADO", "No hay procedimiento ni roles definidos para incidentes.", "Acta de entrevista (ausencia de procedimiento)", "Entrevista"),
    ("6.3", "PARCIAL", "Inducción inicial sin refuerzo anual ni evaluación.", "Lista de asistencia a inducción", "Documental"),
    ("7.2", "IMPLEMENTADO", "Acceso al cuarto de servidores con tarjeta y bitácora.", "Registro fotográfico y bitácora", "Observación"),
    ("8.5", "PARCIAL", "Autenticación multifactor solo en cuentas administrativas.", "Captura de configuración de MFA", "Técnica"),
    ("8.7", "IMPLEMENTADO", "Antimalware centralizado y actualizado en toda la muestra.", "Consola de antimalware", "Técnica"),
    ("8.8", "NO_IMPLEMENTADO", "No se realizan escaneos periódicos de vulnerabilidades.", "Acta de entrevista (sin reportes)", "Entrevista"),
    ("8.13", "PARCIAL", "Respaldos diarios; sin pruebas de restauración documentadas.", "Bitácora de respaldos", "Documental"),
    ("8.15", "NO_IMPLEMENTADO", "Registros locales sin centralización ni revisión.", "Captura de configuración de registros", "Técnica"),
    ("8.23", "PARCIAL", "Filtrado web solo en la sede principal.", "Configuración del proxy", "Técnica"),
    ("8.31", "NO_APLICABLE", "La empresa no desarrolla software propio.", None, None),
]

HALLAZGOS = [
    ("8.8", "ALTA", "No se evidencian escaneos ni reportes periódicos de vulnerabilidades en los servidores expuestos.",
     "ISO/IEC 27002:2022, control 8.8: obtener información sobre vulnerabilidades, evaluar la exposición y tomar medidas apropiadas.",
     "No hay responsable asignado ni procedimiento de gestión de parches y vulnerabilidades.",
     "Mayor probabilidad de explotación de vulnerabilidades conocidas, con impacto en la disponibilidad y confidencialidad de los datos de clientes.",
     "Designar responsable, definir el procedimiento y ejecutar escaneos mensuales con plazos de remediación según la criticidad.", "ALTA", 60),
    ("5.24", "ALTA", "No existe procedimiento documentado ni roles definidos para gestionar incidentes de seguridad; los eventos se atienden de manera informal.",
     "ISO/IEC 27002:2022, control 5.24: definir procesos, roles y responsabilidades para la gestión de incidentes.",
     "Falta de definición de responsabilidades y de un canal único de reporte.",
     "Respuesta tardía o inconsistente, pérdida de evidencia y posible incumplimiento de obligaciones de notificación.",
     "Formalizar el procedimiento, designar el equipo de respuesta, habilitar un canal de reporte y realizar un simulacro semestral.", "ALTA", 60),
    ("8.13", "MEDIA", "Se ejecutan respaldos diarios, pero no hay pruebas de restauración registradas.",
     "ISO/IEC 27002:2022, control 8.13: mantener y probar periódicamente las copias de seguridad.",
     "No existe procedimiento ni responsable de las pruebas de restauración.",
     "Imposibilidad de recuperar información crítica de clientes ante una falla o un ataque de ransomware.",
     "Definir el procedimiento de respaldo y ejecutar pruebas de restauración trimestrales documentadas.", "MEDIA", 90),
    ("8.15", "MEDIA", "Los registros se almacenan localmente en cada servidor, sin centralización ni revisión periódica.",
     "ISO/IEC 27002:2022, control 8.15: producir, proteger y analizar los registros de actividad.",
     "No se ha implementado una solución de gestión de registros.",
     "Dificultad para detectar y reconstruir incidentes, y posibilidad de alteración de los registros.",
     "Centralizar los registros críticos, proteger su integridad y definir una revisión periódica.", "MEDIA", 120),
]


class Command(BaseCommand):
    help = "Carga la auditoría simulada de Empresa ABC (datos ficticios)."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario auditor responsable (se crea si no existe).")
        parser.add_argument("--clave", default=None, help="Contraseña si el usuario se crea.")
        parser.add_argument("--cerrar", action="store_true", help="Deja la auditoría cerrada y con informe.")

    @transaction.atomic
    def handle(self, *args, usuario, clave, cerrar, **opts):
        if ControlModel.objects.count() == 0:
            raise CommandError("El catálogo está vacío. Ejecute primero: python manage.py inicializar")
        User = get_user_model()
        u, creado = User.objects.get_or_create(username=usuario, defaults={"first_name": "Ana", "last_name": "R."})
        if creado:
            if not clave:
                raise CommandError("El usuario no existe: indique --clave para crearlo.")
            u.set_password(clave)
            u.save()
        u.groups.add(Group.objects.get_or_create(name="auditor")[0])

        ids = dict(ControlModel.objects.values_list("codigo_iso", "id"))
        a = c.crear_auditoria().ejecutar(DatosAuditoria(
            organizacion="Empresa ABC (ficticia)",
            objetivo="Evaluar el estado de implementación de 13 controles seleccionados de ISO/IEC 27002:2022 "
                     "en los servicios de TI de la organización.",
            alcance="Servidores, estaciones de trabajo, aplicaciones empresariales, bases de datos de clientes, "
                    "red corporativa y usuarios internos y externos.",
            fecha_inicio=date(2026, 11, 9), fecha_fin=date(2026, 11, 20),
        ), u.id)
        c.seleccionar_controles().ejecutar(a.id, [ids[x[0]] for x in EVALUACIONES])
        c.cambiar_estado().ejecutar(a.id, "iniciar")
        for codigo, estado, obs, evidencia, fuente in EVALUACIONES:
            na = "La empresa adquiere soluciones como servicio y no desarrolla software propio." if estado == "NO_APLICABLE" else ""
            c.evaluar_control().ejecutar(a.id, ids[codigo], estado, obs, na)
            if evidencia:
                c.registrar_evidencia().ejecutar(a.id, ids[codigo], DatosEvidencia(
                    descripcion=evidencia, fuente=fuente, fecha=date(2026, 11, 12),
                    referencia=f"Evidencia simulada – {evidencia}"))
        c.cambiar_estado().ejecutar(a.id, "revision")
        for codigo, sev, cond, crit, causa, efecto, rec, prio, plazo in HALLAZGOS:
            c.registrar_hallazgo().ejecutar(a.id, DatosHallazgo(ids[codigo], cond, crit, causa, efecto, sev, rec, prio, plazo))
        if cerrar:
            c.cambiar_estado().ejecutar(a.id, "cerrar")
            c.generar_informe().ejecutar(a.id)
        estado = c.auditorias().obtener(a.id).estado.etiqueta
        self.stdout.write(self.style.SUCCESS(f"Auditoría Empresa ABC creada (id {a.id}, estado «{estado}»)."))
