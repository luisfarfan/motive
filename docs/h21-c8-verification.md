# H21/C8 — Stream Reliability & Root-Cause Validation

Fecha: 2026-11-20, America/Lima. **Verificación local C8.2 cerrada: hora Application completa y decodificada; C8.1 conserva su hora Window y C8 sus dos intentos largos fallidos.**
**PERSONAL STREAM READY: BLOCKED. PUBLIC BETA READY: fuera de alcance.**
**PRIVATE STREAM TRIAL READY: READY_SCOPED_SUPERVISED**, sólo para el escenario
Application descrito abajo, con receptor local; no certifica recepción externa.
Los límites físicos no se eliminan para aprobar la candidata.

Candidata actual **Motive 21.8.2**, release ARM64, OBS 33.0.1, identidad Apple
Development existente. Rama `codex/h21-c8-stream-reliability`, worktree
`/Users/luisfarfan/Developer/products/motive-h21-c8`. Base obtenida por fetch,
igual a main/origin/main al comenzar:
`1a7560d5b905e833433d22070a6cf83f8e982fcd`.

Bundle actual: `target/h21/Motive-H21-C8-2.app`. SHA-256 del ejecutable:
`8d5c0b751a4fd7d26edda93edc154516eed31de4381628f116918052f252ae79`.
Build y snapshot de fuentes en `var/evidence/H21-C8-2-build/`.

La candidata anterior **Motive 21.8.1 C8.1** queda sellada en
`target/h21/Motive-H21-C8-1.app`, con SHA-256:
`4ccc17a2f3fe0b7c0bbd52c4afbdffbdb846a26a466166c8627c60233a81be74`.
Build y snapshot de fuentes en `var/evidence/H21-C8-1-build/`.

La candidata anterior **Motive 21.8 C8** permanece en
`target/h21/Motive-H21-C8.app`, con SHA-256:
`90d3220df83ae75400642b132e6dfdd7e44cac6d8fbc19655390fffd5ce4acf2`.
Build, snapshot de fuentes, manifiesto de archivos y enlaces en
`var/evidence/H21-C8-build/`. Cada resultado distingue estos ejecutables; ni los PASS de
C7/C8 ni sus FAIL se trasladan automáticamente. No hay merge, push, publicación,
emisión externa nueva o integración de H22/CEF.

## Cambios justificados

1. **Observabilidad SCK:** conserva hora de última muestra por estado y cambios
   de estado que pueden ocurrir entre consultas. Sólo metadata escalar, con
   snapshot explícitamente no atómico. No reconstruye streams ni cambia salud,
   encoders, interleaver, reloj o buffering de 128 ms.
2. **Bug confirmado del verificador:** `active` RTMP podía preceder al primer
   paquete. Se recoge por destino un origen A/V completo, secuencial desde 1,
   sin pérdida/overwrite y con plazo acotado. Charlas C8 confirma el resultado
   en archivos reales; no se cambia el motor para compensar metadata ausente.
3. **Semántica terminal:** añade una interpretación explícita de OBS junto al
   clasificador histórico. Descarte posterior a todo el bracket no se trata
   como pérdida indebida anterior; receptor interrumpido e incertidumbre se
   conservan separados.
4. **Instrumentos físicos y carga 3D:** toma física sin tono ni cortes, variante
   de presentación sin dispositivos físicos y juego nativo aislado con ventana
   exacta, perfil privado, red denegada y supervisor externo. Estos instrumentos
   no sustituyen los escenarios de aceptación que no pudieron ejecutarse.
5. **Identidad del audio C8.1:** una ausencia de catálogo no demuestra que el
   proceso admitido murió. Fija y comprueba PID, UID, nacimiento y ejecutable;
   conserva rechazo de reemplazos, ambigüedad y fallos terminales. La prueba
   prolongada C8 que lo demuestra queda FAIL. No reconstruye SCK.
6. **Identidad de video Application C8.2:** elimina la misma premisa de catálogo
   localizada en `visual_health`; fija identidad OS al admitir y la observa
   también fuera de Program. Rearmar al retornar necesita identidad coincidente actual.
   El fallo largo anterior era de audio con video Window, no una reproducción
   física de este defecto potencial en video Application.
