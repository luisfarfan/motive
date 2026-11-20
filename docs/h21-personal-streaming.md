# H21 — Personal Streaming Core: informe final local

Esta página conserva el cierre **C7**. La ronda actual es
[H21/C8 — fiabilidad y validación causal](h21-c8-verification.md), con su propio
binario, matriz y evidencia. Sus resultados no reescriben los históricos de abajo.

**PERSONAL STREAM READY: BLOCKED.** Verificación cerrada el 2026-11-19,
America/Lima, con **3/3 sesiones de una hora completadas en C7**. Los seis medios
pasan decode completo, cadencia y referencia A/V. La aceptación personal sigue
abierta por sincronía física horaria, condiciones de captura y entrega terminal.
Los FAIL previos permanecen; completar una repetición no los borra.

El [seguimiento supervisado posterior](h21-c7-followup.md) añade Podcast r3 de
una hora y una recepción privada de YouTube confirmada durante el envío. Las
palmadas iniciales/intermedias/finales existen; la deriva física queda PARTIAL
por incertidumbre de medida. R3 conserva un bloque de clipping de entrada y
Spaces sigue sin cambio observado. [Índice del seguimiento](evidence/h21/followup-results.json).

Candidata: **[Motive C7, versión 21.7](h21-c7-verification.md)**, release ARM64
portable firmado con la identidad Apple Development existente. Bundle local:
`target/h21/Motive-H21-C7.app`. SHA-256 del ejecutable:
`7b6a07a96e666e9eac581f303acbce7c03e5d027b032a88233138f26f4903216`.
[Guía para el primer ensayo y destino externo](h21-first-stream.md).
[Índice curado con hashes y referencias](evidence/h21/results.json).

Base obtenida por `git fetch origin`: `25aca10dfeaa22345a7c4d9d232613ffb496bf1a`,
igual a main/origin/main al iniciar. Rama `codex/h21-personal-streaming`, worktree
`/Users/luisfarfan/Developer/products/motive-h21`. Trabajo local sin merge,
rebase, push, release ni publicación. H22 y `web-host-lab/` no se integran.

## Cambios comprobados

C4 repitió la integración H19/H20 y descubrió un fallo de firma/permisos al abrir
normalmente. C5 usa la identidad de desarrollo existente y verifica los permisos
por el flujo normal de macOS. No se reinició TCC ni se relajaron políticas.

C6 permite una nueva oportunidad de respaldo después de un retorno explícito
desde la escena segura a una captura existente y saludable. Dos suspensiones
reales de fullscreen pasan en C7. No se reinicia una fuente detenida por el usuario
ni se reconstruye SCK durante outputs activos.

C7 verifica la identidad exacta ID/PID de una ventana ya admitida, separándola de
los filtros del selector. El cambio de nivel reproducible en C6 deja de provocar
un falso respaldo; cerrar realmente la ventana sigue activándolo. La causa exacta
del rechazo original del Podcast C6 a los 55 minutos no quedó registrada.
Reloj multimedia, buffering de 128 ms e interleaver conservan sus contratos.

## Matriz de aceptación

PASS significa que pasó el recorrido descrito sobre la candidata indicada;
PARTIAL conserva evidencia favorable con cobertura incompleta; FAIL identifica
un resultado observado; BLOCKED señala un gate que no pudo demostrarse.

