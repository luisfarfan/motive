# H13 — producción GPUI real y aceptación nativa

Estado: **PRODUCCIÓN EJECUTADA; ACEPTACIÓN PARCIAL**. El bundle integrado produjo
una sesión de más de 30 minutos con MKV y RTMP concurrentes controlados desde
GPUI. Las pruebas reales conservaron problemas visuales y límites de
contabilidad terminal; no se declara H13 completo. La última repetición de
exclusión del audio propio pasó tras un control de piso, con los criterios
originales: −123,17 dB, próximo al piso numérico. Su
[informe separado](h13-system-audio-exclusion-final.md) conserva también el
primer fallo G y su atribución no resuelta.

El [procedimiento reproducible](h13-native-checklist.md) es una plantilla.
Este documento distingue sus pasos ejecutados, los cambios del ensayo y los
casos todavía pendientes. No se operó la producción por terminal para sustituir
los controles GPUI.

## Identidad y evidencia

- Worktree: `/Users/luisfarfan/Developer/products/motive-h13`, rama
  `codex/h13-live-production`, creado desde H12 `b52d135`; main permanece
  separado. Durante este trabajo main recibió cambios de Show Control de otro
  trabajo; no forman parte del bundle G ni de esta verificación.
- Bundle G, SHA-256 del ejecutable firmado:
  `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93`.
  No se reconstruyó durante las pruebas. El bundle de desarrollo conserva su
  limitación de Frameworks con enlaces absolutos; no es una release portable.
- PID principal **92305**; UI **1440×980**, tema oscuro. Lock físico canónico
  de Motive bajo el owner H13 root. Capturas y dispositivos se probaron en serie.
- Todas las mutaciones de esta toma proceden de **UI**. El
  [observador CLI/MCP](../var/evidence/h13-native-1794941679130733000/report.json)
  conserva 5402 muestras a aproximadamente 2 Hz, revisiones, `last_action`, PID
  común, consultas CLI y barreras. Terminó con `collector_ok=true` y
  `observed_shutdown=true`.
- [Contexto y mapa de medios](../var/evidence/h13-native-1794941679130733000/session-context.json),
  [manifiesto de ocho archivos](../var/evidence/h13-native-1794941679130733000/media-manifest.json)
  y [métricas del intervalo dual](../var/evidence/h13-native-1794941679130733000/metrics-summary.json).
  Los medios/evidencias locales no se incorporan al repositorio ni se publican.
- Medios principales: [grabación MKV](../var/recordings/motive-1794942241896718.mkv)
  y [RTMP recibido](../var/evidence/h13-native-helpers-1794941103475457000/native-rtmp-2.flv).

La cámara integrada fue reconfirmada por el usuario apuntando a contenido
controlado antes de grabar. Las imágenes muestran techo/pared/lámpara. Su UID
fue `6C707041-05AC-0011-0008-000000000001`; el micrófono seleccionado fue
`BuiltInMicrophoneDevice`. La ventana perteneció a la fixture propia
`local.motive.audiofixture`, título `Motive controlled audio fixture`, PID 98743.
No se capturó el escritorio visual ni contenido de otras ventanas.

## Producción y operaciones observadas

Canvas **1920×1080/30**, con coordenadas `design960`. Escena A `scene-1` utiliza
ventana completa y webcam en PiP; B `scene-10` utiliza webcam completa y ventana
en PiP. Ambas reutilizan `source-2` ventana y `source-4` cámara. El lower third
es `source-6`, countdown `source-8` y la alerta creada después, `source-15`.
Los perfiles por destino fueron VideoToolbox CBR 6000/4000 kb/s, keyframe 1 s,
reordering desactivado. Los receptores FFmpeg propios escucharon exclusivamente
en `127.0.0.1:51822`.

Audio global: micrófono `audio-1` y aplicación `audio-2`, ambos a −6 dB al
principio/final, monitoring off. La fixture genera 997 Hz a −24 dBFS peak; un
WAV propio de 440 Hz, reproducido mediante afplay con volumen de proceso 0,5,
estimuló el micrófono sin modificar volumen/routing global. También puede
captar acústicamente 997 Hz: esa energía no se atribuye automáticamente al canal
digital. El primer WAV terminó naturalmente a los 1800 s; la captura de micrófono
y el tono de aplicación continuaron. Un segundo playback cubrió la toma corta.

