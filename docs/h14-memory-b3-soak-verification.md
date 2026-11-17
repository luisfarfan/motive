# H14 — B3: lifecycle 1080p60 y doble salida durante 30 minutos

Estado: **PARTIAL**. La corrida real completó los tres ciclos de lifecycle a
1080p60 y un soak de **1800.07 s** con grabación y RTMP local simultáneos.
La CPU mediana durante el soak fue **52.72% de un núcleo** y el footprint
máximo muestreado, **1277.03 MiB**. La colección nativa cumple su presupuesto;
el RPC de memoria excede el suyo. Los contadores incluyen **39 video skips**,
un render lagged y cero dropped frames de los outputs: esas cifras no son
intercambiables. El análisis de medios y sus límites se detallan abajo.

## Identidad, método y evidencia

Owner **PID 32487**, portable B3 fuera del checkout:
`/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app`.
Fuente compilada `d0deeb5`, empaquetado `ceb40ce`; el producto no cambió durante
la medición. El proceso Python de captura comenzó con los módulos de soporte
de `ceb40ce`. Los cambios posteriores de rutas de harness en `f3f56e2` no se
recargaron en ese proceso. Esta procedencia combina la declaración del
coordinador y los hashes de Git; no inspecciona retroactivamente un intérprete
ya terminado.

Canvas **1920×1080@60**, cuatro instancias de un video propio silencioso
1080p30, decodificación software, loop de 6 s, composición 2×2. Primero se
midieron baseline 20 s y tres ciclos de visible 20 s, oculto reproduciendo
20 s, oculto pausado explícitamente 20 s y settling 60 s tras retirar fuentes.
Después se recrearon cuatro fuentes para el soak, con tono propio **440 Hz**
a ganancia **−12 dB**, grabación MKV y RTMP a receptor local que guarda MKV.
Ambos outputs usaron H.264 VideoToolbox hardware, CBR 4000 kbps, keyframe 1 s,
sin reordenamiento. No se usaron cámara, micrófono ni audio de escritorio.

Son **445 muestras**, intervalo nominal 5 s: 89 de lifecycle y 356 del soak.
Las fases suman **2181.00 s**; primera a última muestra, **2186.51 s**, incluidas
operaciones intermedias. Hay 431 intervalos CPU dentro de fase; sus deltas
recalculados coinciden exactamente con el reporte. Los 445 snapshots nativos
son `PASS`, con `cpu.available` booleano `true`. No hay issues muestreados ni
errores de cleanup. `measurement_completed=true` no equivale a beta aceptada.

- [Reporte original](../var/evidence/h14-memory-b3-60-soak-01/report.json),
  [muestras](../var/evidence/h14-memory-b3-60-soak-01/samples.jsonl) y
  [operaciones](../var/evidence/h14-memory-b3-60-soak-01/operations.jsonl).
- [Análisis de medios](../var/evidence/h14-memory-b3-60-soak-analysis-01/analysis.json)
  y [derivado de memoria](../var/evidence/h14-memory-b3-60-soak-analysis-01/memory-analysis.json).
- [Estado confirmado después del cleanup](../var/evidence/h14-memory-b3-60-soak-01/root-postrun-state.json)
  y [recibo de cierre normal](../var/evidence/h14-memory-b3-60-soak-01/root-normal-shutdown.json).