7. **Verificador de salidas:** espera muestras reales del tono antes de empezar.
   La matriz deja de devolver éxito incondicional cuando un caso interno falla.
   La primera grabación C8.2 conserva FAIL; se repite sólo ese caso con la espera
   corregida y se conservan los otros ocho del mismo binario.
8. **Restauración del ensayo vertical:** el verificador H13 guardaba su proyecto
   generado y no restauraba el archivo anterior. Ahora conserva y restaura bytes
   y permisos, verifica que su última escritura siga intacta y rechaza cambios
   de otro escritor. La repetición real sobre C8.2 comprueba esa restauración.

La [investigación causal](h21-c8-root-cause.md) fija upstream, Apple, CAP-01,
suspensión C7, audio y paquetes. La
[calibración física](h21-c8-physical-calibration.md) define intervalos de
incertidumbre antes de otra medición; no declara un bug de sincronía.

| Clasificación | Conclusión |
|---|---|
| Bug confirmado y corregido | El verificador podía guardar un origen RTMP vacío después de `active`. El nuevo origen exige audio/video y secuencia desde 1 |
| Bug confirmado de Motive, corrección C8.1 | A los 43 minutos, catálogo de aplicación vacío provocó pérdida de audio pese a proceso vivo y muestras frescas; identidad OS independiente, con admisión estricta |
| Extensión justificada C8.2 | Video Application compartía la premisa falsa del catálogo; identidad OS y comprobación actual antes de rearmar, sin reconstruir SCK |
| Bugs del verificador C8.2 | Arranque antes de muestras del tono, agregado que ignoraba FAIL interno y proyecto vertical sin restaurar; corregidos con espera por estado, propagación de fallo y restauración condicionada |
| Observabilidad añadida | Timestamps por estado SCK y contador de cambios. No se presenta como corrección causal del congelamiento |
| Semántica normal observada | Cutoff de paquetes posteriores a stop; `idle` y contenido estático separados de fallo confirmado |
| Configuración/entorno | Startup demo del juego sin perfil inicializado; una pantalla desaparece durante el primer intento largo. Se conservan los fallos y sus límites de atribución |
| Incertidumbre de medida | Contactos físicos sin correspondencia acústica inequívoca; no hay offset ni deriva física aceptados |
| PASS físico acotado | Dos tomas cámara/mic de un minuto sin clipping observado y un recorrido Spaces real; cada uno conserva su alcance |
| Riesgos pendientes | CAP-01 no reproducido pero no resuelto, lifetime SCK incluyendo audio, fluidez bajo carga, escenarios personales y recepción externa C8 |

## Matriz de la candidata anterior C8 (21.8)

