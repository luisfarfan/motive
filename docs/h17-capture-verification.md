# H17 — captura real B7 y límites de recuperación

B7 conserva **FAIL** de frescura visual y recuperación. La segunda prueba
corrobora las tres fases de foco y vuelve a medir congelamiento. La primera
conserva foco **BLOCKED** por un marcador faltante; no se modifica ese resultado.

Binario portable:
`/Users/luisfarfan/Developer/motive-h17-portable/b7/Motive.app`, SHA-256
`d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31`.
Los dos ensayos fueron recogidos por el propietario del lock físico canónico;
esta revisión posterior solo lee sus registros y decodifica archivos cerrados
con ffmpeg/ffprobe embebidos. No hay capturas ni cambios de foco desde el
analizador. Los informes H14/H15 permanecen intactos.

## Ventana externa controlada: 45 segundos

`var/evidence/h17-focus-b7-default/` conserva owner PID 37612, fixture PID
37620 y Window ID 15289. La fixture usa `collectionBehavior=0`, sin ajustes
de aplicaciones ajenas. El wrapper termina BLOCKED: conserva dos marcadores
válidos, pero la escritura del tercero falla. Se registraron 28 observaciones
independientes de fixture al frente, 25 de Motive al frente y una del retorno,
todas corroboradas individualmente. Una observación del retorno no acredita
la fase completa; no se reconstruye un marcador retrospectivo.

El análisis con `verify_h14_collection.py analyze --verify-vt-framing` está
en `var/evidence/h17-focus-b7-default-analysis/`. Se enumeran todos los frames
y se decodifica el contador visual cada seis frames, 5 Hz a 30 FPS. Los
archivos no se recortaron y sus hashes están en `analysis.json`/`review.json`.

| Medida | MKV | RTMP recibido |
|---|---:|---:|
| Frames de video decodificados | 1348 | 1338 |
| Muestras válidas del contador | 225/225 | 223/223 |
| PTS crecientes / gap máximo | PASS / 34 ms | PASS / 34 ms |
| Mayor intervalo de contador repetido | 15,4 s | 15,4 s |
| Salto al reanudarse | 150 ticks | 150 ticks |
| Frescura visual | FAIL | FAIL |
| Entrega completa de cola | PARTIAL | PARTIAL |

La conversión inicial VT Annex B→AVCC queda validada por bytes/metadata; no
se forzó el origen usando el contador. La falta del tercer marcador impide
completar alineación por fases. El FAIL de contador ya se obtiene del archivo
completo y permanece aunque esa alineación no concluya. Esta toma no incluye
una aceptación PCM/AAC/A/V completa.

### Repetición con las tres fases corroboradas

`h17-focus-b7-default-02/` usa el mismo B7, con corrección del instrumento que
empareja el probe independiente con un evento contemporáneo de la fixture.
Las tres fases pasan cobertura: 23/20/16 observaciones independientes y gap
máximo de 0,568 s, según el wrapper. El analizador contrasta además los
metadatos propios de la fixture: 13/11/10 timestamps distintos dentro de las
guardas de fase, sin discrepancias. Son dos observadores con cadencias
distintas; sus conteos no se mezclan.

`h17-focus-b7-default-02-analysis/analysis.json` conserva foco **PASS** y
frescura **FAIL**. MKV decodifica 1340 frames y repite contador 15,4 s; RTMP
decodifica 1331 y repite 15,6 s. Las 224/222 muestras de contador son válidas.
En cada medio, `fixture_front` y `fixture_return` pasan. La región interior
`studio_front` contiene 53 muestras durante 10,4 s con **cero ticks de avance**.
Los archivos completos conservan PTS crecientes, gap máximo 34 ms y colas
PARTIAL. El propietario y la fixture se limpiaron sin errores, owner exit 0.

Esta repetición cierra el bloqueo del protocolo de foco de la segunda toma;
no corrige el congelamiento del producto ni borra el bloqueo de la primera.
No se necesita otra repetición idéntica para confirmar el mismo fallo.

## Planos observados durante la suspensión

Hay 29 muestras con `sample_status=suspended`, desde el bracket host
`[122260.655739458, 122260.670410250]` hasta
`[122275.739047333, 122275.763918875]` segundos. Dentro de esas observaciones:

1. La fixture mantiene el mismo PID/ventana y avanza de 510 a 960 dibujos,
   y de tick 171 a 321. Esto prueba ejecución del productor; no publicación
   de nuevas superficies por WindowServer.
2. Los bounds de WindowServer cambian mientras el frame/content de AppKit
   conserva 680×272/680×240. Se retiene esa diferencia sin atribuirla a una
   preferencia o mecanismo concreto del sistema.
3. SCK conserva callbacks 468, superficies 467 y último surface timestamp
   `122260416783416 ns`. No entrega superficies nuevas en ese intervalo.
4. OBS conserva 441 consumos de superficie, pero los renders con textura
   avanzan de 452 a 905. El render continúa usando la textura disponible;
   esos renders no son prueba de píxeles nuevos.
5. MKV y RTMP contienen PTS continuos, pero el contador decodificado repite
   15,4 s. Ambos medios representan el congelamiento, no solo el preview.
6. Posteriormente SCK vuelve a `complete`; el contador salta 150 ticks.
   No se reinicia automáticamente la fuente ni una salida.

El núcleo expone `CAPTURE_SUSPENDED` mientras ocurre. Cero render lag,
video skips y output drops en los registros no contradice el FAIL de píxeles.
La evidencia sitúa la ausencia de superficies antes del consumo OBS, pero
no distingue la causa interna de WindowServer/SCK ni demuestra causalidad
de Stage Manager. La limpieza conserva `shutdown_ok=true`, owner exit 0,
fixture terminada por su supervisor y `cleanup_errors=[]`.

## Cierre y sustitución de ventana propia

`var/evidence/h17-capture-b7/` conserva owner PID 39474, Window ID inicial
15323 y sustituta 15333. La ventana inicial produce aproximadamente 16 s
de MKV/RTMP antes de cerrarse deliberadamente. La pérdida se identifica como
`SOURCE_UNAVAILABLE`; ambos destinos alcanzan quiescencia 258 ms después
de solicitar su stop. Ese tiempo incluye polling y no certifica flush.

`var/evidence/h17-capture-b7-analysis/` conserva decode completo de ambos
tracks, PTS/DTS, PCM estéreo original y hashes:

| Medida inicial, antes de recuperar | MKV | RTMP recibido |
|---|---:|---:|
| Frames decodificados | 481 | 478 |
| Último PTS video | 16,000 s | 15,921 s |
| Gap máximo video / AAC | 34 / 22 ms | 34 / 22 ms |
| Frames B | 0 | 0 |
| Muestras PCM con clipping | 0 / 0 canales | 0 / 0 canales |
| Output OBS − decoded | 0 | 0 |
| Encoder − decoded | 5 | 5 |
| Integridad estructural | PASS | PASS |

Los contadores no se igualan por ajuste: los cinco frames encoder→decoded
permanecen explícitos. No existe aquí una traza temporal completa que explique
cada diferencia. La entrega de todos los paquetes sigue PARTIAL. El patrón
GPUI de esta fixture no es el contador externo del ensayo anterior; esta
decodificación estructural no acredita por sí sola frescura visual.

Al seleccionar la sustituta, SCK devuelve `SCStreamErrorInvalidParameter`
(-3812) en la finalización de `startCapture`. Motive devuelve
`SOURCE_CREATE_FAILED`, destruye esa instancia inválida y conserva la fuente
anterior como no disponible. No se genera el segundo par de medios. La
recuperación sigue **FAIL**, y los píxeles posteriores a recuperación están
**NOT_EVALUATED**. El cierre posterior del owner termina 0 y sin errores de
cleanup; los logs muestran destrucción de la instancia retirada y fallida.

## Causa todavía acotada, sin parche especulativo

La sustituta sí superó la selección exacta de Window ID/PID y los dos
`addStreamOutput`: el error proviene de `startCapture`, no del rechazo nuevo
de ventana ausente. `obs_obj_invalid` ya estaba en B6; este rechazo correcto
no demuestra que el parche H17 haya resuelto la recuperación.