| Insumo | SHA-256 |
|---|---|
| Ejecutable B3 | `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc` |
| Harness de captura | `d7f89e87515a0206224739139858de5439bb22c502d974dba75a7d4a261281c9` |
| Fixture de entrada | `4360a3700b88afa0d7b3b7493b292e243832d40b7c7ae122368d4118ae171b92` |
| `report.json` original | `4ef2dc13bad5039e903c2033c197c25c43ca3a09e4ac7e25b971634d939002fd` |
| `samples.jsonl` | `b90c07872612f1dfa310e4e8ab3c079c2451797177af8d1babcaed2d2d11d14d` |
| `operations.jsonl` | `eb05344a7806a7ba3db747fe60813d3ae8c9dc7f068b069099a892f1bd429a9a` |
| `analyze_h14_soak.py` | `1ee938c92aac7e7c7aff5107b52dea8eb5fca15a6cb5b620a6a69d5fa84308ce` |
| `h14_soak_helpers.py` | `9d99971813cc603fdc669ab5f3dc3a71dcb773df3c88b80ece67956e8cfca31b` |
| `memory-analysis.json` | `a968ff9721e795cf017bb422d4cf3d337bd70b45b574c90081b40e169dd16dc7` |
| `analysis.json` final | `0627e686a81e9f4145e9bbf55c1917ff1c5ec747cb249abb8f45a6c245846acb` |
| FFmpeg embebido B3 | `d4ee259343e38347333b7a3f31a9603300ce4a6cf9d8bb46e798c41d162f4d25` |
| FFprobe embebido B3 | `a3406f7c9a1c0aa585384914217b70688f43b83b92e7bad830f247ccfd2c90f6` |

El asset canónico importado mide 10,979,448 bytes, tiene `has_audio=false` y
SHA-256 `efc472d4b1d258fc5d37612aae2c8e4659d9a5a62e4f54d5895ef05033a14ff9`.
Los hashes de los módulos de soporte en `ceb40ce` están en el análisis.

Reproducción offline desde este checkout, con directorio de salida nuevo:

```sh
/Users/luisfarfan/Developer/products/motive-h13/var/verify-python/bin/python \
  scripts/analyze_h14_soak.py --postrun-approved \
  --run var/evidence/h14-memory-b3-60-soak-01 \
  --bundle /Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app \
  --capture-support-commit ceb40ce \
  --output var/evidence/h14-memory-b3-60-soak-analysis-REPEAT
```

El Python existente resuelve al entorno de H12, versión 3.14.7, con Pillow.
No se instalaron paquetes. FFmpeg/FFprobe son exclusivamente los del bundle,
con `PATH=/usr/bin:/bin` y sin overrides DYLD. El analizador verifica el hash
del ejecutable, el reporte y los dos medios, usa salida nueva y conserva los
errores originales. Procesa cada medio secuencialmente y no contacta al owner.
Se ejecutó después de finalizar la toma; parte del análisis coexistió con
checks estáticos y smoke de control del coordinador. Su duración operativa no
es una medición de rendimiento de Motive.

## Lifecycle a 60 FPS

Medianas, memoria en **MiB (2²⁰ bytes)**; CPU 100% equivale a un núcleo. Los
primeros deltas al cambiar de fase se excluyen de la distribución de esa fase.

| Fase | CPU % | RSS MiB | Footprint MiB | Malloc in-use MiB | Malloc allocated MiB |
|---|---:|---:|---:|---:|---:|
| Baseline | 21.66 | 263.09 | 369.08 | 85.58 | 166.16 |
| Ciclo 1 visible | 47.65 | 735.05 | 966.17 | 573.48 | 682.62 |
| Ciclo 1 oculto | 39.92 | 840.84 | 1066.08 | 579.40 | 768.75 |
| Ciclo 1 pausado | 22.14 | 841.62 | 1066.55 | 573.46 | 762.61 |
| Ciclo 1 retirado | 21.26 | 801.50 | 973.50 | 86.68 | 738.16 |
| Ciclo 2 visible | 43.70 | 767.03 | 1090.99 | 573.61 | 782.61 |
| Ciclo 2 oculto | 39.21 | 745.70 | 1095.58 | 575.91 | 789.69 |
| Ciclo 2 pausado | 20.86 | 688.23 | 1094.31 | 576.65 | 789.67 |
| Ciclo 2 retirado | 20.54 | 485.77 | 1006.75 | 86.90 | 762.14 |
| Ciclo 3 visible | 49.03 | 707.23 | 1133.47 | 573.87 | 818.64 |
| Ciclo 3 oculto | 45.38 | 766.86 | 1098.42 | 579.80 | 832.81 |
| Ciclo 3 pausado | 27.61 | 595.70 | 1012.25 | 603.51 | 857.94 |
| Ciclo 3 retirado | 20.98 | 147.02 | 350.52 | 87.03 | 802.16 |
| Soak dual | 52.72 | 922.07 | 1258.31 | 764.59 | 1101.22 |