| Área | Estado observado | Evidencia y alcance |
|---|---|---|
| Build y tests | PASS | 134 núcleo, 136 Show Control, 189 Python; Clippy estricto, fmt, release y contrato nativo de diagnóstico SCK |
| Apertura normal | PASS | LaunchServices abre el binario exacto; permisos normales observados; shutdown y socket cerrado |
| UI/CLI/MCP, owner | PASS acotado | El proceso GPUI comparte PID/revisión con CLI y MCP. No se reclama un nuevo gesto de edición por UI |
| Proyectos v1–v6 | PASS | Load/save reales, IDs conservados y restauración exacta del proyecto |
| Window/Application | PASS acotado | Recovery, multiventana, foco, resize y minimize/restore; ambos medios decodificados |
| Identidad admitida | PASS | Subir el nivel de ventana no provoca respaldo falso; cerrarla sí. Mismos outputs y recursos |
| Fullscreen y rearmado | PASS acotado en r2 | Dos respaldos confirmados y retornos explícitos, sin reconstrucción; primer intento conserva FAIL por observar sólo uno |
| Spaces | PASS del recorrido | Ida/vuelta real confirmada por operador y observada en fixture. Fuera del Space, `idle`/estático-no observado; avance decodificado al volver |
| CAP-01 | No reproducido; causa interna pendiente | A → Motive → A corroborado por PID independiente y píxeles. No acredita que el fallo histórico de 15 s esté resuelto |
| Stage Manager/resolución | No repetido en C8 | Evidencia acotada C7 permanece; no se hereda como PASS nuevo ni se cambian ajustes globales |
| Reconstrucción SCK live | BLOCKED | No está probada la barrera de callbacks/referencias. La prohibición del path de video no debe confundirse con una garantía global del mixer histórico; ver lifecycle |
| Audio de app | PASS funcional acotado | Siete etapas H13: piloto, RTMP, recuperación, silencio, transiciones, persistencia y referencia A/V. Ese PASS no prueba lifetime de reconexión SCK |
| Micrófono físico | PASS breve / PARTIAL de aceptación | Dos tomas de 60 s sin clipping observado de entrada/mix, con scalar temporal restaurado. No prueba una hora sin clipping |
| Cámara/micrófono A/V físico | PARTIAL | Segunda toma tiene contactos visibles sin correspondencia acústica inequívoca; deriva horaria no medida |
| Podcast remoto real | BLOCKED | No hubo interlocutor remoto disponible; invitado generado no lo sustituye |
| Charlas 1080p30 | PASS de regresión controlada | 60,261 s, Window/Application/Display propios, cambios de escena/mix y cierre de ventana con respaldo. Sin micrófono ni navegador |
| Perfil vertical | PASS acotado | 1080×1920/30, overlays, transformaciones, Cut/Fade y archivo decodificado; no una charla física completa |
| Navegador visible capturable | BLOCKED | La capacidad autorizada disponible es headless. No se conecta a Dia ni a navegadores personales; no se incorpora CEF |
| VideoToolbox/x264 y outputs | PASS funcional | Nueve casos: destinos independientes, cancelación, shutdown y pérdida deliberada del receptor |
| Tail en parada normal | PASS de semántica observada | En la matriz no faltan paquetes antes/dentro del bracket; un dispatch posterior por salida es compatible con cutoff OBS |
| Pérdida de receptor | PASS funcional / PARTIAL entrega | La grabación sobrevive y RTMP termina con error esperado; no se certifica entrega limpia |
| Charlas RTMP, origen | PASS instrumental y de tail | A/V inicial presente desde secuencia 1; ya no es INCONCLUSIVE por origen vacío |
| Juego 3D nativo | Pilotos PASS; dos intentos largos FAIL | Interrumpidos a 1106,020 s y 2586,611 s por causas diferentes. Ninguno equivale a una hora completa |

## Regresión de C8.1 (21.8.1)

La corrección de identidad pasa 28 comprobaciones nativas, incluido hijo real
con cambio de ejecutable y cierre; 136 tests del núcleo, 136 de Show Control,
Clippy estricto y fmt. La aplicación firmada pasa cierre/reinicio real del
emisor, permanencia del canal fallido sin seguimiento automático, reconexión
explícita idle y grabación decodificada de tonos independientes.

Fullscreen conserva dos intentos fallidos. En el primero, el verificador se
guiaba por el style bit antes del final de la animación y solicitó retorno
cuando SCK había pasado de `complete` a `idle`; el respaldo no se rearmó.
La versión corregida espera el callback AppKit de finalización. En r2 se
observan entrada/salida completas, retorno explícito y respaldo rearmado,
pero sólo un respaldo: el requisito de **dos** respaldos no quedó cubierto.
El contador `suspended` pasa de 5 a 6 al entrar y de 6 a 7 al salir. En la
entrada la captura ya había vuelto a `complete` sin respaldo; la salida sí
activa uno. El historial de callbacks no equivale a un fallo todavía presente
cuando evalúa la política de control.
No se rebaja ese criterio ni se cambia el motor para provocar otra suspensión.
Los dos FAIL y sus medios se conservan; no se hereda el PASS C8 r2.

