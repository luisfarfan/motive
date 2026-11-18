# H17 — GPUI y GPUI Fast

Fecha: 2026-11-18. Estado de evaluación: **PARTIAL**. Backend de producto:
GPUI Kit 0.10.0 / gpui-pre 0.3.12; GPUI Fast sigue desactivado por defecto.
Los gates de comportamiento visual, foco y accesibilidad tienen que pasar
antes de adoptar un backend. Compilar no los acredita.

## Compatibilidad y build

Kit 0.10.0 expone `gpui-fast` y conmuta sus tipos públicos, Base, Component,
assets y plataforma juntos. Motive usa esas reexportaciones, sin dependencias
directas de tipos GPUI. Se añaden únicamente dos features opt-in:

- `gpui-fast = ["gpui-kit/gpui-fast"]`.
- `ui-profiler = ["gpui-kit/profiler"]`.

La primera resolución falló: Fast requiere wgpu `=30.0.1`, mientras el lock
anterior fijaba 30.0.2. `cargo update -p wgpu --precise 30.0.1` resolvió el grafo
sin parchear librerías. El lock fija la familia gpui-fast en **0.1.17**, y
hdrhistogram 7.6.0 para el profiler. Incluye algunas nuevas selecciones de
aristas windows-sys durante la resolución; no se actualiza GPUI Kit ni el
snapshot upstream. wgpu no compila en estos builds macOS/Metal.

Los primeros builds release A y B completaron en 55,85 s y 74 s. Sus logs
están en `var/evidence/h17-gpui/build-a.log` y `build-b.log`; las compilaciones
posteriores con manifiesto son la identidad utilizada por cada benchmark.
`features-a.txt` y `features-b.txt` conservan los árboles de features ARM64.
Los bindings finales verifican entradas idénticas entre A y B; ARM64 confirmado
por `lipo`. La primera verificación estricta de ambos bundles falló por el
Frameworks symlink externo del esquema de desarrollo. Esos bundles se
conservan en `build-a-final` / `build-b-final`. Se prepararon nuevas copias con
Frameworks clonados APFS dentro del bundle, firma ad hoc y
`codesign --verify --strict` PASS en `build-a-verified` / `build-b-verified`.
Hashes de los ejecutables usados por el benchmark:

- A: `136f72ec039f798099e5a91c6057ad78986e215a55e09cf747ead8d380c34a87`.
- B: `544804ce0b610c4fd57c9884d6cac9bea55841ffa7860c811c8b8a78ff20e0e5`.
El grafo B sigue compilando upstream debido a features aditivas; ello no
significa que la ventana esté usando ambos renderers.