| Requisito | Estado | Evidencia y límite |
|---|---|---|
| Integración, build y regresiones | PASS | C7: 134 tests núcleo, 136 Show Control, 169 Python, Clippy/fmt y release. Otros 6 tests del auditor de identidades pasan por separado |
| Identidad del bundle y módulos | PASS | 1.584 archivos regulares idénticos al manifiesto C7; runtime sin cambios; firma profunda estricta válida. Enlaces actuales internos; no había mapa histórico de symlinks |
| Apertura normal y permisos | PASS | C7 pantalla/cámara/micrófono, edición real por UI y shutdown normal; FAIL C4 preservado |
| UI, CLI y MCP, un Production owner | PASS | Renombre real por UI, misma revisión y PID leídos por CLI/MCP |
| Proyectos v1–v6 y restauración | PASS | Pruebas repetidas en C7; seis stores del usuario conservan sus hashes originales |
| Display físico, Window y Application multiventana | PASS acotado | Pilotos C4/C5, lifecycle C7 y horas Gaming/Charlas con medios reales; no implica estabilidad en cualquier escritorio |
| Minimize/restore, resize, pérdida y respaldo | PASS acotado | Lifecycle Window/Application C7 y cierre real de ventana al final de Charlas |
| Fullscreen | PASS acotado | Dos suspensiones y respaldos, con retorno explícito; FAIL C5 conservado |
| Stage Manager / cambio de resolución | PASS acotado | Window con MKV/RTMP; ajustes originales restaurados. Display durante cambio de modo no certificado |
| Spaces | BLOCKED | No se observó un cambio efectivo en los intentos C6 ni en el ensayo C7 supervisado posterior de 180 s; la confirmación llegó tras su cierre |
| CAP-01, congelamiento histórico de foco | PARTIAL | C7 r2 observa A → Motive → A y avance de píxeles; no se reproduce en ese intervalo y no se declara resuelto |
| Reconstrucción SCK live y callbacks tardíos | BLOCKED | Lifetime/stop asíncrono no demostrado; restricción conservada, sin sleeps o reconexiones infinitas |
| Audio de app, recuperación, silencio, gain/mute, mezcla | PASS acotado | Siete etapas H13 repetidas, H10 y horas nuevas. Continuidad del mix/marcador no prueba cada entrada por separado |
| A/V y deriva de referencia de aplicación | PASS | Seis medios: máximo 67 ms, deriva máxima 14,258 ms/h; presupuestos 80 ms y 40 ms/h |
| Sincronía física cámara/micrófono durante una hora | PARTIAL | R3 confirma contactos al inicio/medio/final. Deriva central exploratoria 7,71/9,29 ms/h, pero los intervalos conservadores alcanzan 61,73/63,83 ms/h; no certifica ≤40 ms/h. Un bloque de clipping de entrada permanece FAIL |
| Video 1080p60 Gaming | PASS de formato/cadencia | Juego real ligero instrumentado; textura 800×450 y dibujo mediano 58 FPS. No prueba 60 imágenes únicas/s ni carga de un juego pesado |
| VideoToolbox, x264 y outputs independientes | PASS funcional | Nueve casos cortos C7; tres horas duales con hardware observado y stop independiente |
| Pérdida del receptor | PASS funcional / PARTIAL entrega | Matriz C7 prueba fallo/cierre; contabilidad de la cola del caso de pérdida inconclusa |
| Entrega terminal MKV/RTMP | PARTIAL | Ausencias compatibles con el límite de stop; Charlas RTMP INCONCLUSIVE por traza inicial vacía |
| Cambios Cut/Fade y continuidad | PASS acotado | Once ciclos por hora; cero drops reportados por destinos. Marcadores y timestamps analizados aparte |
| Ausencia de crashes | PASS en las tres horas | Owners y receptores cierran normalmente; no acredita ausencia universal de fallos |
| Recursos bajo carga representada | PARTIAL | Mediciones de tres horas abajo; carga ligera/controlada, sin prueba de ausencia de fugas |
| Gaming / Podcast / Charlas, duración | PASS | 3600,815 / 3600,980 / 3600,939 s. Supervisión externa automática, participación física puntual del usuario |
| Podcast remoto y navegador en Charlas | BLOCKED / cobertura incompleta | Invitado generado propio; no conversación remota de una hora. No hubo navegador nativo propio disponible mediante la herramienta autorizada |
| Inicio, stop, shutdown y limpieza | PASS | Cierres observados, sin procesos propios pendientes, lock propio liberado y ajustes exactos restaurados |
| Emisión externa desde C7 | PASS observado por operador / PARTIAL instrumentación remota | Segundo ensayo privado YouTube de 180,364 s: etiqueta, movimiento y tono confirmados durante el envío; MKV local pasa. Sin copia ni A/V remotos independientes; primer intento sin recepción confirmada |
| Intentos históricos interrumpidos | FAIL conservados | C6 Podcast r1–r4, primer Podcast C7, firma C4, segundo respaldo C5 y geometría H9; detalle en informes por candidata |

