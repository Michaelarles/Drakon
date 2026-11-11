"""Modelos ORM (adaptador de persistencia).

Las restricciones CHECK, UNIQUE y las llaves foráneas replican en PostgreSQL las
reglas del dominio que la base de datos puede garantizar (defensa en profundidad).
Estos modelos NO son el dominio: los repositorios traducen entre ambos.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

ESTADOS_AUDITORIA = [("BORRADOR", "Borrador"), ("EN_EJECUCION", "En ejecución"),
                     ("EN_REVISION", "En revisión"), ("CERRADA", "Cerrada")]
ESTADOS_EVALUACION = [("PENDIENTE", "Sin evaluar"), ("IMPLEMENTADO", "Implementado"),
                      ("PARCIAL", "Parcialmente implementado"), ("NO_IMPLEMENTADO", "No implementado"),
                      ("NO_APLICABLE", "No aplicable")]
NIVELES = [("ALTA", "Alta"), ("MEDIA", "Media"), ("BAJA", "Baja")]
CATEGORIAS = [("ORGANIZACIONAL", "Organizacionales (5)"), ("PERSONAS", "Personas (6)"),
              ("FISICO", "Físicos (7)"), ("TECNOLOGICO", "Tecnológicos (8)")]


def _en(campo, opciones):
    return Q(**{f"{campo}__in": [o[0] for o in opciones]})


class ControlModel(models.Model):
    codigo_iso = models.CharField("código ISO", max_length=10, unique=True)
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=15, choices=CATEGORIAS)
    descripcion = models.TextField("criterio / descripción")
    fuente = models.CharField(max_length=60, default="ISO/IEC 27002:2022")

    class Meta:
        db_table = "control"
        verbose_name = "control"
        verbose_name_plural = "catálogo de controles"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=_en("categoria", CATEGORIAS), name="control_categoria_valida"),
            models.CheckConstraint(condition=~Q(descripcion=""), name="control_criterio_obligatorio"),
        ]

    def __str__(self):
        return f"{self.codigo_iso} {self.nombre}"


class AuditoriaModel(models.Model):
    organizacion = models.CharField(max_length=120)
    objetivo = models.TextField()
    alcance = models.TextField()
    referentes = models.TextField(blank=True, default="")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=15, choices=ESTADOS_AUDITORIA, default="BORRADOR")
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="auditorias")
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auditoria"
        ordering = ["-creada", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(fecha_fin__gte=models.F("fecha_inicio")), name="auditoria_fechas_validas"),
            models.CheckConstraint(condition=_en("estado", ESTADOS_AUDITORIA), name="auditoria_estado_valido"),
            models.CheckConstraint(condition=~Q(organizacion="") & ~Q(objetivo="") & ~Q(alcance=""),
                                   name="auditoria_datos_obligatorios"),
        ]


class EvaluacionControlModel(models.Model):
    auditoria = models.ForeignKey(AuditoriaModel, on_delete=models.CASCADE, related_name="evaluaciones")
    control = models.ForeignKey(ControlModel, on_delete=models.PROTECT, related_name="evaluaciones")
    estado = models.CharField(max_length=16, choices=ESTADOS_EVALUACION, default="PENDIENTE")
    observacion = models.TextField(blank=True, default="")
    justificacion_na = models.TextField(blank=True, default="")

    class Meta:
        db_table = "evaluacion_control"
        constraints = [
            models.UniqueConstraint(fields=["auditoria", "control"], name="evaluacion_control_unica"),
            models.CheckConstraint(condition=_en("estado", ESTADOS_EVALUACION), name="evaluacion_estado_valido"),
            models.CheckConstraint(condition=Q(estado="PENDIENTE") | ~Q(observacion=""),
                                   name="evaluacion_observacion_obligatoria"),
            models.CheckConstraint(condition=~Q(estado="NO_APLICABLE") | ~Q(justificacion_na=""),
                                   name="evaluacion_na_exige_justificacion"),
        ]


class ArchivoEvidenciaModel(models.Model):
    """Usado por el adaptador AlmacenEvidenciasBD. Reemplazable por S3/Supabase."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=100)
    tamano = models.PositiveIntegerField()
    datos = models.BinaryField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "archivo_evidencia"
        constraints = [
            models.CheckConstraint(condition=Q(tamano__gt=0) & Q(tamano__lte=5 * 1024 * 1024),
                                   name="archivo_tamano_maximo_5mb"),
        ]


class EvidenciaModel(models.Model):
    evaluacion = models.ForeignKey(EvaluacionControlModel, on_delete=models.CASCADE, related_name="evidencias")
    codigo = models.CharField(max_length=8)
    descripcion = models.TextField()
    fuente = models.CharField(max_length=200)
    fecha = models.DateField()
    es_simulada = models.BooleanField(default=True)
    referencia = models.CharField(max_length=500, blank=True, default="")
    archivo = models.ForeignKey(ArchivoEvidenciaModel, null=True, blank=True, on_delete=models.SET_NULL)
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "evidencia"
        ordering = ["codigo"]
        constraints = [
            models.CheckConstraint(condition=~Q(descripcion="") & ~Q(fuente=""), name="evidencia_datos_obligatorios"),
            models.CheckConstraint(condition=~Q(referencia="") | Q(archivo__isnull=False) | ~Q(archivo_nombre=""),
                                   name="evidencia_archivo_o_referencia"),
        ]


class HallazgoModel(models.Model):
    auditoria = models.ForeignKey(AuditoriaModel, on_delete=models.CASCADE, related_name="hallazgos")
    evaluacion = models.ForeignKey(EvaluacionControlModel, on_delete=models.PROTECT, related_name="hallazgos")
    codigo = models.CharField(max_length=8)
    condicion = models.TextField()
    criterio = models.TextField()
    causa = models.TextField()
    efecto_riesgo = models.TextField()
    severidad = models.CharField(max_length=5, choices=NIVELES)

    class Meta:
        db_table = "hallazgo"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(fields=["auditoria", "codigo"], name="hallazgo_codigo_unico_por_auditoria"),
            models.CheckConstraint(condition=_en("severidad", NIVELES), name="hallazgo_severidad_valida"),
            models.CheckConstraint(
                condition=~Q(condicion="") & ~Q(criterio="") & ~Q(causa="") & ~Q(efecto_riesgo=""),
                name="hallazgo_campos_obligatorios"),
        ]


class RecomendacionModel(models.Model):
    hallazgo = models.ForeignKey(HallazgoModel, on_delete=models.CASCADE, related_name="recomendaciones")
    codigo = models.CharField(max_length=8)
    descripcion = models.TextField()
    prioridad = models.CharField(max_length=5, choices=NIVELES)
    plazo_dias = models.PositiveIntegerField()

    class Meta:
        db_table = "recomendacion"
        ordering = ["codigo"]
        constraints = [
            models.CheckConstraint(condition=_en("prioridad", NIVELES), name="recomendacion_prioridad_valida"),
            models.CheckConstraint(condition=Q(plazo_dias__gt=0), name="recomendacion_plazo_positivo"),
            models.CheckConstraint(condition=~Q(descripcion=""), name="recomendacion_descripcion_obligatoria"),
        ]


class InformeModel(models.Model):
    auditoria = models.ForeignKey(AuditoriaModel, on_delete=models.CASCADE, related_name="informes")
    version = models.PositiveIntegerField()
    fecha_generacion = models.DateTimeField()
    contenido = models.JSONField()

    class Meta:
        db_table = "informe"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["auditoria", "version"], name="informe_version_unica"),
            models.CheckConstraint(condition=Q(version__gte=1), name="informe_version_positiva"),
        ]
