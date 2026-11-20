# H22 — capacidad de cargas propias

La admisión en **Production permanece en cero**: Browser Host no está integrado
y el gate C de credenciales/confinamiento sigue BLOCKED. Esta matriz mide
superficies offscreen concurrentes en un único host CEF con consumer de
laboratorio. No es una composición OBS, captura, encoder, juego ni transmisión.

Los ensayos corresponden a la [máquina observada](../evidence/H22-machine-metadata.json):
Apple M5 Pro, 48 GiB RAM,
18 CPUs lógicas, macOS 27.2
(26B123), arm64. No se midió utilización
GPU ni estado térmico. Estos resultados no certifican todos los equipos ARM64.

## Protocolo final

- Tres repeticiones independientes de 72 s por configuración; directorios,
  perfiles y generaciones nuevos. Warmup declarado de 10 s, ventana de 60 s.
- Uno, tres y cinco simples 640×360; Goal original con uno/tres/cinco a 640×360
  y tres a 540×960; Lower Third propio con tres a 640×360; Community Alert
  propia con tres a 540×960; mezclas de cinco a 960×540 y 540×960.
- La mezcla usa dos Lower Third, dos Alert y un Lower Third estático. No es una
  extensión de la capacidad simple a contenido arbitrario. Las dimensiones
  corresponden a **cada superficie**, no al tamaño de una escena compuesta.
- 30 FPS solicitados; al menos 28,5 adquisiciones/s, p95 edad ≤100 ms y gaps
  de paint/adquisición/completion **<250 ms** en ventanas activas completas.
  El gap de una ventana continua incluye muestras a ambos lados de sus bordes.
- Eventos de Lower Third duran 4,6 s y Alert 3,2 s; nuevos dispatch cada 6 s,
  sin cola. Goal conserva sus assets originales por hash. Idle y estáticos
  no tienen una expectativa inventada de 30 FPS. Todos los intervalos activos,
  también interrumpidos, permanecen en la evidencia.
- Cada dispatch se contabiliza; máximo dispatch→active es observación nativa,
  no latencia de UI/MCP o prueba de píxeles semánticos. Lifecycle exige cancel
  reconocido antes de ocultar, ausencia de replay y peers realmente activos.
- Soaks de 600 s: cold cycles con tres simples; mezcla de tres con lifecycle;
  tres Goals verticales. Dos lifecycle de 45 s y cold resize de 12 s completan
  cobertura. El profiling de memoria está separado y no acredita cadencia.
- Presupuesto de emergencia del árbol: **2048 MiB RSS muestreado**, deadline
  externo por caso y cleanup por PID/nacimiento. El límite no es RAM física
  exclusiva ni cuota instantánea del kernel. CPU se expresa en % de un core;
  no mide utilización GPU ni reserva margen para juego/captura/encoder.

Los candidatos cold4, widgets3 y goal-load3 usan CEF 150 fijado, sandbox activo,
backend mock de laboratorio, updater desactivado y resolución cerrada. NetLog
Default debe mostrar el rechazo positivo de la petición propia, cero eventos
TCP/UDP y cero componentes instalados. Esto controla la carga, no confina un
proceso nativo comprometido. Cada caso usa el lock físico exclusivo; no comparte
el ensayo con H21. Los perfiles anteriores no heredan este resultado.

## Resultado por configuración

La suite simple completó **9/9 PASS**. [Resumen con entradas verificadas](../evidence/H22-simple-capacity-summary.json).
Los rangos abarcan las tres repeticiones de cada configuración; máximos de edad
y gap abarcan todas sus instancias y ventanas, sin promediar un stall.

| Simples 640×360/30 | Pico RSS por ensayo, MiB | Footprint mediano, MiB | CPU media, % de un core | FPS mínimo | Mayor p95 edad, ms | Mayor gap, ms |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 665,13–666,56 | 357,30–359,53 | 8,62–9,00 | 29,98 | 13,71 | 46,39 |
| 3 | 948,25–950,78 | 459,13–462,42 | 18,56–21,21 | 30,00 | 13,43 | 49,54 |
| 5 | 1227,88–1244,33 | 529,89–571,98 | 28,50–34,31 | 29,98 | 11,97 | 65,31 |

