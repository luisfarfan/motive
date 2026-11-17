# Plan y criterios de aceptación

Estado: 2026-11-17 (America/Lima). Base experimental ejecutable; no es una
release ni paridad con OBS/Meld. La investigación documental quedó resuelta
para esta fase y REA no bloqueó los hitos.

**H13 implementado; aceptación final EN CURSO.** Canvas configurable, audio del
sistema y salidas MKV/RTMP independientes ya comparten núcleo, CLI/MCP y GPUI.
Las 23 suites H1–H12 pasan en sus últimas ejecuciones del bundle G; también
pasan la matriz dual de cuatro casos/doce medios y el A/V visible. Producción
operada por GPUI y sesión prolongada siguen pendientes. La exclusión propia
final conserva FAIL con atribución INCONCLUSIVE. Estado y hashes:
[índice de evidencia](h13-evidence-index.md) y [verificación H13](h13-production-verification.md).

La tabla conserva el alcance y los límites de cada bundle histórico; las
ampliaciones posteriores se registran en su propio hito.

| Hito | Evidencia real | Estado y límite |
|---|---|---|
| 0 — Viabilidad | GPUI Kit abierto; libobs 33.0.1 Metal; patrón propio y captura ScreenCaptureKit de otra ventana GPUI; preview inspeccionado | Verificado en esta Mac; copia CPU, sin zero-copy |
| 1 — Producción | Selección de ventana externa, cámara y micrófono integrados; grabación real; guardar/restaurar; pérdida de ventana y reconexión explícita | Verificado en esta Mac; hot-unplug físico USB, sesiones largas y cámara congelada pendientes |
| 2 — Agentes | MCP/CLI comparten PID y revisión con UI; cambio visible del overlay; desconexión conserva el motor; errores estructurados | Conjunto mínimo verificado; no certificación de todos los clientes MCP |
| 3 — Diferenciador | Overlay animado dentro de archivos; 960×540 y 540×960 con contain, margen seguro y anclaje inferior; vertical 4.166000 s/123 frames | Política mínima verificada; editor libre y salidas simultáneas pendientes |
| 4 — Streaming | libobs → MPEG-TS UDP loopback → FFmpeg, 5.021333 s/150 frames, H.264/AAC y overlay | Receptor local verificado; plataformas públicas y RTMP/SRT pendientes |
| 5 — Primer editor | Ventana + webcam + overlay; transformaciones y orden por MCP; persistencia v3 y reapertura; UI refleja el núcleo | Ver [verificación de escenas](scene-graph-verification.md); una composición/output activo, cambios de recursos solo detenido |
| 6 — Encoder Apple Silicon | Módulo oficial VideoToolbox, selección compartida y fallback x264; comparación de archivos y recursos | Ver [verificación VideoToolbox](videotoolbox-verification.md); alcance inicial H.264, misma resolución/FPS, sin cambiar UI ni UDP local |
| 7 — Salidas configurables | Perfiles v1 separados de escenas v3; RTMP local H.264/AAC, preflight y recuperación por CLI/MCP; rechazo TLS no confiable | Ver [verificación H7](h7-output-verification.md); sin claves ni destinos públicos, RTMPS positivo y cancelación inmediata de handshake pendientes |
| 8 — Streaming confiable | Cancelación diferida con workers finalizados, cierre explícito, Keychain con referencias opacas y pruebas reales | Ver [H8](h8-streaming-verification.md); RTMPS positivo pendiente por falta de destino/cadena confiable, sin cambios a la confianza global |
| 9 — Escenas en vivo | Cut/Fade oficiales durante grabación y RTMP, webcam compartida, preparación, cancelación, fallos y restauración v3 | Ver [H9](h9-scene-transitions-verification.md); núcleo/CLI/MCP sin cambios GPUI, audio global, huecos finales VT y pruebas largas pendientes |
| 10 — Audio Mixer | Micrófono + tono, ganancia/mute, medidores, recuperación por entrada, persistencia v1 y Cut/Fade durante grabación/RTMP reales | [H10](h10-audio-verification.md): CLI/MCP reales y 17 suites H1–H9 aprobadas; USB hot-unplug/permisos/sleep y sesiones largas pendientes |
| 11 — Overlay Engine y widgets | Texto, imagen alpha, formas, video visual, seis animaciones por capa, widgets y tres presets en dos layouts; CLI/MCP, grabación/RTMP y persistencia reales | [H11](h11-overlay-verification.md): 13 clips y 49 tests; aceptación condicionada a regresiones H1–H10 abiertas. Browser bloqueado; GPUI integra el [contrato](h11-overlay-ui-contract.md) por separado |
| 12 — Creative Studio integrado | Biblioteca, picker, inspectores tipados, eventos, animaciones y persistencia desde GPUI; grabación VT/RTMP decodificada; 22 suites en sus últimas ejecuciones | [H12](h12-creative-studio-verification.md): 55 tests y Clippy; se conserva el fallo previo de render lag sin causa resuelta, sin certificar bundles posteriores |
| 13 — Live Production Engine | Bundle G: siete casos de canvas, mezcla/recuperación, matriz dual 4/4 casos y 12/12 medios, A/V visible y 23/23 suites H1–H12 en sus últimas ejecuciones | [H13](h13-production-verification.md): implementado; aceptación final **EN CURSO**. Recorrido GPUI y sesión prolongada pendientes; exclusión propia final FAIL, atribución INCONCLUSIVE |

