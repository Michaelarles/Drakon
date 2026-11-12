"""Adaptador de entrada web. Las vistas solo traducen HTTP ↔ casos de uso."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from drakon.aplicacion.casos_uso import DatosAuditoria, DatosControl, DatosEvidencia, DatosHallazgo
from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.dominio.errores import ErrorDeDominio, NoEncontrado
from drakon.dominio.indicadores import FORMULA_BASE, FORMULA_PONDERADA, CalculadoraIndicadores
from drakon.dominio.valores import MAX_CONTROLES, MIN_CONTROLES, CategoriaControl, EstadoAuditoria, EstadoEvaluacion
from drakon.infraestructura import contenedor as c

from .forms import (
    AuditoriaForm,
    ControlForm,
    EvaluacionForm,
    EvidenciaEdicionForm,
    EvidenciaForm,
    HallazgoForm,
    RecomendacionForm,
)


# ------------------------------------------------------------------ ingreso
class IngresoView(LoginView):
    """Inicio de sesión. Sin «Recordarme», la sesión termina al cerrar el navegador."""

    template_name = "drakon/login.html"

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        if not self.request.POST.get("recordarme"):
            self.request.session.set_expiry(0)
        return respuesta


# ------------------------------------------------------------------ roles
def es_admin(user) -> bool:
    return user.is_superuser or user.groups.filter(name="admin").exists()


def con_auditoria(vista):
    """Carga la auditoría y verifica que el usuario pueda verla (RNF04)."""

    @wraps(vista)
    def envoltura(request, id_auditoria, *args, **kwargs):
        try:
            auditoria = c.auditorias().obtener(id_auditoria)
        except NoEncontrado:
            raise Http404("La auditoría no existe.") from None
        if auditoria.id_auditor != request.user.id and not es_admin(request.user):
            raise PermissionDenied("No tiene acceso a esta auditoría.")
        return vista(request, auditoria, *args, **kwargs)

    return login_required(envoltura)


CATEGORIAS = [(c.value, c.etiqueta) for c in CategoriaControl]


def solo_admin(vista):
    """Funciones administrativas (catálogo): solo el rol «admin» (RNF04)."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_admin(request.user):
            raise PermissionDenied("Solo el administrador puede modificar el catálogo.")
        return vista(request, *args, **kwargs)

    return login_required(envoltura)


def confirmar(request, titulo, mensaje, consecuencias, url_cancelar, boton="Eliminar"):
    """Página de confirmación común para toda eliminación (nunca se borra con un GET)."""
    return render(
        request,
        "drakon/confirmar_eliminar.html",
        {
            "titulo": titulo,
            "mensaje": mensaje,
            "consecuencias": consecuencias,
            "url_cancelar": url_cancelar,
            "boton": boton,
        },
    )


def _alcance_usuario(user):
    return None if es_admin(user) else user.id


# ------------------------------------------------------------------ salud
@require_GET
def salud(request):
    """Usado por Render y el monitor de disponibilidad. Despierta también la BD."""
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    return JsonResponse({"estado": "ok"})


# ------------------------------------------------------------- dashboard
COLORES_ESTADO = [
    ("implementados", "Implementado", "#287A56"),
    ("parciales", "Parcial", "#FFB84D"),
    ("no_implementados", "No implementado", "#E84932"),
    ("no_aplicables", "No aplicable", "#B8AFA4"),
]
CIRCUNFERENCIA = 339.29  # 2·π·54, radio del anillo del gráfico


def segmentos_anillo(ind):
    """Segmentos del gráfico de anillo (stroke-dasharray) calculados desde los indicadores."""
    total = ind.implementados + ind.parciales + ind.no_implementados + ind.no_aplicables
    segmentos, acumulado = [], 0.0
    for campo, etiqueta, color in COLORES_ESTADO:
        n = getattr(ind, campo)
        largo = CIRCUNFERENCIA * n / total if total else 0
        segmentos.append(
            {
                "etiqueta": etiqueta,
                "color": color,
                "n": n,
                "dash": f"{largo:.1f} {CIRCUNFERENCIA:.1f}",
                "offset": f"{-acumulado:.1f}",
            }
        )
        acumulado += largo
    return segmentos, total


