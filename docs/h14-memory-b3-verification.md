# H14 — B3: lifecycle 1080p30 con pausa explícita

Estado: **PARTIAL**. La corrida real completó tres ciclos de video visible,
oculto, oculto pausado y retirado, con cleanup sin errores. Durante la pausa,
la CPU mediana fue **43.7–50.5% menor** que durante la reproducción oculta de
cada ciclo; los relojes de las cuatro fuentes quedaron detenidos. Malloc
in-use permaneció prácticamente igual durante la pausa y descendió al retirar
las fuentes. La colección nativa cumple su presupuesto; el RPC de memoria
sigue excediendo el suyo. No se establece un veredicto de fuga ni aceptación
de 60 FPS, outputs o soak de 30 minutos.

## Identidad y alcance

Owner **PID 11038**, portable B3 ejecutado fuera del checkout con PATH de
sistema y sin overrides DYLD. El [contexto del owner](../var/evidence/h14-portable-b3-1794955908679384000/context.json)
declara fuente compilada `d0deeb5` y fuente de empaquetado `ceb40ce`.
La medición usa canvas **1920×1080@30**, cuatro videos propios silenciosos
1080p30, decodificación software, loop de 6 s y composición 2×2.

Secuencia: baseline 20 s; tres ciclos de visible 20 s, oculto reproduciendo
20 s, oculto pausado 20 s y settling de 60 s después de retirar fuentes.
Son **89 muestras**, con intervalo nominal de 5 s: cinco por fase corta y
trece por fase de retirada. Las trece fases suman **380.95 s**; entre primera
y última muestra transcurren **384.61 s**, incluidas operaciones intermedias.
El reporte conserva `measurement_completed=true`, `cleanup_errors=[]`, sin
error de ejecución ni issues en las 89 muestras. No inició outputs ni usó
entradas de audio.

- [Reporte original](../var/evidence/h14-memory-b3-30-01/report.json),
  [muestras](../var/evidence/h14-memory-b3-30-01/samples.jsonl) y
  [operaciones MCP](../var/evidence/h14-memory-b3-30-01/operations.jsonl).
- [Derivado offline reproducible](../var/evidence/h14-memory-b3-offline-analysis/analysis.json),
  generado por [analyze_h14_memory.py](../scripts/analyze_h14_memory.py).

| Insumo | SHA-256 |
|---|---|
| Ejecutable B3 | `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc` |
| Harness usado | `d7f89e87515a0206224739139858de5439bb22c502d974dba75a7d4a261281c9` |
| Fixture de entrada | `4360a3700b88afa0d7b3b7493b292e243832d40b7c7ae122368d4118ae171b92` |
| `report.json` | `c3e1a171483fc1c72966a7ec2d3918e72fad5f21e2be6dd05ae5fddc4683c3fe` |
| `samples.jsonl` | `83c9c9d7a44b00ed7165d6344a928103a552fd133965095245da81e30bb474e6` |
| `operations.jsonl` | `b8f572ebbee205298052b923a8d17dfca681d6a528740fe7d2a059d76b453d17` |
| Analizador offline | `e20a8ed5685d739d37c2a2a2623416fe5116987a1bba04093ac4f97c305e99bd` |
| Derivado `analysis.json` | `b39d35a594a91e67c4474a2940815a85f62868043be1526725218e737c806e5f` |

El asset importado es el mismo material canónico de 10,979,448 bytes,
1920×1080/6000 ms, `has_audio=false`, SHA-256
`efc472d4b1d258fc5d37612aae2c8e4659d9a5a62e4f54d5895ef05033a14ff9`.

Para recalcular desde la raíz del checkout, sin conectar con Motive:

```sh
python3 scripts/analyze_h14_memory.py var/evidence/h14-memory-b3-30-01
```

El comando emite JSON determinista; `--output RUTA_NUEVA` permite conservar
otra copia y rechaza sobrescribir archivos existentes. El analizador verifica
el hash de muestras contra el reporte, recalcula distribuciones desde cada
muestra y no abre apps, medios, dispositivos ni conexiones IPC. Se contrastaron
sus estadísticas de las 13 fases con el reporte original y también las 10
fases de B2; todas coinciden. No se modificó evidencia original.

