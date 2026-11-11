"""Puertos de salida: interfaces que el núcleo necesita y la infraestructura implementa."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from drakon.dominio.auditoria import Auditoria
from drakon.dominio.catalogo import Control
from drakon.dominio.informe import Informe
from drakon.dominio.valores import CategoriaControl


class RepositorioAuditorias(Protocol):
    def obtener(self, id_auditoria: int) -> Auditoria:
        """Devuelve el agregado completo o lanza NoEncontrado."""

    def guardar(self, auditoria: Auditoria) -> Auditoria:
        """Persiste el agregado completo y devuelve la versión con identificadores."""

    def listar(self, id_auditor: int | None = None) -> list[Auditoria]:
        """Auditorías ordenadas de la más reciente a la más antigua."""

    def eliminar(self, id_auditoria: int) -> None:
        """Elimina la auditoría con todo su agregado e informes."""


class RepositorioCatalogo(Protocol):
    def listar(self, categoria: CategoriaControl | None = None, texto: str | None = None) -> list[Control]: ...

    def obtener_varios(self, ids: list[int]) -> dict[int, Control]: ...

    def obtener(self, id_control: int) -> Control: ...

    def guardar(self, control: Control) -> Control: ...

    def eliminar(self, id_control: int) -> None: ...

    def existe_codigo(self, codigo: str, excluir_id: int | None = None) -> bool: ...

    def en_uso(self, id_control: int) -> bool:
        """True si alguna auditoría tiene seleccionado el control."""


class RepositorioInformes(Protocol):
    def guardar(self, informe: Informe) -> Informe: ...

    def obtener(self, id_informe: int) -> Informe: ...

    def listar(self, id_auditoria: int) -> list[Informe]: ...

    def ultima_version(self, id_auditoria: int) -> int: ...


@dataclass(frozen=True)
class ArchivoAdjunto:
    nombre: str
    tipo: str          # tipo MIME
    contenido: bytes


class AlmacenEvidencias(Protocol):
    def guardar(self, archivo: ArchivoAdjunto) -> str:
        """Guarda el archivo y devuelve su identificador."""

    def obtener(self, archivo_id: str) -> ArchivoAdjunto: ...

    def eliminar(self, archivo_id: str) -> None: ...


class GeneradorPDF(Protocol):
    def generar(self, contenido_informe: dict) -> bytes: ...


class DirectorioUsuarios(Protocol):
    def nombre(self, id_usuario: int) -> str: ...