| Área C8.1 | Resultado | Alcance |
|---|---|---|
| Build y checks | PASS | Release firmado separado; 136 núcleo, 136 Show Control, 191 Python; Clippy/fmt y contratos nativos |
| Audio, identidad OS | PASS acotado | 28 comprobaciones nativas; cierre/reinicio real sin auto-follow y reconexión idle con grabación decodificada |
| Window/Application | PASS acotado | Recovery, foco, resize/minimize y medios completos; mismos recursos admitidos |
| Identidad de ventana | PASS | Cambio de nivel conserva fuente; cierre real provoca respaldo |
| Proyecto v1–v6 y owner | PASS acotado | CLI/MCP usan PID/revisión del mismo proceso GPUI; no nuevo gesto UI |
| Audio de aplicación | PASS funcional | Seis etapas H13, incluida referencia A/V; recovery live no se repite ni se certifica |
| Salidas VT/x264 | PASS funcional | Nueve casos con medios y cutoff normal; receptor interrumpido sigue PARTIAL de entrega |
| Vertical | PASS acotado | 1080×1920/30, composición/overlays/transiciones y archivo decodificado |
| Apertura normal | PASS | LaunchServices, binario exacto, permisos observados, cierre normal |
| Fullscreen | FAIL de cobertura retenido | R2 registra dos transitorios SCK, completa entrada/salida y rearma; sólo un respaldo de los dos exigidos |
| Gaming 1080p60 | Piloto y hora PASS acotado | Hora de 3.601,141 s con Window y audio del juego; 216.363/216.314 frames decodificados. Sin micrófono ni referencia A/V física |
| Charlas Window/Application/Display | No repetido sobre C8.1 | La fixture requiere dos pantallas controladas; sólo está disponible la integrada tras el cambio observado |
| Físico/Spaces/Stage Manager | No repetido sobre C8.1 | No se transforma una prueba de otro hash en certificación nueva |

La hora C8.1 completa ambos medios, con separación máxima de 17 ms entre
paquetes de video y 22 ms de audio. No aparecen congelamientos fuera de los
11 intervalos planificados de escena segura, segundos silenciosos bajo −80 dBFS,
clipping, drops de destino, frames tardíos del compositor ni skips de encoding.
Los 1.321 descartes de preview se informan por separado. Los picos PCM decodificados
son 0,22412/0,22352. Las 3.291 consultas verifican la identidad OS del audio;
el contador de ausencias del catálogo queda en cero. Por tanto, esta hora no
reproduce naturalmente la desaparición de catálogo que motivó la corrección.

| Recurso de la hora C8.1 | Mediana | Máximo |
|---|---:|---:|
| CPU Motive, 100%=un núcleo | 26,48% | 38,72% |
| RSS Motive | 161,22 MiB | 254,50 MiB |
| Footprint Motive | 428,70 MiB | 429,38 MiB |
| CPU juego, lectura `ps` | 99,3% | 107,4% |
| RSS juego | 278,59 MiB | 875,41 MiB |
| GPU global | 73% | 75% |

La ventana mide 3456×2168 y se ajusta al canvas 1920×1080; el juego guarda
contenido de 3456×2112. Las imágenes inspeccionadas del principio, medio y final
muestran avance hasta la vuelta 63, únicamente juego y overlay propio.
La cadencia de archivo no demuestra 60 imágenes únicas por segundo. MKV SHA-256
`7ea52cad54a94fbe69194c42e1fae374bb17cd1bfbf2a3d0b33ee7202fbcbc57`;
RTMP recibido `2ff2456047ece89bd6a52037a18a3de0c1c424dbd21dd9706d72011d0f028b12`.
El clasificador histórico del tail queda PARTIAL y su interpretación OBS PASS:
no se convierte un descarte posterior al bracket de parada en pérdida previa.
Owner, juego y receptor cierran con código 0. El sello C8.1 comprueba 1.584
archivos, tres enlaces internos, firma profunda y fuentes del build sin cambios.

Las tomas físicas y Spaces pertenecen a C8: no se repiten sobre C8.1 mientras
el operador está ausente ni se presentan como PASS físico de este nuevo hash.

## Regresión de C8.2 (21.8.2)

