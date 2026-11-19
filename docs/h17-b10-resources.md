# H17 — recursos y salidas duales de B10

Estado de PERF-01: **PARTIAL**. Se midieron 100 consultas RPC en reposo y dos
sesiones reales de 120 s con grabación y RTMP local a 1080p60 y 720p60. Los
cuatro medios pasan los controles de formato, cadencia, movimiento y PCM.
Estos ensayos no constituyen un soak largo, tres ciclos de liberación, una
medición de GPU ni una comparación que aísle una optimización.

## Identidad y protocolo

App: `/Users/luisfarfan/Developer/motive-h17-portable/b10/Motive.app`, bundle
20, ARM64, **release**, backend predeterminado GPUI-pre 0.3.12, sin Fast ni
profiler. Ejecutable SHA-256:
`1390fa6834c22c7df002b72d3f3e3c9c7d2bb993149663ac07334b4282f279c9`.
Runtime/source candidate: `8806f283f14df077f5d73de4d03d93da5a990d29`.
La [auditoría portable](h17-portable-beta.md) conserva plugin, firma y fuentes.

Se ejecutó secuencialmente idle → dual 1080 → dual 720, bajo el lease físico
y CPU del owner raíz. No hubo builds, otro owner de Motive ni decodificación
de análisis durante la medición. Los receptores locales forman parte de la
carga dual. Los decodes completos comenzaron después de cerrar los owners.
Se omitieron todas las variables `GPUI_` y `MOTIVE_UI_`, conservando el tamaño
predeterminado de la UI. No se abrió cámara, micrófono ni captura de ventana.

Fixture original propia, ya existente:
`var/evidence/h17-checks/owned-memory-b6-matched.mp4`, 10.979.078 bytes,
SHA-256 `ab74850836683cfd7073452d45be5ab0c9173b0f09ff556717ce5d24b716627b`.
Es el mismo archivo de B6: testsrc2 1920×1080, 30 fps, 6 s, sin audio. Cada
sesión usa cuatro decodificadores en loop, uno por fuente, y tono global a
−12 dB para las salidas. En 720 cambia el canvas; los decodificadores siguen
leyendo esta fuente 1080p30.

El plan coincide con el ensayo corto histórico B6: baseline 5 s, un ciclo de
cuatro videos visibles 5 s, ocultos 5 s y retirados con settle 5 s, seguido de
dual-soak 120 s. Intervalo 5 s, sin `--pause-hidden`. Cada destino usa su propio
encoder VideoToolbox de hardware, H.264 CBR 4000 kbps, GOP 1 s, reordering
desactivado; audio AAC 48 kHz estéreo. Hay 33 muestras por sesión: dos en cada
fase corta y 25 en dual. La CPU dual tiene 24 deltas dentro de su fase.

La procedencia histórica está en
`/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-resume-01/dual-short-b6-measurement/report.json`
y [el informe B6](h15-resume-verification.md). **B6 era dev/debug; B10 es
release.** El histórico tampoco registra equivalencia de foco, estado térmico
o entorno. Por tanto la tabla compara carga y configuración, y no atribuye
la reducción de CPU/RPC a Fast, al heartbeat ni a un cambio aislado de H17.

## Recursos observados

CPU del proceso completo, con un core = 100 %. RSS, physical footprint y malloc
tienen coberturas distintas y no deben sumarse. MiB = 1.048.576 bytes.

| Métrica durante dual 120 s | B6 debug 1080p60 | B10 release 1080p60 | B10 release 720p60 |
|---|---:|---:|---:|
| CPU mediana / p95, % de un core | 83,16 / 85,81 | 51,72 / 54,02 | 46,93 / 48,02 |
| RSS mediana, MiB | 921,09 | 860,27 | 796,25 |
| Physical footprint máximo, MiB | 1117,95 | 1085,55 | 1022,33 |
| Malloc en uso mediana, MiB | 577,61 | 577,61 | 544,65 |
| Malloc reservado máximo, MiB | 786,42 | 754,50 | 717,89 |
| RPC memory_diagnostics p95 / máximo, ms | 17,51 / 37,06 | 3,44 / 4,64 | 3,29 / 36,63 |
| Colección nativa p95, µs | 505,42 | 545,42 | 502,75 |
| Delta render lag / video skipped | 0 / 0 | 0 / 0 | 0 / 0 |
| Delta drops grabación / RTMP | 0 / 0 | 0 / 0 | 0 / 0 |
| Delta preview busy drops | 7 | 25 | 11 |

