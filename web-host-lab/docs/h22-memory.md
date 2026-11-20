# H22 — memoria prolongada y límites de atribución

La contabilidad de frames y el cierre pasan. La atribución del crecimiento de
Chromium permanece **PARTIAL**: el perfil final de 600 s crece 59,21 MiB entre
la primera y última mediana y no demuestra meseta. Una estabilización tardía
anterior tiene el confusor de componentes descrito abajo. No hay prueba general
de ausencia de fugas ni de meseta bajo churn. No se introdujeron purgas,
zero-copy, dirty rectangles ni pooling para alterar medidas.

## Baseline y ensayos separados

**Hallazgo posterior:** el [inventario de cachés](../evidence/H22-background-component-audit.json)
encontró 19 manifests de componentes Chromium en cada perfil privado de los
tres ensayos largos, y 2–3 en muestras cortas. No pertenecen al inventario del
widget ni estaban en el SDK verificado. Las cifras siguientes son reales,
pero no describen una carga sin actualización de componentes. Los endpoints
históricos no fueron registrados; no se reconstruye una prueba de egress
inexistente ni se atribuye una cantidad de malloc a esos componentes sin stacks.
La continuación detuvo los perfiles antiguos y completó un contraste separado
con updater desactivado y resolución cerrada de Chromium, detallado al final.

H19 conservó +77,12 MiB de footprint en 600 s, principalmente browser y
renderers. Su [reanálisis](../evidence/H22-baseline/soak-audit.json) no convierte
ese crecimiento en caché ni fuga. Los casos H22 cambian el lifecycle; no son
una comparación controlada de una única optimización contra H19.

| Ventana, segundos | Cold cycles: footprint mediano, MiB | Estable instrumentado: footprint mediano, MiB |
|---|---:|---:|
| 30–90 | 476,23 | 484,37 |
| 120–180 | 541,79 | 564,48 |
| 240–300 | 570,10 | 589,74 |
| 360–420 | 572,53 | 598,51 |
| 480–540 | 579,74 | 597,58 |
| 540–590 | 586,73 | 600,39 |

Cold cycles usa tres fixtures simples, ocho ciclos, 16 cambios de geometría
por reemplazo y 27 generaciones. Pico RSS **944,48 MiB**; cierre nativo
78,73 ms y cleanup externo 9,16 ms. El crecimiento entre la primera y última
mediana es 110,50 MiB; continúa creciendo al final y no se declara meseta.
Conserva [muestras y análisis](../evidence/H22-cold1-cycles600-r2/analysis.json).

El ensayo estable mantiene tres fixtures durante 600 s. Pico RSS **949,83 MiB**;
cierre 90,91 ms y cleanup 9,10 ms. Las tres últimas medianas abarcan 2,81 MiB,
una estabilización local observada, no un límite garantizado a horas/días.
`vmmap -summary` y dos `heap -s --noContent` alteran la carga: sus FPS quedan
**NOT_EVALUATED** para aceptación, aunque los frames y cierres se conservan.
[Análisis de recursos](../evidence/H22-cold1-memory600-r1/analysis.json) y
[perfil por identidad](../evidence/H22-cold1-memory600-r1/memory-analysis.json).

## Qué se midió

El supervisor obtiene RSS y metadatos públicos con libproc; las muestras de
`proc_pid_rusage` conservan PID, nacimiento y start-abstime. Roles sólo se
derivan de argumentos del árbol propio mediante una lista finita. No se leen
buffers de aplicaciones ajenas. CPU es porcentaje de un core, no utilización
de GPU. Procesos más cortos que el intervalo pueden no quedar muestreados.

RSS, physical footprint, virtual, malloc en uso y reservas describen conceptos
distintos. Las sumas secuenciales por proceso no son RAM física única de la
coalición. Las categorías de vmmap se solapan y no deben sumarse como memoria
exclusiva. El paseo público de regiones llega a veces al límite 8192 y se marca
PARTIAL; el resumen vmmap completo se conserva como observación independiente.

Se completaron 24 resúmenes vmmap: ocho identidades en 60/300/570 s, con hash,
identidad anterior/posterior y timeout por proceso. Valores redondeados:

| Proceso | Malloc en uso 60 → 300 → 570 s | Observación |
|---|---|---|
| Browser | 30,8 → 64,7 → 66,8 MiB | Mayor crecimiento de asignaciones del árbol |
| GPU | 16,2 → 8,66 → 9,29 MiB | Footprint 253,5 → 281,8 → 283,6 MiB; malloc no explica todo |
| Renderers activos | ~5,17 → ~5,36 MiB por proceso | Footprint final ~43–45 MiB; asignaciones tardías casi estables |
| Renderer spare | 11,8 → 3,78 MiB | Su reducción impide atribuir todo el cambio a instancias visibles |
| Network / storage | 10,6 → 2,74 / 1,68 → 1,72 MiB | Browser, red y helpers siguen compartidos |