def aviso_principal(recientes):
    """Mensaje del aviso naranja: la acción más importante para el auditor."""
    for a, ind in recientes:
        if a.estado == EstadoAuditoria.EN_REVISION and not a.problemas_para_cierre():
            return {
                "titulo": f"{a.organizacion} ya está lista para cerrarse.",
                "texto": f"Evaluaste {ind.total} controles y documentaste {ind.total_hallazgos} hallazgos con sus "
                "recomendaciones. Solo falta cerrarla y emitir el informe.",
                "accion": "Revisar y cerrar",
                "auditoria": a,
            }
    for a, ind in recientes:
        if a.estado == EstadoAuditoria.EN_EJECUCION:
            return {
                "titulo": f"A {a.organizacion} le faltan {ind.pendientes} controles por evaluar."
                if ind.pendientes
                else f"{a.organizacion} está lista para pasar a revisión.",
                "texto": "Registra la observación y las evidencias de cada control para mantener la trazabilidad.",
                "accion": "Continuar evaluación" if ind.pendientes else "Ver la auditoría",
                "auditoria": a,
                "destino": "evaluar" if ind.pendientes else "detalle",
            }
        if a.estado == EstadoAuditoria.EN_REVISION:
            return {
                "titulo": f"{a.organizacion} está en revisión.",
                "texto": "Documenta los hallazgos y sus recomendaciones; se requieren al menos 3 para cerrar.",
                "accion": "Ver hallazgos",
                "auditoria": a,
                "destino": "hallazgos",
            }
        if a.estado == EstadoAuditoria.BORRADOR:
            return {
                "titulo": f"{a.organizacion} espera sus controles.",
                "texto": f"Selecciona entre {MIN_CONTROLES} y {MAX_CONTROLES} controles de ISO/IEC 27002:2022 "
                "para iniciar.",
                "accion": "Seleccionar controles",
                "auditoria": a,
            }
    return {
        "titulo": "Empecemos tu primera auditoría.",
        "texto": "Registra la organización, el objetivo y el alcance. Drakon te guía en cada paso.",
        "accion": None,
        "auditoria": None,
    }


@login_required
def dashboard(request):
    d = c.consultar_dashboard().ejecutar(_alcance_usuario(request.user))
    segmentos, total = segmentos_anillo(d.indicadores)
    return render(
        request,
        "drakon/dashboard.html",
        {
            "d": d,
            "ind": d.indicadores,
            "segmentos": segmentos,
            "total_anillo": total,
            "aviso": aviso_principal(d.recientes),
            "nombre": request.user.first_name or request.user.get_username(),
            "formula_base": FORMULA_BASE,
            "formula_ponderada": FORMULA_PONDERADA,
        },
    )


# ------------------------------------------------------------- auditorías
@login_required
def auditoria_lista(request):
    auditorias = c.auditorias().listar(_alcance_usuario(request.user))
    filas = [(a, CalculadoraIndicadores.de_auditoria(a)) for a in auditorias]
    return render(request, "drakon/auditoria_lista.html", {"filas": filas})


@login_required
def auditoria_crear(request):
    form = AuditoriaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            a = c.crear_auditoria().ejecutar(DatosAuditoria(**form.cleaned_data), request.user.id)
            messages.success(request, "Auditoría creada en estado «Borrador». Ahora seleccione los controles.")
            return redirect("controles_seleccion", id_auditoria=a.id)
        except ErrorDeDominio as e:
            form.aplicar_error(e)
    return render(request, "drakon/auditoria_form.html", {"form": form, "titulo": "Nueva auditoría"})


