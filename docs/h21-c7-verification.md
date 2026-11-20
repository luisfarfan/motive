# H21 — C7, identidad de ventanas admitidas

Estado: VERIFICACIÓN LOCAL CERRADA. PERSONAL STREAM READY: **BLOCKED**.
Fecha: 2026-11-19. Se conservan C4–C6 y todos sus FAIL.

## Problema observado y reproducción

Podcast C6 r4 terminó a 3345,767 s al observar respaldo no planificado. La
ventana del invitado tenía `SOURCE_UNAVAILABLE`, aunque SCK seguía `running`,
con muestra `complete`, superficie reciente y ningún error o suspensión.
La cámara y ambos outputs seguían activos. Audio sin warnings y cero drops.
El verificador pidió cierre normal; no se completó la hora.

C6 comprobaba la salud de una ventana existente mediante el inventario del
selector. Ese inventario filtra título vacío, nivel distinto de cero y metadata
de presentación de la aplicación, además del ID/PID. Son reglas para ofrecer
opciones de captura, no evidencia suficiente de que una ventana admitida murió.

`H21-C6-window-identity` reproduce el defecto: inicia dual sobre una ventana
propia V4 y luego eleva únicamente su nivel mediante `float 0`. C6 devuelve
`SOURCE_UNAVAILABLE` con SCK `running`/`complete`, superficie de 14,480 ms y 427
samples; activa el respaldo. El test conserva FAIL y todos los procesos salen
normalmente. No se cambian preferencias globales ni se captura otra ventana.

Esto demuestra un defecto reproducible del detector. El campo concreto que
causó el rechazo original a los 55 minutos no quedó registrado; no se afirma
que ese intento haya tenido exactamente el mismo cambio de nivel, ni se declara
resuelto CAP-01 por esta reproducción.

## Cambio de C7

La admisión de ventanas nuevas conserva el selector y sus filtros. Para una
fuente Window ya admitida, la salud consulta el ID exacto mediante
`CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, window_id)` y
comprueba el PID fijado. No busca sustitutos, no amplía el área capturada y no
reinicia SCK. La ventana ausente, un PID distinto o una consulta no disponible
siguen fallando; permisos y diagnóstico de SCK conservan sus guards.

Se registra una observación escalar de identidad: instante, ID/PID esperados,
consulta disponible, ventana encontrada, PID observado, nivel y presencia de
título. No se exponen títulos ni nombres de otras ventanas. La fuente inactiva
puede conservar la última observación, cuyo timestamp permite distinguirla.

Se usa la API pública del SDK local y el mismo patrón de consulta de identidad
presente en `plugins/mac-capture/mac-display-capture.m` de OBS 33.0.1. No se
introducen sleeps, grace periods, colas nuevas ni reconstrucción SCK en vivo.

## Construcción e historial

El primer build C7 falla antes de producir bundle por una colisión entre el
argumento C `id` y el tipo Objective-C `id`. Se renombra a `window_id`; el FAIL
queda en `H21-C7-build`. La segunda construcción conserva fuentes/hashes en
`H21-C7-build-r2`. Los resultados físicos y las tres sesiones horarias de este informe se
ejecutaron sobre el nuevo hash.

## Build y primer recorrido físico

`H21-C7-build-r2`: PASS, fuentes sin cambios durante el build. 134 tests del
núcleo, 136 Show Control y 169 Python; Clippy, formato, release ARM64 y bundle
portable firmado con la identidad de desarrollo existente. Versión local 21.7.
SHA-256: `7b6a07a96e666e9eac581f303acbce7c03e5d027b032a88233138f26f4903216`.

`H21-C7-window-identity`: runtime PASS. La misma ventana permanece capturada al
pasar a nivel 27, con ID/PID exactos observados; no se activa respaldo por ese
cambio. Al cerrar realmente la ventana, sí se activa el respaldo. Fuentes,
mixer y attempts de output conservan identidad, el stop es independiente y
owner/fixture/receptor cierran normalmente.

`H21-C7-window-identity-analysis`: PASS en MKV y receptor RTMP. Los contadores
decodificados avanzan durante la elevación (45 valores distintos por destino),
el cierre real termina en la escena segura y el audio permanece continuo.