| Área C8.2 | Resultado | Alcance |
|---|---|---|
| Build y checks | PASS | Release firmado; 137 núcleo, 136 Show Control, 199 Python finales; Clippy/fmt y contratos nativos de identidad y SCK |
| Identidad OS de audio | PASS acotado | Cierre/reinicio real, canal fallido conserva identidad anterior y reconexión explícita idle; tonos grabados y decodificados |
| Identidad OS de Application video | PASS de regresión | Lifecycle conserva 124 observaciones `matches`; el cierre real produce 25 `changed`, 24 fuera de Program, sin ocultarlo por estar inactiva |
| Window/Application | PASS acotado | Recovery, foco, resize, minimize/restore y ambos medios completos |
| Fullscreen Window propio | PASS acotado | Dos respaldos y dos retornos explícitos, callbacks reales AppKit; mismas fuentes, mixer y outputs; medios decodificados |
| Identidad de ventana | PASS | Cambio de nivel conserva el ID/PID admitido; cierre real activa respaldo |
| Proyectos v1–v6 y owner | PASS acotado | CLI/MCP y proceso GPUI comparten PID/revisión; no se reclama un gesto nuevo de edición por UI |
| Audio de aplicación | PASS funcional | Seis etapas H13, incluida referencia A/V generada; no certifica sincronía física ni reconexión SCK live |
| Salidas VT/x264 | PASS funcional con repetición explícita | Ocho casos originales y repetición del primer caso, sobre el mismo binario; nueve casos resueltos, fallo original retenido |
| Tail normal y receptor perdido | PASS semántico / PARTIAL esperado | Paradas normales compatibles con OBS; sólo el RTMP deliberadamente interrumpido queda parcial |
| Vertical | PASS acotado | 1080×1920/30, overlays, composición, Cut/Fade y medio decodificado; repetición final comprueba restauración exacta del proyecto guardado |
| Foco A → Motive → A | PASS del recorrido | PID independiente y píxeles; CAP-01 no reproducido, no declarado resuelto |
| Apertura normal | PASS | LaunchServices abre el binario exacto, observa permisos y cierra normalmente sin abrir dispositivos físicos |
| Gaming Window | Piloto PASS | 60,282 s, 3.912/3.868 frames MKV/RTMP completos |
| Gaming Application | Piloto y hora PASS | Piloto 60,929 s; hora 3600,503 s, 216.323/216.280 frames completos; identidad OS de audio y video coincidente en 3.311 observaciones de la hora |
| Charlas completa con varios displays | No repetida | La fixture requiere dos pantallas controladas; sólo está disponible la integrada |
| Físico, Spaces manual, Stage Manager/resolución | No repetido | Los resultados C8/C7 conservan sus hashes; no se transfieren a C8.2 |

Los pilotos no registran congelamientos no explicados, clipping, drops de destino,
lag del compositor ni skips de encoding. Preview conserva 21/25 descartes.
Los contadores de ausencia de catálogo quedan en cero: no se induce una expulsión
real del catálogo. El encuadre Application inspeccionado muestra únicamente la
carrera y el overlay propios, con negro alrededor, no el escritorio.

El primer caso VT recording de la matriz pidió iniciar mientras el tono seguía
`warming` con cero frames. El rechazo `AUDIO_NOT_READY` fue correcto. El
verificador ahora espera muestras observadas, sin retardo fijo; la repetición
parte de `ready` con 480 frames. El agregado de la matriz ya no devuelve éxito
incondicional. Los 193 tests Python iniciales se amplían a 196 con los tres
contraejemplos de clasificación. `H21-C8-2-output-matrix-resolved/report.json`
liga ocho casos conservados y esa única repetición; el primer informe sigue FAIL.