## Tres horas y medios decodificados

Cada fila corresponde al mismo C7, sin cambio de runtime. Los máximos A/V son
los mayores valores absolutos medidos en ventanas de 30 s al inicio, medio y
final. La deriva usa el cambio de las medianas inicial/final normalizado por el
intervalo; no se mide continuamente cada fotograma ni la boca del participante.

| Sesión | Duración observada | Frames MKV / RTMP | Máx. A/V MKV / RTMP | Deriva MKV / RTMP |
|---|---:|---:|---:|---:|
| Gaming 1080p60 | 3600,815 s | 216443 / 216348 | 40 / 51 ms | 10,184 / 10,184 ms/h |
| Podcast 1080p30 | 3600,980 s | 108189 / 108163 | 63 / 67 ms | 13,239 / 13,239 ms/h |
| Charlas 1080p30 | 3600,939 s | 108169 / 108150 | 47 / 47 ms | 14,258 / 13,239 ms/h |

Los seis archivos pasan decode completo. Máximo hueco PTS de video: 17 ms en
Gaming, 34 ms en Podcast/Charlas; audio: 22 ms. El marcador de audio 997 Hz no
tiene huecos mayores que 1,2 s (máximo 1,01 s). Cada medio tiene once huecos del
marcador visual durante los cambios de escena. La correspondencia temporal con
los once cambios está revisada en ambos destinos de Gaming/Podcast y en MKV de
Charlas. Para RTMP de Charlas falta el origen de la traza; sus once huecos se
conservan sin inventar una correspondencia con tiempos del supervisor.

Las auditorías de identidad pasan 3005 / 3247 / 3270 observaciones, con máximos
intervalos de 2,297 / 2,068 / 1,889 s. Comprueban identidad muestreada, no lifetime
entre observaciones. Cero drops de output no implica entrega de todos los paquetes.

Gaming usa Arkanoid de `raylib-games`, de Marc Palau y Ramon Santamaria, fijado a
`318688c759eaf391b36b9f893355c038fcf56419`, con licencia conservada y lógica
original incluida sin editar. El driver añade entrada automática, sonido y
marcadores. Su textura 800×450 se escala en Odyssey 3840×1080 y se encaja con
bandas en el canvas 1920×1080. Podcast combina cámara física 1280×720, micrófono
y una app de invitado generada. Charlas alterna Window/Application/Display
propios; al cerrar la ventana final observa respaldo a los 396 ms del comando,
con ambos outputs activos durante otros tres segundos.

## Cámara y palmadas: primera revisión C7 r2

La revisión privada identifica tres contactos iniciales por destino. En MKV,
los brackets visuales son 98,100–98,167; 98,867–98,933; 99,633–99,700 s. Los picos
RMS filtrados asociados son 98,105562; 98,878562; 99,649562 s. Los mismos gestos
se verifican en RTMP con sus propios PTS. La coincidencia acredita que las palmas
quedaron registradas, pero un pico tras dos filtros causales de 3 kHz no equivale
al inicio acústico calibrado. No se transforma ese intervalo exploratorio en PASS.

Las peticiones intermedia/final de esta toma no recibieron confirmación antes
del cierre. La búsqueda acotada revisa 95 s alrededor de la petición intermedia
y desde cinco segundos antes de la final hasta el cierre. Los candidatos fuertes
mantienen fase periódica compatible con el marcador de aplicación; no se
identificó una referencia física independiente tardía. Esto no demuestra que no
exista una palmada más tenue. **La deriva cámara/micrófono queda sin medir.**
No se solicitan más gestos para una toma ya cerrada. Las respuestas de intentos
anteriores no se trasladan a C7 r2.

Después del cierre, el usuario aclaró que había hecho esas palmadas tardías
recién al volver, fuera de la grabación. La nueva toma **C7 r3** sí contiene
referencias en los tres tramos, revisadas por imagen y PCM. Su limitación actual
es la precisión del contacto y del inicio acústico, no la ausencia de gestos;
el [seguimiento](h21-c7-followup.md) conserva los intervalos y el FAIL de clipping.