@con_auditoria
def auditoria_editar(request, auditoria):
    inicial = {k: getattr(auditoria, k) for k in AuditoriaForm.base_fields}
    form = AuditoriaForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        try:
            c.actualizar_auditoria().ejecutar(auditoria.id, DatosAuditoria(**form.cleaned_data))
            messages.success(request, "Datos de la auditoría actualizados.")
            return redirect("auditoria_detalle", id_auditoria=auditoria.id)
        except ErrorDeDominio as e:
            form.aplicar_error(e)
    return render(
        request, "drakon/auditoria_form.html", {"form": form, "titulo": "Editar auditoría", "auditoria": auditoria}
    )


@con_auditoria
def auditoria_eliminar(request, auditoria):
    if request.method == "POST":
        try:
            c.eliminar_auditoria().ejecutar(auditoria.id)
            messages.success(request, f"La auditoría de {auditoria.organizacion} fue eliminada.")
            return redirect("auditoria_lista")
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
            return redirect("auditoria_detalle", id_auditoria=auditoria.id)
    if auditoria.estado == EstadoAuditoria.CERRADA:
        messages.error(request, "Una auditoría cerrada no se puede eliminar: es el soporte del informe emitido.")
        return redirect("auditoria_detalle", id_auditoria=auditoria.id)
    return confirmar(
        request,
        f"¿Eliminar la auditoría de {auditoria.organizacion}?",
        "Esta acción no se puede deshacer.",
        [
            f"{len(auditoria.evaluaciones)} evaluaciones de control",
            f"{len(auditoria.todas_las_evidencias)} evidencias y sus archivos",
            f"{len(auditoria.hallazgos)} hallazgos con sus recomendaciones",
            "Los informes generados",
        ],
        reverse("auditoria_detalle", args=[auditoria.id]),
    )


@con_auditoria
def auditoria_detalle(request, auditoria):
    return render(
        request,
        "drakon/auditoria_detalle.html",
        {
            "a": auditoria,
            "ind": CalculadoraIndicadores.de_auditoria(auditoria),
            "problemas_revision": auditoria.problemas_para_revision(),
            "problemas_cierre": auditoria.problemas_para_cierre(),
            "informes": c.informes().listar(auditoria.id),
            "min": MIN_CONTROLES,
            "max": MAX_CONTROLES,
        },
    )


@require_POST
@con_auditoria
def auditoria_estado(request, auditoria):
    accion = request.POST.get("accion", "")
    try:
        a = c.cambiar_estado().ejecutar(auditoria.id, accion)
        messages.success(request, f"La auditoría ahora está «{a.estado.etiqueta}».")
    except ErrorDeDominio as e:
        messages.error(request, e.mensaje)
    return redirect("auditoria_detalle", id_auditoria=auditoria.id)


# ------------------------------------------------------- catálogo (RF02)
@login_required
def catalogo(request):
    categoria = request.GET.get("categoria") or None
    if categoria not in {c.value for c in CategoriaControl}:
        categoria = None  # un valor manipulado en la URL no debe romper la página
    texto = request.GET.get("q", "").strip() or None
    controles = c.catalogo().listar(categoria, texto)
    return render(
        request,
        "drakon/catalogo.html",
        {
            "controles": controles,
            "categorias": CATEGORIAS,
            "categoria": categoria,
            "q": texto or "",
            "es_admin": es_admin(request.user),
        },
    )


@solo_admin
def control_nuevo(request):
    return _control_form(request, None)


@solo_admin
def control_editar(request, id_control):
    return _control_form(request, id_control)


def _control_form(request, id_control):
    try:
        actual = c.catalogo().obtener(id_control) if id_control else None
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        form = ControlForm(request.POST)
        if form.is_valid():
            try:
                ctrl = c.guardar_control().ejecutar(DatosControl(**form.cleaned_data), id_control)
                messages.success(request, f"Control {ctrl.codigo} {'actualizado' if id_control else 'creado'}.")
                return redirect(reverse("catalogo") + f"?q={ctrl.codigo}")
            except ErrorDeDominio as e:
                form.aplicar_error(e)
    else:
        form = ControlForm(
            initial={
                "codigo": actual.codigo,
                "nombre": actual.nombre,
                "categoria": actual.categoria.value,
                "descripcion": actual.descripcion,
            }
            if actual
            else None
        )
    return render(request, "drakon/control_form.html", {"form": form, "control": actual})