| Operación real desde GPUI | Resultado observado |
|---|---|
| Iniciar MKV y después RTMP | Dos slots activos, perfiles efectivos independientes, mismo PID y capturas. |
| Gain −6/−18/−6 dB; mute/unmute de cada entrada | Referencias aisladas con mic mute y otro intervalo con aplicación mute; conservados todos los cambios reales. |
| Cut A/B y Fade 1500 ms | Estados, frames intermedios y contenido en ambas salidas; también atajos Cmd+1/Cmd+2. |
| Cancelar Fade de 5000 ms | Op 6 cancelada a progreso 0,2342; regreso a escena segura, sin reiniciar salidas. |
| Cambiar lower third en vivo | `H13 A` → `H13 B · En vivo`, visible en ambos medios. |
| Countdown start/pause/resume/reset | Primer ciclo con pausa real y segundo ciclo durante la toma prolongada. |
| Desconectar/reconectar micrófono | Aplicación y outputs continúan; mic instance 1→3, app permanece instance 2. No simula hot-unplug físico. |
| Cancelar Cmd+Q y menú Quit | Mismo PID e intentos continúan. Cancelar confirmación de stop RTMP tampoco detiene salidas. |
| Stop RTMP1, start RTMP2, stop REC1 | Superviviente conserva su intento. RTMP continúa después de detener MKV. |
| Start REC2 y detener todas | Ambas barreras terminales; estudio sigue abierto. |
| Terminar receptor RTMP3 propio | `OUTPUT_DISCONNECTED`; REC3 continúa. Recovery dirigido y RTMP4 arrancan explícitamente. |
| Cancelar RTMP5 con peer silencioso | `cancel_deferred=true`, UI Finalizando; REC3 sigue. Al liberar peer termina la barrera y se recupera por UI. Intento sin medio. |
| Cmd+Q confirmado con REC3 y RTMP6 | Última acción `UI · request_shutdown`, revisión 179; ambos slots idle/native_busy=false antes de la salida observada del PID. |

La UI rechazó ocultar una capa durante las salidas con `OUTPUT_BUSY` y dejó su
visibilidad intacta. Crear una alerta estaba deshabilitado mientras había
salidas; se creó entre tomas. Esos controles bloqueados no se cuentan como
operaciones realizadas. Algunos controles AX pertenecían a contenido recortado
en scroll: los clicks sin efecto no se contabilizan; mute/unmute aplicado se
deduce del estado real, no del intento de click.

## Duración y recursos

RTMP1 estuvo activo **1815,762 s (30 min 15,762 s)**; REC1 **1884,483 s**. Hay
**1814,745 s** entre la primera y última muestra dual observada. Se introdujeron
eventos durante el tramo largo, sin análisis FFmpeg ni builds simultáneos.

| Medida durante ambos intentos 1 activos | Resultado |
|---|---:|
| CPU mediana / p95 | 70,71 / 81,86 % de un núcleo lógico |
| RSS mediana / máximo observado | 243,66 / 262,39 MiB |
| Render lag / encoding skips | 0 / 0 |
| Drops de salida MKV / RTMP | 0 / 0 |
| Clipping nativo del master | 0 bloques |
| Copias omitidas del preview | **221** adicionales (148→369) |

Las seis instancias visuales permanecen constantes durante el primer tramo
dual. La reconexión explícita del micrófono es una recreación prevista de esa
entrada, no una captura duplicada. Estos recursos corresponden a ventana,
webcam y widgets; no se comparan con cuatro videos locales para afirmar una
optimización de memoria. CPU/RSS son muestreados, no máximos continuos del sistema.

## Archivos y medición de audio

El [análisis estructural completo](../var/evidence/h13-native-analysis-1794944731171479000/report.json)
conserva hashes, comandos, decode completo, todos los PTS/DTS y bloques PCM de
ambos canales. Los ocho archivos son H.264 1920×1080/30 + AAC 48 kHz estéreo.
Todos pasan decode y cadencia estricta: gaps de video hasta 34 ms y AAC hasta
22 ms, incluidos los finales. Siete tienen resultado funcional PASS; RTMP3,
interrumpido intencionalmente, queda INCONCLUSIVE respecto de finalización.
El resultado global del instrumento es **INCONCLUSIVE por cobertura**, no una
aceptación automática. Ninguna muestra PCM alcanza saturación; el pico mayor
de los archivos completos es aproximadamente **−8,887 dBFS**.

