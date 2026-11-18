# H14 · B3: matriz final de salidas

Los **15 casos seriales** conservan **10 PARTIAL y 5 FAIL**; ninguno alcanza
PASS agregado. Se generaron 22 medios: todos decodifican sin errores, pero siete
fallan la cadencia estricta y dos colas contienen AAC ausente anterior al bracket
de stop. Desactivar reordering mantiene el máximo intervalo de video en 34 ms
en esta matriz; no demuestra entrega completa ni un arreglo de flush.

La revisión es exclusivamente sobre los índices, manifests e informes JSON
terminados. No vuelve a ejecutar FFmpeg, no modifica medios ni cambia gates.
El [índice de 14 casos](../var/evidence/h14-output-matrix-b3-01/index.json), el
[shutdown independiente](../var/evidence/h14-output-matrix-b3-01/shutdown-index.json)
y la [auditoría reproducible](../var/evidence/h14-output-matrix-b3-audit-01/audit.json)
conservan las rutas exactas y hashes de cada informe primario y medio.

## Configuración y resultados

Bundle B3 externo al checkout, ejecutable SHA-256
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
1080p30, H.264 a 4000 kbps, keyframe de un segundo, AAC y patrón/tono controlados.
El encoder solicitado fue seleccionado sin fallback. Cada caso pidió ocho
segundos de observación activa, además de preparación y finalización.

Los casos 1–14 usaron PID 88708. El caso 15 usó owner fresco PID **98965**, que
cerró normalmente. No se mezclan los attempts de ambos procesos. “Funcional”
es el gate original de decode/cadencia/AAC/clipping/cleanup; “agregado” también
conserva contabilidad de cola y medios deliberadamente parciales.

| # | Encoder | Reorder | Salida / finalización | Gap máximo video MKV / RTMP | Funcional | Agregado |
|---:|---|---|---|---|---|---|
| 1 | VT | off | MKV / stop | 34 / — ms | PASS | PARTIAL |
| 2 | VT | off | RTMP / stop | — / 34 ms | PASS | PARTIAL |
| 3 | VT | off | Dual / stop | 34 / 34 ms | PASS | PARTIAL |
| 4 | VT | on | MKV / stop | 66 / — ms | FAIL | FAIL |
| 5 | VT | on | RTMP / stop | — / 133 ms | FAIL | FAIL |
| 6 | VT | on | Dual / stop | 134 / 133 ms | FAIL | FAIL |
| 7 | x264 | off | MKV / stop | 34 / — ms | PASS | PARTIAL |
| 8 | x264 | off | RTMP / stop | — / 34 ms | PASS | PARTIAL |
| 9 | x264 | off | Dual / stop | 34 / 34 ms | PASS | PARTIAL |
| 10 | x264 | on | MKV / stop | 67 / — ms | FAIL | FAIL |
| 11 | x264 | on | RTMP / stop | — / 34 ms | PASS | PARTIAL |
| 12 | x264 | on | Dual / stop | 67 / 67 ms | FAIL | FAIL |
| 13 | VT | off | Dual / cancel | 34 / 34 ms | PASS | PARTIAL |
| 14 | VT | off | Dual / receiver-loss | 34 / 34 ms | PASS | PARTIAL |
| 15 | VT | off | Dual / shutdown | 34 / 34 ms | PASS | PARTIAL |

Los 22 decodes terminan con código 0 y stderr vacío. AAC conserva máximo
intervalo de 22 ms y cero muestras saturadas en el PCM medido del canal 0. Los siete FAIL
funcionales por medio corresponden al gate original de cadencia de video
superior a 50 ms; no se recortaron los últimos frames para pasarlo. El gate de
DTS conserva su excepción previa y explícita para el prefijo inicial de MKV
con reordering; no se amplió esa regla.

## Contabilidad de cola

El clasificador original se conserva, con origen tomado de la primera
correspondencia nativo/contenedor y tolerancia de **1.1 ms** por cuantización.
No hay hash de payload nativo ni una demostración criptográfica de identidad.
La traza de 256 entradas describe la cola retenida, no toda la sesión ni la
etapa encoder→observador.

- **19 medios:** `STOP_BOUNDARY_PACKETS_NOT_DELIVERED`. Se enumeran paquetes
  ausentes posteriores/al bracket de stop; no se declaran entregados.
- **2 medios:** `FAIL`, por un AAC anterior al bracket de stop en cada uno.
- **1 medio:** `INCONCLUSIVE`, el receptor terminado deliberadamente, sin
  bracket de parada normal para su cola.