@solo_admin
def control_eliminar(request, id_control):
    try:
        ctrl = c.catalogo().obtener(id_control)
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        try:
            c.eliminar_control().ejecutar(id_control)
            messages.success(request, f"Control {ctrl.codigo} eliminado del catálogo.")
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
        return redirect("catalogo")
    return confirmar(
        request,
        f"¿Eliminar el control {ctrl.codigo} del catálogo?",
        ctrl.nombre,
        ["Solo se permite si ninguna auditoría lo ha seleccionado"],
        reverse("catalogo"),
    )


@con_auditoria
def controles_seleccion(request, auditoria):
    if request.method == "POST":
        ids = [int(i) for i in request.POST.getlist("controles") if i.isdigit()]
        try:
            a = c.seleccionar_controles().ejecutar(auditoria.id, ids)
            n = len(a.evaluaciones)
            if MIN_CONTROLES <= n <= MAX_CONTROLES:
                messages.success(request, f"Selección guardada: {n} controles. Ya puede iniciar la ejecución.")
                return redirect("auditoria_detalle", id_auditoria=a.id)
            messages.warning(
                request,
                f"Selección guardada con {n} controles. Para iniciar la ejecución "
                f"se requieren entre {MIN_CONTROLES} y {MAX_CONTROLES}.",
            )
            return redirect("controles_seleccion", id_auditoria=a.id)
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
            seleccionados = set(ids)
    else:
        seleccionados = set(auditoria.ids_controles)
    controles = c.catalogo().listar()
    return render(
        request,
        "drakon/controles_seleccion.html",
        {
            "a": auditoria,
            "controles": controles,
            "seleccionados": seleccionados,
            "categorias": CATEGORIAS,
            "min": MIN_CONTROLES,
            "max": MAX_CONTROLES,
            "bloqueado": auditoria.estado != EstadoAuditoria.BORRADOR,
        },
    )


# ------------------------------------------- evaluación y evidencias (RF03/RF04)
@con_auditoria
def evaluar_inicio(request, auditoria):
    """Lleva al primer control sin evaluar (o al primero de la lista)."""
    if not auditoria.evaluaciones:
        messages.warning(request, "Primero seleccione los controles de la auditoría.")
        return redirect("auditoria_detalle", id_auditoria=auditoria.id)
    pendiente = next((e for e in auditoria.evaluaciones if not e.evaluada), auditoria.evaluaciones[0])
    return redirect("evaluar_control", id_auditoria=auditoria.id, id_control=pendiente.id_control)


def _contexto_evaluacion(auditoria, id_control, form=None, form_evidencia=None):
    try:
        ev = auditoria.evaluacion(id_control)
    except NoEncontrado:
        raise Http404("El control no está en esta auditoría.") from None
    controles = c.catalogo().obtener_varios([id_control])
    indice = auditoria.ids_controles.index(id_control)
    ids = auditoria.ids_controles
    evaluados = sum(1 for e in auditoria.evaluaciones if e.evaluada)
    if form is None:
        inicial = {
            "estado": ev.estado.value if ev.evaluada else None,
            "observacion": ev.observacion,
            "justificacion_na": ev.justificacion_na,
        }
        form = EvaluacionForm(initial=inicial)
    return {
        "a": auditoria,
        "ev": ev,
        "control": controles.get(id_control),
        "form": form,
        "form_evidencia": form_evidencia
        or EvidenciaForm(initial={"fecha": auditoria.fecha_inicio, "es_simulada": True}),
        "editable": auditoria.estado == EstadoAuditoria.EN_EJECUCION,
        "anterior": ids[indice - 1] if indice > 0 else None,
        "siguiente": ids[indice + 1] if indice + 1 < len(ids) else None,
        "posicion": indice + 1,
        "evaluados": evaluados,
        "total": len(ids),
        "hallazgos_control": [h for h in auditoria.hallazgos if h.id_control == id_control],
        "falta_evidencia": {
            e.id_control for e in auditoria.evaluaciones if e.estado.exige_evidencia and not e.evidencias
        },
    }