| Medio / intento | Frames decodificados | Contador nativo de output |
|---|---:|---:|
| REC1 | 56530 | 56530 |
| RTMP1 | 54469 | 54469 |
| RTMP2 | 1513 | 1513 |
| REC2 | 335 | 335 |
| REC3 | 8176 | **8177** |
| RTMP3, fallo inducido | 1147 | **1149** |
| RTMP4 | 1228 | **1229** |
| RTMP6 | 1842 | 1842 |

Los contadores OBS de paquetes despachados no confirman por sí solos escritura
o recepción final. Se conservan las diferencias terminales: un frame en REC3
y RTMP4 y dos en RTMP3. Los logs/cutoffs de parada son compatibles con esa
semántica, pero sin traza por paquete no se atribuye exactamente cada diferencia.
**Contabilidad terminal exacta sigue pendiente**; cero drops y PTS interiores
continuos no significan preservación demostrada de cada último frame.

El [análisis PCM por eventos](../var/evidence/h13-native-pcm-1794944899076084000/report.json)
y su [resumen](../var/evidence/h13-native-pcm-1794944899076084000/summary.json)
registran 18 comparaciones de gain PASS, **−12,000512 a −11,994918 dB**, y error
RMS máximo **0,142828 dB**. Hay 79 fragmentos reales y 48684 ventanas de 20 ms,
con paso de 10 ms: cero saturación, pico máximo −17,91 dBFS en esos fragmentos.
Los 34 eventos calibrados entre REC1/RTMP1 pasan sus checks. Las referencias
usan mic mute/disconnected; no identifican ganancia digital desde el 997 Hz
mezclado que también recoge el micrófono.

El PCM alrededor de los fallos RTMP3/5 conserva la mezcla en las ventanas
extraídas, pero su asociación temporal usa un ancla posterior: **INCONCLUSIVE
por extrapolación**, sin inventar un bracket temprano. Los clips cortos sin
referencias tienen cobertura explícitamente limitada. Ningún check de estas
ventanas prueba continuidad PCM de cada muestra de los 30 minutos. Los PTS y
bloques de todo el archivo permanecen disponibles, y la sincronización A/V
se acredita por el ensayo dedicado G, no por los instantes de polling.

## Revisión visual y fallos conservados

La [revisión de medios](../var/evidence/h13-native-visual-extract-1794944740966518000/visual-review.md)
conserva 18 eventos, 36 ventanas de extracción y 73 frames periódicos. Sus
16 probes de Cut/Fade pasan; los dos del Fade cancelado se evalúan como
cancelación, sin hacerlos pasar por Fade completo. Lower y countdown son
legibles y sus cambios coinciden en ambos destinos. Las muestras periódicas
de la toma larga muestran el contador avanzando; no demuestran ausencia de
congelamientos entre muestras.

**Alerta parcialmente ocluida, intento principal:** `layer-16` y ventana
`layer-3` tenían `order=2`. El desempate por ID coloca la ventana encima. El
trigger y sus fases sí se observan, pero título/subtítulo no son completamente
legibles. Se corrigió mediante **Subir capa** en GPUI (order 3), sin cambiar el
motor. La nueva toma compacta conserva esa corrección; su revisión de medios
se incorpora por separado, sin borrar el fallo anterior.

**Continuidad visual de REC3 FAIL:** el contador queda en `136267776` en
muestras a 185/245 s; RTMP6 también conserva ese valor. La fixture sigue
avanzando audio y draw_count. Hay correlación temporal con
`occlusion_visible=false`, pero el muestreo no establece el inicio exacto del
congelamiento. Esto no identifica causalmente WindowServer, SCK o una retención posterior.
OBS reporta 680×272 sin issue, y la fuente no expone frame_age/cadencia medidos:
no puede interpretarse esa salud como garantía de frescura. No se realizó una
serie indefinida de repeticiones ni se cambiaron ajustes globales de ventanas.

## Persistencia y reapertura compacta