La selección empezó a `122466.810438750`, aproximadamente 115 ms después de
la respuesta de abrir la ventana; esa respuesta encola trabajo GPUI y no
certifica su publicación SCK completa. La fuente inicial capturada medía
680×452, pero no se conservaron las dimensiones `SCWindow`/configuración de
la sustituta al fallar. No puede atribuirse el error a dimensiones cero,
filtro inválido, formato o una carrera de publicación sin ese dato.

La sesión retirada ya había emitido `SCStreamErrorNoCaptureSource` (-3815).
El flag `capture_failed` del módulo hace que su destructor no solicite un
segundo stop. El log de destrucción y la cola OBS no son una confirmación
independiente de todos los callbacks asíncronos de SCK. Tampoco hay evidencia
de que un solapamiento de sesiones causara -3812.

El siguiente contraste requería una única repetición con metadata escalar
de la ventana exacta y su configuración al iniciar, sin títulos ni otras
aplicaciones. No se justifican sleeps, reconexiones infinitas, cambios de
formato o alteraciones de stop/lifetime con esta evidencia.

## B9: geometría inválida demostrada al sustituir

La repetición acotada está en `var/evidence/h17-capture-b9/` y su log nativo
en `h17-capture-b9-owner/owner.log`. B9 tiene SHA-256
`7ecf6b28288fed4cc7121d755b435310a59d80ced8268475e8c884e8d0576e24`.
El propietario fue PID 79255. Las dos consultas coinciden con ese PID exacto;
el ID cambia de 15831 a 15836 tras cerrar y recrear la fixture propia.

| Dato observado inmediatamente antes de startCapture | Inicial | Sustituta |
|---|---:|---:|
| SCWindow.frame, puntos | 680×452 | 0×0 |
| SCContentFilter.contentRect, puntos | 680×452 | 0×0 |
| pointPixelScale | 1 | 1 |
| SCStreamConfiguration, dimensiones | 680×452 | 0×0 |
| Intervalo configurado | 30000000/1000000000 s | Igual |
| Resultado start | Admitida | InvalidParameter −3812 |

Esto demuestra que OBS intentó iniciar una configuración con dimensiones
cero en la sustituta. La identidad correcta y un objeto enumerable no
acreditan geometría capturable. No prueba por qué macOS publicó ese rectángulo,
ni atribuye el estado a Stage Manager o a solapamiento de sesiones.

El primer par de medios se conserva y las salidas alcanzan quiescencia en
260 ms tras la pérdida deliberada. No existe un medio posterior a recuperación.
El rechazo `SOURCE_CREATE_FAILED`, el **FAIL** de recuperación y el cierre
normal (exit 0, `cleanup_errors=[]`) permanecen en sus informes originales.
La corrección siguiente debe rechazar esa geometría antes de crear/iniciar
SCStream, explicar que la ventana todavía no está lista y conservar la
reselección explícita. No debe inventar dimensiones ni reintentar sin límite.

## B10: rechazo temprano y reselección explícita

B10 tiene ejecutable SHA-256
`1390fa6834c22c7df002b72d3f3e3c9c7d2bb993149663ac07334b4282f279c9`
y módulo mac-capture
`fae4bb68823d1963b7644da74ae77dcf2b56dd8d29b56948c37803b23047a197`.
El caso `var/evidence/h17-capture-b10/` usa owner PID 29891 y únicamente la
fixture de ventana del propio proceso. Es una prueba por CLI/MCP, no un gesto
GPUI ni una prueba de foco externo.

Tras grabar y transmitir la ventana 15955, cerrarla produjo la parada segura
de ambos destinos. Se abrió la sustituta 15962. La primera selección exacta
ID/PID encontró frame 0×0 y respondió **CAPTURE_NOT_READY** con la explicación
«macOS no ha publicado dimensiones válidas…». El log conserva
`motive_capture_geometry_not_ready`; esa instancia no llegó a `startCapture`
ni generó el error −3812.

El flag explícito de prueba `--retry-not-ready-once` autorizó una sola segunda
selección, tras corroborar nuevamente la misma ID/PID propia. No hay sleeps,
selección por nombre ni reintentos automáticos del producto. La segunda
consulta obtuvo frame/filtro/configuración 680×452 y la fuente quedó lista.
Entre las respuestas de las dos selecciones hay aproximadamente 266 ms; no
es una latencia garantizada ni un tiempo de espera configurado.