@con_auditoria
def evaluar_control(request, auditoria, id_control):
    if request.method == "POST":
        form = EvaluacionForm(request.POST)
        if form.is_valid():
            try:
                a = c.evaluar_control().ejecutar(
                    auditoria.id,
                    id_control,
                    form.cleaned_data["estado"],
                    form.cleaned_data["observacion"],
                    form.cleaned_data["justificacion_na"],
                )
                ev = a.evaluacion(id_control)
                if ev.estado.exige_evidencia and not ev.evidencias:
                    messages.warning(
                        request,
                        f"Control {ev.codigo_control} guardado. Recuerde adjuntar al menos una "
                        "evidencia: «Implementado» y «Parcial» la exigen.",
                    )
                    return redirect("evaluar_control", id_auditoria=a.id, id_control=id_control)
                messages.success(request, f"Control {ev.codigo_control} evaluado como «{ev.estado.etiqueta}».")
                siguiente = next((e for e in a.evaluaciones if not e.evaluada), None)
                if request.POST.get("ir") == "siguiente" and siguiente:
                    return redirect("evaluar_control", id_auditoria=a.id, id_control=siguiente.id_control)
                if siguiente is None:
                    messages.info(request, "Evaluaste todos los controles. Ya puedes enviar la auditoría a revisión.")
                    return redirect("auditoria_detalle", id_auditoria=a.id)
                return redirect("evaluar_control", id_auditoria=a.id, id_control=id_control)
            except ErrorDeDominio as e:
                form.aplicar_error(e)
        return render(request, "drakon/evaluacion.html", _contexto_evaluacion(auditoria, id_control, form=form))
    return render(request, "drakon/evaluacion.html", _contexto_evaluacion(auditoria, id_control))


TIPOS_POR_EXTENSION = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _tipo_mime(archivo) -> str:
    """El tipo lo decide la extensión (el navegador puede enviar uno genérico); el dominio lo valida."""
    nombre = archivo.name.lower()
    for ext, tipo in TIPOS_POR_EXTENSION.items():
        if nombre.endswith(ext):
            return tipo
    return archivo.content_type or "application/octet-stream"


@require_POST
@con_auditoria
def evidencia_agregar(request, auditoria, id_control):
    form = EvidenciaForm(request.POST, request.FILES)
    if form.is_valid():
        d = form.cleaned_data
        archivo = None
        if d.get("archivo"):
            f = d["archivo"]
            archivo = ArchivoAdjunto(nombre=f.name, tipo=_tipo_mime(f), contenido=f.read())
        try:
            ev = c.registrar_evidencia().ejecutar(
                auditoria.id,
                id_control,
                DatosEvidencia(
                    descripcion=d["descripcion"],
                    fuente=d["fuente"],
                    fecha=d["fecha"],
                    es_simulada=d["es_simulada"],
                    referencia=d["referencia"],
                    archivo=archivo,
                ),
            )
            messages.success(request, f"Evidencia {ev.codigo} registrada y ligada al control.")
            return redirect("evaluar_control", id_auditoria=auditoria.id, id_control=id_control)
        except ErrorDeDominio as e:
            form.aplicar_error(e)
    ctx = _contexto_evaluacion(auditoria, id_control, form_evidencia=form)
    ctx["abrir_evidencia"] = True
    return render(request, "drakon/evaluacion.html", ctx)