En PID 92305 se guardaron proyecto v5, mixer v2 y perfiles v1 por UI. Se alteró
X de la alerta 340→350, mute de aplicación y bitrate 6000→6100; los respectivos
controles Restaurar recuperaron exactamente los documentos originales y dejaron
los otros stores intactos. Hay [snapshots antes/después](../var/evidence/h13-native-1794941679130733000/persistence/after-restore.json)
y comparación de bytes. No arrancó ninguna salida implícitamente.

PID **36494**, mismo bundle G, reabrió con UI **1024×780**. Su
[arranque](../var/evidence/h13-native-compact-1794944782314737000/fresh-start.json)
no capturó dispositivos ni inició salidas. Proyecto, mixer y perfiles se
restauraron por GPUI; los widgets no reanudaron sus relojes/visibilidad efímeros.
La cámara recibió frames; la ventana inicialmente `CAPTURE_NOT_READY` recibió
su primer frame al activar la fixture mediante Finder. IDs persistidos iguales,
instance IDs propios del nuevo PID. Se eligieron perfiles y endpoint runtime
por UI, y se guardó la corrección de orden de alerta.

CUA mostró repetidamente una miniatura de Stage Manager y `windowNotFoundAtPosition`,
con operaciones lentas y un timeout. El usuario volvió a poner el estudio al
frente y se renovó la vinculación. No se cambiaron ajustes globales ni se
convirtieron clicks fallidos en éxitos. Ambas salidas se iniciaron después de
recuperar el control visible, con receptor propio en `127.0.0.1:19351`.

El [observador compacto](../var/evidence/h13-native-1794944801555031000/report.json)
terminó con collector_ok y observed_shutdown. El primer peer silencioso agotó
los 30 s antes de confirmar Quit; el diálogo quedó obsoleto y la grabación siguió.
Se conserva ese intento. Un segundo peer entregó solo el byte RTMP v3 y 15
bytes de S1 a intervalos, manteniendo el handshake incompleto de forma acotada.
Tras confirmar Cmd+Q, MKV finalizó, RTMP conservó native_busy/cancel_deferred y
Motive permaneció abierto. Al liberar el peer salió **0,835 s** después de la
solicitud de liberación, sin señales al proceso Motive. Véase
[estado pendiente](../var/evidence/h13-native-compact-1794944782314737000/shutdown-pending-state.json)
y [resultado de cierre](../var/evidence/h13-native-compact-1794944782314737000/shutdown-outcome.json).

El [análisis estructural compacto](../var/evidence/h13-native-analysis-1794946801711114000/report.json)
da PASS funcional y de cadencia para los dos medios: H.264 1920×1080/30 + AAC
48 kHz estéreo, decode completo, gaps de video ≤34 ms y AAC ≤22 ms. MKV contiene
13880 frames, igual que su contador nativo; RTMP contiene **5027 frente a 5028
nativos**. Esa diferencia terminal de un frame se conserva como pendiente.
Los peaks PCM completos son −12,3145 dBFS (MKV) y −16,7297 dBFS (RTMP), sin
saturación. La cobertura global sigue INCONCLUSIVE; no hubo nuevas referencias
aisladas de gain ni nuevos Cut/Fade en esta toma.

La [revisión visual compacta](../var/evidence/h13-native-visual-extract-1794946829324892000/visual-review.md)
acredita **alerta corregida PASS**: título “ALERTA H13” y subtítulo “Motive”
completos, aparición y desaparición en ambos destinos. Conserva **continuidad
de ventana FAIL**: contador `193356288` en ocho muestras MKV (PTS 5…425 s) y
tres RTMP (5,021…125,021 s). No determina congelamiento ininterrumpido entre
muestras ni su causa. Una fuente reportada sin issue no garantiza frescura.

El botón rojo, Dock Quit, cierre con permisos revocados y hot-unplug físico no
se declaran ejecutados. Las regresiones H1–H12 sobre G y sus propios alcances
se conservan en el [índice](h13-evidence-index.md).

## Cierre del ensayo

La [limpieza final](../var/evidence/h13-build/final-physical-cleanup.json)
confirma que Motive, fixtures, playbacks y receptores propios terminaron y que
se liberó el lock físico compartido. No se forzó la salida de Motive. El
último control de exclusión también cerró sus owners normalmente y conservó
bytes/permisos de proyecto, mixer y perfiles. No quedan pruebas físicas ni
decodificaciones en curso. Los cambios quedan en commits locales de H13;
no se hizo merge, push, release ni emisión pública desde este trabajo.