Cada salida B10 registra 7200 frames adicionales dentro de la ventana dual;
esto no equivale al número total de frames de los archivos ni demuestra la
entrega de su cola. En todo el tramo muestreado, incluyendo fases cortas y
transiciones, B10 suma 29/16 preview busy drops (1080/720) y cero lag/skips.
El preview tiene más drops que B6 en la ventana dual; no se oculta ese resultado
con la reducción observada de CPU.

Las 66 muestras nativas de B10 tienen status PASS. La derivación independiente
recalcula los 28 intervalos de CPU por sesión con diferencia absoluta cero
frente al instrumento. Ninguna fase supera los umbrales configurados de
p95 RPC 20 ms, p95 colección nativa 2000 µs o revisión de footprint 1536 MiB.
Sí existe una muestra RPC de 36,63 ms en 720: el p95 cumple y el máximo no se
elimina. Los umbrales no certifican toda la experiencia interactiva.

Las fases cortas sólo tienen un intervalo de CPU cada una. En 1080, baseline /
cuatro visibles / ocultos / retirados fueron 20,36 / 48,14 / 38,13 / 25,87 %;
en 720, 20,92 / 42,46 / 37,22 / 22,31 %. Ocultar no pausa los decodificadores.
Cinco segundos no permiten presentar esos valores como percentiles estables.

| Última muestra de cada fase, MiB | B10 1080 baseline | B10 1080 retirados | B10 720 baseline | B10 720 retirados |
|---|---:|---:|---:|---:|
| Malloc en uso | 85,58 | 86,94 | 49,73 | 50,77 |
| Malloc reservado | 166,14 | 666,14 | 125,61 | 637,67 |
| RSS | 253,20 | 770,34 | 196,88 | 741,31 |
| Physical footprint | 367,05 | 885,20 | 309,83 | 853,55 |

Tras retirar las cuatro fuentes, malloc en uso queda 1,36/1,05 MiB por encima
de la última muestra baseline; el espacio reservado y residente permanece
elevado. Estos datos distinguen memoria en uso y retenida por el proceso. No
hay stacks de asignación ni prueba de propiedad: evaluación de fuga
**PARTIAL**, con categoría cruda `INCONCLUSIVE`, sin forzar purge ni ampliar
el settle para alterar la medida.

Idle usa el mismo instrumento de B6: 100 `memory_diagnostics`, pausa de 50 ms,
owner fresco y PID constante. B10: mediana **1,390 ms**, p95 **4,611 ms**, máximo
**23,185 ms**, gate p95 **PASS**. B6 debug: 3,310 / 12,919 / 37,552 ms. El status
JSON se comprobó explícitamente: este script puede salir 0 aun cuando el
presupuesto p95 resulte FAIL.

## Los cuatro medios completos

Se analizaron todos los frames y paquetes, hashes y movimiento de cuatro
cuadrantes, además de todo el PCM estéreo. Las herramientas son las incluidas
en B10, sin variables DYLD, con cwd del analizador y sin un owner vivo.

| Medio | Frames decodificados | Duración contenedor, s | Mayor intervalo sin cambio significativo entre cuadrantes, s | Controles de medio |
|---|---:|---:|---:|---|
| 1080 grabación | 7255 | 120,938 | 0,600 | PASS |
| 1080 RTMP recibido | 7226 | 120,468 | 0,600 | PASS |
| 720 grabación | 7254 | 120,938 | 0,551 | PASS |
| 720 RTMP recibido | 7225 | 120,437 | 0,534 | PASS |