La hora Podcast r2 no tuvo avisos de clipping; el PCM final alcanza 0,177/0,178.
El ruido ambiente no identifica por sí solo la causa de los avisos anteriores.
El aviso de entrada se observa antes del fader: reducir solo ese fader no repara
una entrada ya saturada. El nivel físico temporal volvió a su valor original.

## Recursos observados

| Sesión | CPU mediana, 100% = un núcleo | RSS mediana | Footprint mediano | Cambio footprint entre extremos | GPU mediana del dispositivo |
|---|---:|---:|---:|---:|---:|
| Gaming | 31,60% | 162,17 MiB | 393,31 MiB | +17,59 MiB | 36% |
| Podcast | 26,48% | 209,28 MiB | 506,91 MiB | +15,05 MiB | 25% |
| Charlas | 16,98% | 229,83 MiB | 354,20 MiB | +16,52 MiB | 14% |

CPU/memoria corresponden al proceso Motive, no al conjunto de juego, fixtures y
receptor. GPU incluye todas las aplicaciones. No se prueba ausencia de fugas ni
rendimiento bajo juegos pesados. El compositor no reporta frames de render lag
ni video skipped en estas horas; los descartes del preview se registran aparte.

## Fallos preservados, artefactos y cierre

El primer Podcast C7 falla a 474,782 s por suspensión SCK durante una animación
de escritorio. Conserva identidad exacta, audio limpio y decode diagnóstico
completo; no cuenta como hora. Una interacción del usuario es hipótesis sin
causa confirmada. C6 r4 falla a 3345,767 s por falsa pérdida de Window con SCK
fresco; sus intentos anteriores incluyen clipping. El primer Gaming C7 queda
bloqueado antes de iniciar por consola bloqueada. No se mezclan esos resultados.

Dos fallos de herramientas finales también permanecen: la revisión auxiliar de
marcadores de Charlas asumía una traza RTMP inicial no vacía; su repetición informa
PARTIAL con ese origen ausente. El primer cotejo final incluía symlinks que el
manifiesto de build excluye; la repetición usa la misma población de archivos,
verifica destinos internos y firma estricta. No se modificó el bundle ni se
repitió decode para ocultar estos fallos.

`H21-final-artifacts-r2` confirma 1.584 archivos regulares sin diferencias,
runtime idéntico y firma válida. Conserva un archivo suplementario de 118 fuentes
de implementación/verificación, además del archivo fuente completo del build.
`H21-final-cleanup` pasa los 14 controles: stores originales por hash, socket y
procesos propios ausentes, lock propio liberado, Odyssey exactamente 3840×1080
@240 Hz modo 111, Stage Manager 0 y micrófono scalar 0,3764705955982208.
Todas las aserciones temporales de `caffeinate` están cerradas.

El seguimiento posterior repite la integridad de 1.584 archivos y amplía el
archivo complementario a 126 fuentes. Su limpieza final pasa 15 checks e incluye
las cuatro tomas nuevas (Podcast r3, Spaces y dos ensayos privados RTMPS), con
sus medios en 0600 y todos los procesos/aserciones cerrados. Los reports del
cierre original anterior se conservan sin sobrescribir.

La evidencia privada permanece en `var/evidence` y los coordinadores en `var/run`,
ambos modo 0700. Los 44 MKV de esta misión identificados por sus reports están
0600; `~/Movies` ya era 0700. No se cambiaron archivos ajenos ni preferencias
permanentes. Los hashes de stores permiten comparar bytes; no había registro
histórico de sus modos. El índice curado no incorpora imágenes de cámara,
inventarios privados ni credenciales.

## Gates que faltan para PERSONAL STREAM READY

1. Reducir/calibrar la incertidumbre de la sincronía física cámara/micrófono
   para certificar ≤40 ms/h. R3 ya contiene referencias inicial/intermedia/final;
   su clipping puntual conserva un gate de calidad separado.
2. Observar realmente Spaces y la captura de un navegador propio permitido;
   cubrir Display durante cambio de resolución si ese uso se pretende aceptar.