## Resultados por fase

Memoria en **MiB (2²⁰ bytes)**, valores medianos. CPU por intervalos nativos,
con 100% equivalente a un núcleo. El primer delta al cambiar de fase se
conserva aparte y no entra en la distribución de la siguiente fase: quedan
cuatro intervalos CPU por fase corta y doce por retirada.

| Fase | CPU % | RSS MiB | Footprint MiB | Malloc in-use MiB | Malloc allocated MiB |
|---|---:|---:|---:|---:|---:|
| Baseline | 15.02 | 174.67 | 369.74 | 85.40 | 166.16 |
| Ciclo 1 visible | 40.23 | 716.86 | 969.28 | 575.94 | 669.56 |
| Ciclo 1 oculto | 34.34 | 741.41 | 1014.02 | 587.87 | 710.03 |
| Ciclo 1 pausado | 19.34 | 738.59 | 1037.31 | 587.83 | 730.03 |
| Ciclo 1 retirado | 15.48 | 201.78 | 944.30 | 86.20 | 690.16 |
| Ciclo 2 visible | 39.12 | 690.28 | 1143.22 | 573.15 | 814.75 |
| Ciclo 2 oculto | 35.03 | 743.03 | 1143.75 | 585.08 | 830.81 |
| Ciclo 2 pausado | 17.33 | 725.94 | 1146.05 | 585.07 | 830.81 |
| Ciclo 2 retirado | 15.12 | 160.11 | 341.00 | 86.29 | 794.16 |
| Ciclo 3 visible | 38.82 | 675.45 | 948.53 | 573.02 | 818.73 |
| Ciclo 3 oculto | 34.41 | 746.16 | 976.99 | 584.98 | 839.05 |
| Ciclo 3 pausado | 17.24 | 744.06 | 944.28 | 584.98 | 839.03 |
| Ciclo 3 retirado | 16.59 | 236.56 | 341.83 | 86.31 | 802.16 |

Los 89 snapshots nativos son `PASS`, con `cpu.available` de tipo booleano y
valor `true` en todos ellos. La corrección de esquema pendiente en B2 queda
observada en B3. Los **76 deltas CPU** recalculados con los acumulados getrusage
y timestamps nativos coinciden con el reporte, con diferencia numérica cero
en este recálculo. Esto verifica esos campos, no todos los booleanos del producto.

## Comparación dentro de cada ciclo

Las doce operaciones de ocultamiento devuelven
`layouts.horizontal.visible=false` en las capas propias. Las doce operaciones
`overlay_event(pause)` completan con éxito. Las 60 observaciones de hijos en
fases ocultas declaran `playing`; las 60 observaciones durante pausa declaran
`paused`, mantienen un hijo por fuente y `audio_mixers=0`. Los doce relojes
individuales permanecen constantes a través de las cinco muestras de su fase
pausada. Los IDs y series completas se conservan en el derivado.

| Ciclo | CPU oculta % | CPU pausada % | Cambio, puntos porcentuales | Reducción respecto a oculta |
|---|---:|---:|---:|---:|
| 1 | 34.34 | 19.34 | −15.01 | 43.7% |
| 2 | 35.03 | 17.33 | −17.70 | 50.5% |
| 3 | 34.41 | 17.24 | −17.18 | 49.9% |

La pausa se asocia con menor CPU en los tres ciclos y con detención del reloj
de medios, conservando los recursos del hijo. Malloc in-use cambia menos de
**0.11 MiB** entre el último snapshot oculto y el último pausado de cada ciclo.
Al retirar las fuentes después de pausar, in-use desciende aproximadamente
**499–502 MiB**. Pausar no equivale a descargar el video.

Es una comparación secuencial, no aleatorizada. La oclusión/visibilidad efectiva
de GPUI no se cuantificó en las muestras y el coordinador informó dificultades
de Stage Manager. No se atribuyen diferencias B2/B3 a la pausa ni a un cambio
de código: la misma fixture y FPS no eliminan diferencias de estado del sistema
o visibilidad. Tampoco se atribuyen todos los cambios VM de B3 a la pausa.
Los estados y relojes no prueban frescura de píxeles decodificados.

