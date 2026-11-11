"""Agregado Control: catálogo de controles ISO/IEC 27002:2022."""
from dataclasses import dataclass

from .errores import DatoInvalido
from .valores import CategoriaControl


@dataclass
class Control:
    codigo: str
    nombre: str
    categoria: CategoriaControl
    descripcion: str
    fuente: str = "ISO/IEC 27002:2022"
    id: int | None = None

    def __post_init__(self):
        self.codigo = (self.codigo or "").strip()
        self.nombre = (self.nombre or "").strip()
        self.descripcion = (self.descripcion or "").strip()
        if not self.codigo:
            raise DatoInvalido("El código ISO del control es obligatorio.", "codigo")
        if not self.nombre:
            raise DatoInvalido("El nombre del control es obligatorio.", "nombre")
        if not self.descripcion:
            raise DatoInvalido("El criterio o descripción del control es obligatorio.", "descripcion")
        self.categoria = CategoriaControl(self.categoria)

    @property
    def orden(self) -> tuple[int, ...]:
        """Clave para ordenar códigos como 5.2 < 5.10."""
        return tuple(int(p) for p in self.codigo.split(".") if p.isdigit())
