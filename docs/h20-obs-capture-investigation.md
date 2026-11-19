# H20 — OBS, ScreenCaptureKit y CAP-01

Revisión de código y evidencia: 18 de noviembre de 2026 (Lima).
Este documento separa observaciones, hipótesis y experimentos pendientes.

## Hechos establecidos

B7 de H17 demostró un intervalo de aproximadamente 15 s en el que el productor
propio siguió dibujando: draws 510→960 y ticks 171→321. SCK mantuvo 468 callbacks,
467 superficies y la misma superficie; el consumo OBS quedó en 441 mientras los
renders aumentaron 452→905. El contador visual decodificado se repitió durante
15,4 s en MKV y 15,6 s en RTMP. Los timestamps continuaron con saltos máximos de
34 ms. Hubo 29 observaciones `suspended` y después reapareció una superficie
`complete`. Esto localiza el intervalo antes del consumo de superficies de OBS;
no identifica cuál componente interno de macOS dejó de producirlas.

La evidencia original y sus límites permanecen en
[H17](h17-capture-verification.md). B9 tuvo un fallo distinto: geometría 0×0 y
SCStream -3812 al crear una sesión. B10 rechazó la geometría inválida y permitió
una reselección explícita. No solucionó CAP-01. Cambiar los criterios de B7,
contar frames renderizados o observar PTS continuos no constituye una solución.

## Versiones examinadas

- OBS 33.0.1, commit `65c320b46e1af5c7a555161aea6182cdf7a8c524`, archivo fuente
  SHA-256 `9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b`.
  Motive conserva sus bytes en `.deps/obs-studio-33.0.1`; el builder compara cada
  fuente de mac-capture contra el archivo antes de crear una copia parcheada.
- La consulta de releases oficiales devolvió 33.0.1 como última estable.
  `master` observado: `717cfa8b7e633853cd21ad2cc656185b3b4255bb`, 39 commits por
  delante. Esta afirmación es una fotografía, no una dependencia de `master`.
- La comparación revisada cambia la selección de pixel format: extrae un helper
  y limita RGBAHalf a ARM64 con macOS 15+, conservando BGRA en Intel. No contiene
  una corrección demostrada de foco/suspensión/reinicio para CAP-01. Los cambios
  de raw audio en `libobs/obs-output.c` no prueban reparación del tail codificado.