@con_auditoria
def evidencia_eliminar(request, auditoria, codigo):
    try:
        evidencia, id_control = auditoria.evidencia(codigo), auditoria.control_de_evidencia(codigo)
    except NoEncontrado:
        raise Http404 from None
    if request.method != "POST":
        return confirmar(
            request,
            f"¿Eliminar la evidencia {codigo}?",
            evidencia.descripcion,
            ["El archivo adjunto, si lo tiene", "Su vínculo con el control"],
            reverse("evaluar_control", args=[auditoria.id, id_control]),
        )
    try:
        c.eliminar_evidencia().ejecutar(auditoria.id, codigo)
        messages.success(request, f"Evidencia {codigo} eliminada.")
    except ErrorDeDominio as e:
        messages.error(request, e.mensaje)
    return redirect("evaluar_control", id_auditoria=auditoria.id, id_control=id_control)


@con_auditoria
def evidencia_editar(request, auditoria, codigo):
    try:
        evidencia = auditoria.evidencia(codigo)
        id_control = auditoria.control_de_evidencia(codigo)
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        form = EvidenciaEdicionForm(request.POST, tiene_archivo=bool(evidencia.archivo_id))
        if form.is_valid():
            d = form.cleaned_data
            try:
                c.editar_evidencia().ejecutar(
                    auditoria.id,
                    codigo,
                    DatosEvidencia(
                        descripcion=d["descripcion"],
                        fuente=d["fuente"],
                        fecha=d["fecha"],
                        es_simulada=d["es_simulada"],
                        referencia=d["referencia"],
                    ),
                )
                messages.success(request, f"Evidencia {codigo} actualizada.")
                return redirect("evaluar_control", id_auditoria=auditoria.id, id_control=id_control)
            except ErrorDeDominio as e:
                form.aplicar_error(e)
    else:
        form = EvidenciaEdicionForm(
            tiene_archivo=bool(evidencia.archivo_id),
            initial={
                "descripcion": evidencia.descripcion,
                "fuente": evidencia.fuente,
                "fecha": evidencia.fecha,
                "referencia": evidencia.referencia,
                "es_simulada": evidencia.es_simulada,
            },
        )
    return render(
        request,
        "drakon/evidencia_form.html",
        {
            "a": auditoria,
            "x": evidencia,
            "form": form,
            "id_control": id_control,
            "editable": auditoria.estado == EstadoAuditoria.EN_EJECUCION,
        },
    )


@con_auditoria
def evidencia_archivo(request, auditoria, codigo):
    try:
        archivo = c.archivo_evidencia().ejecutar(auditoria.id, codigo)
    except NoEncontrado:
        raise Http404 from None
    resp = HttpResponse(archivo.contenido, content_type=archivo.tipo)
    resp["Content-Disposition"] = f'inline; filename="{archivo.nombre}"'
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


# ------------------------------------------- hallazgos y recomendaciones (RF05/RF06)
def _controles_para_hallazgo(auditoria):
    return [
        (e.id_control, f"{e.codigo_control} · {e.nombre_control} ({e.estado.etiqueta})")
        for e in auditoria.evaluaciones
        if e.evaluada and e.estado != EstadoEvaluacion.NO_APLICABLE
    ]


@con_auditoria
def hallazgos(request, auditoria):
    controles = c.catalogo().obtener_varios(auditoria.ids_controles)
    filas = [(h, controles.get(h.id_control)) for h in auditoria.hallazgos]
    return render(
        request,
        "drakon/hallazgos.html",
        {
            "a": auditoria,
            "filas": filas,
            "form_rec": RecomendacionForm(),
            "editable": auditoria.estado in (EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION),
            "problemas_cierre": auditoria.problemas_para_cierre(),
        },
    )