Pausar reduce la CPU mediana respecto a oculto reproduciendo **44.5%, 46.8%
y 39.2%** en los tres ciclos. Las 60 observaciones pausadas declaran `paused`
y los doce relojes de fuente permanecen constantes dentro de su fase.
Ocultar solo no pausa: `restart_on_activate=false` y
`close_when_inactive=false` siguen siendo la configuración de producto. No
se añadió una política automática de suspensión.

Durante la pausa, malloc in-use cambia −5.94, +0.003 y +2.97 MiB entre endpoints;
al retirar las fuentes, baja **486.78, 489.76 y 516.48 MiB**. En el tercer
endpoint retirado, frente al baseline final, in-use es **+1.45 MiB**, allocated
**+635.98 MiB** y footprint **−20.37 MiB**. El footprint retenido tras las dos
primeras retiradas cae en la tercera; las reservas de malloc permanecen altas.
No se deduce ownership ni ausencia/presencia de fuga de esas diferencias.

Es una secuencia corta, no aleatorizada. La oclusión efectiva de GPUI y la
presión global de memoria no se cuantificaron. No se atribuye la diferencia
frente al [lifecycle B3 a 30 FPS](h14-memory-b3-verification.md) solo al FPS.

## Soak: memoria, CPU e instrumentación

Durante los **1800.07 s** hay 356 muestras y 355 intervalos CPU. Las cuatro
fuentes declaran un único hijo silencioso en las **1424 observaciones**; sus
relojes avanzan y su estado es `playing`. Eso no reemplaza la comprobación de
píxeles del medio final.

| Métrica de soak | Mediana | p95 | Máximo muestreado |
|---|---:|---:|---:|
| CPU, % de un núcleo | 52.72 | 56.39 | 62.57 |
| RSS, MiB | 922.07 | 963.25 | 972.34 |
| Footprint, MiB | 1258.31 | 1265.44 | 1277.03 |
| Compressed, MiB | 85.22 | 121.19 | 170.42 |
| Malloc in-use, MiB | 764.59 | 765.00 | 765.12 |
| Malloc allocated, MiB | 1101.22 | 1101.28 | 1101.28 |

Las medianas en ventanas consecutivas de cinco minutos desde la primera
muestra del soak describen una subida inicial y una meseta de in-use; no
demuestran estabilidad indefinida ni identifican al responsable de la subida.

| Ventana, s | Muestras | CPU % | Footprint MiB | In-use MiB | Allocated MiB |
|---|---:|---:|---:|---:|---:|
| 0–300 | 60 | 53.46 | 979.75 | 577.20 | 906.78 |
| 300–600 | 59 | 52.14 | 1214.27 | 764.56 | 1101.22 |
| 600–900 | 59 | 52.55 | 1256.71 | 764.59 | 1101.20 |
| 900–1200 | 59 | 52.55 | 1258.69 | 764.61 | 1101.22 |
| 1200–1500 | 59 | 52.54 | 1264.55 | 764.90 | 1101.28 |
| 1500–1800 | 60 | 53.18 | 1264.69 | 764.98 | 1101.27 |

El [derivado de esas ventanas](../var/evidence/h14-memory-b3-60-soak-analysis-01/five-minute-buckets.json)
registra el hash de muestras y la agrupación exacta: filas `dual_soak`, ventanas
semiabiertas por `floor((monotonic - primera_muestra_soak) / 300)`, medianas y
CPU nula excluida. SHA-256:
`104d7d0d17cc33ef52395fb513024a78185a03bf0b1d57b8f6760a048c4a6382`.

