from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("salud/", views.salud, name="salud"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("catalogo/nuevo/", views.control_nuevo, name="control_nuevo"),
    path("catalogo/<int:id_control>/editar/", views.control_editar, name="control_editar"),
    path("catalogo/<int:id_control>/eliminar/", views.control_eliminar, name="control_eliminar"),
    path("auditorias/", views.auditoria_lista, name="auditoria_lista"),
    path("auditorias/nueva/", views.auditoria_crear, name="auditoria_crear"),
    path("auditorias/<int:id_auditoria>/", views.auditoria_detalle, name="auditoria_detalle"),
    path("auditorias/<int:id_auditoria>/editar/", views.auditoria_editar, name="auditoria_editar"),
    path("auditorias/<int:id_auditoria>/eliminar/", views.auditoria_eliminar, name="auditoria_eliminar"),
    path("auditorias/<int:id_auditoria>/estado/", views.auditoria_estado, name="auditoria_estado"),
    path("auditorias/<int:id_auditoria>/controles/", views.controles_seleccion, name="controles_seleccion"),
    path("auditorias/<int:id_auditoria>/evaluar/", views.evaluar_inicio, name="evaluar_inicio"),
    path("auditorias/<int:id_auditoria>/evaluar/<int:id_control>/", views.evaluar_control, name="evaluar_control"),
    path("auditorias/<int:id_auditoria>/evaluar/<int:id_control>/evidencias/", views.evidencia_agregar, name="evidencia_agregar"),
    path("auditorias/<int:id_auditoria>/evidencias/<str:codigo>/eliminar/", views.evidencia_eliminar, name="evidencia_eliminar"),
    path("auditorias/<int:id_auditoria>/evidencias/<str:codigo>/editar/", views.evidencia_editar, name="evidencia_editar"),
    path("auditorias/<int:id_auditoria>/evidencias/<str:codigo>/archivo/", views.evidencia_archivo, name="evidencia_archivo"),
    path("auditorias/<int:id_auditoria>/hallazgos/", views.hallazgos, name="hallazgos"),
    path("auditorias/<int:id_auditoria>/hallazgos/nuevo/", views.hallazgo_nuevo, name="hallazgo_nuevo"),
    path("auditorias/<int:id_auditoria>/hallazgos/<str:codigo>/editar/", views.hallazgo_editar, name="hallazgo_editar"),
    path("auditorias/<int:id_auditoria>/hallazgos/<str:codigo>/eliminar/", views.hallazgo_eliminar, name="hallazgo_eliminar"),
    path("auditorias/<int:id_auditoria>/hallazgos/<str:codigo>/recomendaciones/", views.recomendacion_agregar, name="recomendacion_agregar"),
    path("auditorias/<int:id_auditoria>/recomendaciones/<str:codigo>/editar/", views.recomendacion_editar, name="recomendacion_editar"),
    path("auditorias/<int:id_auditoria>/recomendaciones/<str:codigo>/eliminar/", views.recomendacion_eliminar, name="recomendacion_eliminar"),
    path("auditorias/<int:id_auditoria>/informe/", views.informe_generar, name="informe_generar"),
    path("informes/<int:id_informe>/pdf/", views.informe_pdf, name="informe_pdf"),
]