@con_auditoria
def hallazgo_nuevo(request, auditoria):
    opciones = _controles_para_hallazgo(auditoria)
    controles = c.catalogo().obtener_varios(auditoria.ids_controles)
    if request.method == "POST":
        form = HallazgoForm(request.POST, controles=opciones)
        if form.is_valid():
            d = form.cleaned_data
            try:
                h = c.registrar_hallazgo().ejecutar(
                    auditoria.id,
                    DatosHallazgo(
                        id_control=d["id_control"],
                        condicion=d["condicion"],
                        criterio=d["criterio"],
                        causa=d["causa"],
                        efecto=d["efecto"],
                        severidad=d["severidad"],
                        recomendacion=d["recomendacion"],
                        prioridad=d["prioridad"] or None,
                        plazo_dias=d["plazo_dias"],
                    ),
                )
                messages.success(
                    request, f"Hallazgo {h.codigo} registrado{' con su recomendación' if h.recomendaciones else ''}."
                )
                return redirect("hallazgos", id_auditoria=auditoria.id)
            except ErrorDeDominio as e:
                form.aplicar_error(e)
    else:
        id_control = request.GET.get("control")
        inicial = {}
        if id_control and id_control.isdigit() and int(id_control) in controles:
            ctrl = controles[int(id_control)]
            inicial = {
                "id_control": ctrl.id,
                "criterio": f"ISO/IEC 27002:2022, control {ctrl.codigo} ({ctrl.nombre}): {ctrl.descripcion}",
            }
        form = HallazgoForm(initial=inicial, controles=opciones)
    criterios = {
        cid: f"ISO/IEC 27002:2022, control {ctrl.codigo} ({ctrl.nombre}): {ctrl.descripcion}"
        for cid, ctrl in controles.items()
    }
    return render(
        request,
        "drakon/hallazgo_form.html",
        {
            "a": auditoria,
            "form": form,
            "criterios": criterios,
            "sin_controles": not opciones,
            "editable": auditoria.estado in (EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION),
        },
    )


@con_auditoria
def hallazgo_editar(request, auditoria, codigo):
    try:
        h = auditoria.hallazgo(codigo)
    except NoEncontrado:
        raise Http404 from None
    opciones = _controles_para_hallazgo(auditoria)
    controles = c.catalogo().obtener_varios(auditoria.ids_controles)
    if request.method == "POST":
        form = HallazgoForm(request.POST, controles=opciones, edicion=True)
        if form.is_valid():
            d = form.cleaned_data
            try:
                c.editar_hallazgo().ejecutar(
                    auditoria.id,
                    codigo,
                    DatosHallazgo(
                        id_control=d["id_control"],
                        condicion=d["condicion"],
                        criterio=d["criterio"],
                        causa=d["causa"],
                        efecto=d["efecto"],
                        severidad=d["severidad"],
                    ),
                )
                messages.success(request, f"Hallazgo {codigo} actualizado.")
                return redirect(reverse("hallazgos", args=[auditoria.id]) + f"#{codigo}")
            except ErrorDeDominio as e:
                form.aplicar_error(e)
    else:
        form = HallazgoForm(
            controles=opciones,
            edicion=True,
            initial={
                "id_control": h.id_control,
                "severidad": h.severidad.value,
                "condicion": h.condicion,
                "criterio": h.criterio,
                "causa": h.causa,
                "efecto": h.efecto,
            },
        )
    criterios = {
        cid: f"ISO/IEC 27002:2022, control {ctrl.codigo} ({ctrl.nombre}): {ctrl.descripcion}"
        for cid, ctrl in controles.items()
    }
    return render(
        request,
        "drakon/hallazgo_form.html",
        {
            "a": auditoria,
            "form": form,
            "criterios": criterios,
            "sin_controles": not opciones,
            "hallazgo": h,
            "editable": auditoria.estado in (EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION),
        },
    )


@con_auditoria
def hallazgo_eliminar(request, auditoria, codigo):
    try:
        h = auditoria.hallazgo(codigo)
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        try:
            c.eliminar_hallazgo().ejecutar(auditoria.id, codigo)
            messages.success(request, f"Hallazgo {codigo} eliminado con sus recomendaciones.")
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
        return redirect("hallazgos", id_auditoria=auditoria.id)
    return confirmar(
        request,
        f"¿Eliminar el hallazgo {codigo}?",
        h.condicion,
        [f"{len(h.recomendaciones)} recomendación(es) asociada(s)", "Los demás hallazgos conservan su código"],
        reverse("hallazgos", args=[auditoria.id]),
    )


