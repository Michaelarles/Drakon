"""Admin de Django: solo para el catálogo de controles (rol «admin», RNF04)."""

from django.contrib import admin

from .models import ControlModel

admin.site.site_header = "DRAKON · Administración"
admin.site.site_title = "DRAKON"
admin.site.index_title = "Usuarios, roles y catálogo"
admin.site.site_url = "/"


@admin.register(ControlModel)
class ControlAdmin(admin.ModelAdmin):
    list_display = ("codigo_iso", "nombre", "categoria", "fuente")
    list_filter = ("categoria",)
    search_fields = ("codigo_iso", "nombre", "descripcion")
