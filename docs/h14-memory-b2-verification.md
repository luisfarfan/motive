# H14 — B2: memoria y rendimiento del lifecycle 1080p30

Estado: **PARTIAL**. La ejecución real completó tres ciclos y su cleanup sin
errores. La colección nativa cumple el presupuesto de observación; la latencia
RPC de memoria lo excede. La retirada de videos reduce malloc in-use cerca del
baseline, pero conserva reservas y footprint superiores al inicio. Estos datos
no demuestran fuga ni ausencia de fuga. No hubo grabación ni streaming en esta
corrida; el dual-soak de 1800 s y la aceptación a 60 FPS siguen pendientes.

## Ejecución y evidencia

El owner fresco **PID 93493** ejecutó el portable B2 fuera del checkout, desde
`/Users/luisfarfan/Developer/motive-h14-portable/b2`, con PATH de sistema y sin
overrides DYLD. La configuración medida fue **1920×1080 a 30 FPS**. Se usaron
cuatro fuentes de video propias, silenciosas, con decodificación software y
loop de 6 s, distribuidas en una composición 2×2. El material de entrada es
testsrc2 generado localmente a 1080p30. No se abrieron dispositivos físicos.

Secuencia: baseline de 20 s; tres ciclos con 20 s visible, 20 s oculto y 60 s
de settling tras retirar capas y fuentes. Hubo **74 muestras**, cada 5 s:
cinco por baseline/visible/oculto y trece por fase de retirada. Las diez fases
sumaron **320.65 s**; entre la primera y última muestra transcurrieron
**323.62 s**, incluyendo operaciones entre fases. El reporte conserva
`measurement_completed=true`, `cleanup_errors=[]` y ningún error de ejecución.

Evidencia original, sin reescritura durante este análisis:

- [Reporte de la corrida](../var/evidence/h14-memory-b2-30-01/report.json),
  [muestras](../var/evidence/h14-memory-b2-30-01/samples.jsonl) y
  [operaciones](../var/evidence/h14-memory-b2-30-01/operations.jsonl).
- [Identidad del owner](../var/evidence/h14-memory-b2-owner30-1794954833415580000/context.json),
  [estado previo al cierre](../var/evidence/h14-memory-b2-owner30-1794954833415580000/normal-shutdown.json)
  y [log del proceso](../var/evidence/h14-memory-b2-owner30-1794954833415580000/studio.log).
- [Derivación offline](../var/evidence/h14-memory-b2-offline-analysis/analysis.json)
  con hashes de entrada, distribuciones, endpoints y deltas en bytes.

| Insumo | SHA-256 |
|---|---|
| Ejecutable B2 | `16294752571dc8599df8fdadfa4710963c4d51bd957d5cf569be2ff53a539ceb` |
| Harness usado en la corrida | `6161e11914b6339c2d25ac9e5680b8c4522c68f12a2fe01afabbfa3fb194eb1b` |
| Fixture de entrada | `4360a3700b88afa0d7b3b7493b292e243832d40b7c7ae122368d4118ae171b92` |
| Asset importado canónico | `efc472d4b1d258fc5d37612aae2c8e4659d9a5a62e4f54d5895ef05033a14ff9` |
| `report.json` | `470ef46434e822400daf4452832869469b57261e63cf0e157dea1bd47ce2d288` |
| `samples.jsonl` | `f63e74999164d6b9d2eaf0535ccca44f1cb9b2574fd6011a597dab6245adc140` |
| `operations.jsonl` | `647257ff0556cd175165b813471cf1d16504c1150200ca0ad07ebf94a3a0d889` |
| Derivación offline `analysis.json` | `0dc3480dfba25c301f7e9e36a66ae91ed96c4066b46555268611dc3bf287ecdc` |

El asset importado mide 10,979,448 bytes, conserva 1920×1080/6000 ms y declara
`has_audio=false`. No se compara su hash con el archivo de entrada como si la
importación debiera ser una copia idéntica.

## Resultados por fase

Valores de memoria en **MiB (2²⁰ bytes)**. CPU mediana por intervalo, donde
100% representa un núcleo. RSS, footprint y malloc son medianas de cada fase;
no se suman sus categorías. La CPU excluye el primer intervalo al cambiar de
fase, que puede incluir creación, ocultamiento o retirada. Hay cuatro deltas
CPU por fase corta y doce por fase de retirada.