3. Demostrar lifetime del stop/callback SCK antes de habilitar reconstrucción en
   vivo; conservar respaldo y reconexión explícita en idle mientras tanto.
4. Completar la contabilidad terminal con trazas iniciales/finales suficientes,
   manteniendo la distinción entre paquetes interiores y posteriores a stop.
5. Ampliar carga al juego y conversación remota reales que se usarán. El destino
   privado de YouTube ya recibió imagen/movimiento/tono observados en el ensayo
   C7 r2 de tres minutos; no acredita una hora remota ni A/V remoto instrumental.
   CAP-01 sigue abierto.

## Autorizaciones y límites de las sesiones

El usuario autorizó la grabación local controlada de Display, permitió elegir
un juego porque no tenía juegos instalados, confirmó cámara y ambiente preparados,
desbloqueó la sesión gráfica y completó Touch ID para el flujo normal de permisos.
También confirmó que hará palmadas visibles/audibles al inicio y final de Podcast
cuando se le avise. No se necesita volver a solicitar esas autorizaciones.

En el seguimiento autorizó usar el destino YouTube existente, afirmando que
estaba privado. La captura aportada muestra esa visibilidad. Los dos intentos
acotados enviaron únicamente patrón/texto/tono generados; no se emitieron sus
grabaciones de cámara/micrófono, no se extrajo la clave ni se cambió su destino.

El 19 de noviembre autorizó también «ambos ensayos y restaurar»: activar
temporalmente Stage Manager y cambiar Odyssey de 3840×1080 a 3200×900, devolviendo
ambos ajustes al estado previo. La lectura inicial observa Stage Manager `0` y
3840×1080 a 240 Hz (modo 111). El ensayo mantiene captura de una ventana propia;
no usa esa autorización para grabar contenido personal durante la reorganización.

El usuario autorizó después bajar temporalmente la entrada física del micrófono
integrado de 38% (scalar exacto 0,3764705956) a 20% y restaurarla, tras el clipping
observado durante las palmadas. El valor original se conserva por ensayo.

Tras el bloqueo de consola, autorizó explícitamente `caffeinate`. Cada nuevo
ensayo puede mantener únicamente las aserciones de pantalla y reposo por
inactividad (`-d -i`), con límite de 3900 s y ligadas al proceso supervisor.
Se cierran al acabar; no se cambian preferencias permanentes ni se desactiva
el bloqueo manual. Gaming C7 r2 observa ambas aserciones en `pmset` antes de
continuar su hora. El primer lanzamiento bloqueado se conserva aparte.
La misma autorización cubre una aserción acotada durante la espera por el lock;
solo mantiene la consola disponible. Se cierra al observar que la etapa
siguiente tiene su propia aserción, sin adelantar captura, builds o decode al
turno de H22. Cada proceso conserva el límite de 65 minutos y su cierre queda
registrado. Las preferencias permanentes no se modifican.

El supervisor admite únicamente un proceso nuevo propio. Ante bloqueo de consola,
RSS mayor que 1536 MiB o timeout, pide abortar la suite y ofrece 30 s para cierre
normal. Si el proceso de prueba no responde, lo termina como último recurso antes
de que venza la cobertura propia de Display: se conserva FAIL y el lock si quedan
descendientes. No selecciona ni termina un owner ajeno y no cambia energía/TCC.
La prueba unitaria de esa terminación usa procesos Python propios, no prueba
captura ni sustituye la evidencia nativa.


El MCP de navegador autorizado es `proxima-browser`, descrito por su skill local
como Chrome headless con sesión de la suite PROXIMA. Ese perfil/servicio ajeno
no se usa como fixture de Motive. No hay aquí un recorrido documentado que
proporcione una ventana nativa propia y visible bajo el supervisor del proyecto.
Por eso la parte navegador de Charlas queda BLOCKED; Window/Application/Display
propios sí pueden ensayarse. No se conecta a Dia/CDP ni se abre un perfil personal
como sustitución. Un navegador headless renderizado no certificaría captura SCK
de una ventana de navegador visible.