La sesión Application C8.2 completa **3600,503 s** con 11 excursiones planificadas
Cut/Fade al respaldo y retorno; ninguna activación inesperada del respaldo.
MKV y RTMP recibido se decodifican completamente: **216.323/216.280 frames** y
173.058.048/173.025.280 muestras PCM, respectivamente. Máximos intervalos de
paquetes: 17 ms video y 22 ms audio. No hay candidatos de congelamiento bajo el
criterio documentado de 0,5 s y diferencia luma 0,003 a 160×90; tampoco segundos
de audio por debajo de −80 dBFS. Los picos PCM son 0,217889/0,216193.
Cero clipping pre-fader/mix, drops de destino, lag del compositor y skips de
encoding observados; 1.396 descartes de preview se contabilizan por separado.

Las 3.311 consultas registran identidad OS coincidente para video y audio;
ambos contadores de ausencias del catálogo permanecen en cero. Los contadores
nativos avanzan 216.646 superficies, con cero errores, muestras inválidas,
regresiones PTS o estados suspendidos y cuatro estados idle. No son una medida
de imágenes únicas ni una observación continua entre consultas. Esta hora
no reproduce naturalmente el fallo de catálogo anterior.

| Recurso de la hora C8.2 | Mediana | Máximo |
|---|---:|---:|
| CPU Motive, 100%=un núcleo | 25,30% | 28,26% |
| RSS Motive | 236,48 MiB | 256,19 MiB |
| Footprint Motive | 430,27 MiB | 430,83 MiB |
| CPU juego, lectura `ps` | 105,4% | 111,3% |
| RSS juego | 591,50 MiB | 879,89 MiB |
| GPU global | 76% | 77% |

El footprint aumenta 13,11 MiB entre primera y última observación, con la
asignación inicial de Fade; estos datos no prueban ausencia de fugas. GPU abarca
todas las aplicaciones. La única topología observada es la pantalla integrada;
Application entrega 3456×2234 al canvas 1920×1080. El juego en ventana guarda
contenido 3456×2112 y `max_texture_size=512`, sin acreditar gráficos al máximo.
Las imágenes decodificadas de inicio, medio y final muestran las vueltas 1, 32
y 63, únicamente juego, overlay propio y márgenes negros.

MKV SHA-256 `feb58f934d81a68e049ac0a2a586629513dd56d337c153afee615cdcaeef0943`;
RTMP recibido `1e21a6bb8981ae2cb925ec797f619d29b9907aa4e45e8231542f0940e0931efb`.
El análisis completo es PASS; tail histórico PARTIAL e interpretación OBS PASS.
Owner, juego y receptor cierran con código 0, sin errores de limpieza.
No se abre micrófono/cámara ni se calibra A/V con el sonido del juego.

## Juego real y fallos conservados