Los resúmenes heap del mismo browser contienen 68.101.856 y 68.504.816 bytes
en uso: **+402.960 bytes** entre observaciones tardías. Identifican 10.000
objetos CrZombie/CrFatZombie en ambas, aproximadamente 4,3 MB. El código
Chromium documenta esa retención diagnóstica acotada; no demuestra que explique
los ~62 MB de asignaciones sin clase Objective-C ni todo el crecimiento.
[Fuentes fijadas y hashes](../research/h22-memory-sources.json).

No hay stacks de asignación ni una prueba de propiedad para cada bloque CEF.
Por ello no se afirma “son sólo cachés” ni “hay una fuga demostrada”. La siguiente
investigación útil requiere perfiles de asignación simbolizados del browser y
GPU, correlacionados por identidad y reproducibles sin tocar datos reales.
No justifica modificar el producto ni ampliar el presupuesto actual.

## Buffers propios y presupuesto

Cada mailbox retiene un pending y un lease completo; la copia entrante puede
coexistir temporalmente. Las contabilidades terminales nativas quedan
conservadas y con cero bytes/leases propios al cerrar cada generación. Eso
acredita buffers del host, no libera necesariamente caches internas de CEF.

El nuevo receiver binario puede tener payload de validación, copia de publish,
pending anterior y lease: **hasta cuatro imágenes completas transitorias**,
además del mailbox productor, sockets y texturas. A 640×360 son 3,52 MiB por
receiver; al máximo 1920×1080 son 31,64 MiB. H23 debe presupuestar esos dominios
por separado; no se anuncia zero-copy ni un ahorro no medido.

El watchdog mantiene **2048 MiB RSS muestreado** como emergencia del árbol CEF,
no capacidad admitida ni límite duro instantáneo del kernel. Se rechazan
observaciones RSS faltantes de procesos propios. Una futura composición debe
añadir su presupuesto OBS/encoder/captura y medir el margen real.

## Fallos del instrumento conservados

`H22-cold1-cycles600-r1` terminó por timeout de `ps`, con cleanup externo y
evidencia parcial preservada; no cuenta como un soak aprobado. El observador
H22 sustituye ese subprocess por consultas libproc acotadas y conserva los
tests reales de deadline, RSS y reap de hijos propios.

`H22-pilot-r1-lower3h` conserva divergencia entre duración nativa y monotónica
del supervisor, compatible con suspensión del sistema, sin causalidad probada.
Desde pilot-r2 se comparan mach_absolute_time y mach_continuous_time: una
discontinuidad >50 ms falla el ensayo, sin recortar huecos. Un `caffeinate -i`
propio vive sólo durante el lock; no cambia pmset, políticas globales, pantalla
ni suspensión forzada. Sus procesos se cierran al liberar el slot.

## Contraste de 600 s con resolución cerrada

[H22-cold4-memory600-r1](../evidence/H22-cold4-memory600-r1/analysis.json)
usa tres fixtures simples 640×360/30, perfil nuevo privado y política
closed-resolver-v2. [NetLog](../evidence/H22-cold4-memory600-r1/network-analysis.json)
conserva 986 eventos, control propio rechazado con −130, **cero eventos TCP/UDP,
cero hits en listeners y cero manifests**. Es observación de Chromium y del
control propio, no una captura OS completa ni aceptación de terceros.

| Ventana, segundos | Footprint mediano, MiB | CPU media, % de un core |
|---|---:|---:|
| 30–90 | 473,70 | 19,76 |
| 120–180 | 491,95 | 21,50 |
| 240–300 | 519,29 | 19,15 |
| 360–420 | 525,90 | 20,71 |
| 480–540 | 529,58 | 19,59 |
| 540–590 | 532,92 | 18,80 |

El delta entre primera y última mediana es **+59,21 MiB**. Las tres últimas
abarcan **7,02 MiB** y siguen aumentando: no se declara meseta. El pico RSS
muestreado fue **1016,61 MiB**, superior al pico del perfil antiguo; el cambio
no acredita una reducción general de memoria. El cierre nativo tomó 49,88 ms,
cleanup externo 8,65 ms, con cero leases/bytes propios retenidos y sin procesos
observados sobrevivientes. FPS queda NOT_EVALUATED por instrumentación.

El [perfil por identidad](../evidence/H22-cold4-memory600-r1/memory-analysis.json)
completó las 24 tomas vmmap de ocho procesos, sin etapas faltantes. No se ejecutó
heap en este contraste; su estado es NOT_FULLY_OBSERVED, no un cero inventado.
Valores redondeados por vmmap:

| Rol | Footprint 60 → 300 → 570 s, MiB | Malloc en uso 60 → 300 → 570 s, MiB |
|---|---|---|
| Browser | 56,9 → 52,8 → 57,9 | 26,6 → 28,6 → 22,7 |
| GPU | 251,7 → 280,7 → 279,1 | 16,4 → 8,81 → 9,38 |
| Renderer A | 36,1 → 42,7 → 44,9 | 5,13 → 5,32 → 5,34 |
| Renderer B | 34,9 → 41,8 → 43,6 | 5,06 → 5,32 → 5,33 |
| Renderer C | 35,1 → 42,0 → 42,8 | 13,1 → 5,33 → 5,34 |
| Renderer spare | 26,1 → 26,1 → 26,1 | 3,69 → 3,69 → 3,69 |
| Network | 23,3 → 21,3 → 21,4 | 10,3 → 2,33 → 2,35 |
| Storage | 20,2 → 20,2 → 20,2 | 1,69 → 1,69 → 1,69 |