Las verificaciones H0–H10 de la tabla son evidencia histórica de sus respectivos
bundles. En el bundle H11 `a423dee…20b3d`, los tres manifests de regresión
registran **14 suites distintas PASS y cinco todavía fallidas**: H1 por contenido
de cámara casi negro, encoding por 9/13 frames de lag VideoToolbox y preparación
de ventana sin dimensiones de video en scenes/H9 faults/H9 transitions. Se mantienen los
criterios y los fallos. La sesión bloqueada es una hipótesis para la captura de
ventanas, pendiente de repetición desbloqueada; no hay causalidad confirmada.
El bundle final B7 `bd748f…dced6` reconfirmó 13 suites, incluyendo H10 completo;
`verify.py` conserva solo su PASS anterior porque usa captura de ventana.
El diagnóstico B7 de encoding conserva 6 frames de lag al arranque y cadencia
estable posterior. No se rebajó su criterio; la causa sigue abierta.
Estos pendientes impedían aceptar aquel bundle H11; el detalle y hashes están
en el [informe H11](h11-overlay-verification.md). H12 repitió los grupos con
éxito en su propio bundle, sin borrar los fallos históricos. H13 conserva su
propia evidencia G y mantiene abiertos los gates específicos indicados abajo.

## Reproducir y consultar evidencia