Último snapshot del soak, con las cuatro fuentes y ambos outputs todavía
activos: RSS **935.38 MiB**, compressed **84.59 MiB**, footprint **1264.33 MiB**,
in-use **765.00 MiB**, allocated **1101.27 MiB**. No es un endpoint de memoria
después de stop y limpieza: no se recolectó ese endpoint con este instrumento.
Las categorías se solapan; no se suman. Malloc cubre zonas registradas, no
todos los mmap, IOSurface/GPU ni asignadores externos. Los high-water de zonas
no representan un máximo simultáneo del proceso.

| Consulta | Mediana | p95 | Máximo | Presupuesto |
|---|---:|---:|---:|---|
| Nativa, 445 muestras | 0.557 ms | 0.865 ms | 1.408 ms | p95 ≤2 ms: cumple |
| RPC memoria, 445 muestras | 26.33 ms | 47.24 ms | 144.23 ms | p95 ≤20 ms: excede |
| Nativa, solo soak | 0.558 ms | 0.800 ms | 1.161 ms | p95 ≤2 ms: cumple |
| RPC memoria, solo soak | 25.61 ms | 50.88 ms | 144.23 ms | p95 ≤20 ms: excede |
| RPC status, solo soak | 38.45 ms | 39.56 ms | 531.13 ms | Informativo |

Los p95 de RPC memoria exceden 20 ms en todas las fases; **304/445 consultas**
superan 20 ms. El tiempo nativo excluye JSON y transporte. Sin trazas de cola
y serialización no se distribuye el resto de latencia ni se mide causalmente
la perturbación del instrumento. El footprint máximo está bajo el umbral
de revisión **1536 MiB**, sin garantía sobre máximos entre muestras. Los
presupuestos son criterios de revisión, no garantías generales de producto.

Durante el intervalo entre muestras del soak aumentan: renders **108000**,
copias de preview **50372**, preview busy drops **433**, lagged frames **1**,
video skipped frames **39**. No hay resets de esos contadores. Los 39 skips
aparecen entre **238.90 y 243.96 s** desde la primera muestra del soak; el
lagged frame entre **1106.36 y 1111.44 s**. Esos intervalos de muestreo no
ubican cada evento a precisión de frame y no prueban qué componente lo causó.

## Medios decodificados

**PASS en ambos medios para el alcance de formato, cadencia, píxeles y PCM.**
El análisis global conserva **PARTIAL**. Los diez procesos FFmpeg/FFprobe
finalizaron con código cero y stderr vacío. Se decodificó todo el video y
todo el audio; no se recortó el final ni se cambiaron tolerancias después de
ver el resultado. Los originales conservaron hashes y metadata de archivo.

| Medio | Bytes | SHA-256 |
|---|---:|---|
| [Grabación MKV](/Users/luisfarfan/Movies/Motive/motive-1794957324258691.mkv) | 918450629 | `6ee7993f8a66a5acdd98106cd7e59228f233647fd8e3835bb5d1d510d2bb0be2` |
| [RTMP local recibido](../var/evidence/h14-memory-b3-60-soak-01/received-loopback.mkv) | 918216472 | `d50e0e8dc72744aef1294e688386d2f29d9e248fa2c765ec744a8f52074eeb15` |

Ambos son H.264 High, **1920×1080, 60/1 FPS, yuv420p BT.709**, sin B-frames;
AAC-LC **48 kHz estéreo**. Time base de Matroska, 1/1000.

