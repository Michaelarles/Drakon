<<<<<<< HEAD
# DRAKON

![Drakon](src/drakon/infraestructura/web/static/drakon/avatar/logo_completo.png)

Sistema de Gestión de Auditorías de Sistemas de Información (proyecto académico, Ingeniería de Sistemas).
Apoya una auditoría básica de seguridad de la información con ISO/IEC 27002:2022: configurar la auditoría, seleccionar controles, evaluarlos, registrar evidencias, documentar hallazgos y recomendaciones y generar el informe consolidado.

## Arquitectura hexagonal

```
infraestructura  →  aplicación  →  dominio        (las dependencias apuntan hacia el centro)
```

| Capa | Carpeta | Contenido |
|---|---|---|
| Dominio | `src/drakon/dominio/` | Agregados `Auditoria`, `Control` e `Informe`, estados, reglas de negocio e indicadores. Python puro. |
| Aplicación | `src/drakon/aplicacion/` | `puertos/` (interfaces) y `casos_uso/` (una clase por acción del usuario, RF01–RF09). |
| Infraestructura | `src/drakon/infraestructura/` | Adaptadores: `web/` (Django), `persistencia/` (ORM + PostgreSQL), `evidencias/`, `pdf/` y `contenedor.py` (inyección de dependencias). |

La regla de dependencia se verifica automáticamente:

```bash
PYTHONPATH=src lint-imports
```

## Ejecutar en local

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DEBUG=true                                       # Windows: set DEBUG=true
python manage.py migrate
python manage.py inicializar                            # roles + 93 controles ISO 27002
python manage.py createsuperuser
python manage.py cargar_empresa_abc --usuario ana --clave "Prueba-2026!"   # datos de la demo
python manage.py runserver
```

Sin `DATABASE_URL` se usa SQLite; con ella, PostgreSQL. **Plan B con Docker:** `docker compose up --build` levanta la app y su PostgreSQL en http://localhost:8000 (usuario `admin`, clave `Admin-2026!`).

## Pruebas

```bash
pytest                    # unitarias, de integración y de aceptación (CP-01 a CP-13)
PYTHONPATH=src lint-imports
```

- `tests/unit/`: dominio y casos de uso con adaptadores en memoria (sin base de datos).
- `tests/integracion/`: repositorios y restricciones CHECK/UNIQUE en la base de datos.
- `tests/aceptacion/`: flujo por HTTP.

Para probar contra PostgreSQL: `DATABASE_URL=postgresql://... pytest`.

## Despliegue (planes gratuitos)

| Componente | Servicio |
|---|---|
| Aplicación | Render, Web Service gratuito (Docker), con `render.yaml` |
| Base de datos | Neon, plan Free (PostgreSQL, sin vencimiento) |
| Evidencias | En PostgreSQL (máx. 5 MB; PDF, PNG o JPG) |
| Disponibilidad | Monitor HTTP gratuito llamando a `/salud/` cada 10 minutos |

1. **Neon:** crear el proyecto `drakon` y copiar el *connection string* (`postgresql://...?sslmode=require`).
2. **Render:** *New → Blueprint* → elegir este repositorio. Render lee `render.yaml` y pide:
   - `DATABASE_URL`: el connection string de Neon.
   - `DJANGO_SUPERUSER_USERNAME` y `DJANGO_SUPERUSER_PASSWORD`: el administrador inicial.
3. Cada `git push` a `main` redespliega. El contenedor migra, ejecuta `inicializar` y arranca gunicorn.
4. **Datos de la demo:** el plan gratuito de Render no tiene consola. Define `DEMO_USUARIO` y `DEMO_CLAVE` en Render y, al arrancar, se carga Empresa ABC, solo si la base no tiene auditorías.
5. **Monitor:** UptimeRobot o cron-job.org → `https://<app>.onrender.com/salud/` cada 10 minutos.

**Antes de la sustentación:** respaldo con `pg_dump "$DATABASE_URL" > respaldo.dump`, revisar el monitor y abrir la URL 5 minutos antes.

## Identidad visual (propuesta «Brasa» + aviso naranja)