Se produjo un segundo par MKV/RTMP durante 15 segundos y se detuvo primero
RTMP y después REC. Los snapshots de esa fase no registran issues. La
quiescencia observada fue 276 ms para RTMP y 268 ms para REC, con las reservas
de polling y entrega ya descritas. Ambos destinos terminaron idle; owner
exit 0, `cleanup_errors=[]`.

Admisión negativa y reselección real: **PASS** en este caso controlado.
El informe primario conserva **PARTIAL**, con píxeles y entrega sujetos al
análisis de los cuatro medios. No se reescriben B7/B9 ni se transfiere este
resultado al caso de foco externo: CAP-01 sigue **FAIL**.

### Decodificación y píxeles B10

`var/evidence/h17-capture-b10-analysis/` conserva los comandos, hashes,
trazas por frame, contactos visuales y brackets de snapshots. Los cuatro
medios pasan los 16 checks estructurales: H.264 1080p30, AAC estéreo 48 kHz,
decode completo, PTS/DTS válidos, gaps de 34/22 ms y cero clipping digital.

| Medio | Video observado → decoded | AAC observado → contenedor | Cambios del patrón | Mayor estado constante interior |
|---|---:|---:|---:|---:|
| Inicial MKV | 479→478 | 748→748 | 145 | 200 ms |
| Inicial RTMP | 475→474 | 742→742 | 145 | 200 ms |
| Recuperado MKV | 477→477 | 747→746 | 144 | 200 ms |
| Recuperado RTMP | 463→463 | 725→724 | 141 | 200 ms |

Se clasificaron cinco regiones de color controladas en **cada frame**;
ninguno fue inválido. Las muestras de texto confirman ticks crecientes tras
recuperar, de 3 a 132/133 hasta aproximadamente 14 s. La fixture GPUI usa un
timer nominal de 100 ms: esto prueba progreso visible en esta toma, no que
la fuente produzca 30 contenidos nuevos por segundo. Los medios recuperados
conservan un salto de estado 3→0 al inicio; no se acredita entrega de cada
actualización. El mayor estado constante total es 267 ms en MKV recuperado;
los iniciales conservan 366,3 ms al final del cierre deliberado. No se
descartaron frames ni se amplió un umbral.

Las 28 observaciones de la fuente recuperada muestran age 3–31 ms,
superficies 15→444, consumos 14→437 y renders 15→457. El contador de callbacks
suspended subió 0→2 entre ready y ambos outputs activos, y después permaneció
en 2 durante toda la fase recuperada. Los snapshots no son atómicos y no se
alinean esos callbacks con un frame concreto del medio.

El progreso controlado después de recuperar tiene **PASS** acotado; la
entrega exacta de actualizaciones y paquetes sigue **PARTIAL**. El analizador
histórico marca los dos medios iniciales `INCONCLUSIVE` por cierre intencional,
aunque sus 16 checks son PASS. Un agregado provisional confundió esa categoría
con FAIL estructural; se preservó en `report.initial-aggregation.json` y se
corrigió el derivado, sin cambiar medios ni resultados crudos.

### Cobertura que permanece separada

| Caso | Estado y alcance |
|---|---|
| Alta normal, cierre con dual activo y cierre del owner | PASS B10, ventana propia y parada segura |
| Geometría inválida y diagnóstico específico | PASS B10, rechazo antes de iniciar SCStream |
| Nueva ID, reselección explícita y segundo dual con píxeles | PASS B10 para la secuencia concreta; gate general de recuperación PARTIAL |
| PID incorrecto / identidad no encontrada | PASS de contrato offline; prueba física adversarial NOT_EVALUATED |
| Suspensión por cambio real de foco y frescura general | FAIL B7 conservado; B10 no repite el mismo experimento sin hipótesis nueva |
| Terminación de productor externo con output, resize, minimización y otros Spaces | NOT_EVALUATED en B10; los ensayos anteriores no certifican esas combinaciones |
| Sleep/wake | NOT_EVALUATED; procedimiento supervisado en la matriz principal |

El cambio no convierte todas las ventanas de terceros en fuentes fiables.