@con_auditoria
def recomendacion_editar(request, auditoria, codigo):
    try:
        h, r = auditoria.recomendacion(codigo)
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        form = RecomendacionForm(request.POST)
        if form.is_valid():
            try:
                c.editar_recomendacion().ejecutar(
                    auditoria.id,
                    codigo,
                    form.cleaned_data["recomendacion"],
                    form.cleaned_data["prioridad"],
                    form.cleaned_data["plazo_dias"],
                )
                messages.success(request, f"Recomendación {codigo} actualizada.")
                return redirect(reverse("hallazgos", args=[auditoria.id]) + f"#{h.codigo}")
            except ErrorDeDominio as e:
                form.aplicar_error(e)
    else:
        form = RecomendacionForm(
            initial={"recomendacion": r.descripcion, "prioridad": r.prioridad.value, "plazo_dias": r.plazo_dias}
        )
    return render(
        request,
        "drakon/recomendacion_form.html",
        {
            "a": auditoria,
            "h": h,
            "r": r,
            "form": form,
            "editable": auditoria.estado in (EstadoAuditoria.EN_EJECUCION, EstadoAuditoria.EN_REVISION),
        },
    )


@con_auditoria
def recomendacion_eliminar(request, auditoria, codigo):
    try:
        h, r = auditoria.recomendacion(codigo)
    except NoEncontrado:
        raise Http404 from None
    if request.method == "POST":
        try:
            c.eliminar_recomendacion().ejecutar(auditoria.id, codigo)
            messages.success(request, f"Recomendación {codigo} eliminada.")
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
        return redirect(reverse("hallazgos", args=[auditoria.id]) + f"#{h.codigo}")
    consecuencias = (
        ["Para cerrar la auditoría, cada hallazgo necesita al menos una recomendación"]
        if len(h.recomendaciones) == 1
        else []
    )
    return confirmar(
        request,
        f"¿Eliminar la recomendación {codigo} del hallazgo {h.codigo}?",
        r.descripcion,
        consecuencias,
        reverse("hallazgos", args=[auditoria.id]),
    )


@require_POST
@con_auditoria
def recomendacion_agregar(request, auditoria, codigo):
    form = RecomendacionForm(request.POST)
    if form.is_valid():
        try:
            r = c.agregar_recomendacion().ejecutar(
                auditoria.id,
                codigo,
                form.cleaned_data["recomendacion"],
                form.cleaned_data["prioridad"],
                form.cleaned_data["plazo_dias"],
            )
            messages.success(request, f"Recomendación {r.codigo} agregada al hallazgo {codigo}.")
        except ErrorDeDominio as e:
            messages.error(request, e.mensaje)
    else:
        errores = "; ".join(e for lista in form.errors.values() for e in lista)
        messages.error(request, f"No se agregó la recomendación: {errores}")
    return redirect("hallazgos", id_auditoria=auditoria.id)


# --------------------------------------------------- informe PDF (RF08)
@require_POST
@con_auditoria
def informe_generar(request, auditoria):
    try:
        informe = c.generar_informe().ejecutar(auditoria.id)
        messages.success(request, f"Informe versión {informe.version} generado a partir de los datos registrados.")
    except ErrorDeDominio as e:
        messages.error(request, e.mensaje)
    return redirect("auditoria_detalle", id_auditoria=auditoria.id)


@login_required
def informe_pdf(request, id_informe):
    try:
        informe, contenido = c.descargar_informe_pdf().ejecutar(id_informe)
        auditoria = c.auditorias().obtener(informe.id_auditoria)
    except NoEncontrado:
        raise Http404 from None
    if auditoria.id_auditor != request.user.id and not es_admin(request.user):
        raise PermissionDenied("No tiene acceso a este informe.")
    resp = HttpResponse(contenido, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="informe_auditoria_{auditoria.id}_v{informe.version}.pdf"'
    return resp