| Fase | CPU % | RSS MiB | Footprint MiB | Malloc in-use MiB | Malloc allocated MiB | RPC memoria p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 14.35 | 213.30 | 374.91 | 84.42 | 174.14 | 39.80 |
| Ciclo 1 visible | 39.08 | 703.88 | 949.88 | 575.28 | 653.69 | 32.13 |
| Ciclo 1 oculto | 34.33 | 761.42 | 1024.74 | 587.30 | 730.08 | 38.92 |
| Ciclo 1 retirado | 16.59 | 725.59 | 931.31 | 85.68 | 690.14 | 77.00 |
| Ciclo 2 visible | 38.78 | 715.53 | 1145.14 | 572.72 | 826.62 | 31.27 |
| Ciclo 2 oculto | 35.02 | 723.56 | 1140.25 | 584.57 | 838.88 | 34.36 |
| Ciclo 2 retirado | 16.79 | 704.81 | 1047.42 | 85.90 | 802.16 | 56.54 |
| Ciclo 3 visible | 39.40 | 676.84 | 1146.55 | 572.78 | 826.44 | 78.56 |
| Ciclo 3 oculto | 33.98 | 692.03 | 1142.10 | 584.65 | 842.89 | 34.56 |
| Ciclo 3 retirado | 15.00 | 673.00 | 1049.03 | 85.98 | 806.14 | 48.51 |

El p95 usa nearest-rank. Con cinco o trece muestras por fase coincide con el
máximo de esa fase; la resolución estadística es limitada. El muestreo de
5 s no acota picos más breves. El mayor footprint **muestreado** fue
**1147.70 MiB**, inferior al umbral de revisión configurado de 1536 MiB.
Ese umbral no define por sí solo aceptación del producto ni diagnóstico de
fugas.

Los 74 snapshots nativos tienen estado `PASS`. B2 serializa `cpu.available`
como el entero `1`, en lugar de un booleano JSON. Es un defecto de esquema,
corregido después para B3; se conserva la evidencia original. El recálculo
independiente de los 64 deltas CPU internos a fases, usando los acumulados
getrusage y los timestamps nativos, coincide con los valores registrados
(diferencia inferior a 10⁻¹² puntos porcentuales). Este defecto de
tipo no invalida esos cálculos numéricos, pero B2 no satisface ese detalle del
contrato JSON tipado.

## Retención después de retirar las fuentes

Esta tabla usa **la última muestra** del baseline y de cada settling de 60 s;
son endpoints y no las medianas anteriores.

| Endpoint | RSS MiB | Compressed MiB | Footprint MiB | Malloc in-use MiB | Malloc allocated MiB |
|---|---:|---:|---:|---:|---:|
| Baseline | 178.36 | 52.50 | 374.91 | 84.36 | 174.14 |
| Retirada 1 | 629.22 | 152.30 | 933.52 | 85.68 | 690.14 |
| Retirada 2 | 203.56 | 688.88 | 1047.42 | 85.90 | 802.14 |
| Retirada 3 | 199.17 | 693.83 | 1049.06 | 85.98 | 806.14 |

Tras el tercer ciclo, malloc in-use supera el baseline final en **1.62 MiB**;
allocated en **632.00 MiB** y footprint en **674.16 MiB**. La retirada reduce
in-use, respecto al último snapshot oculto, en **501.69, 498.67 y 498.67 MiB**
por ciclo. Del segundo al tercer endpoint, footprint aumenta **1.64 MiB** e
in-use **0.077 MiB**. Tres ciclos no bastan para establecer una meseta ni
excluir crecimiento posterior.

La tercera fase de settling ilustra el límite de RSS: entre su primera y
última muestra RSS baja de **679.27 a 199.17 MiB**, compressed sube de
**214.75 a 693.83 MiB**, y footprint permanece en aproximadamente
**1049.03–1049.06 MiB**. Por ello, la caída de RSS no acredita liberación
equivalente de memoria contabilizada al proceso.

La evidencia distingue retorno de gran parte de las asignaciones vivas
visibles para malloc y retención de reserva/contabilidad VM. No identifica al
propietario de toda la retención: malloc no cubre allocators independientes,
mmap ni GPU/IOSurface; los campos VM se superponen. No se midieron stacks de
asignación, ownership de cachés, utilización GPU ni presión global de memoria.
No hubo purge ni presión artificial para alterar los resultados.

## Videos ocultos y coste de observación

Las doce operaciones que ocultan las capas propias devuelven
`layouts.horizontal.visible=false` en esas capas. Las sesenta observaciones de hijos
durante fases ocultas (3 fases × 5 muestras × 4 fuentes) conservan
`media_state=playing`, un hijo por fuente y `audio_mixers=0`; sus relojes
avanzan con el wrap esperado del loop de 6 s. El campo de overlay
`phase=visible` es su estado de apariencia intrínseco, distinto de la
visibilidad de la capa en la escena.