| Goal original 640×360/30 | Repeticiones válidas | Pico RSS, MiB | Footprint mediano, MiB | CPU media, % de un core | FPS mínimo | Mayor p95 edad, ms | Mayor gap, ms |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3/3 | 796,39–856,02 | 233,53–238,59 | 2,75–3,11 | 28,98 | 12,41 | 72,94 |
| 3 | 2/3 — no admitido | 1337,13–1348,64 | 398,36–402,54 | 5,55–6,17 | 28,41 | 12,46 | 83,74 |
| 5 | 2/3 — no admitido | 1831,34–1891,92 | 559,08–582,20 | 8,18–9,83 | 27,61 | 12,40 | 163,58 |

Estos Goals reciben eventos cada 6 s y completan su animación entre eventos.
Su CPU/footprint mediano incluyen ese idle; no se comparan como coste por frame
con las fixtures continuamente animadas. El FPS/gap se calcula sólo sobre cada
evento completo declarado, sin descartar sus muestras de adquisición. Se
conservan además contadores de paints/coalescing; los bytes BGRA retenidos son
muestras first/visual/latest, no un archivo de video de todos los frames.

La primera repetición con tres Goal falló en un evento: 28,41098 FPS frente al
mínimo 28,5. Con cinco, la primera falló en tres intervalos contemporáneos, con
mínimo 27,60821 FPS. Las otras dos repeticiones de cada configuración pasaron.
Los rangos incluyen los FAIL: no se admiten tres ni cinco mediante una media
que oculte esas ventanas. [Diagnóstico y límites de atribución](h22-failures.md).
Un Goal es la única configuración Goal horizontal que cumple tres repeticiones;
no se interpoló capacidad para dos, ni se probó su sesión de horas.

| Otros widgets propios / superficie | Válidas | Pico RSS, MiB | Footprint mediano, MiB | CPU media, % de un core | FPS mínimo | Mayor p95 edad, ms | Mayor gap, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 Lower Third / 640×360 | 3/3 | 933,58–964,42 | 463,44–469,92 | 13,43–16,68 | 29,83 | 12,26 | 65,15 |
| 3 Community Alert / 540×960 | 3/3 | 978,95–995,98 | 497,01–519,92 | 11,88–12,62 | 29,86 | 12,42 | 47,59 |
| Mezcla de 5 / 960×540 | 3/3 | 1221,88–1255,27 | 589,07–606,50 | 19,60–20,64 | 29,84 | 12,59 | 47,66 |
| Mezcla de 5 / 540×960 | 3/3 | 1249,39–1252,44 | 602,54–614,03 | 18,84–19,84 | 29,88 | 12,49 | 48,86 |
| 3 Goal original / 540×960 | 3/3 | 1377,98–1391,27 | 447,58–447,89 | 6,34–6,98 | 28,97 | 15,01 | 77,27 |

Cinco es el máximo **verificado de estos fixtures**, no un máximo intrínseco
del motor ni una cuota para Goal. La matriz corta está completa: **31/33 PASS** y dos FAIL de cadencia
conservados. El PASS de Goal vertical no borra los FAIL horizontales ni permite
interpolar capacidad.

La [matriz final v2](../evidence/H22-capacity-final-v2.json) y su
[conciliación de cobertura](../evidence/H22-coverage-final-v2.json) acreditan
**39/39 casos ejecutados, 35 PASS y cuatro FAIL** en sus gates declarados.
La matriz conserva 67 filas de planes: 28 rutas quedaron sin ejecución y sus
casos se cubrieron una sola vez en continuaciones; no se sustituyen FAIL.
Los hashes de cada auditoría y de sus entradas se verifican al consolidar.