| Comprobación | Grabación | RTMP local recibido |
|---|---:|---:|
| Frames de video decodificados | 108057 | 108028 |
| Primer / último PTS video, s | 0 / 1800.933 | 0.021 / 1800.471 |
| Span visual, incluido último periodo nominal, s | 1800.9497 | 1800.4667 |
| Duración de contenedor, s | 1800.981 | 1800.490 |
| Gaps video PTS/DTS, ms | 16–17 | 16–17 |
| Paquetes AAC | 84421 | 84398 |
| Gaps AAC PTS/DTS, ms | 21–22 | 21–22 |
| Frames PCM por canal | 86446080 | 86423552 |
| Duración PCM, s | 1800.9600 | 1800.4907 |
| RMS global por canal, aprox. | 0.01119852 | 0.01119846 |
| Peak PCM L / R | 0.01741320 / 0.01730179 | 0.01803438 / 0.01805654 |
| Ventanas completas PCM de 100 ms | 18009 | 18004 |
| Muestras no finitas / abs ≥0.999 | 0 / 0 | 0 / 0 |
| Ventanas completas bajo −80 dBFS RMS | 0 | 0 |
| Error de amplitud del tono 440 Hz en ventanas, dB | −0.00938…−0.00535 | −0.00682…−0.00197 |

Todos los PTS y DTS de paquetes, y PTS de frames, están presentes y crecen
estrictamente. No hay gaps sobre **25 ms** en video ni **23 ms** en AAC.
El primer PTS AAC de grabación es −21 ms; su secuencia completa se conserva,
sin convertir ese priming en un error ni inferir sincronización desde él.
Los dos spans visuales superan 1800 s. La diferencia de duración entre medios
no mide pérdida: son intentos independientes con inicios/stops distintos.

La decodificación PCM usa bloques de hasta 1 s, no una matriz de 30 minutos
en RAM. RMS, peak, no finitos y clipping abarcan todas las muestras; el gate
de silencio usa ventanas completas de 100 ms y conserva además una ventana
parcial final por medio. No excluye transitorios más cortos de 100 ms. Se
midieron **32 ventanas de 1 s por medio**, cada una en ambos canales, para
440 Hz y controles 997/2011 Hz: la amplitud 440 Hz está dentro del umbral
predefinido ±2 dB respecto a 0.01584893. Esto no es seguimiento continuo de
pitch ni prueba de audición humana.

La frescura usa **todos los frames** reducidos a gray 128×72. Cada MD5 de
frame coincide con el `framemd5` oficial de FFmpeg, y su cantidad coincide
con FFprobe. Los cuatro cuadrantes 64×36 tienen hashes independientes. Para
distinguir variaciones pequeñas de compresión de movimiento más sustancial,
se compara una grilla de 16×9 píxeles por cuadrante con su último frame de
cambio significativo: MAD ≥1 nivel y al menos 2% de sondas con delta ≥8.
No se remueven duplicados: una fuente de 30 FPS en canvas 60 FPS los permite.

| Medio / cuadrante | Pares con cambio significativo | Mayor run idéntico exacto, s | Mayor run sin cambio significativo, s |
|---|---:|---:|---:|
| Grabación / superior izquierdo | 39205 | 0.334 | 0.567 |
| Grabación / superior derecho | 39457 | 0.317 | 0.567 |
| Grabación / inferior izquierdo | 39186 | 0.351 | 0.601 |
| Grabación / inferior derecho | 39362 | 0.334 | 0.567 |
| RTMP / superior izquierdo | 39636 | 0.184 | 0.567 |
| RTMP / superior derecho | 39310 | 0.100 | 0.567 |
| RTMP / inferior izquierdo | 39632 | 0.083 | 0.517 |
| RTMP / inferior derecho | 39436 | 0.167 | 0.567 |

Los ocho cuadrantes pasan el umbral previo de revisión **<1 s** sin cambio
significativo, pero sí hay un episodio de aproximadamente **0.6 s** en la
grabación, PTS 239.033–239.617 s. El recibido presenta su episodio principal
en PTS 238.671–239.221 s. La cercanía al intervalo de 39 skips merece revisión;
no se establece causalidad ni igualdad del origen de esos relojes. Pasar el
umbral no equivale a ausencia de toda pausa visual. La reducción y la grilla
pueden omitir detalle fino; no sustituyen una inspección subjetiva a 1080p.
Los CSV por frame, framemd5, frames/paquetes JSONL y estadísticas PCM se
conservan en los subdirectorios `recording/` y `streaming/` del análisis.

