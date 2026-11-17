# H14 — memoria y rendimiento: instrumento y metodología

Estado: **PARTIAL**. Implementados el query nativo explícito y el runner. El
self-test del instrumento está verificado; la matriz de Motive y el soak de
30 minutos necesitan ejecución por el dueño del lock físico. No se afirma
fuga ni ausencia de fuga a partir de RSS o de este self-test.

## Integración y cobertura

`native/memory-diagnostics.h` exporta
`char *motive_memory_diagnostics(void)`: JSON UTF-8 asignado con malloc;
el caller libera mediante `free`/`motive_free`. No depende de un engine OBS,
no abre otro proceso y no guarda estado ni inicia timers. El núcleo expone
`{"op":"memory_diagnostics"}` y el tool MCP de igual nombre, con respuesta
`ok`, `pid`, `revision`, `memory`. La consulta no cambia la revisión.

El bridge se compila con ARC. El JSON se construye dentro de un autoreleasepool
y se copia a un buffer propio antes de salir. No debe llamarse desde el
callback multimedia ni añadirse al polling automático de `status`/GPUI.
`malloc_zone_statistics` puede adquirir locks del allocator. El usuario de
este query controla explícitamente su frecuencia.

| Campo | Medida | Límite de interpretación |
|---|---|---|
| `vm.physical_footprint_bytes` | `task_info(mach_task_self(), TASK_VM_INFO).phys_footprint` | Contabilidad física del proceso; no equivale a RSS |
| `vm.resident_bytes`, `resident_peak_bytes` | Páginas residentes y pico que informa TASK_VM_INFO | Cachés, paginación y memoria compartida impiden inferir fuga |
| `vm.internal_bytes`, `external_bytes`, `compressed_bytes`, `reusable_bytes`, `device_bytes` | Categorías públicas de TASK_VM_INFO | Se superponen; no sumar entre sí ni al footprint |
| `malloc.in_use_bytes` | `size_in_use` de todas las zonas registradas | No cubre allocators independientes, mmap, GPU/IOSurface |
| `malloc.allocated_bytes` | Reserva `size_allocated` del allocator | Reserva retenida no significa objetos vivos |
| `malloc.zone_high_water_touched_sum_bytes` | Suma de `max_size_in_use` de zonas | High-water de memoria tocada; no pico simultáneo de heap vivo |
| `cpu.user_seconds`, `system_seconds` | `getrusage(RUSAGE_SELF)` acumulado | Todos los threads; deltas/tiempo real, 100% equivale a un núcleo |
| `collection_us` | Tiempo de task_info + malloc stats + getrusage | Excluye JSON y transporte; runner mide RPC y status aparte |

Se comprueba el count devuelto por TASK_VM_INFO antes de usar la revisión
correspondiente. Error de kernel/cobertura insuficiente se conserva como
`PARTIAL`, código y valores null. El snapshot no es atómico entre subsistemas.
No hay dumps, contenido de memoria, stacks de asignación ni herramientas
privilegiadas. No se mide utilización GPU; solo se conservan categorías VM.

