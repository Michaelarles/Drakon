"""Formularios web: validan formato en el servidor (RNF03). Las reglas de negocio las valida el dominio."""
from django import forms

from drakon.dominio.errores import ErrorDeDominio


class FormularioBase(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            clase = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            campo.widget.attrs.setdefault("class", clase)

    def aplicar_error(self, error: ErrorDeDominio) -> None:
        """Muestra un error del dominio junto al campo que lo causó."""
        campo = error.campo if error.campo in self.fields else None
        self.add_error(campo, error.mensaje)


class AuditoriaForm(FormularioBase):
    organizacion = forms.CharField(label="Organización", max_length=120)
    objetivo = forms.CharField(label="Objetivo", widget=forms.Textarea(attrs={"rows": 3}))
    alcance = forms.CharField(label="Alcance", widget=forms.Textarea(attrs={"rows": 3}))
    fecha_inicio = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fecha_fin = forms.DateField(label="Fecha de cierre", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    referentes = forms.CharField(
        label="Referentes normativos", required=False,
        initial="ISO 19011:2018; ISO/IEC 27001:2022; ISO/IEC 27002:2022",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        datos = super().clean()
        ini, fin = datos.get("fecha_inicio"), datos.get("fecha_fin")
        if ini and fin and fin < ini:
            self.add_error("fecha_fin", "La fecha de cierre debe ser igual o posterior a la de inicio.")
        return datos


# ------------------------------------------------------------- RF03
ESTADOS_EVALUACION = [
    ("IMPLEMENTADO", "Implementado"),
    ("PARCIAL", "Parcialmente implementado"),
    ("NO_IMPLEMENTADO", "No implementado"),
    ("NO_APLICABLE", "No aplicable"),
]


class EvaluacionForm(FormularioBase):
    estado = forms.ChoiceField(label="Estado de implementación", choices=ESTADOS_EVALUACION,
                               widget=forms.RadioSelect,
                               error_messages={"required": "Seleccione uno de los cuatro estados."})
    observacion = forms.CharField(label="Observación del auditor", widget=forms.Textarea(attrs={"rows": 3}))
    justificacion_na = forms.CharField(label="Justificación de «No aplicable»", required=False,
                                       widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].widget.attrs.pop("class", None)

    def clean(self):
        datos = super().clean()
        if datos.get("estado") == "NO_APLICABLE" and not (datos.get("justificacion_na") or "").strip():
            self.add_error("justificacion_na", "Un control «No aplicable» exige justificación.")
        return datos


# ------------------------------------------------------------- RF04
FUENTES = [("Documental", "Documental"), ("Entrevista", "Entrevista"), ("Observación", "Observación directa"),
           ("Técnica", "Prueba técnica / captura"), ("Registro", "Registro del sistema")]


class EvidenciaForm(FormularioBase):
    descripcion = forms.CharField(label="Descripción", max_length=500)
    fuente = forms.ChoiceField(label="Fuente", choices=FUENTES)
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    referencia = forms.CharField(label="Referencia o enlace", required=False, max_length=500,
                                 help_text="Obligatoria si no adjunta un archivo.")
    archivo = forms.FileField(label="Archivo (PDF, PNG o JPG, máx. 5 MB)", required=False)
    es_simulada = forms.BooleanField(label="Evidencia simulada (ejercicio académico)", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["es_simulada"].widget.attrs["class"] = "form-check-input"
        self.fields["archivo"].widget.attrs["accept"] = ".pdf,.png,.jpg,.jpeg"

    def clean(self):
        datos = super().clean()
        if not datos.get("archivo") and not (datos.get("referencia") or "").strip():
            self.add_error("referencia", "Adjunte un archivo o indique una referencia de la evidencia.")
        return datos


# ------------------------------------------------------------- RF05 / RF06
NIVELES = [("ALTA", "Alta"), ("MEDIA", "Media"), ("BAJA", "Baja")]


class RecomendacionForm(FormularioBase):
    recomendacion = forms.CharField(label="Recomendación", widget=forms.Textarea(attrs={"rows": 2}))
    prioridad = forms.ChoiceField(label="Prioridad", choices=NIVELES)
    plazo_dias = forms.IntegerField(label="Plazo sugerido (días)", min_value=1, max_value=730)


class HallazgoForm(FormularioBase):
    id_control = forms.TypedChoiceField(label="Control asociado", coerce=int, choices=[])
    severidad = forms.ChoiceField(label="Severidad", choices=NIVELES)
    condicion = forms.CharField(label="Condición (qué se encontró)", widget=forms.Textarea(attrs={"rows": 2}))
    criterio = forms.CharField(label="Criterio (qué debería ser)", widget=forms.Textarea(attrs={"rows": 2}))
    causa = forms.CharField(label="Causa", widget=forms.Textarea(attrs={"rows": 2}))
    efecto = forms.CharField(label="Efecto o riesgo", widget=forms.Textarea(attrs={"rows": 2}))
    recomendacion = forms.CharField(label="Recomendación", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    prioridad = forms.ChoiceField(label="Prioridad", choices=NIVELES, required=False)
    plazo_dias = forms.IntegerField(label="Plazo sugerido (días)", min_value=1, max_value=730, required=False)

    def __init__(self, *args, controles=(), edicion=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["id_control"].choices = [("", "Seleccione…")] + list(controles)
        if edicion:  # las recomendaciones se editan aparte
            for campo in ("recomendacion", "prioridad", "plazo_dias"):
                del self.fields[campo]

    def clean(self):
        datos = super().clean()
        if "recomendacion" in self.fields and (datos.get("recomendacion") or "").strip():
            if not datos.get("prioridad"):
                self.add_error("prioridad", "Indique la prioridad de la recomendación.")
            if not datos.get("plazo_dias"):
                self.add_error("plazo_dias", "Indique el plazo sugerido en días.")
        return datos


class EvidenciaEdicionForm(EvidenciaForm):
    """Edición de los datos de una evidencia; el archivo adjunto se conserva."""

    def __init__(self, *args, tiene_archivo=False, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["archivo"]
        self.tiene_archivo = tiene_archivo
        if tiene_archivo:
            self.fields["referencia"].help_text = "Opcional: la evidencia ya tiene un archivo adjunto."

    def clean(self):
        datos = forms.Form.clean(self)
        if not self.tiene_archivo and not (datos.get("referencia") or "").strip():
            self.add_error("referencia", "Indique una referencia: esta evidencia no tiene archivo adjunto.")
        return datos


CATEGORIAS = [("ORGANIZACIONAL", "Organizacionales (5)"), ("PERSONAS", "Personas (6)"),
              ("FISICO", "Físicos (7)"), ("TECNOLOGICO", "Tecnológicos (8)")]


class ControlForm(FormularioBase):
    codigo = forms.CharField(label="Código", max_length=10, help_text="Por ejemplo: 8.13")
    nombre = forms.CharField(label="Nombre del control", max_length=200)
    categoria = forms.ChoiceField(label="Categoría", choices=CATEGORIAS)
    descripcion = forms.CharField(label="Criterio / descripción", widget=forms.Textarea(attrs={"rows": 4}))
