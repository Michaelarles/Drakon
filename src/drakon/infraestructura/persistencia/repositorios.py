"""Adaptadores de persistencia: implementan los puertos con el ORM de Django.

Cada repositorio traduce entre modelos ORM y objetos del dominio (mappers).
`guardar` sincroniza el agregado completo dentro de una transacción.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, Q

from drakon.dominio.auditoria import Auditoria, EvaluacionControl, Evidencia, Hallazgo, Recomendacion
from drakon.dominio.catalogo import Control
from drakon.dominio.errores import NoEncontrado
from drakon.dominio.informe import Informe
from drakon.dominio.valores import (
    CategoriaControl, EstadoAuditoria, EstadoEvaluacion, Prioridad, Severidad,
)

from .models import (
    AuditoriaModel, ControlModel, EvaluacionControlModel, EvidenciaModel,
    HallazgoModel, InformeModel, RecomendacionModel,
)


# ------------------------------------------------------------------ mappers
def control_a_dominio(m: ControlModel) -> Control:
    return Control(id=m.id, codigo=m.codigo_iso, nombre=m.nombre,
                   categoria=CategoriaControl(m.categoria), descripcion=m.descripcion, fuente=m.fuente)


def _auditoria_a_dominio(m: AuditoriaModel) -> Auditoria:
    evaluaciones, por_eval = [], {}
    for e in m.evaluaciones.all():
        ev = EvaluacionControl(
            id=e.id, id_control=e.control_id, codigo_control=e.control.codigo_iso,
            nombre_control=e.control.nombre, estado=EstadoEvaluacion(e.estado),
            observacion=e.observacion, justificacion_na=e.justificacion_na,
            evidencias=[Evidencia(id=x.id, codigo=x.codigo, descripcion=x.descripcion, fuente=x.fuente,
                                  fecha=x.fecha, es_simulada=x.es_simulada, referencia=x.referencia,
                                  archivo_id=str(x.archivo_id) if x.archivo_id else None,
                                  archivo_nombre=x.archivo_nombre)
                        for x in e.evidencias.all()],
        )
        evaluaciones.append(ev)
        por_eval[e.id] = e.control_id
    evaluaciones.sort(key=lambda ev: tuple(int(p) for p in ev.codigo_control.split(".") if p.isdigit()))
    hallazgos = [
        Hallazgo(id=h.id, codigo=h.codigo, id_control=por_eval[h.evaluacion_id], condicion=h.condicion,
                 criterio=h.criterio, causa=h.causa, efecto=h.efecto_riesgo, severidad=Severidad(h.severidad),
                 recomendaciones=[Recomendacion(id=r.id, codigo=r.codigo, descripcion=r.descripcion,
                                                prioridad=Prioridad(r.prioridad), plazo_dias=r.plazo_dias)
                                  for r in h.recomendaciones.all()])
        for h in m.hallazgos.all()
    ]
    return Auditoria(
        id=m.id, organizacion=m.organizacion, objetivo=m.objetivo, alcance=m.alcance,
        fecha_inicio=m.fecha_inicio, fecha_fin=m.fecha_fin, id_auditor=m.auditor_id,
        referentes=m.referentes, estado=EstadoAuditoria(m.estado),
        evaluaciones=evaluaciones, hallazgos=hallazgos,
    )


def _consulta_auditorias():
    return AuditoriaModel.objects.prefetch_related(
        Prefetch("evaluaciones", queryset=EvaluacionControlModel.objects.select_related("control")
                 .prefetch_related("evidencias")),
        Prefetch("hallazgos", queryset=HallazgoModel.objects.prefetch_related("recomendaciones")),
    )


# ------------------------------------------------------------- repositorios
class RepositorioAuditoriasDjango:
    def obtener(self, id_auditoria: int) -> Auditoria:
        try:
            return _auditoria_a_dominio(_consulta_auditorias().get(pk=id_auditoria))
        except AuditoriaModel.DoesNotExist:
            raise NoEncontrado("La auditoría no existe.")

    def listar(self, id_auditor: int | None = None) -> list[Auditoria]:
        qs = _consulta_auditorias()
        if id_auditor is not None:
            qs = qs.filter(auditor_id=id_auditor)
        return [_auditoria_a_dominio(m) for m in qs]

    @transaction.atomic
    def eliminar(self, id_auditoria: int) -> None:
        # Los hallazgos protegen a sus evaluaciones (PROTECT): se eliminan primero.
        HallazgoModel.objects.filter(auditoria_id=id_auditoria).delete()
        AuditoriaModel.objects.filter(pk=id_auditoria).delete()

    @transaction.atomic
    def guardar(self, a: Auditoria) -> Auditoria:
        m, _ = AuditoriaModel.objects.update_or_create(
            pk=a.id,
            defaults=dict(organizacion=a.organizacion, objetivo=a.objetivo, alcance=a.alcance,
                          referentes=a.referentes, fecha_inicio=a.fecha_inicio, fecha_fin=a.fecha_fin,
                          estado=a.estado.value, auditor_id=a.id_auditor),
        )
        a.id = m.id

        # Hallazgos de controles retirados se borran primero (FK PROTECT hacia evaluación)
        codigos_h = [h.codigo for h in a.hallazgos]
        HallazgoModel.objects.filter(auditoria=m).exclude(codigo__in=codigos_h).delete()
        EvaluacionControlModel.objects.filter(auditoria=m).exclude(control_id__in=a.ids_controles).delete()

        eval_ids = {}
        for ev in a.evaluaciones:
            em, _ = EvaluacionControlModel.objects.update_or_create(
                auditoria=m, control_id=ev.id_control,
                defaults=dict(estado=ev.estado.value, observacion=ev.observacion,
                              justificacion_na=ev.justificacion_na),
            )
            ev.id = eval_ids[ev.id_control] = em.id
            codigos_ev = [x.codigo for x in ev.evidencias]
            EvidenciaModel.objects.filter(evaluacion=em).exclude(codigo__in=codigos_ev).delete()
            for x in ev.evidencias:
                xm, _ = EvidenciaModel.objects.update_or_create(
                    evaluacion=em, codigo=x.codigo,
                    defaults=dict(descripcion=x.descripcion, fuente=x.fuente, fecha=x.fecha,
                                  es_simulada=x.es_simulada, referencia=x.referencia,
                                  archivo_id=x.archivo_id, archivo_nombre=x.archivo_nombre),
                )
                x.id = xm.id

        for h in a.hallazgos:
            hm, _ = HallazgoModel.objects.update_or_create(
                auditoria=m, codigo=h.codigo,
                defaults=dict(evaluacion_id=eval_ids[h.id_control], condicion=h.condicion,
                              criterio=h.criterio, causa=h.causa, efecto_riesgo=h.efecto,
                              severidad=h.severidad.value),
            )
            h.id = hm.id
            RecomendacionModel.objects.filter(hallazgo=hm).exclude(
                codigo__in=[r.codigo for r in h.recomendaciones]).delete()
            for r in h.recomendaciones:
                rm, _ = RecomendacionModel.objects.update_or_create(
                    hallazgo=hm, codigo=r.codigo,
                    defaults=dict(descripcion=r.descripcion, prioridad=r.prioridad.value, plazo_dias=r.plazo_dias),
                )
                r.id = rm.id
        return a


class RepositorioCatalogoDjango:
    def listar(self, categoria: CategoriaControl | None = None, texto: str | None = None) -> list[Control]:
        qs = ControlModel.objects.all()
        if categoria in {c.value for c in CategoriaControl} or isinstance(categoria, CategoriaControl):
            qs = qs.filter(categoria=CategoriaControl(categoria).value)
        if texto:
            qs = qs.filter(Q(codigo_iso__icontains=texto) | Q(nombre__icontains=texto)
                           | Q(descripcion__icontains=texto))
        return sorted((control_a_dominio(m) for m in qs), key=lambda c: c.orden)

    def obtener_varios(self, ids: list[int]) -> dict[int, Control]:
        return {m.id: control_a_dominio(m) for m in ControlModel.objects.filter(id__in=ids)}

    def obtener(self, id_control: int) -> Control:
        try:
            return control_a_dominio(ControlModel.objects.get(pk=id_control))
        except ControlModel.DoesNotExist:
            raise NoEncontrado("El control no existe.")

    def guardar(self, control: Control) -> Control:
        m, _ = ControlModel.objects.update_or_create(
            pk=control.id, defaults=dict(codigo_iso=control.codigo, nombre=control.nombre,
                                         categoria=control.categoria.value, descripcion=control.descripcion))
        return control_a_dominio(m)

    def eliminar(self, id_control: int) -> None:
        ControlModel.objects.filter(pk=id_control).delete()

    def existe_codigo(self, codigo: str, excluir_id: int | None = None) -> bool:
        return ControlModel.objects.filter(codigo_iso__iexact=codigo).exclude(pk=excluir_id).exists()

    def en_uso(self, id_control: int) -> bool:
        return EvaluacionControlModel.objects.filter(control_id=id_control).exists()


class RepositorioInformesDjango:
    @staticmethod
    def _a_dominio(m: InformeModel) -> Informe:
        return Informe(id=m.id, id_auditoria=m.auditoria_id, version=m.version,
                       fecha_generacion=m.fecha_generacion, contenido=m.contenido)

    def guardar(self, informe: Informe) -> Informe:
        m = InformeModel.objects.create(auditoria_id=informe.id_auditoria, version=informe.version,
                                        fecha_generacion=informe.fecha_generacion, contenido=informe.contenido)
        return self._a_dominio(m)

    def obtener(self, id_informe: int) -> Informe:
        try:
            return self._a_dominio(InformeModel.objects.get(pk=id_informe))
        except InformeModel.DoesNotExist:
            raise NoEncontrado("El informe no existe.")

    def listar(self, id_auditoria: int) -> list[Informe]:
        return [self._a_dominio(m) for m in InformeModel.objects.filter(auditoria_id=id_auditoria)]

    def ultima_version(self, id_auditoria: int) -> int:
        ultimo = InformeModel.objects.filter(auditoria_id=id_auditoria).order_by("-version").first()
        return ultimo.version if ultimo else 0


class DirectorioUsuariosDjango:
    def nombre(self, id_usuario: int) -> str:
        u = get_user_model().objects.filter(pk=id_usuario).first()
        if not u:
            return "—"
        return u.get_full_name() or u.get_username()
