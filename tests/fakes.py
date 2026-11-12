"""Adaptadores en memoria: implementan los puertos sin base de datos.

Demuestran la ventaja de la arquitectura hexagonal: los casos de uso se prueban
sin Django ni PostgreSQL. También sirven para trabajar la interfaz en paralelo.
"""

import copy
import itertools
import json
from datetime import date
from pathlib import Path

from drakon.aplicacion.puertos import ArchivoAdjunto
from drakon.dominio.catalogo import Control
from drakon.dominio.errores import NoEncontrado

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "controles_iso27002.json"


class RepoAuditoriasMemoria:
    def __init__(self):
        self._datos, self._ids = {}, itertools.count(1)

    def guardar(self, auditoria):
        if auditoria.id is None:
            auditoria.id = next(self._ids)
        self._datos[auditoria.id] = copy.deepcopy(auditoria)
        return copy.deepcopy(auditoria)

    def obtener(self, id_auditoria):
        if id_auditoria not in self._datos:
            raise NoEncontrado("La auditoría no existe.")
        return copy.deepcopy(self._datos[id_auditoria])

    def listar(self, id_auditor=None):
        res = [copy.deepcopy(a) for a in self._datos.values() if id_auditor in (None, a.id_auditor)]
        return sorted(res, key=lambda a: a.id, reverse=True)

    def eliminar(self, id_auditoria):
        self._datos.pop(id_auditoria, None)


class RepoCatalogoMemoria:
    def __init__(self):
        datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self._controles = {i: Control(id=i, **d) for i, d in enumerate(datos, start=1)}

    def listar(self, categoria=None, texto=None):
        return [c for c in self._controles.values() if categoria in (None, c.categoria)]

    def obtener_varios(self, ids):
        return {i: self._controles[i] for i in ids if i in self._controles}

    def obtener(self, id_control):
        if id_control not in self._controles:
            raise NoEncontrado("El control no existe.")
        return self._controles[id_control]

    def guardar(self, control):
        if control.id is None:
            control.id = max(self._controles) + 1
        self._controles[control.id] = control
        return control

    def eliminar(self, id_control):
        self._controles.pop(id_control, None)

    def existe_codigo(self, codigo, excluir_id=None):
        return any(c.codigo.lower() == codigo.lower() and c.id != excluir_id for c in self._controles.values())

    def en_uso(self, id_control):
        return id_control in getattr(self, "usados", set())

    def por_codigo(self, codigo):
        return next(c for c in self._controles.values() if c.codigo == codigo)


class RepoInformesMemoria:
    def __init__(self):
        self._datos, self._ids = {}, itertools.count(1)

    def guardar(self, informe):
        from dataclasses import replace

        informe = replace(informe, id=next(self._ids))
        self._datos[informe.id] = informe
        return informe

    def obtener(self, id_informe):
        return self._datos[id_informe]

    def listar(self, id_auditoria):
        return [i for i in self._datos.values() if i.id_auditoria == id_auditoria]

    def ultima_version(self, id_auditoria):
        return max((i.version for i in self.listar(id_auditoria)), default=0)


class AlmacenMemoria:
    def __init__(self):
        self.archivos, self._ids = {}, itertools.count(1)

    def guardar(self, archivo: ArchivoAdjunto) -> str:
        clave = f"arch-{next(self._ids)}"
        self.archivos[clave] = archivo
        return clave

    def obtener(self, archivo_id):
        return self.archivos[archivo_id]

    def eliminar(self, archivo_id):
        self.archivos.pop(archivo_id, None)


class UsuariosMemoria:
    def nombre(self, id_usuario):
        return f"Auditor {id_usuario}"


class PDFFalso:
    def generar(self, contenido):
        return b"%PDF-falso " + contenido["auditoria"]["organizacion"].encode()


# Los 13 controles y estados del ejemplo de Empresa ABC
EJEMPLO_ABC = [
    ("5.1", "IMPLEMENTADO"),
    ("5.15", "IMPLEMENTADO"),
    ("5.18", "PARCIAL"),
    ("5.24", "NO_IMPLEMENTADO"),
    ("6.3", "PARCIAL"),
    ("7.2", "IMPLEMENTADO"),
    ("8.5", "PARCIAL"),
    ("8.7", "IMPLEMENTADO"),
    ("8.8", "NO_IMPLEMENTADO"),
    ("8.13", "PARCIAL"),
    ("8.15", "NO_IMPLEMENTADO"),
    ("8.23", "PARCIAL"),
    ("8.31", "NO_APLICABLE"),
]

DATOS_ABC = dict(
    organizacion="Empresa ABC (ficticia)",
    objetivo="Evaluar el estado de implementación de 13 controles de ISO/IEC 27002:2022.",
    alcance="Servidores, estaciones de trabajo, aplicaciones, bases de datos de clientes y red corporativa.",
    fecha_inicio=date(2026, 11, 9),
    fecha_fin=date(2026, 11, 20),
)