Desaparece el gran crecimiento de malloc del browser observado con componentes
instalados. Persisten crecimiento de footprint y dominios GPU/renderers que
malloc no explica por sí solo. Entre perfiles cambiaron updater, resolución,
MediaRouter, sonda propia y NetLog; **no es un A/B que atribuya todo el delta a
un componente concreto**. No hay stacks que identifiquen cada retención. La
conclusión sigue siendo PARTIAL para atribución y meseta prolongada, con
presupuesto y cierre observados; sin optimización especulativa del allocator.

## Soaks finales sin profiler de stacks

El [cold cycles final](../evidence/H22-soak-r2-coldcycles3/analysis.json) usa el
mismo perfil cerrado, 27 generaciones y 16 reemplazos. No tiene vmmap/heap
concurrente; sus métricas libproc y gates de frames se evalúan por separado.

| Ventana, s | Cold cycles: footprint mediano, MiB | CPU media, % de un core |
|---|---:|---:|
| 30–90 | 453,81 | 17,02 |
| 120–180 | 460,88 | 16,34 |
| 240–300 | 472,06 | 16,44 |
| 360–420 | 477,20 | 17,19 |
| 480–540 | 481,37 | 16,86 |
| 540–590 | 493,48 | 18,25 |

El delta entre primera y última mediana es **+39,66 MiB**; la última sube
12,11 MiB respecto de la anterior. **No demuestra meseta.** El último recreate
está programado a 482 s: la cola final tiene tres widgets estables, no churn
durante los 600 s completos. Pico RSS 986,13 MiB, cierre nativo 2317,59 ms y
cleanup externo 13,47 ms; los frames y leases propios terminan liberados.
NetLog observa 4114 eventos, control −130, cero sockets/hits/manifests.

No se resta este delta al perfil estable instrumentado para atribuir una
mejora: cambian lifecycle, historia de identidades e instrumentación. El límite
RSS de 2048 MiB se conserva como parada de emergencia, no como demostración
de estabilidad indefinida ni presupuesto aprobado para captura/encoder.

La [mezcla final de 600 s](../evidence/H22-soak-r2-widgetmix3h/analysis.json)
conserva 31 generaciones y 14 reemplazos. Su funcionalidad/cierre pasan, pero
el auditor de workload falla por pausas tardías; no es capacidad admitida.

| Ventana, s | Mezcla: footprint mediano, MiB | CPU media, % de un core |
|---|---:|---:|
| 30–90 | 461,59 | 8,69 |
| 120–180 | 465,03 | 8,86 |
| 240–300 | 471,69 | 8,15 |
| 360–420 | 484,10 | 8,45 |
| 480–540 | 499,62 | 8,50 |
| 540–590 | 502,78 | 9,16 |

Delta **+41,19 MiB**, última ventana +3,16 MiB; no demuestra meseta. La última
operación de lifecycle ocurrió a 404,60 s, por lo que las últimas ventanas
observan una mezcla estable. Pico RSS 933,70 MiB, cierre 121,86 ms y cleanup
9,95 ms, cero leases/bytes de frames retenidos. CPU media incluye idle y no
explica por sí sola los stalls de hasta 465,57 ms; el máximo heartbeat UI fue
488,38 ms. NetLog conserva 4535 eventos y cero sockets/hits/manifests.

El [Goal vertical final de 600 s](../evidence/H22-soak-r2-goals3v/analysis.json)
pasa 291 eventos completos, contabilidad y cierre, sin profiler concurrente.

| Ventana, s | Goal vertical: footprint mediano, MiB | CPU media, % de un core |
|---|---:|---:|
| 30–90 | 521,38 | 7,46 |
| 120–180 | 540,89 | 7,95 |
| 240–300 | 452,47 | 7,87 |
| 360–420 | 548,39 | 7,53 |
| 480–540 | 508,19 | 7,62 |
| 540–590 | 488,12 | 7,57 |

El delta final es −33,26 MiB, pero las medianas oscilan entre 452,47 y
548,39 MiB: no es una meseta estable ni demuestra ausencia de fuga. No se
atribuyen esas oscilaciones a caches, GPU o liberación concreta sin stacks
de allocation de ese ensayo. Pico RSS 1425,31 MiB, cierre 65,14 ms y cleanup
9,01 ms; cero frames/leases retenidos. NetLog: 1124 eventos, control −130,
cero sockets/hits/manifests. Es un único ensayo de diez minutos con eventos
cada seis segundos; no acredita sesiones de horas ni memoria conjunta con OBS.