El producto conserva `restart_on_activate=false` y
`close_when_inactive=false`; la pausa fue una operación explícita del harness.
No se implementó una nueva política de pausa automática al ocultar. Véase la
explicación de OBS y visibilidad de capa en el [informe B2](h14-memory-b2-verification.md).

## Endpoints de memoria y presupuestos

Última muestra del baseline y de cada settling de 60 s; no son las medianas
de la tabla anterior. Las categorías VM se superponen y no deben sumarse.

| Endpoint | RSS MiB | Compressed MiB | Footprint MiB | Malloc in-use MiB | Malloc allocated MiB |
|---|---:|---:|---:|---:|---:|
| Baseline | 172.16 | 44.27 | 369.74 | 85.40 | 166.17 |
| Retirada 1 | 163.31 | 628.78 | 944.33 | 86.27 | 690.16 |
| Retirada 2 | 159.36 | 20.23 | 341.00 | 86.19 | 794.12 |
| Retirada 3 | 152.97 | 30.67 | 339.70 | 86.31 | 802.16 |

Al tercer endpoint, respecto al baseline final, malloc in-use es **+0.91 MiB**,
allocated **+635.98 MiB** y footprint **−30.03 MiB**. El primer settling
retuvo footprint elevado; en los posteriores el footprint descendió mientras
allocated siguió alto. La reserva informada por malloc no representa por sí
sola páginas físicas residentes. No se puede atribuir ownership, liberación
de todos los objetos ni una fuga con estos contadores. No se midieron stacks
de asignación, presión global del sistema ni utilización GPU. El mayor
footprint muestreado fue **1147.25 MiB**, menor que el umbral de revisión
de 1536 MiB; eso no constituye una garantía de máximos entre muestras.

| Observación, 89 consultas | Mediana | p95 | Máximo | Presupuesto |
|---|---:|---:|---:|---|
| Colección nativa | 0.493 ms | 0.897 ms | 1.215 ms | p95 ≤2 ms: cumple |
| RPC de memoria | 30.54 ms | 48.05 ms | 91.29 ms | p95 ≤20 ms: excede |
| RPC de status | 37.56 ms | 40.18 ms | 84.58 ms | Medido por separado |

**66/89 RPC de memoria (74.2%)** superan 20 ms y los p95 de las trece fases
exceden el presupuesto. Los p95 por fase y los del conjunto están en el
derivado; se usa nearest-rank. Con cinco o trece muestras por fase, p95 es el
máximo de esa fase. El tiempo nativo excluye JSON/transporte; no hay medición
que reparta la latencia restante entre cola, IPC o serialización. La latencia
de pared no equivale a CPU ni mide por sí sola cuánto altera el render el
instrumento. Sigue pendiente investigar el presupuesto RPC.

## Cleanup, continuidad y límites pendientes

Entre primera y última muestra se registran **11538 renders**, **10746 copias
de preview** y **31 preview busy drops** adicionales, sin aumento de
`lagged_frames` ni `video_skipped_frames`. No se clasifican diferencias entre
renders/copias como pérdida de salida. Ningún slot obtuvo attempt, por lo
que los skips no aceptan encoders, streaming o entrega.

Las doce fuentes y capas propias, la escena y el asset se retiraron sin
errores. El estado final restaura escenas/fuentes, escena activa, variante,
video, perfiles/configuración de salida y store del mixer. Quedan cero fuentes
de overlay dinámico y ninguna animación activa. El proyecto sigue en versión
5; avanzan la revisión **3→124** y `graph.next_id` **2→28**. El estado no es
idéntico byte a byte y no se ejecutó `save_project`. Este informe termina en
el cleanup de la corrida; no afirma cierre del owner, que el coordinador
puede reutilizar para las pruebas posteriores de GPUI.

Quedan pendientes lifecycle a 60 FPS, dual-soak de 1800 s y verificación de
medios reales con PTS/DTS, frescura y sincronización A/V. Aquí
`decoded_freshness`, `audio_video_sync` y `gpu_utilization` permanecen
`NOT_EVALUATED`. No hay inferencia de ausencia de fuga a partir de RSS bajo,
footprint final bajo o retorno de malloc in-use. La cobertura del instrumento
y sus límites están en la [metodología](h14-memory-methodology.md).