Referencias primarias: [cabecera pública TASK_VM_INFO de Apple](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/task_info.h),
[cabecera pública malloc de Apple](https://github.com/apple-oss-distributions/libmalloc/blob/main/include/malloc/malloc.h),
[guía Apple de medición de memoria](https://developer.apple.com/documentation/xcode/gathering-information-about-memory-use).
Las firmas/campos se contrastaron también con el SDK macOS instalado.

## Validación aislada del instrumento

```sh
clang -fobjc-arc -Wall -Wextra -Werror -framework Foundation \
  native/memory-diagnostics.m scripts/fixtures/h14_memory_selftest.m \
  -o target/memory-diagnostics/selftest
target/memory-diagnostics/selftest > target/memory-diagnostics/selftest.json
```

El helper no enlaza Motive/libobs ni abre dispositivos. Asigna/toca/libera
16 MiB propios y comprueba que malloc in-use aumenta y después disminuye.
Resultado: **PASS**; incremento **16,781,152 bytes**, descenso
**16,774,272 bytes**. Sobre 30 consultas posteriores, colección nativa
mediana/p95/máximo **63.771/68.584/71.041 µs**; llamada completa más parseo
JSON **82.479/89.750/91.417 µs**. No se trasladan esos costes automáticamente
a una producción activa con muchas zonas y contención.

Evidencia: `target/memory-diagnostics/selftest.json`, SHA-256
`69caeaa0e9fbda72ae026a4bf05f7a39f51d88a723b80de782c960dfce235411`.
Python syntax, `--plan` y Clang con warnings como errores pasan. No se ejecutó
el runner contra Motive en esta fase de preparación.

## Protocolo reproducible

`scripts/verify_h14_memory.py` necesita app ya abierta, su PID comprobado,
lock canónico H14 del checkout y directorio nuevo de evidencia. Nunca
construye, firma, abre, fuerza cierre o reinicia Motive. El proceso MCP es
solo cliente del núcleo existente. No captura dispositivos, envía RTMP externo
ni confirma recuperación automáticamente.

Primero generar la fixture fuera de cualquier ventana de medición:

```sh
python3 scripts/verify_h14_memory.py --prepare-fixture target/memory-fixture.mp4
python3 scripts/verify_h14_memory.py --plan --mode lifecycle --fps 30
```

La fixture es testsrc2 propio de 1080p30/6 s sin audio; queda un manifiesto
con comando y SHA-256. Puede reutilizarse un video H11 propio indicando su
hash conocido. El runner no acepta una ruta sin hash. Para producción se usa
un patrón ya existente, cuatro hijos de video silenciosos, y tono −12 dB
solo al iniciar ambos outputs.

```sh
python3 scripts/verify_h14_memory.py --lock-held --mode lifecycle \
  --app /ruta/Motive.app/Contents/MacOS/motive --store-root /ruta/store \
  --fixture target/memory-fixture.mp4 --fixture-sha256 HASH_VERIFICADO \
  --output var/evidence/h14-memory-lifecycle-01 --fps 30

python3 scripts/verify_h14_memory.py --lock-held --mode dual-soak \
  --app /ruta/Motive.app/Contents/MacOS/motive --store-root /ruta/store \
  --fixture target/memory-fixture.mp4 --fixture-sha256 HASH_VERIFICADO \
  --output var/evidence/h14-memory-dual-01 --fps 30 --soak-seconds 1800
```

Secuencia predeterminada: baseline 20 s; tres ciclos de cuatro videos visibles
20 s, ocultos 20 s y eliminados/settling 60 s. Dual-soak vuelve a crear los
cuatro videos, inicia MKV y receptor RTMP de loopback con VideoToolbox separados,
y observa 1800 s. `--fps 60` es otro experimento, no aceptación heredada de
30 FPS. Para comparación A/B se necesitan owners frescos y carga equivalente.

`--mode observe --soak-seconds N` solo consulta una producción ya configurada;
no modifica fuentes, outputs ni configuración. En los modos que mutan se exige
un owner inicial disposable de patrón/overlay legado, mixer vacío y outputs
quiescentes. Se crean IDs propios y se eliminan tras parar únicamente los
outputs propios. Se restaura escena, variantes, canvas y perfiles seleccionados.
La revisión previa a ejecución corrigió la retirada de capas antes de fuentes:
el núcleo rechaza `remove_source` si sigue referenciado. Se retiran únicamente
capas de la escena creada por el harness; una referencia en una escena ajena
detiene el cleanup para revisión. Un fallo parcial conserva el ID para reintento.
La cancelación usa el intento de salida registrado y `cancel_output_target`,
que también admite connecting; nunca detiene un intento posterior. Se espera
la transición de vuelta a la escena original antes de eliminar la escena propia.
No se guarda proyecto. Los contadores de IDs/migración no retroceden; si no
había endpoint previo, falta API unset y queda elegido el loopback de prueba.
Si lock/owner/quiescencia no se pueden confirmar, se conserva cleanup pendiente
en el informe; no se fuerza liberación de recursos nativos.

Además se exige destino externo sin seleccionar, ningún enrollment pendiente,
sin issues ni animaciones/transición activas. No reutilizar para estas tomas el
owner donde se está introduciendo una clave o probando RTMPS. Preparar un owner
fresco y disposable por configuración, conservando fuera de la prueba los stores
y medios anteriores mediante el procedimiento del owner; el harness no los
vacía ni modifica Keychain. `--store-root` debe señalar el store real del bundle
(desarrollo: `var`; portable: Application Support), con `imports` ya creado y
privado. Un path incorrecto no puede corregirse cambiando el HOME del proceso.

Plan mínimo que cubre ambos FPS sin repetir innecesariamente el lifecycle:

1. Generar/verificar la fixture antes de medir, con SHA-256 conocido. Comprobar
   herramientas del harness (`ffmpeg`, `lsof`) y reservar aproximadamente 5 GB
   libres para dos salidas 4 Mbit/s durante 1800 s, medios y evidencia. Son rutas
   de herramientas de prueba, no dependencias runtime añadidas al producto.
2. Owner fresco 1: `--mode lifecycle --fps 30 --cycles 3 --hold 20 --settle 60
   --interval 5`: 320 s de fases más preparación/cleanup.
3. Owner fresco 2, mismo binario, fixture y visibilidad del estudio:
   `--mode dual-soak --fps 60 --cycles 3 --hold 20 --settle 60 --interval 5
   --soak-seconds 1800`: 320 s de lifecycle más 1800 s de ambas salidas activas.
   Total mínimo de fases de las dos corridas: **2440 s (40 min 40 s)**. No incluye
   importación, arranques, cleanup, relanzamientos ni análisis posterior.
4. Decodificar MKV/RTMP y revisar PTS, audio y píxeles después de medir. El video
   fixture 30 FPS se mantiene idéntico en ambos canvas: la segunda toma evalúa
   composición/salidas a 60 FPS, no cuatro decodificadores de material 60 FPS.

Seis tests offline de `test_h14_memory_harness.py` pasan: orden de retirada,
respeto de referencias ajenas, reintento tras fallo parcial, cancelación en
connecting, protección de intentos posteriores/quiescentes y deltas de CPU.
Son pruebas del harness/contrato; no sustituyen la ejecución real ni dan PASS
de memoria, fuga, salida o rendimiento del producto.

## Presupuesto, análisis y límites

Muestreo predeterminado 5 s, mínimo permitido 1 s. Presupuesto inicial de
observación: p95 nativo ≤2 ms, RPC de memoria ≤20 ms. Umbral de revisión
footprint: 1536 MiB. Son umbrales explícitos de revisión configurables, no
evidencia de fuga ni definición universal de éxito. Se informa cada fase que
los excede. La colección objetivo 2 ms cada 5 s equivale a 0.04% de tiempo de
pared; el coste real incluye JSON/MCP/status y se mide por separado.

`samples.jsonl` conserva memoria, CPU por intervalo, contadores globales y por
output, drops de preview/copias, estado de fuentes, media clocks, diagnósticos
de captura, transición e issues. El JSON resumen contiene mediana/p95/min/max
por fase, deltas de contadores y cambios de attempt; nunca resta contadores
que se reiniciaron. El log MCP mantiene la secuencia de operaciones. No hay
buffer de frames ni sondeo externo a otro task.
El primer delta de CPU al cambiar de fase incluye la operación de transición
(creación/hide/remove); se conserva como `between_phase_cpu_percent` y no entra
en la distribución CPU de la fase siguiente. Una consulta sin cobertura válida
de footprint/CPU aborta con su muestra conservada, en vez de declarar completa
una medición sin esos datos. El timeout del receptor deja status FAIL y conserva
el informe aun si la terminación del proceso propio también falla.

Comparar baseline/visible/hidden/released y ciclos posteriores distingue
recursos vivos, reserva del allocator y páginas residentes, sin demostrar por
sí solo ownership o fugas. Los hijos OBS deben seguir siendo uno por fuente
con `audio_mixers=0`; las muestras preservan sus tiempos/estados al ocultar.
No se hace purge ni presión artificial de memoria para mejorar cifras.

Los archivos MKV y el receptor se conservan con hash. El runner deja
decodificación, PTS/DTS/A-V y frescura de píxeles como **NOT_EVALUATED**: deben
contrastarse después con el verificador multimedia del hito. Un contador de
callbacks, superficie consumida, media clock o archivo existente no cierra
esos gates. El cierre de proyecto, recuperación de dispositivos y la interfaz
GPUI requieren sus pruebas independientes. Los resultados pueden ser
inconclusos sin bloquear automáticamente los gates P0.

## B2 follow-up: hidden playback and packet origin

The initial 1080p30 lifecycle run keeps the original visible → hidden → removed
sequence. B2 explicitly sets OBS FFmpeg `restart_on_activate=false` and
`close_when_inactive=false`; upstream `ffmpeg_source_deactivate` only stops the
player when restart-on-activate is true. Continued playback while hidden is
therefore a configured behavior, not evidence of a leak.

For a controlled follow-up, `--pause-hidden` adds one 20-second phase per cycle
after hiding: the existing `overlay_event(pause)` targets only the four owned
sources, checks their real `media_state=paused`, samples CPU/VM/malloc, then
removes them normally. It changes no automatic product behavior or persisted
configuration. Compare hidden-playing and hidden-paused within the same run.
The 1080p60 dual-soak plan with this option lasts 380 + 1800 seconds plus setup.

Future dual-soak runs also retain output packet traces just after three frames
and after final quiescence, before cleanup. This supports timestamp-origin
correlation; trace coverage must still be checked instead of assuming every
packet survived the bounded ring. The already-running 30 fps lifecycle has no
outputs and is unaffected by these harness additions.