Se descargó el archivo firmado oficial de
[SuperTuxKart 1.5](https://github.com/supertuxkart/stk-code/releases/tag/1.5).
SHA-256 del ZIP:
`c266acdb8a63a3fe30f52652d9b749f5beba4abeb9e54382fbb934b00c53b303`.
Ejecutable:
`504a9b38a43236fd3c5e0a832bae99ea88ffc66290ec85ebba60f4c192f4c841`.
Firma profunda y notarización verificadas. No se instala globalmente ni se
modifica el binario. OpenGL 4.1 sobre Apple M5 Pro, Lighthouse, 20 karts, luces
dinámicas, sombras 2048, SSAO, bloom y texturas HD solicitados por CLI.

El proceso usa `SUPERTUXKART_SAVEDIR` y un directorio temporal propios. El sandbox
por proceso deniega red y escritura fuera del perfil, y lectura del perfil
personal del juego. No se cambia `HOME`, TCC, preferencias ni sandbox globales.
El directorio global de SuperTuxKart no se creó. El juego y Motive tienen límites
de tiempo/RSS independientes, cierre observado y lock canónico compartido.

Dos smokes sin Motive terminaron con SIGSEGV en
`DemoWorld::updateIdleTimeAndStartDemo` al comenzar sin jugador local. La carrera
directa inicializa ese jugador y permaneció viva 35 s; el perfil así preparado
evita el camino inicial observado. Esto es evidencia acotada de startup del
juego, no un crash atribuido a Motive ni una corrección de su código.

Se conservan también: admisión de audio demasiado temprana en el primer piloto,
aviso de tutorial detectado visualmente en r2 y timeout de carga de pista en r3.
El código oficial del
[menú](https://github.com/supertuxkart/stk-code/blob/1.5/src/states_screens/main_menu_screen.cpp)
vincula ese aviso a `use-frequency=0`; el perfil privado lo inicializa. El runner
espera por separado el selector de audio y la carga de pista. No se contabilizan
menús ni segundos de un proceso abierto como juego validado. R4 muestra y
decodifica una carrera real; el juego cierra normalmente con código 0.

Piloto r4: 60,099 s de sesión; 3.918 frames MKV y 3.861 RTMP decodificados
(incluyen inicio y salida a escena segura). Audio propio presente, picos PCM
0,2135/0,2152, sin segundos bajo −80 dBFS, sin candidatos de congelamiento bajo
el criterio documentado del analizador. Cero drops de destino, cero frames
retrasados/omitidos del compositor; 14 descartes de preview separados.

| Recurso del piloto | Mediana | Máximo |
|---|---:|---:|
| CPU Motive, 100%=un núcleo | 20,99% | 23,73% |
| RSS Motive | 240,25 MiB | 244,78 MiB |
| Footprint Motive | 358,24 MiB | 375,06 MiB |
| CPU juego, lectura `ps` | 83,4% | 85,4% |
| RSS juego | 562,41 MiB | 834,45 MiB |
| GPU global | 42,5% | 47% |

La captura de ventana efectiva mide 1920×1050 y se ajusta al canvas 1920×1080;
la configuración guardada por el juego informa contenido de 1920×1022. Conserva
luces dinámicas, SSAO, bloom y sombras 2048 activados, pero `max_texture_size=512`:
no es una prueba de gráficos al máximo. No se afirma detalle nativo 1080 de todo
el contenido ni 60 imágenes únicas/s.
GPU incluye todas las aplicaciones. Esta carga 3D concreta no equivale a todos
los juegos exigentes. No se abre micrófono durante el ensayo autónomo; su prueba
breve es separada. El sonido del juego no es una referencia A/V calibrada.

## Medición física y aceptación de producto

La toma sin tonos de 60 s produce 1.840/1.816 frames completamente decodificados,
cadencia máxima 34 ms video/22 ms audio. Las 238 observaciones no contienen
issues ni bloques de clipping pre-fader/mix. No se emparejan picos de voz/mesa
posteriores con los contactos visibles anteriores. El resultado físico sigue
PARTIAL, sin imputar un offset grande inexistente.

El scalar 0,2 se usa sólo durante las tomas autorizadas y se restaura a
0,3764705955982208. Los videos físicos permanecen privados con acceso del dueño.
El análisis de contactos no se publica. La cámara y el micrófono se cerraron
antes de continuar autónomamente.

**PRIVATE STREAM TRIAL READY: READY_SCOPED_SUPERVISED** corresponde a Application
seleccionada explícitamente en la pantalla integrada estable, carrera SuperTuxKart
1.5 en ventana y audio de esa app, overlays propios, Cut/Fade y salida dual
hardware con receptor local. Hay que detener salidas antes de recuperar un canal.
Window tiene piloto C8.2 y hora C8.1 separados; no se suman como una hora Window
de C8.2. Este alcance no incluye micrófono/cámara, fullscreen del juego, invitado
remoto, navegador ni reconstrucción SCK live.
**PERSONAL STREAM READY** requiere todavía sincronía
física calibrada, ausencia de clipping durante la sesión de uso, conversación
remota real y las condiciones concretas de captura que vaya a usar el dueño.
No depende de borrar todos los FAIL históricos. **PUBLIC BETA READY** requiere
otros gates y está fuera de C8. La recepción privada YouTube C7 no certifica un
envío C8; esta ronda usa receptores locales y no publica contenido.

La [guía actualizada](h21-first-stream.md) explica selección explícita de fuente
y audio, respaldo, retorno, parada independiente y flujo seguro de destino.
El [índice curado C8](evidence/h21/c8-results.json) vincula candidata, informes,
medios y límites sin incluir contenido privado. Los tres bundles conservan
1.584 archivos regulares y tres enlaces internos cada uno, con firma profunda
estricta válida. Las fuentes runtime C8.2 siguen iguales al build; el archivo
suplementario final distingue las correcciones posteriores de verificadores.

La primera comprobación de limpieza conserva FAIL: el verificador histórico
H13 vertical había dejado su proyecto generado. Sus bytes coinciden con los
backups de C8.1/C8.2 y su JSON con el estado registrado en el ensayo propio.
Se conserva ese archivo desplazado y se restaura la copia inicial por hash y
modo. La corrección del verificador pasa tres pruebas (restauración exacta,
rechazo de otra escritura y archivo ausente/symlink) y otra ejecución real
1080×1920/30: `h13-video-1795168609683591000`, con `project_restored=true`.
El total final es 199 tests Python; no se recompila ni cambia el binario por
estas correcciones del instrumento. La segunda comprobación conserva ambos
stores originales, nivel de micrófono restaurado, owners cerrados, socket
ausente, 75 informes de owners con salida 0, 27 aserciones temporales cerradas
y lock liberado. Los 140 medios existentes vinculados por los informes quedan
con acceso 0600; evidencia y wrappers privados, 0700. No se afirma haber
restaurado una pantalla desconectada por un actor no observado.

## Intentos que no aprobaron

Además de los crashes y pilotos del juego descritos arriba, se conservan sin
reescribir el primer fullscreen (sólo un respaldo de los dos exigidos), la
invocación inicial de identidad sin el argumento `--mode` y el primer ensayo de
presentación sin micrófono, que intentó mutear un ID ausente. Este último error
pertenecía a la nueva variante del verificador; se condicionó esa operación a
la existencia del canal y se repitió como r2. No fue un crash del motor.
Los agregados `baseline`, `extra` y `extra-rest` mantienen sus estados FAIL
debidos a esos intentos; `baseline-rest`, `extra-last` y los informes r2 conservan
por separado sus nuevos resultados. Los supervisores cerraron sus owners,
incluso cuando la suite no aprobó.

## Reproducción local

Los comandos completos de cada intento están en su informe de supervisor.
Los artefactos privados de esta Mac conservan la copia oficial del juego, el
perfil offline inicializado, los wrappers autorizados y los analizadores por
hash. Usar nombres de evidencia nuevos y el lock canónico; nunca adjuntarse a
una producción del dueño ni reconstruir la captura para evitar un FAIL.

Para repetir el escenario 3D con esos artefactos, desde este worktree y con la
autorización temporal vigente, sin cámara ni micrófono:

```sh
trial="H21-C8-2-repeat-$(date +%Y%m%dT%H%M%S)"
python3 scripts/with_physical_lock.py --owner h21-repeat \
  --purpose 'Ensayo 3D local explícito' --timeout 3870 -- \
  python3 var/run/h21_with_awake.py "var/evidence/$trial-awake" \
  python3 scripts/h21_run_owned_session.py \
  --app target/h21/Motive-H21-C8-2.app --output "var/evidence/$trial-owner" \
  --timeout 3780 python3 scripts/verify_h21_native_game.py \
  --app target/h21/Motive-H21-C8-2.app --output "var/evidence/$trial" \
  --seconds 3600 --game-app .deps/stk-1.5/SuperTuxKart.app \
  --seed-players var/evidence/H21-C8-stk-race-smoke/profile/config-0.10/players.xml \
  --authorized-controlled-game --capture-mode application
```

Después del cierre, ejecutar `scripts/analyze_h21_native_game.py` con `--app`,
`--report` y un `--output` nuevo bajo otro lease para CPU. Para un intento
interrumpido, `--inspect-failed-session` decodifica lo retenido y mantiene el
resultado global FAIL. El análisis de tail usa `scripts/analyze_h21_session_tail.py`
con el reporte y el directorio de probes; no convierte metadata ausente en
entrega completa. La [guía de uso](h21-first-stream.md) describe el recorrido
manual y los límites de captura/audio de aplicación.