En los cuatro: H.264 a la resolución declarada y 60 fps, sin B-frames, PTS/DTS
presentes y crecientes, gap de video máximo 17 ms y AAC continuo. La repetición
exacta de píxeles más larga por cuadrante es 33,7 ms. El umbral del analizador
para revisar falta de cambio significativo es 1 s. El PCM tiene cero muestras
no finitas o saturadas y cero ventanas completas de 100 ms bajo −80 dBFS;
los controles del tono pasan. Los hashes de los medios permanecen iguales.

**Entrega PARTIAL** en los cuatro; los informes crudos conservan `INCONCLUSIVE`:
el prefijo inicial de paquetes no prueba el origen para correlacionar la cola
(`initial_packet_origin_unproven`).
Se conservan los deltas nativos frente a frames decodificados: output frames
menos decoded = 1/1/1/0; encoded menos decoded = 12/13/13/12, en el orden de la
tabla. No se clasifican automáticamente como pérdidas ni se eliminan del
informe. Sin evento compartido entre el tono continuo y el video silencioso,
**sincronía A/V NOT_EVALUATED**. Los agregados de análisis siguen **PARTIAL**;
el PASS por medio tiene el alcance explícito de formato/cadencia/píxeles/PCM.

### Corrección del instrumento de 720

El primer análisis de 720 se conserva íntegro en
`var/evidence/h17-b10-dual720-analysis/`: **FAIL instrumental**, antes del decode,
porque `analyze_h14_soak.py` fijaba 1920×1080. El commit posterior `1e01dcc`
valida dimensiones contra la resolución explícita del plan; rechaza una
resolución distinta, incluso si está soportada, y planes ausentes/desconocidos.
Conserva los guards de codec, FPS, audio y cantidad de streams.

El reanálisis usa **los mismos archivos y hashes**, sin recaptura, y escribe
`var/evidence/h17-b10-dual720-analysis-resolution-aware/`. Los 13 tests del
analizador pasan, incluidos cuatro nuevos de formato. Después de terminar
todos los decodes, la suite Python completa pasa **149 tests**, exit 0.
La regresión Rust/native de B10 pertenece al snapshot `8806f28`; no se
recompiló el producto por este cambio del instrumento. El análisis 1080 conserva
el analizador original, cuyo hash coincide con el usado en B6; no se reemplaza.

## Evidencia y preservación

Comandos ejecutados y resultados derivados están en
`var/evidence/h17-b10-resources/`: `idle-command.json`, `dual1080-command.json`,
`dual720-command.json`, `comparison.json`, ambas derivaciones de memoria,
comandos/logs de los análisis, `analysis-resolution-tests.log` y
`all-python-tests.log` con su recibo de exit. Cada replay requiere un lease
nuevo, ausencia de owner y directorios de evidencia nuevos; los existentes no
se sobrescriben.

Los directorios `h17-b10-idle-owner`, `h17-b10-dual1080-owner` y
`h17-b10-dual720-owner` conservan logs, binding y reportes de owner. Los PID
94789, 94954 y 34561 cerraron normalmente con exit 0; suites exit 0 y cleanup
vacío. Las mediciones completas están en `h17-b10-dual1080-measurement` y
`h17-b10-dual720-measurement`; sus reportes originales conservan **PARTIAL**.
`PASS_RUNNER` sólo acredita la ejecución del wrapper y no sustituye estos gates.

`preflight.json`, `postflight.json` y `final-cleanup.json` cotejan por bytes/hash
los **41 archivos originales** del data root portable: cero cambios y cero
archivos nuevos. Todos los journals previos permanecen intactos; no se borra
ni se restaura uno de ellos. Al devolver el lease no quedaban Motive, ffmpeg,
ffprobe ni socket portable. El lock canónico permanecía intacto y lo liberó
después el owner raíz, tras su propia comprobación final.

La conclusión acotada no cambia los resultados separados de
[captura B10](h17-capture-verification.md),
[Show Control antes del tick](h17-show-before-tick-protocol.md) ni la decisión
de [mantener GPUI Fast desactivado](h17-gpui-performance.md). No se realizó una
optimización adicional del heartbeat de 33 ms a partir de estas medidas.