| Token | Color | Uso |
|---|---|---|
| Naranja Drakon | `#F47721` | Botones principales y aviso de inicio. Siempre con **texto carbón** (5,6:1), nunca blanco. |
| Ember | `#B4531A` | Enlaces y texto naranja sobre fondos claros (5,0:1). |
| Charcoal | `#252321` | Textos y botones secundarios. |
| Warm White / Sand / Peach | `#F7F5F1` / `#EAE4DC` / `#FCE9DA` | Fondo general, superficies y resaltados. |
| Success / Amber / Flame | `#287A56` / `#FFB84D` / `#E84932` | Implementado / Parcial / No implementado (siempre con símbolo y texto). |

- Tipografía: Plus Jakarta Sans, incluida en el proyecto. Bootstrap y los íconos también se sirven localmente, sin depender de CDN.
- Avatar: `static/drakon/avatar/`. Hay **máximo un Drakon por pantalla**, y nunca junto a tablas de datos de hallazgos. Poses: `bienvenida` (ingreso), `hero` (aviso de inicio), `vacio` (estados vacíos), `error` (bloqueos), `listo` (confirmaciones), `ayuda` (consejos), `celebracion` (auditoría cerrada).
- Estilos: `static/drakon/drakon.css`.

## Roles (RNF04)

- **auditor:** gestiona solo sus auditorías.
- **admin:** ve todas las auditorías y edita el catálogo de controles en `/admin/`. El usuario necesita `is_staff` para entrar al admin.

## Matriz CRUD

Todas las entidades tienen sus cuatro operaciones. Lo que cambia por entidad son las reglas del proceso auditor que las limitan.

| Entidad | Crear | Consultar | Editar | Eliminar | Reglas |
|---|---|---|---|---|---|
| Auditoría | ✅ | ✅ lista, detalle, inicio | ✅ en borrador o ejecución | ✅ con confirmación | Una auditoría **cerrada** no se elimina ni se edita. |
| Control (catálogo) | ✅ rol admin | ✅ todos | ✅ rol admin | ✅ rol admin | Código único. No se elimina si una auditoría lo usa. |
| Selección de controles | ✅ | ✅ | ✅ en borrador | ✅ al desmarcarlo | Entre 10 y 15 para iniciar la ejecución. |
| Evaluación de control | ✅ | ✅ | ✅ en ejecución | — | La evaluación se corrige; no se borra. «No aplicable» exige justificación. |
| Evidencia | ✅ | ✅ y descarga | ✅ en ejecución | ✅ con confirmación | Archivo PDF/PNG/JPG validado o referencia. |
| Hallazgo | ✅ | ✅ | ✅ en ejecución o revisión | ✅ con confirmación | Conserva su código H-nn; no aplica a controles «No aplicable». |
| Recomendación | ✅ | ✅ | ✅ en ejecución o revisión | ✅ con confirmación | Cada hallazgo necesita al menos una para cerrar. |
| Informe | ✅ genera versiones | ✅ PDF | — | — | Es una instantánea: no se edita, se emite una nueva versión. |

Ninguna eliminación ocurre con un GET: siempre hay una página de confirmación que muestra lo que se afecta. Cada auditor solo ve y modifica sus propias auditorías (RNF04).

## Estado del avance

| Requisito | Dominio y casos de uso | Interfaz web |
|---|---|---|
| RF01 Registrar auditoría | ✅ | ✅ |
| RF02 Gestionar y seleccionar controles | ✅ | ✅ |
| RF03 Evaluar controles | ✅ | ✅ |
| RF04 Registrar evidencias | ✅ | ✅ (archivo o referencia; valida el tipo real del archivo) |
| RF05/RF06 Hallazgos y recomendaciones | ✅ | ✅ |
| RF07 Indicadores | ✅ | ✅ (dashboard y detalle) |
| RF08 Informe PDF | ✅ | ✅ (botón en el detalle; versiones preliminares y final) |
| RF09 Dashboard | ✅ | ✅ |

> Los indicadores son descriptivos: no constituyen certificación ni sustituyen el juicio profesional del auditor. Todos los datos de Empresa ABC son ficticios.
=======
# Drakon
Software de auditoria de sistemas
>>>>>>> 3267b94fcdebf07d6177eef3be30147c9f4ffa49