`H21-C7-ui-owner`: PASS. La apertura normal observa los tres permisos concedidos.
Una edición real por interfaz renombra la escena a `H21 C7 UI` y muestra revisión
3; CLI y MCP leen ese mismo proyecto y PID. El owner termina normalmente, sin
errores de limpieza. No se guarda el proyecto de prueba sobre el del usuario.

## Base integrada repetida

`H21-C7-baseline-stages` termina sus doce invocaciones sin errores: fullscreen y
decode; recuperación Application/Window; proyectos v1–v6; política de salidas;
lifecycle Application/Window y sus decodes; siete etapas de audio y matriz de
outputs. Los estados funcionales se inspeccionan además del exit del coordinador.

`h13-system-audio-1795112326630713000`: las siete etapas pasan (pilot, RTMP,
recovery, silence, transitions, persistence y A/V). Los siete pares A/V de la
referencia corta quedan entre −69,125 y −36,125 ms. No acreditan deriva horaria
ni sincronía física de cámara/micrófono.

`H21-C7-output-matrix`: nueve PASS funcionales, sin repetir el fallo de readiness
que apareció en C6. Se prueban VideoToolbox/x264, recording/streaming/dual,
cancelación, receptor perdido y shutdown. La entrega terminal conserva su
aceptación PARTIAL; cero drops y reproducción correcta no la convierten en PASS.

Las regresiones físicas adicionales y las sesiones largas se detallan abajo.
Estos resultados acotados no convierten el intento C6 de 55 minutos en una hora
aceptada.

## Condiciones del escritorio

`H21-C7-resolution` y su análisis: PASS de Window durante el cambio autorizado
de Odyssey a 3200×900 y el retorno. La comprobación posterior al cierre observa
exactamente 3840×1080, 240 Hz, modo 111. No certifica Display durante ese cambio.

`H21-C7-stage-manager` y su análisis: PASS de Window con MKV/RTMP. El cambio se
realiza por la interfaz normal de Ajustes, off → on → off. La lectura posterior
al cierre confirma el valor original 0; no se modifica ninguna otra preferencia.

El primer foco C7 queda BLOCKED: las dos peticiones no consiguen foreground y
el observador identifica `loginwindow` PID 423. La primera regresión física H9
falla al admitir una ventana con geometría SCK 0×0 (`CAPTURE_NOT_READY`), antes
de iniciar outputs. Ambos intentos cierran sus owners y conservan informes.
Una lectura posterior de consola es desbloqueada; se repiten las pruebas con
preflight explícito, sin cambiar runtime, permisos ni políticas de energía.
La proximidad temporal no demuestra por sí sola la causa del fallo de geometría.

`H21-C7-focus-r2`: recorrido observado A → Motive → A y análisis de píxeles PASS,
con preflight de consola desbloqueada. CAP-01 sigue siendo un riesgo histórico,
no un defecto declarado resuelto. La finalización de la fixture de foco usa el
SIGTERM previsto por ese protocolo; el owner sale con 0 y no quedan errores de
limpieza.

H9 r2 vuelve a fallar en el mismo punto con `CAPTURE_NOT_READY`. Esto refuta una
atribución exclusiva al bloqueo de consola. La suite elige su ventana al aparecer
en el inventario CG; esa presencia no acredita geometría publicada por SCK. Tras
dos intentos se conserva el bloqueo del recorrido y se investigará la admisión;
no se repite a ciegas, no se suprime el guard y no se cambia el criterio histórico.
H10 se ejecuta por separado para que el primer fallo de H9 no oculte sus resultados.

La variación posterior mueve únicamente la construcción de la fixture antigua
a `applicationDidFinishLaunching`, conservando contenido, geometría y todas
las aserciones de H9. `H21-C7-h9-fixture-startup` PASS, manifest
`h13-regressions-1795113605125390000`: SCK admite 720×452 y termina la suite de
transiciones/cámara/audio. El diff, fuentes antes/después y hashes quedan en
`H21-C7-fixture-startup-diagnosis`. Es evidencia favorable a la hipótesis de
arranque; una ejecución no demuestra que todos los 0×0 históricos tengan esa
causa. El binario C7 no cambia y los dos FAIL originales permanecen.

