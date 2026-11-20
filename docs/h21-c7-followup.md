# H21 C7 — seguimiento supervisado

**Seguimiento cerrado; PERSONAL STREAM READY sigue BLOCKED.** La candidata C7
conserva el ejecutable `7b6a07a96e666e9eac581f303acbce7c03e5d027b032a88233138f26f4903216`.
No se recompiló el runtime. Este seguimiento añade evidencia a las tres horas
anteriores, sin sustituir sus resultados ni borrar fallos.

## Podcast r3

La nueva toma completó **3600,411 s** con cámara y micrófono preparados,
invitado generado y MKV + RTMP loopback. El owner cerró con código 0, sin errores
de limpieza; el nivel físico del micrófono volvió al escalar exacto autorizado.
Las referencias inicial, intermedia y final fueron confirmadas mientras se
grababa. Las marcas de solicitud/confirmación solo delimitan búsquedas; la
sincronía requiere localizar el contacto visible y el sonido en los medios.

La calidad del micrófono conserva **FAIL**: se observó un bloque saturado entre
los segundos 72,064 y 73,152, antes del fader. El contador permaneció en 1 después
de las referencias intermedia y final; la mezcla no saturó. Completar la hora
no elimina ese fallo. Ambos medios pasan decode completo y cadencia:
108.171 frames MKV y 108.139 RTMP. La referencia de aplicación tiene máximos
de 63/57 ms y deriva de 20,368/10,184 ms/h. Esas mediciones pasan los presupuestos
de la referencia generada; no sustituyen la sincronía física.

Las 3.214 observaciones de identidad pasan, con hueco máximo de 2,330 s.
Los once huecos del marcador visual corresponden a los once cambios previstos;
el componente de audio no tiene huecos mayores de 1,2 s. No hay drops de output
ni frames lagged/skipped del compositor; se registran 309 drops del preview,
un contador distinto. CPU mediana 28,42% de un núcleo, RSS 202,08 MiB,
footprint mediano 517,70 MiB y delta −0,52 MiB; GPU global mediana 28%.
No prueban ausencia de fugas. Ambas colas conservan
`STOP_BOUNDARY_PACKETS_NOT_DELIVERED` y clasificación PARTIAL.

La revisión física confirma contactos visibles y sonido cercano en **inicio,
medio y final**: seis contactos del MKV y tres correspondientes del receptor
fueron inspeccionados con sus PTS reales. Se conserva PCM sin filtrar y la
sensibilidad de nueve umbrales con corrección exacta del retardo del filtro
finito. Un candidato final a 3497,3105 s se excluye porque las manos están abajo.

**Sincronía/deriva físicas PARTIAL por precisión, ya no por falta de referencias.**
Los intervalos exploratorios audio−video son compatibles con 80 ms, pero no
constituyen calibración del AAC, exposición ni propagación acústica. Comparando
el primer contacto inspeccionado y el primer contacto final bien delimitado,
la estimación central de deriva es 7,71/9,29 ms/h. Sus intervalos conservadores
son **[−46,30; +61,73] / [−45,25; +63,83] ms/h**: no permiten certificar
`|deriva| ≤40 ms/h`. No es evidencia de que la deriva real exceda el presupuesto.
La incertidumbre visual de 33–67 ms no se reemplaza por un instante inventado.

Evidencia privada: `var/evidence/H21-C7-podcast-60min-r3/`, sus reports de owner,
calibración, awake y análisis. No se publica el material de cámara/micrófono.

## Spaces con operador

`H21-C7-spaces-operator-r1` conserva **FAIL**: la ventana propia entró en
fullscreen nativo en el Odyssey, pero no se observó `on_active_space=false`
durante los 180 s concedidos. La confirmación del usuario llegó después del
cierre; no acredita el momento de la acción. No se reconstruyó SCK ni se cambió
ninguna preferencia global. Fixture, receptor y owner cerraron con código 0.
El gate Spaces sigue sin verificar; no se declara reparado por una confirmación
posterior ni se heredan PASS de fullscreen.

## Destino privado de YouTube

El usuario autorizó expresamente el destino existente y confirmó su privacidad.
El ensayo usó solo el patrón generado, el texto único **H21 C7 / YT-B8A685** y un
tono. No incluyó cámara, micrófono ni captura de pantalla. El inicio se confirmó
en la UI nativa normal; la clave permaneció en Keychain y no pasó por CLI/MCP.

El runtime local pasa **180,169 s** de RTMPS junto con MKV, seguido por stop
independiente y cierre normal. Los bytes del store de destinos no cambiaron.
El MKV local pasa decode completo, H.264 1080p30 + AAC 48 kHz estéreo, 6.658
frames, cadencia y continuidad del tono. Estas observaciones no prueban entrega
ni sincronía remotas.

**Recepción remota del primer intento NOT_CONFIRMED.** El propietario respondió inicialmente que
veía etiqueta/movimiento/tono, pero retiró esa confirmación durante la emisión:
no veía ningún directo en la sala de control de YouTube Studio. Se conservan
ambas declaraciones; `remote-operator-correction.json` supersede el resultado
de `remote-operator-observation.json`. La captura aportada después del stop
muestra **No hay datos** y **Privado**; no establece el estado durante el primer
envío. No se infiere una clave errónea únicamente de los contadores locales.

Se repitió una sola vez con la sala real ya abierta e identificada, conservando
destino y credencial. `H21-C7-private-youtube-r2` pasa **180,364 s** de runtime;
el propietario confirma durante el envío la etiqueta nueva **H21 C7 / YT-BB63E4**,
el cuadrado en movimiento y el tono en YouTube. **PASS de recepción observada
por el operador**, sin copia remota decodificada ni medida numérica de A/V remoto.
No se atribuye el primer intento a una causa que no quedó demostrada.

El segundo MKV local también pasa decode, cadencia y continuidad: **6.294 frames**.
Ambas repeticiones conservan el stop independiente, cierre normal y store de
destinos sin cambios. El resultado favorable r2 no reclasifica el r1 corregido.

Evidencia: `var/evidence/H21-C7-private-youtube-r1/`,
`H21-C7-private-youtube-r1-analysis/`, `H21-C7-private-youtube-r2/`,
`H21-C7-private-youtube-r2-analysis/` y sus wrappers. No hubo emisión pública
autorizada ni cambio de la privacidad de YouTube desde Motive.

## Integridad y cierre

`H21-C7-followup-final-artifacts`: PASS de los **1.584 archivos regulares**,
firma profunda estricta y runtime sin cambios; 126 fuentes complementarias
archivadas. `H21-C7-followup-final-cleanup`: **15 checks PASS**. Seis stores
idénticos al baseline, micrófono al escalar original, resolución exacta y Stage
Manager restaurados, grabaciones nuevas privadas, sin socket, procesos propios,
lock retenido ni aserciones de reposo pendientes.

Se conserva el fallo del primer extractor PCM: FFmpeg rechazó `.5`; el análisis
r2 usa `0.5` y no modifica medios ni umbrales. El primer coordinador de análisis
en espera se canceló antes de empezar para investigar la corrección de YouTube;
su aserción se cerró. El análisis horario devuelve exit 1 por el FAIL de calidad
del micrófono aunque ambos medios pasen, sin convertir ese resultado en PASS.

[Índice del seguimiento con hashes](evidence/h21/followup-results.json).