Seguir README.md para bootstrap/bundle. Abrir Motive y su fuente de prueba,
mantenerla disponible y comenzar sin una salida activa:

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/verify_control.py
python3 scripts/verify.py
```

La ejecución original de ambos scripts terminó con éxito. En esa tanda pasaron
seis pruebas unitarias; H11 amplió el conjunto a 49, H12 a 55 y el bundle H13
`d9b8d702…e0e2d93` a 71, con Clippy y formato limpios.
La integración usa el motor y hardware reales, sin mocks. Se conservaron las
pruebas fallidas.

- `var/evidence/acceptance.json`: archivos, duración, frames, audio, overlay y
  muestras de CPU/RSS; `ok: true`.
- `var/evidence/control-integration.json`: intercambio MCP, PID/revisión y
  continuidad tras desconexión.
- `var/evidence/source-loss.json`: error tras cerrar la fuente de captura.
- `var/evidence/horizontal.png` y `vertical.png`: frames reales del motor.
- `var/evidence/build-identity.json`: hashes del ejecutable, fuentes y lockfile.
- `var/evidence/final-acceptance-runtime.log`, `tests.log`, `clippy.log` y
  `bundle.log`: runtime y verificaciones.

Las rutas de videos están en acceptance.json. Son artefactos locales ignorados
por Git y reproducibles. El bundle está en `target/Motive.app`.

## Medición y límites

Durante la regresión H1, `ps` registró CPU mediana 33.3 %, máximo
39.5 %, y RSS entre 190.6 y 307.7 MiB. Build debug con UI
y ventana controlada; excluye el helper de muxing y la carga restante del
sistema. Los contadores de render, output y preview están en acceptance.json.
Son contadores distintos. No demuestran cero latencia ni ausencia de pérdidas
en todos los niveles. No hubo benchmark comparativo ni prueba prolongada de
memoria.

En la primera etapa el micrófono estaba denegado. En H1 se autorizaron cámara,
micrófono y pantalla mediante los permisos normales de macOS y se verificó
grabación física. Ver [informe H1](h1-verification.md) para evidencia, firma
de desarrollo, desconexión de ventana y límites de hot-unplug. Solo esta
Mac/macOS 27.2 fueron probados. El mínimo de build 15.0 no equivale a una matriz
de compatibilidad ejecutada.

## Evolución de interfaz nativa

La rama aislada `codex/ui-evolution` modulariza GPUI y añade gestión de escenas,
Cut/Fade, fuentes, perfiles, RTMP local y el mixer H10 ya integrado/verificado.
Todos los controles usan Production; preferencias visuales tienen su archivo
local separado. Ver [resultados y límites](ui-evolution-verification.md) y
[mapa UI/núcleo](ui-architecture.md). No equivale a terminar el Design System;
biblioteca de grabaciones, propuestas de agentes y entrada nativa de secretos
necesitan contratos y pantallas apropiados. La UI se integró en `main` mediante
el commit `55c23f5`. H12 incorporó después los controles específicos de H11;
H13 añade canvas, audio del sistema y salidas dirigidas. Su aceptación nativa
final se sigue en el [recorrido H13](h13-native-acceptance.md).

## Alcance histórico de H11 y evolución posterior

El núcleo H11 reutiliza fuentes oficiales libobs para texto, imágenes y video,
con formas, widgets y animaciones limitadas por capa. Los timers avanzan sin
cliente MCP. Los presets originales lower-third, starting-soon y BRB tienen
layouts horizontal/vertical. Imports asíncronos desde una bandeja explícita
producen assets administrados por ID; no aceptan rutas ni URLs arbitrarias.
El proyecto guarda v4 solo cuando contiene definiciones H11, conserva v3 para
los anteriores y sigue cargando v1–v3. Mixer y perfiles siguen separados.

H12 cerró los cinco grupos de regresión que quedaron abiertos en H11 e integró
el [contrato de overlays](h11-overlay-ui-contract.md) en GPUI, con el mismo
`Production`, definiciones tipadas, eventos e IDs de operación, sin duplicar
renderer ni reloj. H13 conserva esos gates en su repetición serial final.
Las animaciones de capa esperan confirmación interna del propietario antes de
permitir cambios de grafo o Cut/Fade; no existe ack público.

Browser/CEF queda bloqueado hasta resolver aislamiento y lifecycle; HTML/JS no
está habilitado. El video importado no aporta audio. Evaluar audio de medios
mediante H10, tipografía/fallback, HDR/alpha de video y automatización creativa
adicional como incrementos independientes. El límite estimado de 256 MiB y cuatro
fuentes de video no limita RSS ni picos: siguen pendientes presión de memoria,
decoders ocultos y sesiones largas. Ver [arquitectura](h11-architecture-review.md)
y [comparación oficial](h11-comparison.md).

H10 implementa Audio Mixer en el núcleo compartido, con aceptación real de
micrófono + tono, ganancia/mute, medidores, reapertura por entrada y persistencia
separada. Ver [H10](h10-audio-verification.md) y el
[contrato GPUI](h10-audio-ui-contract.md). La captura de audio del sistema,
pospuesta en la [evaluación H10](h10-system-audio-next.md), se implementa en H13
mediante el módulo oficial SCK y el [contrato v1/v2](h13-video-audio-contract.md).
Conservar pendientes USB hot-unplug, revocación de permisos y sesiones largas;
no añadir filtros, monitorización ni audio por escena en este alcance.

Sigue pendiente validar RTMPS positivo con un destino controlado y certificado
públicamente confiable. Antes de habilitarlo, registrar localmente destinos
autorizados y vincular sus referencias Keychain a hostname/puerto/aplicación;
MCP seleccionará destinos aprobados, sin recibir claves ni URLs arbitrarias.
No requiere un dominio propio de Motive. Ver el [informe H8](h8-streaming-verification.md)
para el bloqueo de una CA aislada, evidencia y secuencia de prueba privada.

Conservar pendientes sesiones largas, USB hot-unplug, sleep/wake, matriz de
macOS y bundle portable/notarizado. No añadir multistream, nube, pagos ni
marketplace, ni emitir a servicios públicos sin autorización. Una grabación y
un destino RTMP concurrentes en H13 no habilitan multistream ni dos lienzos.

## Ampliación H1

Ver [informe de verificación](h1-verification.md) y ejecutar
`scripts/verify_h1.py` con los UIDs físicos solo cuando corresponda.
UI, CLI y MCP siguen controlando la misma instancia de Production.
Las grabaciones y los inventarios de dispositivos permanecen fuera de Git.

## Incremento de escenas

El formato v3 añade escenas, recursos reutilizables y capas con IDs estables y
transformaciones horizontal/vertical independientes; H11 añade definiciones
opcionales mediante v4; H13 añade v5 al declarar configuración explícita de
video, conservando v1–v4 a 540p30. UI, CLI y MCP usan `Production`; `tools/list`,
`video_capabilities`, `output_capabilities` y `overlay_capabilities` describen
la superficie vigente. Las pruebas históricas
de composición y recuperación están en
[scene-graph-verification.md](scene-graph-verification.md); la repetición actual
sobre H11 y sus fallos quedan en el [informe H11](h11-overlay-verification.md).
Las regresiones H13 preservan fixtures v3/v4 reales; no migran toda la matriz a
v5 para hacerla pasar. Ver [preparación y restauración](h13-regressions.md).

## H12 — integración funcional verificada

Worktree separado sobre `d2fb22e`. Los cinco grupos de regresión H11 abiertos
pasan en el baseline integrado exacto, con cámara preparada, sesión desbloqueada
y sin relajar gates. H10 requirió corregir el estadístico del verificador RMS,
conservando el margen de 2 dB, los fallos originales y nuevas grabaciones físicas.
Detalle y hashes: [H12 verificación](h12-creative-studio-verification.md).

Implementados en GPUI: biblioteca, selector nativo seguro, definición tipada por
tipo, eventos, presets, Fade/Slide/Scale con op IDs y persistencia existente v4.
[Contrato de integración](h12-creative-studio-contract.md). Producción conjunta
operada desde GPUI y decodificada en grabación VT/RTMP local: texto editado,
transparencia, video, ventana propia, widgets, animaciones y mixer. Restauración
v4/mixer y recuperación desde picker verificadas; CPU/RSS de cuatro videos medidos.
Las 22 suites del bundle final pasan en sus últimas ejecuciones. Se preserva el
fallo inicial de encoding con 2 lag frames: ABBA posterior pasa con gates intactos,
pero su causa sigue abierta. No se declara eliminada esa intermitencia ni se
reescribe el informe histórico H11. Browser/CEF permanece restringido.
Revisión de tamaños, temas y límites accesibles: [auditoría nativa](h12-native-ui-audit.md).

## H13 — implementación y aceptación final EN CURSO

El núcleo tiene una sola composición, mezcla y reloj libobs. `configure_video`
selecciona 540p/720p/1080p y 30/60 FPS únicamente con recursos quiescentes;
las dos orientaciones conservan coordenadas de diseño 960×540/540×960.
Proyecto v5 persiste la configuración explícita y las versiones anteriores
conservan 540p30. No se promete la cadencia del compositor para cada captura.

`system_audio_sources` permite seleccionar una aplicación por bundle ID único
o el escritorio principal por UUID. La identidad reutiliza canal y controles;
el módulo OBS solicita excluir el audio de Motive y el núcleo rechaza escritorio
junto con aplicaciones por solapamiento. La exclusión final sigue sin acreditar.
Mixer v1 sigue válido; las nuevas fuentes requieren v2. Se mantienen ganancia,
mute, medidores post-fader/pre-mute, master post-mute/pre-clamp, monitoreo apagado
y recuperación explícita por entrada. [Contrato canvas/audio](h13-video-audio-contract.md).

`outputs` expone `recording` y `streaming`; cada intento tiene perfil efectivo,
par H.264/AAC, estado, duración, métricas y fallo propios. `start_output`,
`stop_output_target`, `cancel_output_target` y `recover_output_target` actúan
por destino; `cancel_all_outputs` conserva el estudio abierto. Los arranques
heredados siguen exclusivos y stop ambiguo devuelve `OUTPUT_TARGET_REQUIRED`.
La barrera RTMP H8 permanece por slot. [Contrato de salidas](h13-output-contract.md)
y [decisión de arquitectura](h13-production-architecture.md).

El bundle G (`d9b8d702…e0e2d93`) tiene 71 tests, Clippy y formato PASS, y
**23/23 suites H1–H12 distintas PASS en sus últimas ejecuciones**. El conteo
del [índice de evidencia](h13-evidence-index.md) incorpora nuevas grabaciones
con [referencias aisladas H10](h13-h10-metrology.md); conserva los fallos y
manifiestos previos sin convertirlos en PASS.

En G pasan siete configuraciones de canvas, siete etapas de audio del sistema
y la matriz dual: **4/4 casos y 12/12 medios**, incluidos fallos de receptor y
helper muxer; dos archivos son parciales intencionales. A/V con ventana visible
pasa con siete pares de pulsos, mediana audio−video **+24,27 ms** y rango
**33 ms**, sin acreditar latencia cero. Se verifica además H8 con cierre
pendiente y rechazo de nuevos trabajos, y cierre durante una
importación 1080p de 20,27 s: 29 consultas del worker activo, máximo 88,9 ms,
petición de cierre 30,7 ms y salida del owner en 3,271 s. Esta evidencia de
núcleo no sustituye el flujo nativo de confirmación/cancelación.

La [exclusión propia final](h13-system-audio-exclusion-final.md) permanece
**FAIL; atribución INCONCLUSIVE**: supresión −16,41 dB frente al gate <−45 dB,
con fondo adicional de banda ancha. No acredita exclusión ni demuestra por sí
sola una regresión concreta de SCK; el PASS del bundle C queda separado.

El [probe dirigido de memoria](h13-encoder-tail-investigation.md) observa la
destrucción de ocho fuentes ffmpeg y sus wrappers, y asignaciones malloc activas
cercanas al baseline: 35,4M frente a 33,5M según `vmmap`. Persisten páginas
residentes: 835,5M en esa zona, y RSS mediana de 1141,38 MiB tras liberar y
esperar 20 s frente a 178,41 MiB iniciales. No es un PASS de presupuesto de
memoria ni prueba causal de fuga o de su ausencia; `vmmap` puede perturbar la
residencia y este protocolo es más corto que H12.

Los siguientes gates siguen abiertos hasta contar con sus informes completos:

- Producción GPUI integrada con ambas salidas, audio del sistema/micrófono,
  Cut/Fade, edición/widgets, stop/recovery por destino y persistencia.
- Confirmación, cancelación y cierre desde ventana, menú y Cmd+Q con salidas
  activas/conectando; inspección de estados y tamaños nativos.
- Exclusión del audio propio del bundle final, con condiciones de audio
  controladas que permitan atribuir el resultado; conservar el FAIL actual.
- Sesión prolongada y análisis completo de sus medios, recursos y cadencia.

El [informe H13](h13-production-verification.md) separa cada hash y resultado;
el [checklist nativo](h13-native-acceptance.md) distingue observaciones y pasos pendientes.
No se ocultan las congelaciones anteriores de ventanas ni los huecos finales
de video. La corrección del tono determinista tiene su
[investigación de entrega](h13-audio-startup-investigation.md), y los costes
CPU/RSS y colas se conservan en la [medición de encoders](h13-encoder-tail-investigation.md).
Siguen pendientes USB hot-unplug, revocación real de permisos, cambio físico de
display, sleep/wake, otras versiones de macOS, RTMPS positivo confiable y bundle
portable/notarizado. No hay autorización de push, merge, release ni emisión pública.
