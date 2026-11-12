from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from drakon.infraestructura.web.views import IngresoView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", IngresoView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("drakon.infraestructura.web.urls")),
]