Cadencia sostenida/activa: 35 PASS, tres FAIL y un NOT_EVALUATED. Este último
es cold resize de 12 s: pasa continuidad y lifecycle, pero no tiene una ventana
de FPS de 60 s. Goal lifecycle pasa cadencia y falla cierre; por eso los conteos
por gate no se suman como ensayos distintos. La
[precisión del resumen](../evidence/H22-summary-scope-precision.json) conserva
los primeros agregados y demuestra que no cambió ningún campo nativo previo.

## Lifecycle y duración prolongada

| Caso final | Resultado | FPS mínimo evaluado | Mayor gap activo, ms | Pico RSS, MiB | Cierre nativo, ms |
|---|---|---:|---:|---:|---:|
| Mezcla lifecycle, 3 × 640×360, 45 s | PASS | 30,04 | 46,85 | 937,45 | 55,03 |
| Goal lifecycle, 3 × 640×360, 45 s | FAIL de cierre | 28,98 | 70,00 | 1350,88 | 5403,68 |
| Cold resize, 3 simples, 12 s | PASS de operaciones | No evaluado | 52,76 | 929,94 | 101,43 |
| Cold cycles, 3 simples 640×360, 600 s | PASS | 30,00 | 58,34 | 986,13 | 2317,59 |
| Mezcla, 3 × 640×360, 600 s | FAIL de cadencia/continuidad | 25,89 | 465,57 | 933,70 | 121,86 |
| Goal, 3 × 540×960, 600 s | PASS | 29,07 | 81,69 | 1425,31 | 65,14 |

Estos son ensayos únicos de cada escenario largo/lifecycle. El soak de Goal
vertical completa 291 eventos evaluables; no equivale a tres repeticiones de
600 s ni a una sesión de horas. La mezcla completa 194 eventos, con 11 FAIL
tardíos después de sus operaciones. Su máximo dispatch→active fue 282,45 ms;
el de Goal vertical largo fue 3,52 ms. Son latencias nativas, no de presentación.
El resultado largo de la mezcla impide admitirla a 600 s, aunque sus variantes
cortas de cinco widgets hayan pasado. No se mezclan conteos, resolución,
historia de lifecycle o duración para ampliar esa admisión.

Los detalles están en [continuidad](h22-continuity.md),
[memoria](h22-memory.md) y [fallos](h22-failures.md). El cierre Goal de 5403,68 ms
se conserva frente a 5000 ms; los contratos aislados no lo remedian.

## Límites de admisión

La capacidad de laboratorio sólo puede admitir el conteo, resolución, contenido,
frecuencia de eventos y duración realmente probados. No cubre 60 FPS, superficies
CEF 1080p, paquetes arbitrarios ni sesiones de horas. El límite binario máximo
1920×1080 valida tamaños de transporte; no es un benchmark CEF para ese tamaño.

H23 necesita presupuesto agregado y pruebas del único owner OBS: CEF, buffers
productor/receptor, texturas, captura, encoder, escenas compartidas y cierre.
El mayor conteo que pase aquí no demuestra fluidez del juego ni de la emisión.
Hasta entonces no se transforma RSS de emergencia en una recomendación de
widgets por stream ni se habilita contenido de terceros.

## Evidencia anterior preservada

[Resumen de la primera campaña](../evidence/H22-capacity-legacy-summary.json):
cinco casos completados y el resto no ejecutado tras el hallazgo de componentes.
Los valores son reales pero pertenecen al perfil anterior, con trabajo de
actualización no excluido. No se mezclan con los candidatos finales ni se usan
para cubrir una repetición faltante. El FAIL global de aquella campaña no
significa que un caso detenido antes del lanzamiento haya fallado en FPS.

## Inspección visual retenida

[Inspección de siete PNG reales](../evidence/H22-visual-inspection-final-v2.json)
con hashes: Goal original horizontal/vertical, Lower Third, Alert y componentes
animados/estáticos de las mezclas. Texto y paneles observados permanecen dentro
de sus superficies. Alpha/premultiplicación se verifican aparte sobre BGRA.
No son imágenes generadas, una composición OBS ni prueba de movimiento de todos
los frames; los límites de cadencia proceden de las trazas/contabilidad nativas.