En total se conservan 13 videos y 12 AAC ausentes posteriores/al bracket,
dos AAC pre-stop y tres paquetes sin bracket normal (dos videos y un AAC).
No se clasifica ningún ausente dentro del bracket.

Las pérdidas pre-stop concretas son:

| Caso / medio | Secuencia AAC | `sys_dts_usec` | Inicio de bracket stop, ns | Relación |
|---|---:|---:|---:|---|
| 6 · VT reorder dual / MKV | 685 | 76890376112 | 76890415298666 | ≈39.187 ms antes |
| 12 · x264 reorder dual / RTMP | 864 | 76975355718 | 76975404466000 | ≈48.748 ms antes |

En ambos, el video anterior por secuencia ya cruza el cutoff. La secuencia es
compatible con la semántica oficial de parada descrita en
[contabilidad H14](h14-output-accounting.md): el plugin puede terminar al primer
paquete con DTS de sistema posterior y rechazar el AAC siguiente aun cuando
su DTS sea anterior. Esta compatibilidad no elimina el FAIL ni demuestra el
vaciado de todo el backlog.

Los contadores permanecen separados. Ejemplos `encoder / output OBS / decoded`:
caso 1 MKV **254/252/251**; caso 6 MKV **269/268/267**; caso 11 RTMP
**289/288/287**; caso 15 MKV **259/258/258** y RTMP **252/251/251**.
En shutdown ambos videos retenidos están presentes, pero falta un AAC posterior
al stop en cada destino. La igualdad de dos contadores no convierte la salida
en íntegra. No se restó ninguna unidad para producir igualdad.

## Desconexión, cancelación y barreras

Cancelación dual termina funcionalmente correcta y conserva una ausencia de
frontera en cada destino. La pérdida deliberada del receptor produce
`OUTPUT_DISCONNECTED`, código nativo −5, recuperación explícita; el archivo
recibido se marca `expected_partial=true`. Su cola sin bracket normal permanece
INCONCLUSIVE. La grabación simultánea continúa con cadencia correcta. El exit
255 del receptor terminado por el ensayo es retenido, no normalizado a cero.

Los 15 casos conservan `cleanup_errors=[]`, stores sin cambios y hash B3 intacto.
Los manifests comprueban ausencia de procesos del grupo y liberan sus leases:
14 muestran `QUIESCENT_OBSERVED`; shutdown muestra `OWNER_ABSENT_OBSERVED`, con
el diagnóstico terminal del PID 98965 y los attempts correctos. No se forzó
la salida del owner ni se modificó la barrera H8.

El intervalo nativo stop→quiescencia observado fue **105–252 ms en VT** y
**1329–1437 ms en x264**. Incluye polling; no es una medida directa de flush
del encoder. Los wrappers presentan `PROCESS_FAILED` porque los hijos devolvieron
FAIL o PARTIAL; el índice `PROCESS_COMPLETED` indica que terminó el recorrido,
no aceptación beta. Las barreras y liberación de lease se evalúan por separado.

## Comparación con la matriz histórica

Se conservan los resultados anteriores de
[docs/h14-output-accounting.md](h14-output-accounting.md):

- La matriz histórica describía seis FAIL normales con reordering. B3 presenta
  **cinco FAIL y un PARTIAL** entre esos seis: x264/RTMP aislado mantiene cadencia
  de 34 ms, pero pierde un paquete final trazado; no es un nuevo PASS agregado.
- VT con reordering llega ahora a **133–134 ms** en streaming/dual, frente a los
  66–67 ms documentados antes. x264 llega a 67 ms en esta matriz, frente a hasta
  133 ms antes. Son resultados de intentos distintos y fronteras de parada
  distintas; no se atribuyen por sí solos a una mejora o regresión causal.
- Sin reordering, ambas matrices mantienen máximo gap de 34 ms y diferencias
  terminales explícitas. El default `frame_reordering=false` sigue siendo una
  mitigación conservadora, no un arreglo demostrado. Los perfiles guardados que
  activan reordering conservan su valor y la advertencia tipada existente.

La aceptación general de beta y la entrega completa permanecen abiertas.
La auditoría de los 15 casos tiene SHA-256
`b9cd5bcfe1e03128412c274b6607e0e3866d57cc1f8cc72b6d399462026f758f`;
su [script JSON-only](../var/evidence/h14-output-matrix-b3-audit-01/audit.py)
revalida los hashes exactos del coordinador y los informes primarios.