Referencias: [release](https://github.com/obsproject/obs-studio/releases/tag/33.0.1),
[comparación fijada](https://github.com/obsproject/obs-studio/compare/33.0.1...717cfa8b7e633853cd21ad2cc656185b3b4255bb),
[captura 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-video-capture.m),
[delegate 33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-common.m).

## Semántica que importa

OBS usa `screen_capture` para Display=0, Window=1 y Application=2. Display filtra
un display concreto; Application incluye la aplicación en un display concreto;
Window usa `desktopIndependentWindow`. Esto no implica que cualquier ventana
minimizada o movida entre Spaces entregue imágenes nuevas continuamente.

El stream configura una cola de 8 y un intervalo de 0,9 veces el frame OBS. El
delegate recibe samples, extrae IOSurface y el render posterior reutiliza la
textura. El reloj y el render siguen siendo de libobs. Los contadores de render
no acreditan una nueva superficie ni cambios de contenido.

Apple distingue `complete` (nuevo frame), `idle` (sin cambio nuevo), `blank`,
`suspended`, `started` y `stopped`. Una edad grande sin buffers no basta para
diagnosticar congelamiento de contenido estático. Una muestra `suspended` sí debe
mostrarse como suspendida; no como saludable porque sigue habiendo render.
[SCFrameStatus](https://developer.apple.com/documentation/screencapturekit/scframestatus),
[filtro de ventana](https://developer.apple.com/documentation/screencapturekit/sccontentfilter/init(desktopindependentwindow:)),
[filtro de aplicación](https://developer.apple.com/documentation/screencapturekit/sccontentfilter/init(display:including:exceptingwindows:)).

`didStopWithError` y `capture_failed` permiten la acción Restart Capture en OBS.
Una ausencia de superficies sin ese callback no equivale a activar esa ruta.
El stop SCK es asíncrono: drenar la cola de destrucción OBS no demuestra que haya
terminado el callback de parada SCK. H20 no añade reconstrucción automática de
una sesión en vivo sin probar ese lifetime. `SCStreamErrorUserStopped` (-3817)
queda marcado como intención del usuario; no se reinicia automáticamente.

## Issues: qué aportan y qué no

| Referencia | Observación comunicada | Límite para Motive |
|---|---|---|
| [#14175](https://github.com/obsproject/obs-studio/issues/14175) | OBS 33.0.1 puede comenzar grabando la imagen anterior de una fuente detenida | Apoya bloquear preflight detenido; no explica B7 |
| [#11435](https://github.com/obsproject/obs-studio/issues/11435) | Congelamientos intermitentes; discusión de replayd, presión y Restart Capture | Reportes/hipótesis, sin trazas causales de nuestra Mac |
| [#8928](https://github.com/obsproject/obs-studio/issues/8928) | Captura congelada tras sleep/wake; Restart Capture añadido en OBS 30 | Sleep/wake no es la secuencia A→B→A; preservar stop intencional |
| [#12623](https://github.com/obsproject/obs-studio/issues/12623) | Fullscreen y cambios de foco asociados a congelamiento | Asociación en otra configuración; no atribuir a Stage Manager |
| [#12044](https://github.com/obsproject/obs-studio/issues/12044) | Display y audio pueden congelarse; cambiar a ventana ayuda en algunos casos | Display no es universalmente más fiable |
| [#13755](https://github.com/obsproject/obs-studio/issues/13755) | Error -3805 y crash Qt tras sleep en otra versión | No predice un crash GPUI ni demuestra causa compartida |
| [#13131](https://github.com/obsproject/obs-studio/issues/13131) | Congelamiento intermitente/error 3821 comunicado | Sin reproducción local causal |

Hipótesis abiertas: suspensión impuesta por el sistema al cambiar el contexto de
presentación; diferencias entre filtros; ciclo de vida/activación del consumidor;
efecto de instrumentación/admisión Motive. Ninguna está confirmada. No cambiar
preferencias de Spaces/Stage Manager, sandbox, TCC o políticas globales para
obtener un PASS. Tras dos intentos sin progreso en el mismo fallo se cambia de
hipótesis o se registra el bloqueo.

## Diferencias Motive y experimento comparable

H17 añade observadores SCK y OBS, exactitud de ID/PID de ventana, rechazo de
admisión/geometría inválida y observación de esos rechazos. H20 añade identidad de
display/app, rechazo de targets ausentes y geometría display inválida, marca de
stop intencional y límites de alcance: ventana sin child windows; aplicación sin
menú compartido. No cambia cola, clock, intervalos o política de restart OBS.

No se encontró OBS instalado en `/Applications` ni `~/Applications`; sí existe
el bundle fijado `.deps/OBS.app`. El contraste automatizado usa el **mismo owner
Motive/libobs con módulos mac-capture distintos**, no la UI Qt de OBS. Demuestra
diferencias del módulo bajo ese owner; no equivalencia con toda la aplicación OBS.

`scripts/build_obs_capture.py --variant` produce cuatro variantes inventariadas:

1. `upstream`: fuentes originales, sin observadores Motive.
2. `observed`: solo instrumentación SCK, sin admisión adicional.
3. `admission`: parches H17 más el código observador actual.
4. `motive`: todos los anteriores y admisión multimodo H20.

Cada bundle privado conserva el mismo ejecutable owner, libobs, encoder, output
module y herramientas. Solo se sustituye mac-capture, se corrigen sus rpaths y se
firma localmente. Un inventario explicita cada hash y las diferencias; no se
presenta el manifiesto original como identidad del módulo sustituido.

La secuencia es fixture propia→Motive→fixture propia, 15 s por tramo. El probe
independiente corrobora PID frontal y la fixture reporta su estado; dos solicitudes
de foco no corroboradas bloquean el ensayo. Se usan 1080p30, VideoToolbox CBR,
tono propio, MKV y receptor RTMP loopback. Se decodifica el contador a 5 Hz y se
conservan PTS, trazas, estado de productor, foco y cleanup.

La variante upstream **no tiene telemetría SCK**. Su alineación usa el reloj OBS
ya expuesto por `output_diagnostics`, dentro del bracket RPC. No se fabrican
callbacks/superficies; píxeles y outputs siguen siendo observables. Los gates de
geometría, foco, clocks, identidad y contenido permanecen. Una condición de foco
fallida es BLOCKED/INCONCLUSIVE, nunca PASS de captura.

## Audio y tail

La traza H17 observa paquetes antes del plugin de salida. Un paquete observado no
es un paquete escrito/recibido/decodificado. Se conserva el corte por `stop_ts`,
los tails pendientes y el fallo histórico de orden AAC; ni el contador fresco ni
el EOF del receptor acreditan entrega completa. El contraste correlaciona cada
medio con sus trazas y reporta pérdidas/reordenamiento separadamente. No se cambia
buffering 128 ms, interleaver, clock ni VideoToolbox por conjetura.

No se ha medido aquí A/V de juego/cámara/micrófono ni deriva de una hora. El tono
interno permite comprobar decodificación de audio, no sincronía audiovisual humana.
