# H14 — Biblioteca básica de grabaciones

La biblioteca enumera metadatos de la carpeta fija de grabaciones; todavía no
certifica integridad, decodifica, reproduce, borra ni importa medios. La presencia
de un MKV y el final de un output no equivalen a una grabación verificada.

## Contrato compartido

UI, CLI y MCP consultan la misma `Production::recordings_snapshot()`. La UI abre
el panel «Grabaciones» desde el icono de carpeta de la barra superior, actualiza la
lista y permite solicitar que Finder seleccione un archivo.

```sh
Motive.app/Contents/MacOS/motive ctl '{"op":"refresh_recordings"}'
Motive.app/Contents/MacOS/motive ctl '{"op":"recordings"}'
```

Los nombres MCP son `refresh_recordings` y `recordings`, ambos sin argumentos.
El primero admite un trabajo y devuelve el estado normal del núcleo; el segundo
devuelve `{ok,pid,revision,recordings}`. Consultar hasta `phase` `ready` o `error`.
No se aceptan rutas, directorios, límites ni campos extra. `recordings` es una
consulta repetible; el transporte no repite automáticamente `refresh_recordings`.

El snapshot versión 1 incluye `directory`, `phase` (`idle`, `scanning`, `ready`,
`error`), `error`, `observed_unix_ms`, límites, contadores e `items`. Cada item
contiene `id` (basename), `bytes`, `modified_unix_ms`, `state`, `failure_code`,
`attempt_id` y `media_verified:false`. La revisión pertenece al control de la
producción; `observed_unix_ms` identifica la lectura de metadatos. Un error al
refrescar conserva la lista anterior con su fecha y declara `phase:error`.

| Estado | Evidencia disponible |
| --- | --- |
| `writing` | La ruta coincide con la salida actual y su worker nativo sigue ocupado. |
| `finalizing` | La salida actual sigue ocupada y solicitó cancelación, se detiene o tiene un fallo. |
| `error` | La salida actual ya no está ocupada y conserva fallo o recuperación pendiente. |
| `closed_unverified` | No hay salida actual activa asociada; el contenido no está verificado. |

`closed_unverified` no asegura que otro proceso no use el archivo. Los archivos
de ejecuciones previas no heredan una afirmación de éxito ni una asociación de
intento inventada. `failure_code` se conserva durante finalización si corresponde.
No hay estado `complete` ni `verified` en este incremento.

## Acceso acotado y cierre

`Library::refresh` crea un único worker de metadatos: examina como máximo 1024
entradas y devuelve como máximo 100 archivos. Ordena por modificación descendente
dentro del subconjunto examinado; una lista truncada no garantiza los 100 archivos
más recientes de toda la carpeta. `omitted_entries` cuenta omisiones observadas,
no entradas que quedaron fuera del límite de exploración.

Solo admite `motive-<1..24 dígitos>.mkv` bajo `paths::recordings_dir()`. Abre cada
componente del directorio con `openat/O_NOFOLLOW`, enumera mediante descriptor y
usa `fstatat/AT_SYMLINK_NOFOLLOW`. Rechaza enlaces simbólicos, enlaces duros,
directorios, FIFOs y otros tipos; no lee contenido del archivo. Un directorio
configurado que contiene un componente simbólico se declara no disponible.

La consulta de Finder se prepara fuera del hilo UI con un descriptor macOS
`O_EVTONLY`, verificación de tipo, número de enlaces e identidad de inode antes y
después de abrir. La UI entrega únicamente el path validado a la API oficial
GPUI `App::reveal_path`, que delega a `NSWorkspace` para selección en Finder.
No usa shell, AppleScript ni abre/reproduce el medio. Conserva los descriptores
hasta despachar la solicitud. Esto no pretende crear un sandbox frente a otro
proceso del mismo usuario que renombre archivos después de la comprobación.

`Production` rechaza refresh en ambas fases de cierre y sigue haciendo `poll`
hasta `!Library::busy()`. La UI espera además el worker de reveal y cancela el
despacho a Finder si comenzó el cierre. Ningún `Drop` hace join bloqueante.

Errores estructurados: `RECORDING_SCAN_BUSY`, `RECORDING_SCAN_UNAVAILABLE`,
`RECORDING_SCAN_FAILED`, `RECORDINGS_DIRECTORY_INVALID`,
`RECORDINGS_DIRECTORY_UNAVAILABLE`, `INVALID_RECORDING_ID`,
`RECORDING_UNAVAILABLE`, `RECORDING_UNSAFE_ENTRY`. No se incluyen rutas del SO ni
contenido arbitrario en mensajes de error.

## Verificación y límites

Los tests de dominio cubren traversal/campos extra, enlaces simbólicos y duros,
tipos no regulares, límites, proyección de estados y drenaje del worker. No
representan grabaciones reales ni validación del selector de Finder.

`cargo test --quiet`: 82/82 PASS; `cargo clippy --all-targets -- -D warnings` y
`git diff --check`: PASS. Los hashes de fuentes, binario de tests y revisión
están en `var/evidence/h14-recordings-domain-1794950778116030000/checks.json`.
Ese registro conserva también el primer fallo de compilación de una declaración
nativa concurrente, corregido antes de la ejecución satisfactoria. No se
reconstruyó ni abrió el bundle firmado durante estos checks.

La validación de reproducción/integridad necesitará un job explícito con un
resultado ligado a identidad y modificación del archivo. Duración, thumbnails,
playback, borrado y migración de archivos quedan fuera de esta biblioteca básica.
La verificación física de navegación, cierre con worker y selección visible en
Finder se registra en el informe general H14; no se declara aprobada aquí.

Referencia oficial inspeccionada en dependencias fijadas: GPUI pre 0.3.12,
`src/app.rs::reveal_path`; macOS, `src/platform.rs::reveal_path` invoca
`NSWorkspace::selectFile_inFileViewerRootedAtPath`.
