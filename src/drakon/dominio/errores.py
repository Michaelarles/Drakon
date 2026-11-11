"""Errores del dominio. No dependen de ningún framework."""


class ErrorDeDominio(Exception):
    """Error base del dominio. `campo` indica el dato que lo causó, si aplica."""

    def __init__(self, mensaje: str, campo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campo = campo


class DatoInvalido(ErrorDeDominio):
    """Un dato no cumple el formato o es obligatorio y falta (RNF03)."""


class ReglaDeNegocioViolada(ErrorDeDominio):
    """Una operación no está permitida por las reglas del proceso auditor."""


class NoEncontrado(ErrorDeDominio):
    """El elemento solicitado no existe."""