Fuentes oficiales consultadas: [Kit v0.10.0](https://github.com/longbridge/gpui-kit/blob/v0.10.0/website/docs/getting-started.md),
[GPUI Fast](https://github.com/longbridge/gpui-fast), y código publicado de
`gpui-kit-0.10.0`, `gpui-pre-0.3.12` y `gpui-fast-0.1.17` en el registro Cargo,
identificado por los checksums de Cargo.lock.

## Notificaciones, dependencias y límites

`Studio::new` conserva el heartbeat de 33 ms. Cada vuelta ejecuta Show Control,
lifecycle y lectura del nuevo preview; una vez por segundo consulta salud,
importaciones e inventario de dispositivos. La notificación final es
incondicional, aun si la secuencia de preview no avanzó. El mismo Studio es
una sola entidad grande: su `Render` construye los paneles y consulta estado
compartido. La mayoría del layout visible no son vistas independientes
retenibles. Que Fast retenga otras entidades no elimina esa reconstrucción.

Hay datos externos al seguimiento de entidades GPUI: snapshots de libobs,
medidores, progreso de operaciones y duración de outputs. Eliminar `notify()`
solo porque no llegó preview dejaría esos datos obsoletos. No se cambia ni el
heartbeat ni Production, ni se adopta un refactor especulativo.

El backend Fast retiene vistas/layout/texto y conserva contenido de scroll;
en su código macOS está habilitado con Metal. Cambios externos a entidades
necesitan notificación explícita. El diagnóstico oficial
`GPUI_VIEW_RETENTION=0` permite aislar retención; `GPUI_SCROLL_LAYERS=0` aísla
las capas de scroll. Estas variables se eliminan del entorno de la prueba
para comparar los defaults. [Retención](https://github.com/longbridge/gpui-fast/blob/main/docs/retained-mode.md),
[scroll](https://github.com/longbridge/gpui-fast/blob/main/docs/scroll-layers.md).

La implementación 0.1.17 conserva nodos AX al reutilizar subárboles y aplica
invalidación AX; sus listas virtuales desactivan la capa cuando accesibilidad
está activa. Esto es evidencia de diseño del backend, no una prueba de
VoiceOver en Motive. Window Composition es opt-in para contenido nativo:
Motive no la activa ni la requiere para el preview. Browser Engine conserva
su decisión independiente.

## Instrumentación reproducible

`ui-profiler` compila un adaptador pequeño a los histogramas oficiales
`Window::frame_duration_snapshot` / `input_latency_snapshot`. Únicamente con
`MOTIVE_UI_PROFILE=1` escribe una línea JSON por segundo a stderr. No genera
otro timer, reloj audiovisual, RPC ni motor de telemetría. Un build por defecto
excluye este módulo completamente.

Distingue duración de `Window::draw` en el hilo UI (tiempo de pared),
invalidación→presentación, intervalos animados, input→frame y tiempo del
cuerpo del heartbeat antes de `notify()`. No convierte esas duraciones en
CPU del proceso; esta última procede de contadores Mach independientes. Estas métricas no
miden fin de trabajo GPU ni latencia captura→pantalla. Los histogramas se
restan para cada intervalo; falta de inputs es `NOT_EVALUATED`, nunca latencia
cero. Registra notificaciones con/sin preview nuevo sin asumir que una
notificación sin preview sea innecesaria. Retiene hasta 128 muestras de
heartbeat entre lecturas y declara cualquier descarte. El muestreo ocurre
antes del render actual: la última fracción antes del cierre no entra en la
última línea, y una ventana sin renders no produce filas.

El collector reutiliza `memory_diagnostics`, `cpu_interval` y `summarize` de
H14 para CPU, RSS, footprint, memoria comprimida, malloc in-use/allocated,
RPC, preview drops y contadores libobs. CPU 100% equivale a un núcleo.
El collector del patrón consulta memoria/estado cada 0,5 s; esas consultas
también pasan por `Studio::command`, que notifica incluso al leer. Ambos
builds reciben la misma carga, pero este resultado no es CPU idle sin RPC.
El lifecycle usa su intervalo existente de 1 s.
No se equipara RSS o memoria reservada con fuga.

Preparación aislada (no abre la aplicación):

```sh
python3 scripts/h17_gpui_benchmark.py prepare --variant a --output var/evidence/h17-gpui/build-a-final
python3 scripts/h17_gpui_benchmark.py prepare --variant b --output var/evidence/h17-gpui/build-b-final
```

Cada preparación conserva hashes de entradas antes/después del build, hash
binario, módulos nativos, versión de Rust/macOS y comandos. Si cambian las
fuentes durante el build, devuelve `BLOCKED` y no prepara un bundle. Los apps
son bundles de desarrollo con firma ad hoc: no son la beta portable ni usan
Keychain/certificados.

Bajo el lock canónico, sin otro owner/build/codificador de fixture en marcha:

```sh
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_A --output var/evidence/h17-gpui/pattern-a1
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_B --output var/evidence/h17-gpui/pattern-b1
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_B --output var/evidence/h17-gpui/pattern-b2
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_A --output var/evidence/h17-gpui/pattern-a2
```

Son owners frescos, 1024×780, calentamiento de 5 s y 30 s de muestra por
defecto (las tomas ejecutadas H17 usan `--seconds 20`), patrón
y overlay propios, mixer vacío y outputs detenidos. No es idle sin preview:
la composición y preview avanzan. El runner confirma PID real del binario y
peer del socket, no carga stores, y solicita cierre normal verificando exit 0.
Muestrea también el PID frontmost mediante NSWorkspace cada 0,5 s, sin títulos,
nombres de aplicaciones. Por defecto no pide cambiar foco. `--ensure-focus`
exige el PID activo antes de calentar; si no coincide, solicita una sola
activación del bundle exacto y espera como máximo 2 s. Si no se corrobora,
termina `BLOCKED` sin medir. Una pérdida de foco conserva los
números pero clasifica la toma `PARTIAL`; no se compara como ventana activa.

Para cuatro decoders propios: generar antes de medir con
`verify_h14_memory.py --prepare-fixture RUTA_NUEVA.mp4`, verificar su SHA-256,
y añadir `--workload four-videos --fixture RUTA --fixture-sha256 HASH` a run.
Reutiliza el lifecycle H14 a 1080p60, tres ciclos visibles/ocultos/retirados,
10 s por fase, sin outputs. Conserva el resultado original del harness,
cleanup y todas las muestras. Correlaciona intervalos completos del profiler
con fases por reloj de pared con control de deriva; no mezcla el import con
la fase estable. El p95 por segundo se conserva como tal: la mediana de esos
p95 no se anuncia como p95 de todos los frames.

## Resultados ejecutados

Los artefactos completos están en `var/evidence/h17-gpui/`. El derivado
`comparison.json` referencia los informes primarios y mantiene las tomas
excluidas. Se comparan los mismos hashes de fuentes/módulos de los dos
builds congelados, aunque el árbol H17 avanzó después. Ambos tienen profiler
activado; estos números no describen un B7/B8 sin instrumentación.

### Patrón y preview, sin outputs

Cada toma tiene 40 muestras de proceso, 19 intervalos completos de GPUI usados
para el resumen y 20,4 s aproximadamente de medición tras 5 s de calentamiento.
Las columnas draw son **medianas de los p50/p95 calculados en cada intervalo**,
no percentiles globales de todos los frames. CPU es porcentaje de un núcleo.

| Toma | Estado | Foco corroborado | CPU mediana | Draw p50 / p95 por intervalo, ms | Footprint máximo, MiB | RPC memoria p95, ms | Preview drops |
|---|---|---|---|---|---|---|---|
| A1 actual | PASS | 40/40 | 20,07% | 3,77 / 5,39 | 263,19 | 6,09 | 3 |
| B1 Fast | PASS | 40/40 | 18,49% | 2,83 / 4,54 | 275,03 | 12,15 | 1 |
| B2 Fast | PASS | 40/40 | 20,10% | 3,32 / 4,64 | 269,08 | 7,08 | 1 |
| A2 actual, excluida | PARTIAL | 0/40 | 20,15% | 3,70 / 5,21 | 268,83 | 26,28 | 0 |
| A3 retorno actual | PASS | 40/40 | 18,06% | 2,93 / 4,93 | 272,19 | 7,14 | 0 |

A2 permaneció con un PID frontmost distinto. No se atribuye a un bug de
activación de Motive ni a una acción específica del usuario. Se preservó y
se repitió el retorno A con el nuevo preflight de foco: A3 ya estaba activa,
por lo que no necesitó una solicitud extra. A3 ocurrió **después de las primeras
tomas de lifecycle**, por lo que la selección A1/B1/B2/A3 no se presenta como
un ABBA continuo y perfectamente balanceado.

Fast reduce los p95 de draw por intervalo en estas tomas, pero su CPU total
se solapa con A: no hay una ventaja consistente de proceso demostrada.
La prueba no justifica adoptar Fast automáticamente.

El profiler registró solamente 1/3/1/2 notificaciones sin preview nuevo
frente a 539/546/540/544 con preview nuevo en A1/B1/B2/A3. Por tanto, eliminar
notificaciones sin frame no explica el coste principal de este perfil.
Los máximos del cuerpo del heartbeat fueron 54,76/54,19/58,83/58,34 ms.
Aparecen picos aproximadamente una vez por segundo, compatibles con el bloque
de salud/inventario/importación que ejecuta ese periodo; esta instrumentación
**no separa las llamadas** y no establece cuál los causa. No se cambió ese
bloque ni el scheduler para mejorar la medición.

### Cuatro videos propios, canvas 1080p60

`videos-a` y `videos-b-focus` completaron baseline y tres ciclos
visible/oculto/retirado, 10 s por fase, con foco **202/202** cada uno. La
fixture es el mismo testsrc2 1920×1080 a 30 FPS, SHA-256
`4360a3700b88afa0d7b3b7493b292e243832d40b7c7ae122368d4118ae171b92`.
El canvas es 60 FPS; no se afirma que cada decoder entregue 60 FPS.

La primera toma `videos-b` queda **PARTIAL**, foco 0/202, y fuera de la
comparación activa. El nuevo intento usó `--ensure-focus`; corroboró el PID
antes de medir sin necesitar activación extra. Ambas tomas B permanecen.

| Fase | CPU mediana A / B, % de un núcleo | Draw p95 por intervalo A / B, ms | Malloc in-use mediana A / B, MiB |
|---|---|---|---|
| Baseline sin videos | 27,12 / 23,66 | 6,23 / 5,21 | 91,08 / 92,08 |
| Ciclo 1 visible | 48,10 / 45,84 | 3,65 / 3,11 | 579,01 / 580,99 |
| Ciclo 1 oculto | 42,92 / 39,79 | 3,97 / 3,02 | 582,06 / 586,92 |
| Ciclo 1 retirado | 27,04 / 21,37 | 6,29 / 4,85 | 92,32 / 93,99 |
| Ciclo 2 visible | 48,17 / 48,59 | 3,69 / 3,62 | 579,45 / 581,03 |
| Ciclo 2 oculto | 41,26 / 43,00 | 3,48 / 3,41 | 579,44 / 583,99 |
| Ciclo 2 retirado | 28,85 / 28,21 | 5,92 / 5,42 | 92,65 / 94,03 |
| Ciclo 3 visible | 48,67 / 47,64 | 3,73 / 3,24 | 579,47 / 581,10 |
| Ciclo 3 oculto | 43,98 / 43,14 | 3,99 / 3,90 | 579,52 / 584,06 |
| Ciclo 3 retirado | 21,56 / 24,99 | 3,25 / 5,28 | 93,01 / 94,09 |

Hay 8–9 intervalos GPUI íntegramente contenidos en cada fase. Cada fila de
CPU tiene 10 deltas y cada fase 11 snapshots de memoria. Fast no gana todas
las fases; la ventaja visible de CPU es pequeña y variable. Una ejecución
por backend, con tres ciclos internos, no es un benchmark universal.

Footprint máximo muestreado: **1115,19 MiB A / 1082,22 MiB B**. Tras el tercer
retiro, la fase conserva máximos **818,95 / 964,11 MiB** y RSS mediana
**900,14 / 886,67 MiB**, mientras malloc in-use volvió a **93,01 / 94,09 MiB**.
Malloc allocated sigue en **790,13 / 762,16 MiB** frente a ~170 MiB de baseline.
Esto evidencia que residencia, reserva del allocator y asignaciones vivas
miden cosas diferentes. No acredita una fuga ni su ausencia. Los aproximadamente
2 MiB adicionales de in-use después de tres ciclos requieren atribución de
ownership antes de llamarlos fuga; no justifican inventar un soak largo.

En las diez fases hay **0 deltas de render lag/skips**, con **33/36 preview
drops** respectivamente. Se conservan los contadores iniciales y los eventos
entre fases en las muestras originales; no se anuncia cero drops globales.
RPC memoria p95 excedió 20 ms en dos fases A (39,16 y 22,18 ms) y tres B
(22,21; 35,63; 37,87 ms). No se ocultan esos picos con el promedio global.
Outputs permanecieron detenidos: no hay medios para decodificar ni PASS de
entrega, A/V, píxeles frescos o latencia botón→frame en estas tomas.

Todos los ocho owners de estas tomas salieron **0** mediante shutdown normal,
con cleanup sin errores y preferencias UI sin cambios. El último `pgrep -x
motive` no encontró procesos; se cedió el lease al root conservando su lock.

El harness H14 acepta ahora `--resolution hd720|full_hd1080` con el default
histórico intacto. El plan declara preset/dimensiones y cada sample comprueba
width/height/FPS reales. La prueba 720p del root tiene su propio informe y no
se añade retrospectivamente a esta comparación GPUI 1080p.

## Gates de adopción

| Gate | Estado | Evidencia o siguiente paso |
|---|---|---|
| Compilación release A/B ARM64 | PASS | Bindings con fuentes/módulos iguales, firma ad hoc strict |
| Mediciones de patrón/preview con foco | PASS | A1/A3 y B1/B2, 40/40 por toma; scope controlado con profiler |
| ABBA continuo completo | PARTIAL | A2 perdió cobertura de foco; A3 posterior se identifica por separado |
| Cuatro videos 1080p60/tres ciclos | PASS | A y B-focus, 202/202; medición y cleanup, sin certificación visual |
| Ventaja CPU consistente | PARTIAL | Rangos solapados y fases en las que Fast empeora |
| Scrolling/listas/Live Deck/editor | NOT_EVALUATED | Falta el mismo recorrido nativo A/B |
| Diálogos/popovers/foco de controles/eventos | NOT_EVALUATED | Foco de aplicación sí observado; no navegación de controles |
| Ausencia de pantallas stale/frescura de preview | NOT_EVALUATED | Los contadores no prueban píxeles avanzando |
| VoiceOver/accesibilidad | NOT_EVALUATED | No ejecutada sobre ambos backends; inspección de código no la sustituye |
| Adopción como default | BLOCKED | Mejora limitada y gates funcionales pendientes |

Se conserva GPUI actual como backend de producto. La comparación es real y
reproducible; no se modificaron Production, Show Control ni la cadencia para
hacerla pasar. Verificación de implementación: ambos builds release, formato,
compilación Python y los seis tests existentes del harness de memoria pasan.