`H21-C7-audio-regressions`: PASS de `verify_h10_audio.py` y
`verify_h10_mixer.py`, manifest `h13-regressions-1795114263404868000`. Los stores
se restauran y el owner final verificado cierra con 0, sin errores de limpieza.
Así quedan cubiertas las regresiones H9/H10 sobre C7 con la diferencia de fixture
anotada; la aceptación horaria se evalúa por separado.

## Primer intento horario C7: suspensión durante animación

`H21-C7-podcast-60min` termina FAIL a los 474,782 s por respaldo no planificado.
La identidad de la ventana permanece exacta: ID 20242, PID 88748, nivel 0,
consulta disponible y ventana encontrada. No repite el rechazo del selector
corregido en C7. SCK registra una muestra `suspended` y después vuelve a
`complete`; el respaldo conserva la escena segura. No se recrea la captura.

La telemetría de ambas ventanas muestra una animación coincidente: disminuyen
sus bounds y se desplazan, sin minimizarse ni dejar de dibujar, y después
recuperan sus dimensiones. Una interacción con el escritorio es una hipótesis,
no una causa confirmada. No se confirmó qué interacción lo causó. La
[definición de Apple de `suspended`](https://developer.apple.com/documentation/screencapturekit/scframestatus/suspended)
describe la ausencia de una nueva imagen por suspensión de actualizaciones;
no identifica qué interacción produjo este evento concreto.

Al fallar, recording/streaming siguen activos con 14253/14244 frames y cero
drops. No hay avisos de calidad de audio. El owner, la fixture y el receptor
cierran normalmente, sin errores de limpieza, y el micrófono vuelve al scalar
original exacto. Estos contadores no sustituyen el decode, ni acreditan una
hora o sincronía física. La solicitud de palmadas se cancela al cerrar el ensayo.
La candidata y sus políticas de respaldo se mantuvieron sin cambios durante
las tres horas posteriores; el fallo original queda abierto.

`H21-C7-podcast-60min-failure-review` decodifica por completo ambos medios sin
errores, conservando el informe original y el estado de sesión FAIL. No evalúa
deriva horaria ni convierte el intento interrumpido en un piloto aceptado.
Las seis pruebas del auditor nuevo de identidades pasan en
`H21-C7-identity-audit-tests-beab3efbd932b4f4`; son tests de análisis offline,
separados de los 169 tests Python registrados al construir C7.

El primer lanzamiento horario de Gaming queda `BLOCKED_BEFORE_START`:
`H21-C7-game-60min-owner` observa la consola bloqueada y no inicia owner ni
fixture. No es una sesión física de cero segundos ni una prueba del juego.
El wrapper restaura el micrófono exactamente y libera el lock. Se solicita
desbloqueo y autorización para una aserción temporal de reposo de 65 minutos;
no se modifica ninguna preferencia ni se inicia esa aserción sin respuesta.

## Gaming C7 r2: primera hora completa

Después de la autorización explícita de `caffeinate`, `H21-C7-game-60min-r2`
completa 3600,815 s. Runtime PASS: once cambios programados Cut/Fade con retorno,
MKV/RTMP simultáneos y stop independiente. La última observación activa conserva
cero drops en ambos destinos y no hay avisos de audio. El owner, juego,
cobertura y receptor cierran con 0; la aplicación de audio auxiliar recibe el
SIGTERM previsto por el protocolo. No quedan errores de limpieza.

El micrófono vuelve al scalar original exacto. La aserción de reposo del ensayo
se cierra; un relevo acotado mantiene la consola durante el paso al análisis,
que obtiene después el lock canónico. Ningún decode compite con la captura.
La auditoría de identidad, el decode completo, A/V, deriva y entrega terminal
se evalúan aparte. Una hora de runtime no se convierte automáticamente en
aceptación completa ni en PERSONAL STREAM READY.

El análisis de Gaming r2 pasa duración, decode, cadencia, PCM y A/V en ambos
medios: 216443 frames MKV y 216348 recibidos. Máximo |audio−video| del marcador:
40 ms en MKV y 51 ms en RTMP; deriva de medianas ≈10,184 ms/h en ambos,
dentro de los presupuestos históricos. Los 3005 puntos de identidad pasan,
con separación máxima de 2,297 s. Son observaciones, no prueba de lifetime SCK.

Cada medio tiene once huecos del marcador visual mayores que 1,2 s, en
correspondencia con los once pasos planificados por la escena segura. La
revisión conserva tiempos y límites; no se presenta como prueba de todos los
píxeles. No hay huecos del marcador de audio mayores que 1,2 s: máximo 1,01 s.
La continuidad del mix y de su componente 997 Hz no certifica por separado
todas las otras entradas. La carga y resolución interna del juego se describen
aparte de los 60 FPS de salida.

La cola final queda PARTIAL en los dos destinos:
`STOP_BOUNDARY_PACKETS_NOT_DELIVERED`, con el clasificador histórico intacto.
No se infiere entrega total a partir del decode ni se ocultan las ausencias
compatibles con el límite de stop. El análisis cierra sus procesos y aserciones
de reposo, sin cambiar el binario C7 ni sus fuentes runtime.

## Podcast C7 r2: segunda hora completa

`H21-C7-podcast-60min-r2` completa 3600,980 s con runtime y calidad de audio
PASS. Conserva once ciclos de escena y mezcla, 108012/108005 frames en la
última observación activa de MKV/RTMP y cero drops. Owner, fixture y receptor
cierran con 0, sin errores de limpieza; el micrófono vuelve a su scalar exacto
y se cierra la aserción de reposo de la captura. El análisis offline toma el
lock después de ese cierre.

La auditoría de identidad pasa 3247 observaciones, con separación máxima de
2,068 s. La cámara mantiene su identidad y entrega frames a 1280×720; esto no
prueba por sí solo sincronía física. Las palmadas iniciales se confirmaron;
las solicitudes intermedia y final no recibieron confirmación antes del cierre.
La revisión final conserva los gestos realmente observables en los medios,
sin inferirlos de las solicitudes.

El decode completo y las puertas de cadencia/PCM pasan en ambos medios:
108189 frames MKV y 108163 recibidos, máximo hueco PTS de video 34 ms y de
audio 22 ms. El marcador de la aplicación mide máximo |audio−video| de
63/67 ms y deriva de 13,239 ms/h, dentro del presupuesto. No hay huecos de su
marcador de audio mayores que 1,2 s. Los once huecos visuales se contrastan
aparte con las once salidas programadas de la escena principal.

La entrega terminal conserva PARTIAL: todos los paquetes de video trazados
están presentes y falta un paquete AAC por destino en o después del bracket
de stop (`DOCUMENTED_STOP_CUTOFF_COMPATIBLE`). No hay pérdida anterior a stop
en esas trazas acotadas. El análisis y sus aserciones de reposo cierran con 0.
CPU mediana de Motive: 26,48% de un núcleo; RSS mediana 209,28 MiB y footprint
mediano 506,91 MiB. El footprint entre extremos crece 15,05 MiB; esa observación
no demuestra ausencia de fugas. La carga es una cámara física, micrófono y
aplicación de invitado generada, no una conversación remota de una hora.

## Podcast C7 r2: revisión física final

`H21-C7-podcast-60min-r2-physical-sync/analysis.json`: PARTIAL. Se inspeccionan
las tres palmadas iniciales en ambos archivos: manos separadas en frame 12 y
juntas en frame 14 de cada secuencia. En MKV los brackets visuales son
98,100–98,167; 98,867–98,933 y 99,633–99,700 s. Los picos RMS filtrados asociados
son 98,105562; 98,878562 y 99,649562 s. RTMP conserva los mismos gestos con su
propio origen. Pico filtrado no equivale a onset acústico; el retardo de los dos
filtros causales de 3 kHz no se calibró. No se declara PASS físico por esa resta.

La búsqueda posterior abarca 95 s alrededor de la petición intermedia y todo
el intervalo desde cinco segundos antes de la final hasta el cierre. Sus
candidatos fuertes conservan una fase de un segundo compatible con el marcador
de la aplicación; no se identifica una palmada física tardía. Una palmada más
tenue no queda descartada. No hay referencia final utilizable y la deriva física
es NOT_MEASURED. Las solicitudes no confirmadas no sustituyen esa referencia.
La hora no tuvo avisos de clipping y el PCM final máximo es 0,177/0,178.

## Charlas C7: tercera hora completa

`H21-C7-charlas-60min`: runtime/calidad de audio PASS, 3600,939 s y once ciclos
entre Window y Application/Display. Última observación activa: 108003/107997
frames MKV/RTMP y cero drops. Al cerrar la ventana propia final, se observa el
respaldo a 0,396 s del comando de cierre; ambas salidas continúan otros tres
segundos. Se detienen independientemente y owner/fixture/receptor cierran con 0.
Micrófono restaurado exactamente, sin errores de limpieza.

`...-analysis`: decode completo, duración y cadencia PASS. 108169/108150 frames,
máximo hueco PTS de video 34 ms y audio 22 ms. Referencia A/V máxima 47 ms en
ambos medios; deriva de medianas inicial/final 14,258 ms/h en MKV y 13,239 ms/h
en RTMP. No hay huecos del marcador de audio mayores que 1,2 s. La auditoría de
identidad pasa 3270 observaciones con intervalo máximo 1,889 s.

La entrega terminal queda PARTIAL: MKV pierde un paquete de video compatible
con el corte de stop y conserva todos los AAC trazados. RTMP es INCONCLUSIVE,
`beginning_of_trace_not_complete`: la traza inicial guardada estaba vacía.
No se reconstruye un origen supuesto ni se relaja el clasificador histórico.
El decode correcto no resuelve esa ausencia de instrumentación.

La revisión auxiliar de los once huecos visuales falló con `StopIteration` al
asumir una primera traza de video RTMP. El log y `...-marker-review/failure.json`
permanecen; ese fallo hizo salir con 1 al coordinador offline, aunque decode,
identidad, cola y preparación física ya habían terminado con 0. La repetición
metadata-only `...-marker-review-r2` conserva PARTIAL: once cambios correlacionados
en MKV y once huecos RTMP sin mapa al reloj del supervisor. No se repitió ni
sobrescribió el análisis de medios para cambiar el resultado.

CPU mediana 16,98% de un núcleo, RSS 229,83 MiB, footprint 354,20 MiB y cambio
entre extremos +16,52 MiB. GPU mediana del dispositivo 14%. Cero render lag/video
skipped; 524 descartes del preview son una métrica distinta de drops de output.
El navegador queda BLOCKED por falta de una ventana nativa propia mediante la
herramienta autorizada; no se usa un navegador personal ni H22.

## Integridad y cierre final

`H21-final-artifacts` conserva un FAIL del cotejo: contó el symlink
`libobs.framework/libobs` como archivo extra, mientras el manifiesto original
excluye symlinks. `H21-final-artifacts-r2` aplica esa misma regla del build:
PASS de los 1.584 archivos regulares, cero diferencias/extras, runtime intacto,
enlaces actuales internos y `codesign --verify --deep --strict` exit 0. No había
mapa histórico de enlaces; no se afirma comparación histórica de sus destinos.
El bundle no se modificó. Archivo suplementario de 118 fuentes conservado.

`H21-final-cleanup`: 14 checks PASS. Seis stores iguales por hash al baseline,
Odyssey 3840×1080@240 modo 111, Stage Manager 0 y micrófono exactamente
0,3764705955982208. No quedan owners, fixtures, receptores, coordinadores Python
ni aserciones de reposo H21. Socket ausente y lock propio liberado. Evidencia
privada conservada; ningún proceso o lock ajeno se modifica.

Las tres horas están completas; su aceptación global sigue BLOCKED. La
[matriz final](h21-personal-streaming.md) separa formato/cadencia, referencia de
aplicación, sincronía física, entrega terminal y alcance de carga. Ese cierre
original no incluyó emisión externa, publicación, merge o push.

## Seguimiento supervisado posterior

El [seguimiento C7](h21-c7-followup.md) conserva el mismo binario y añade una
hora Podcast r3 con contactos visibles/sonido al inicio, medio y final. Ambos
medios pasan; un bloque de clipping de entrada mantiene calidad FAIL y la
incertidumbre de los intervalos físicos mantiene deriva PARTIAL. Spaces no
observa el cambio solicitado. El segundo ensayo privado de YouTube sí recibe
confirmación del operador de etiqueta, movimiento y tono durante 180,364 s de
envío; el primer intento conserva su confirmación retirada. No hay aceptación
de A/V remoto sin medición independiente. Integridad completa y 15 checks de
limpieza pasan de nuevo. No hay merge, push ni release.