La CPU mediana oculta conserva **86.2–90.3%** de la CPU visible. Es coherente
con el comportamiento configurado: [sources.inc](../native/overlays/sources.inc)
establece `close_when_inactive=false` y `restart_on_activate=false`
(líneas 225–231). El código oficial vendorizado de OBS 33.0.1,
`plugins/obs-ffmpeg/obs-ffmpeg-source.c:662–674`, llama a
`media_playback_stop` al desactivar solo dentro de la condición
`restart_on_activate`. B2 no implementa pausa automática al ocultar. El dato
no constituye por sí solo una regresión de lifecycle ni evidencia de fuga.

| Observación, 74 consultas | Mediana | p95 | Máximo | Presupuesto |
|---|---:|---:|---:|---|
| Colección nativa | 0.474 ms | 0.884 ms | 1.346 ms | p95 ≤2 ms: cumple |
| RPC de memoria | 28.95 ms | 56.54 ms | 78.56 ms | p95 ≤20 ms: excede |
| RPC de status | 37.04 ms | 38.75 ms | 81.11 ms | Medido por separado |

**54/74 RPC de memoria (73.0%)** superan 20 ms; los p95 de las diez fases
exceden ese presupuesto. La colección nativa mide task_info, estadísticas
malloc y getrusage; excluye construcción de JSON y transporte. La latencia
restante no permite atribuir por separado cola, IPC, serialización o espera
del cliente. Estos tiempos de pared tampoco equivalen a CPU consumida ni
cuantifican el efecto causal del instrumento sobre el render. Se necesita
descomposición de esa ruta antes de declarar resuelto el presupuesto RPC.

## Continuidad, cleanup y trabajo pendiente

Entre la primera y última muestra los contadores aumentan en **9708 renders**,
**9018 copias de preview** y **42 preview busy drops**; no aumentan
`lagged_frames` ni `video_skipped_frames`. Los contadores no prueban frescura
de píxeles y las diferencias entre renders y copias no se clasifican como
pérdida de salida. Ninguna salida obtuvo attempt: los slots permanecieron
sin encoders activos. Por tanto, cero skips no certifica codificación,
entrega RTMP ni sincronización A/V.

Se retiraron las doce capas y doce fuentes propias, la escena y el asset de
prueba. El estado final tiene `overlays_runtime.sources=[]` y no animaciones
activas. Se restauraron la escena, fuentes/capas originales, canvas
960×540@30, variantes y perfiles elegidos; el store del mixer permanece
igual. No se ejecutó `save_project`. El estado no vuelve a ser byte a byte
idéntico: la versión del proyecto avanza de 3 a 5, aparece la configuración de
video `legacy540` explícita, `graph.next_id` pasa de 2 a 28 y la revisión de producción de 2 a
99. Esos contadores/migraciones no retroceden, como documenta el protocolo.

El dueño de la prueba observó cierre normal mediante Cmd+Q. El recibo de
cierre, revisión 100, conserva ambos slots idle y `native_busy=false`; el log
termina con destrucción de fuentes y `Freeing OBS context data`. No se deduce
del cierre una garantía general de liberación de todas las reservas previas.

Pendiente para cerrar esta fase de H14:

1. Ejecutar el lifecycle a 60 FPS y dual-soak de 1800 s con ambos outputs,
   conservando trazas de paquetes iniciales/finales y medios decodificables.
2. Comparar oculto reproduciendo frente a pausa explícita dentro de una misma
   corrida mediante el nuevo `--pause-hidden`. B2 a 30 FPS frente a B3 a 60 FPS
   no sería un A/B causal: cambian binario y frecuencia del canvas. Se conserva
   la fixture 30 FPS, por lo que no se afirma carga de decodificadores a 60 FPS.
3. Investigar la latencia RPC que excede 20 ms y la retención VM/allocator con
   evidencia de ownership si se requiere atribuir su causa. No hay veredicto
   de fuga ni de ausencia de fuga en esta toma.
4. Verificar frescura decodificada, PTS/DTS y sincronización A/V en la corrida
   con salidas. Aquí permanecen `NOT_EVALUATED`, al igual que utilización GPU.

La [metodología](h14-memory-methodology.md) define cobertura, presupuestos y
límites del instrumento. Las mejoras posteriores del runner no se atribuyen
retroactivamente a esta evidencia B2.
