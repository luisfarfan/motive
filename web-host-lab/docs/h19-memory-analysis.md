# H19 — memoria y capacidad sostenida del host propio

La medición separa RSS del árbol, footprint por proceso, mapas de regiones y
buffers de Motive. Ninguno de esos totales es una medida de páginas físicas
únicas. El alcance es el CEF fijado 150.0.19 / Chromium 150.0.7871.252, ARM64,
640×360 a 30 FPS, un host con contextos/orígenes propios separados y backend
Keychain de pruebas. No representa una configuración distribuible.

La candidata posterior de escritura fija pasa las nueve ejecuciones de
capacidad y acepta **5 widgets animados propios** en este subconjunto. Su pico
RSS muestreado es **1251.91 MiB** y el mínimo observado, **29.983 FPS**. El lote inicial
falló en 3-r3 y se conserva completo. La matriz general, terceros, credenciales
de producción y memoria física única no quedan resueltos por este resultado.
El soak posterior conserva cadencia estable y cierre, pero **falla continuidad
funcional de un peer durante resize** y registra crecimiento de footprint;
no valida estabilidad funcional completa ni ausencia de fugas.

## Auditoría independiente y ventanas

`tools/h19_performance_audit.py` lee evidencia retenida; no ejecuta ni importa el
runner nativo ni sus funciones de cálculo. Verifica SHA-256 del gzip y del JSON
descomprimido del supervisor, build report, fuentes de colectores, metadatos y
frames BGRA. Reconstruye CPU desde ticks Mach acumulados, numerador/denominador
del reloj y observaciones consecutivas con PID/birth/proc_start_abstime iguales.
Un proceso nuevo, perdido o sustituido no aporta un cero inventado. Recalcula
las distribuciones y las compara con los reports originales.