## Entrega, cleanup y límites

La correlación de entrega queda **INCONCLUSIVE** en los dos medios. El
prefijo inicial de audio coincide en tamaño, keyframe y deltas PTS; para los
primeros tres paquetes de video, keyframe y deltas encajan pero **ninguno de
los tamaños coincide**. El guard de origen no se relaja y el clasificador de
tail no se aplica con ese origen sin demostrar. No se atribuye el desacuerdo
a pérdida ni se presume una transformación de empaquetado: hace falta probar
la correspondencia. Incluso una coincidencia de metadata no sería identidad
criptográfica ni cerraría la ruta encoder→observador.

| Contador terminal / observación real | Grabación | Streaming |
|---|---:|---:|
| Encoded frames nativos | 108060 | 108030 |
| Output frames nativos | 108058 | 108029 |
| Paquetes de video observados antes del plugin | 108058 | 108029 |
| Paquetes video reales / frames decodificados | 108057 | 108028 |
| Diferencia encoded − decoded | 3 | 2 |
| Diferencia output − decoded | 1 | 1 |
| Output dropped frames nativos | 0 | 0 |
| Paquetes de audio observados / reales | 84421 / 84421 | 84398 / 84398 |
| Stop solicitado → quiescence observado | 189 ms | 189 ms |

Son snapshots terminales por intento **1**, distintos de los deltas de
contadores entre muestras durante soak. La traza retiene 256 registros por
slot y sobrescribió 192223/192171 registros; `trace_missed_records=0` no
significa que conserve toda la toma. No se descuentan las diferencias de
conteo como si fueran un cierre ya demostrado. `frames_written`,
`frames_received` y `frames_decoded` nativos siguen `null`,
`delivery_verified=false`. La verificación offline mide frames reales en
estos archivos, sin cambiar ese estado de producto.

El cleanup retira las 16 fuentes de video propias de lifecycle/soak, sus
capas, escena de prueba, asset y entrada de tono. Restablece fuentes/escenas
originales, escena activa, variante, resolución/FPS y perfiles `standard`.
El mixer queda sin inputs; `next_id` avanza 1→2. La configuración de output
conserva el endpoint RTMP local sin credencial porque no existe una operación
`unset`: el reporte lo declara en `cleanup_note`. La revisión avanza 2→171,
`graph.next_id` 2→36 y el proyecto cargado v3 se normaliza a v5; el harness
no ejecuta `save_project`. No es restauración byte a byte ni una prueba de
persistencia de esos stores.

El coordinador confirmó outputs `idle`, `native_busy=false`, sin issues,
mixer vacío y ausencia de overlays dinámicos, después solicitó cierre normal.
El recibo identifica PID 32487 y la revisión 172; el proceso terminó sin
force-quit. No hubo reinicio ni purga del owner durante el soak.

Permanecen abiertos: presupuesto RPC, investigación del episodio de skips y
pausa subsegundo, correspondencia de entrega y pérdidas de tail, utilización
GPU y diagnóstico de ownership/asignaciones. La sincronización A/V es
**NOT_EVALUATED**: un tono continuo y videos silenciosos no ofrecen un evento
audiovisual común identificable. RTMP de loopback no verifica red remota,
RTMPS ni recepción de una plataforma. El estudio de memoria es
**INCONCLUSIVE_NO_OWNERSHIP_OR_ALLOCATION_STACK_EVIDENCE** para fugas.
No se infiere ausencia de fuga de RSS, la meseta de malloc ni el retorno de
footprint. La aceptación global H14 sigue separada de estos checks de medios.
Véase la [metodología de memoria](h14-memory-methodology.md) para cobertura
del instrumento y la [verificación 1080p30](h14-memory-b3-verification.md)
para la corrida independiente anterior.
