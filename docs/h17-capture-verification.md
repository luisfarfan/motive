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

El siguiente contraste requiere una única repetición con metadata escalar
de la ventana exacta y su configuración al iniciar, sin títulos ni otras
aplicaciones. No se justifican sleeps, reconexiones infinitas, cambios de
formato o alteraciones de stop/lifetime con esta evidencia.