La unidad CPU se contrastó además con código primario Apple XNU, commit
`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`, con seis fuentes y hashes en
`research/h19-cpu-units-source-index.json`. En
[kern_resource.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_resource.c#L3406),
RUSAGE_INFO_V0 llama `fill_task_rusage`; en
[bsd_kern.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/bsd_kern.c#L1249),
ésta asigna user/system desde `task_power_info_locked` sin convertir unidades.
[task.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/task.c#L6807)
los obtiene de `rm_time_mach`, y
[recount.h](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/recount.h#L136)
declara unidades de timebase Mach. El struct de `sys/resource.h` del SDK no
incluye comentario de unidad: por sí solo no justificaría llamarlas nanosegundos.
La conversión usa la razón observada 125/3 y suma ticks antes del floor. Es
correspondencia semántica con fuente pública de Apple, no una atestación
binaria del kernel macOS 27.2 ejecutado ni una calibración de carga adicional.

El SDK expone estas funciones, pero su `libproc.h` las etiqueta interfaces
privadas de información de procesos. Su uso aquí es instrumentación del
laboratorio, no una promesa de ABI pública estable para distribuir el producto
ni autorización para usar interfaces privadas de sandbox.

Los recursos usan únicamente Python monotonic: arranque/warmup [0,10) s,
steady [10,70) s y últimos diez segundos de la duración solicitada. Solo se
incluye un intervalo CPU si sus dos extremos pertenecen a la fase. 100% CPU
significa un core ocupado; no se divide por el número de cores. La CPU del
supervisor y procesos que nacen y mueren entre muestras no se contabiliza.

Los frames usan únicamente el reloj nativo y su ventana por instancia desde
creación+10 s hasta creación+70 s. Se conserva la diferencia con la ventana del
supervisor; no se restan timestamps de ambos relojes. Se exige traza completa,
conservación exacta de paints y cero bytes/leases propios tras cierre. Para una
instancia animada: al menos 28.5 adquisiciones/s, age p95 ≤100 ms y primer paint
no transparente ≤3000 ms desde creación. El cierre nativo hasta retorno de
CefShutdown y el cierre observado por supervisor deben ser ≤5000 ms. Son
adquisiciones del consumer de laboratorio que escribe disco, no FPS audiovisual
ni latencia end-to-end. El tiempo de copia Rust se registra por separado.
También se verifica el primer paint desde `initialize_enter`, en el mismo reloj
nativo. Ninguna de esas dos cifras es el tiempo desde `Popen` del supervisor.

Los tests negativos cubren conversión Mach y floor, reutilización de PID,
cambio de identidad de inicio, CPU alterada, límites de fase, métricas ausentes,
traza truncada, ventana corta, conservación rota, muestra consumida ausente,
orden temporal y el umbral exacto del 95%. Son fixtures aritméticos, no evidencia
de ejecución de CEF.

## Resultados sostenidos del lote inicial

**El lote sostenido original falla aceptación: `animated-3-r3` entrega menos de
28.5 FPS en sus tres instancias.** Los nueve runners cerraron normalmente y
pasaron sus gates de recursos, identidad y conservación. La auditoría de
performance es un gate adicional: no se convierten esos nueve PASS de ejecución
en nueve PASS de capacidad.

Fuente: `research/h19-performance-capacity-audit-v2.json`, que conserva hashes de
los reports, muestras, binario final
`edccc2eef22cd2f7ef336c4256023b42555da97a8b1b9f18498a6ed715a07bd6` y colectores.
Son tres repeticiones por count, orden balanceado 1/3/5, 3/5/1, 5/1/3; cada una
dura 72 s y empieza con procesos/contextos privados nuevos. Eso no vacía las
cachés globales del OS ni garantiza condiciones idénticas de presión de memoria.
Las fuentes exactas de los tres colectores y del auditor v2 están archivadas en
`evidence/H19-measurement-sources/manifest.json`; los 18 tests del auditor pasan
en `research/h19-performance-audit-tests.log`. Este es el lote inicial del
binario llamado `final`; una candidata posterior y su A/B deben tener artefactos
y resultados nuevos y no heredar su aceptación por nombre.

| Caso | RSS peak MiB, run entero | RSS steady mediana MiB | Footprint steady mediana MiB | CPU arranque / steady, % de un core | FPS mínimo por instancia | Auditoría |
|---|---:|---:|---:|---:|---:|---|
| 1-r1 | 671.17 | 667.33 | 365.23 | 11.08 / 7.23 | 30.000 | PASS |
| 1-r2 | 668.61 | 405.72 | 359.96 | 11.81 / 7.97 | 29.567 | PASS |
| 1-r3 | 661.00 | 527.16 | 358.75 | 11.04 / 8.02 | 28.750 | PASS |
| 3-r1 | 936.80 | 635.93 | 468.92 | 20.68 / 16.18 | 29.917 | PASS |
| 3-r2 | 925.06 | 736.96 | 467.76 | 21.81 / 16.96 | 29.500 | PASS |
| 3-r3 | 929.39 | 813.78 | 469.87 | 22.06 / 17.79 | 26.867 | **FAIL** |
| 5-r1 | 1210.58 | 963.12 | 567.14 | 36.19 / 32.63 | 29.900 | PASS |
| 5-r2 | 1235.72 | 989.70 | 579.73 | 30.62 / 27.50 | 29.967 | PASS |
| 5-r3 | 1204.64 | 769.38 | 549.73 | 34.62 / 30.35 | 29.383 | PASS |

Todas las instancias conservan age de adquisición p95 ≤12.30 ms, primer paint
desde creación ≤566.29 ms y desde initialize_enter ≤1024.46 ms. El máximo
cierre→CefShutdown observado es 377.42 ms; el cierre final del supervisor es
65.23 ms. No hay bytes/leases propios retenidos ni procesos propios observados
restantes. Esas condiciones pasan también en 3-r3; no corrigen su FPS fallido.

La regla conservadora detiene la capacidad en el primer nivel probado menor
que falla: este lote solo acepta **1 widget** como capacidad sostenida; no
certifica 3 ni 5, aunque las tres ejecuciones de cinco pasaron individualmente.
La matriz congelada completa sigue PARTIAL. El primer archivo
`h19-performance-capacity-audit.json` ya marcaba el lote FAIL, pero su agregación
inicial escogía el máximo count que pasó y devolvía 5; se conserva como defecto
del clasificador, corregido explícitamente por v2, sin reescribir evidencia.

## Coste compartido e incremental observado

Las medianas entre repeticiones de las medianas steady de footprint son
359.96/468.92/567.14 MiB para 1/3/5. La diferencia descriptiva es 54.48 MiB por
widget añadido entre 1 y 3, y 49.11 MiB entre 3 y 5. No es RAM física única ni
una predicción para otros paquetes, viewports, rates o counts. Los máximos de
RSS de los runs son 671.17/936.80/1235.72 MiB, todos dentro del stop de 2048 MiB;
no se elevó el límite para obtener PASS.

El coste compartido no es una constante: sumando por muestra todos los roles
excepto renderer, y luego tomando mediana de cada run y entre runs, el footprint
es 300.19/342.80/373.02 MiB. Browser y GPU crecen con la carga; compartirlos evita
duplicar árboles enteros, pero no elimina sus costes por widget.

| Rol | Footprint mediana de medianas, 1 / 3 / 5 widgets MiB | CPU steady mediana, 1 / 3 / 5, % de un core |
|---|---:|---:|
| Browser | 45.31 / 52.72 / 62.06 | 2.10 / 4.20 / 7.28 |
| GPU helper | 213.67 / 249.02 / 255.09 | 3.73 / 7.47 / 14.29 |
| Network | 21.22 / 22.06 / 22.58 | 0.08 / 0.05 / 0.07 |
| Storage | 19.42 / 19.56 / 19.58 | <0.01 / <0.01 / <0.01 |
| Renderers agregados | 60.10 / 127.00 / 191.65 | 1.75 / 5.14 / 8.59 |

Hubo mediana de 2/4/6 procesos renderer para 1/3/5 widgets, incluyendo un proceso
adicional; no se presume una correspondencia uno-a-uno widget/proceso. Un helper
utility apareció en una repetición de uno y las tres de tres/cinco (medianas de
footprint 15.09/15.14/16.59 MiB cuando estuvo presente). Las medianas por rol no
se suman para reconstruir la mediana del árbol: la mediana de una suma difiere
de la suma de medianas. RSS de `ps` y resident de `proc_pid_rusage` se muestrean
secuencialmente; diferencias puntuales no se interpretan como páginas únicas.

El baseline H18 de árboles separados, corto y no repetido como este lote,
estableció presión de RSS y fallo de cinco árboles. No permite una comparación
porcentual causal de CPU steady o throughput con estos 72 s; el contraste válido
del lote actual es entre sus counts manteniendo binario/fixture/viewport.

## Por qué 3-r3 falla aunque sus paints continúan

El host aceptó 2155 paints por instancia, sin callbacks busy/invalid; las
adquisiciones totales fueron 1957/1960/1959 y coalescing 198/195/196. En la
ventana nativa exacta de 60 s hubo 1612/1616/1615 adquisiciones:
26.867/26.933/26.917 FPS. El máximo tiempo de publicación OnPaint fue
0.499/0.308/0.433 ms y la copia media 100–114 µs. No hay señal de una copia
OnPaint de medio segundo.

El trabajo del consumer, que mantiene el lease mientras reescribe el frame
completo a disco, acumuló 8.92/8.74/8.90 s en la ventana (frente a unos 0.71 s
en r1 y 2.0 s en r2). Hay 27–29 muestras de trabajo >100 ms por instancia.
Los peores bloqueos coinciden en los tres consumers:

| Inicio relativo al initialize_enter nativo | Inicio relativo al epoch | Duración de trabajo |
|---:|---:|---:|
| 50.382–50.385 s | 50.207–50.210 s | 526.6–529.6 ms |
| 57.617 s | 57.439–57.444 s | 413.9–414.0 ms |
| 27.453 s | 27.275–27.280 s | 373.2–373.3 ms |
| 32.217–32.220 s | 32.040–32.047 s | 361.8–364.4 ms |

La CPU steady total fue 17.79% de un core, frente a 16.18/16.96% en r1/r2.
Esto sustenta una hipótesis de bloqueo compartido en el camino del consumer de
disco o su scheduling, no una conclusión de saturación CPU o copia CEF lenta.
El timer abarca escrituras, completion, release y descheduling; no identifica
el syscall o recurso concreto. La prueba A/B de una eventual corrección debe
preservar escritura completa por frame, semántica de completion y evidencia de
este fallo; no reemplazarlo con un resultado posterior.

Age mide hasta adquisición, antes del trabajo lento. Por eso un age p95 bajo
no significa que la escritura/completion termine con el mismo age. V2 calcula
además completion-age, gaps de adquisición y offsets de los ocho mayores
trabajos de cada instancia, conservando los relojes nativos sin mezclarlos con
el supervisor. Ninguna de estas cifras representa presentación audiovisual.

## A/B de la escritura de tamaño fijo

Se conserva un par posterior de 72 s en
`evidence/H19-consumer-comparison/`: baseline con el binario inicial y candidata
`8a76e3ce6409d911cf04bd4815c5c8065d13aa21a8c620cdf839f0d7b44c311b`.
La candidata conserva escritura completa de cada frame y completion tras el
trabajo; solo deja de repetir `ftruncate` para un archivo cuya longitud ya está
fijada por el epoch. No cambia la definición de FPS ni se omiten escrituras.

| Variante | FPS nativo de las tres instancias | Máximo trabajo consumer por instancia, ms | Trabajo >100 ms, por instancia | CPU steady % de un core | RSS peak MiB |
|---|---|---|---|---:|---:|
| Baseline | 29.200 / 29.200 / 29.217 | 615.27 / 611.67 / 619.45 | 6 / 4 / 6 | 19.89 | 931.59 |
| Candidata | 30.000 / 30.000 / 30.000 | 1.20 / 1.52 / 1.79 | 0 / 0 / 0 | 20.40 | 926.61 |

Ambas pasan aceptación en este par. La candidata registra, en cada epoch,
2154 escrituras completas, iguales a `successful_disk_writes`, un `ftruncate`,
cero rechazos de descriptor/longitud y 921600 bytes fijos. Estos counters son
obligatorios cuando el build incluye `fixed_frame_file.hpp`; el binario viejo
se marca `NOT_PRESENT_LEGACY_BINARY`, sin inventar counters retrospectivos.
La longitud no prueba por sí misma correspondencia de viewport; los metadatos
y la identidad de epoch se verifican aparte.

Las auditorías independientes están en
`research/h19-consumer-baseline-audit.json` y
`research/h19-consumer-candidate-audit.json`. Es una observación favorable a la
hipótesis del camino de escritura. Un solo par secuencial no aísla estado del
filesystem, presión de memoria ni scheduling, no demuestra causalidad y por sí
solo no certifica capacidad repetida. La CPU tampoco bajó en este par. El fallo
original 3-r3 continúa vigente como evidencia inicial, y la matriz de la nueva
candidata se evalúa por separado.

El auditor v3 y colectores exactos están en
`evidence/H19-measurement-sources-v3/manifest.json`; sus 25 tests pasan en
`research/h19-performance-audit-v3-tests.log`. Añade validación negativa de
counters, ventanas nativas tardías y auditoría del soak de 600 s sin modificar
las fuentes ni las muestras de recolección.

## Capacidad repetida de la candidata

El lote nuevo `evidence/H19-candidate-capacity/`, binario `8a76e3ce…44c311b`,
completa nueve runs de 72 s, con el mismo orden balanceado y criterios. Su
auditoría independiente
`research/h19-performance-candidate-capacity-audit.json` es **PASS**: los tres
niveles 1/3/5 pasan las tres repeticiones. La capacidad aceptada es cinco
widgets animados propios a 640×360/30; no se extrapola a seis, otro contenido,
otro CEF ni otro equipo, y no se atribuye cadencia al pipeline audiovisual.

| Caso candidato | RSS peak MiB | RSS steady mediana MiB | Footprint steady mediana MiB | CPU arranque / steady, % de un core | FPS mínimo |
|---|---:|---:|---:|---:|---:|
| 1-r1 | 663.92 | 558.08 | 364.98 | 10.47 / 7.20 | 30.000 |
| 1-r2 | 712.17 | 537.72 | 366.90 | 10.16 / 7.19 | 30.017 |
| 1-r3 | 668.86 | 552.56 | 364.76 | 10.45 / 7.89 | 30.000 |
| 3-r1 | 945.86 | 936.52 | 470.51 | 19.38 / 16.04 | 30.000 |
| 3-r2 | 947.30 | 938.55 | 469.24 | 19.55 / 15.90 | 30.000 |
| 3-r3 | 958.50 | 945.61 | 464.93 | 19.38 / 15.36 | 30.000 |
| 5-r1 | 1241.33 | 1226.09 | 594.47 | 29.64 / 25.97 | 29.983 |
| 5-r2 | 1251.91 | 1228.71 | 594.63 | 28.95 / 25.02 | 30.000 |
| 5-r3 | 1222.66 | 1063.33 | 587.59 | 30.20 / 25.64 | 30.000 |

Todas las instancias pasan los counters de archivo fijo y conservación; ninguna
tiene trabajo consumer >100 ms (máximo 4.286 ms). El máximo age de adquisición
p95 es 12.098 ms y el de completion p95, 12.227 ms. Primer paint desde creación
≤254.03 ms y desde initialize_enter ≤405.97 ms. Cierre nativo ≤164.92 ms,
cleanup del supervisor ≤56.83 ms, sin procesos propios observados restantes.
Los extremos se calculan sobre las 27 instancias de los nueve runs.

La memoria no mejoró como consecuencia demostrada de esta modificación del
consumer. Los máximos RSS 1/3/5 subieron de 671.17/936.80/1235.72 a
712.17/958.50/1251.91 MiB. Las medianas entre runs de footprint steady pasaron de
359.96/468.92/567.14 a 364.98/469.24/594.47 MiB. La presión, residencia de cachés
y scheduling no estuvieron controlados como variables experimentales; no se
atribuye esa diferencia al writer. Las medianas de CPU steady de la candidata
son 7.20/15.90/25.64% de un core; el par A/B aislado anterior tuvo CPU algo
mayor en la candidata. No se presenta un ahorro causal adicional de CPU/RAM.

| Rol candidato | Footprint mediana de medianas, 1 / 3 / 5 MiB | CPU steady mediana, 1 / 3 / 5, % de un core |
|---|---:|---:|
| Browser | 48.39 / 57.16 / 73.12 | 1.88 / 3.64 / 5.70 |
| GPU helper | 214.31 / 242.05 / 279.56 | 3.62 / 6.86 / 11.13 |
| Network | 23.47 / 24.20 / 24.44 | 0.13 / 0.08 / 0.05 |
| Storage | 20.28 / 20.30 / 20.50 | <0.01 / <0.01 / <0.01 |
| Renderers agregados | 60.46 / 126.79 / 194.34 | 1.83 / 5.09 / 8.71 |

Las medianas del coste compartido excluyendo renderers, sumadas primero por
muestra, son 305.07/342.41/400.57 MiB de footprint. El incremento descriptivo
total es 52.13 MiB/widget entre 1 y 3 y 62.61 MiB/widget entre 3 y 5. Se conserva
la salvedad de que son cargas agregadas, no páginas únicas. El renderer tiene
medianas de 2/4/6 procesos. El helper utility aparece en dos runs de tres,
con footprint mediano observado 21.99 y 15.72 MiB cuando está presente; no se
inventa un cero de utilización/memoria donde no fue observado.

La diferencia arquitectónica frente a árboles separados sigue siendo compartir
browser/servicios CEF entre paquetes propios revisados. El cambio del consumer
demuestra reducción de llamadas redundantes y cadencia observada más estable
en este lote; no demuestra una nueva reducción de memoria del motor.

## Carga estática/mixta: seis casos completos

`research/h19-performance-static-mixed-audit.json` verifica los seis runs y
marca el lote **PASS**. Se conserva
`research/h19-performance-static-mixed-partial-audit.json`, que había verificado
solo cuatro, con estado PARTIAL y dos repeticiones faltantes. El coordinador
original se pausó entre casos para ceder el turno físico a H20 y se reanudó con
la misma identidad. Los aproximadamente 656 s del wrapper incluyen esa pausa;
cada run mantuvo 72 s y las ventanas 10+60 s. No quedó CEF vivo durante la cesión.

| Caso | RSS peak MiB | Footprint steady mediana MiB | CPU steady % de un core | Adquisiciones steady |
|---|---:|---:|---:|---|
| static-1-r1 | 655.50 | 183.76 | 0.584 | 0; age p95 null |
| static-1-r2 | 711.06 | 183.74 | 0.736 | 0; age p95 null |
| static-1-r3 | 664.48 | 182.32 | 0.626 | 0; age p95 null |
| mixed-5-r1 | 1194.88 | 512.45 | 8.017 | Instancia 1: 30 FPS; 2–5: 0 |
| mixed-5-r2 | 1194.09 | 510.22 | 8.341 | Instancia 1: 30 FPS; 2–5: 0 |
| mixed-5-r3 | 1174.84 | 511.35 | 8.137 | Instancia 1: 29.983 FPS; 2–5: 0 |

Los paints iniciales reales, counters, identidad, cierre y conservación pasan
también para las instancias estáticas. Cero adquisiciones en la ventana estable
es un resultado esperado de esa fixture; no se inventa un age p95 ni se aplica
un objetivo de animación a una imagen estática.

Las medianas entre repeticiones de CPU steady son 0.626% de un core para un
widget estático y 8.137% para cinco mixtos; sus footprints medianos son 183.74 y
511.35 MiB. El máximo primer paint desde creación es 200.56 ms y el máximo
cierre nativo, 62.86 ms. Son observaciones de esos workloads; la pausa y el estado
del sistema impiden atribuir cada diferencia de memoria o CPU a una única causa.

## Soak de 600 s: mediciones válidas, fallo funcional conservado

El caso real `evidence/H19-candidate-soak/lifecycle-3-600s/` ejecutó una secuencia
de remove/add, hidden/resume, resize, restart, crash y suspend/resume durante
los primeros 23 s, seguida de tres widgets vivos hasta el cierre. No es un
ensayo de churn repetido durante diez minutos.

`research/h19-performance-soak-audit.json`, calculado con el auditor v3 congelado,
pasa sus gates de ventanas estables, contabilidad, límites y cierre. El checker
funcional independiente en `evidence/H19-candidate-soak/lifecycle-3-600s/analysis.json`
conserva **FAIL / PEER_OBSERVATION_GAP**. Son conclusiones distintas: el PASS
de recursos y FPS estable no convierte el soak completo en PASS funcional.

Durante el intervalo hidden de A, el resize de C coincide con un gap de
**458.977 ms** en los paints consumidos de D, que no estaba siendo redimensionado.
Con origen `initialize_enter` nativo, D pasa de frame 119 a 121 entre
9.339841 y 9.798819 s; C solicita resize en 9.350941 s y su primer paint nuevo
tarda 447.491 ms. Los trabajos de consumer de D alrededor del gap fueron
0.060/0.122 ms. Esto no es el mismo indicio de escritura lenta que el fallo
inicial 3-r3. La observación indica interferencia temporal entre peers durante
esa operación compartida; no identifica por sí sola el mecanismo interno.
Se conserva el límite original de continuidad <250 ms, sin relajar el gate ni
reinterpretar un resultado posterior como reparación de este fallo.
La revisión `evidence/H19-candidate-functional-review.json` conserva ocho
diagnósticos cortos PASS y este FAIL del soak. La preparación request→nuevo
epoch ocupa 5.464 ms; nuevo epoch→primer paint nativo, 442.026 ms. El intervalo
largo ocurre después de preparar el host, y no respalda atribuirlo al antiguo
`ftruncate` repetido. La causa CEF/GPU/scheduling concreta permanece sin aislar.

Las ventanas de recursos son relativas al lanzamiento Python; las ventanas de
frames son relativas al initialize_enter nativo. No se restan entre sí.

| Ventana Python | Muestras | RSS mediana MiB | Footprint mediana MiB | Procesos mediana | CPU % de un core |
|---|---:|---:|---:|---:|---:|
| 30–90 s | 214 | 824.10 | 468.55 | 8 | 19.265 |
| 540–590 s | 179 | 403.50 | 545.67 | 8 | 18.742 |

El RSS bajó **420.60 MiB**, mientras el footprint subió **77.12 MiB**. No es
memoria plana y la caída de RSS no demuestra liberación de memoria comprometida.
La suma de footprints puede incluir cargos comprimidos y otros tipos de
residencia; estas muestras no identifican el allocator, caché o mecanismo de
esa variación. El máximo RSS muestreado fue 925.16 MiB y el máximo footprint
agregado observado, 547.17 MiB. Se retuvieron las 2108 muestras del supervisor,
sin truncamiento; 21 tienen cobertura parcial de memoria o identidad CPU.

| Rol | Footprint mediano temprano → tardío MiB | Diferencia descriptiva MiB | CPU temprano → tardío, % de un core |
|---|---:|---:|---:|
| Browser | 60.52 → 106.06 | +45.55 | 4.342 → 4.343 |
| GPU helper | 236.95 → 240.36 | +3.41 | 9.660 → 9.252 |
| Renderers agregados | 127.16 → 155.94 | +28.78 | 5.243 → 5.147 |
| Network | 23.67 → 22.61 | −1.06 | 0.019 → 0.001 |
| Storage | 20.28 → 20.49 | +0.20 | <0.001 → <0.001 |

El crecimiento se observa principalmente en browser y renderers; no se
atribuye a GPU ni a buffers Rust retenidos sin evidencia adicional. Un utility
transitorio aparece en la ventana temprana y no en la tardía; su ausencia no se
rellena con una medida de utilización cero. Las diferencias de medianas por rol
no son una descomposición aditiva exacta del cambio de mediana agregada.

| Instancia final, generación 138862770680 | FPS nativo 30–90 s | FPS nativo 540–590 s | Completion-age p95 temprano / tardío, ms |
|---|---:|---:|---:|
| 1 | 29.967 | 30.000 | 11.605 / 11.960 |
| 3 | 30.000 | 30.000 | 11.258 / 12.289 |
| 4 | 29.983 | 29.980 | 12.314 / 11.661 |

No hay trabajos consumer >100 ms en esas seis ventanas; el máximo temprano es
99.315 ms y el tardío 0.806 ms. La estabilidad de esas ventanas posteriores no
oculta el gap funcional inicial. Los ocho epochs conservan exactamente
**53597 paints = 53586 consumidos + 10 coalesced + 1 invalidado por cierre**.
No hay stale, leases ni bytes lógicos retenidos al final. Se copiaron
49657651200 bytes acumulados en 5.714 s de copia medida, unos 106.61 µs por
paint aceptado: tráfico acumulado, no RAM viva. Cada writer mantiene un truncate,
escritura completa por éxito y cero rechazos de descriptor/longitud.

El cierre nativo hasta retorno de shutdown fue 157.154 ms; CefShutdown por sí
solo, 61.052 ms; cleanup del supervisor, 42.471 ms. El árbol propio observado
terminó sin PIDs restantes. Ninguna de estas comprobaciones demuestra ausencia
de fugas o la estabilidad de workloads no medidos.

## Retiro de B y liberación lógica mientras el host sigue vivo

El recibo `evidence/H19-candidate-soak/live-retired-epochs.json`, observado a
04:01:35.687568 UTC, registra el host propio PID 30411, birth
`[1795060425,213087]`, vivo y con argumentos esperados coincidentes. La
verificación separada `research/h19-soak-retirement-match.json`, reproducible
con `research/h19-soak-retirement-check.py`, corrobora esa identidad en 2106
observaciones del supervisor y compara los cinco SHA-256 de epochs retirados
con los archivos finales. Todos coinciden sin cambios y conservan pending,
leased, retained_leases y retained_bytes iguales a cero.

Esto aporta evidencia de liberación **lógica de buffers propios antes del
cierre del host**, no solo después de terminar el proceso. No prueba que malloc
devolviera sus páginas al sistema ni que Chromium liberara todas sus cachés.
La liveness en aquel instante es la observación externa retenida; no se hizo
una consulta retroactiva al OS después de que el proceso terminara.

B (instancia 2, generación 138862770679) cerró su epoch a 3.354630 s desde
initialize_enter nativo, con 84 paints consumidos y cero bytes/leases retenidos.
Su renderer PID 30430, birth `[1795060426,49447]`, tiene diez observaciones
corroboradas en el árbol; la última está a 3.498416 s **del lanzamiento Python**.
Esos offsets tienen orígenes distintos: no se restan para afirmar una latencia
de liberación ni para asignar bytes de una muestra a ese cierre.

| Ventana aproximada desde lanzamiento Python | Muestras | RSS mediana MiB | Footprint mediana MiB | Procesos mediana |
|---|---:|---:|---:|---:|
| 2–3 s | 4 | 922.94 | 469.44 | 8 |
| 3.5–4.5 s | 3 | 731.33 | 432.40 | 7 |
| 6–7 s | 4 | 832.30 | 460.29 | 8 |

Son ventanas descriptivas de arranque alrededor de cambios de población,
con muy pocas muestras y sin alineación exacta con el reloj nativo. No permiten
atribuir la diferencia a memoria física liberada por B: también hay cachés,
otro browser creado, servicios compartidos y cambios de residencia. Las
identidades de renderer y ledgers aportan la evidencia delimitada de lifecycle;
la recuperabilidad física de cada componente permanece sin medir.

## Regiones: evidencia parcial, categorías distintas

`evidence/H19-v2-memory-regions-1/memory-regions.json` conserva un diagnóstico
separado, alrededor de 3.17 s, usando metadatos de la interfaz expuesta por el SDK
`proc_pidinfo(PROC_PIDREGIONINFO)`, página de 16384 bytes. No se leyó contenido de
memoria. Es anterior al binario final de capacidad y no se mezcla con su fase
steady. Todos los walks quedan **PARTIAL**: los cuatro servicios terminaron con
`EINVAL` sin poder distinguir fin normal de fallo; los dos renderers llegaron
al límite explícito de 8192 regiones.

| Rol | Regiones | Private resident MiB | Shared resident MiB | Shared-now-private MiB | Virtual GiB |
|---|---:|---:|---:|---:|---:|
| Browser | 293 | 47.56 | 331.72 | 15.25 | 466.78 |
| GPU | 294 | 29.36 | 347.97 | 14.25 | 466.59 |
| Network | 135 | 22.78 | 311.98 | 13.64 | 466.52 |
| Storage | 117 | 19.39 | 311.88 | 13.42 | 466.48 |
| Renderer A | 8192 | 23.09 | 317.08 | 12.27 | 1458.27 |
| Renderer B | 8192 | 26.73 | 318.66 | 12.39 | 1452.06 |

Son columnas observadas por API, no sumandos disjuntos: mappings alias, páginas
shared y COW pueden solaparse. No se suman private/shared/COW ni se resta shared
de RSS para obtener RAM única. El campo `unique_physical_bytes` permanece null.
El walk de cada renderer encontró 8008/7963 regiones de share-mode empty; no
completó el mapa. No equivale a 1.4 TiB de RAM comprometida o residente.

La reserva grande es consistente con V8, pero este walk no atribuye cada región
a un allocator. Chromium 150.0.7871.252 fija V8
`4a1d2352a737585a271c534201b502078ce6d856` en
[DEPS](https://github.com/chromium/chromium/blob/150.0.7871.252/DEPS).
Su [v8-internal.h](https://github.com/v8/v8/blob/4a1d2352a737585a271c534201b502078ce6d856/include/v8-internal.h#L220)
define 2^40 bytes de sandbox virtual para esta familia de plataforma y
[sandbox.h](https://github.com/v8/v8/blob/4a1d2352a737585a271c534201b502078ce6d856/src/sandbox/sandbox.h#L42)
documenta reservas/guard regions. Los tres archivos descargados tienen hashes
en `research/h19-memory-source-index.json`. Esa explicación de diseño no permite
atribuir toda la reserva observada a V8, medir heap vivo ni afirmar aislamiento
OS por la existencia del sandbox interno de V8.

Apple distingue memoria limpia recuperable, dirty, comprimida/intercambiada y
cargos de recursos gráficos compartidos en Apple silicon. El footprint no es
equivalente a RSS; la suma secuencial por proceso tampoco es una medición de
coalition o de páginas únicas. El diagnóstico presente no clasifica exactamente
cuántos bytes serían recuperables bajo presión. [Apple, Profile and optimize
your game's memory](https://developer.apple.com/videos/play/wwdc2022/10106/).

## Buffers Rust, Chromium y recuperación

En `poc/browser-host/src/frame.rs` hay como máximo un frame pendiente, un lease y
una copia transitoria completa por mailbox. A 640×360 BGRA un frame contiene
921600 bytes: 0.879 MiB; tres contienen 2.637 MiB por widget, hasta 13.184 MiB
lógicos para cinco widgets. No incluye overhead de allocator, dirty-rect Vec,
registros de telemetría, caché de archivos del consumer, superficies CEF/OSR,
heap V8, servicios Chromium ni recursos gráficos.

Cada publicación reserva un Vec y copia los píxeles dentro del lifetime de
OnPaint. `copy_ns` mide `extend_from_slice` tras reservar capacidad, incluyendo
timing y posibles page faults; no mide la reserva ni todo OnPaint ni constituye
un microbenchmark aislado de memcpy. Los bytes copiados son tráfico acumulado,
no RAM viva. Es incorrecto comparar esos gigabytes acumulados con RSS residente.

Los buffers propios son una fracción del árbol Chromium. El cierre invalida
autoridad, une el consumer y suelta pending/lease; las cuentas finales permiten
comprobar cero bytes lógicos propios retenidos. No prueban que el allocator
devuelva inmediatamente páginas al sistema. Mientras permanezca otro widget,
servicios compartidos y cachés de Chromium pueden permanecer residentes sin
ser pooling de browser/context autorizado por Motive.

Tres repeticiones con procesos nuevos comprueban repetibilidad y limpieza del
árbol observado. No demuestran recuperación de cachés dentro de un host vivo ni
ausencia de fugas a largo plazo. Una caída de RSS, especialmente con compresión
o presión de memoria, tampoco prueba liberación lógica. El soak y lifecycle se
evalúan como evidencia separada; no se infiere su resultado desde este lote.

Los recursos GPU carecen de una medida de utilización validada: `gpu_percent`
permanece null. El helper GPU es un proceso observado, no un contador de carga
GPU. No se ejecutaron herramientas de privilegio, procesos ajenos ni cambios
de configuración del sistema para completar este análisis.
