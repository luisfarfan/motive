# H13 — checklist práctico de aceptación GPUI

Estado: **PENDIENTE DE EJECUCIÓN**. Este documento se obtuvo leyendo el código de
UI actual y la evidencia H12; no acredita clicks, accesibilidad, medios ni cierre.
Root completará tiempos, IDs y enlaces de evidencia del bundle final.

| Registro | Valor observado |
|---|---|
| Commit / árbol / SHA-256 del ejecutable firmado | Pendiente |
| Owner del lock canónico / PID inicial | Pendiente |
| Ventana / tema / dimensiones de UI | Pendiente |
| UID y nombre visible de cámara integrada preparada | Pendiente |
| UID y nombre visible de micrófono autorizado | Pendiente |
| Bundle ID / PID único de Motive Audio Fixture | Pendiente |
| Directorio del observador / capturas nativas | Pendiente |
| Puerto loopback / PID de cada receptor propio | Pendiente |
| IDs escena A/B, ventana, webcam, micrófono y aplicación | Pendiente |
| IDs lower third / countdown / alerta | Pendiente |
| `(pid, target, attempt_id)` → archivo MKV/segmento RTMP | Pendiente |

## Límites del recorrido y observación

Todas las mutaciones de Motive se hacen mediante GPUI. CLI/MCP pueden consultar
`status`, `outputs`, `audio_mixer`, `output_profiles` y `overlay_state`; no crear
la composición, corregir valores, arrancar/parar salidas ni restaurar por terminal.
El observador pasivo `scripts/observe_h13_native.py` es apto para este recorrido;
`--allow-shutdown` contempla el cierre final. Los helpers externos pueden abrir
la fixture de audio y los receptores loopback propios, reproducir un WAV propio
para el micrófono o interrumpir el receptor bajo prueba. Ningún helper genera el
reloj multimedia de Motive ni decide que una operación UI terminó.

El observador muestrea a 2 Hz: dejar al menos un segundo entre operaciones
discretas y conservar screenshots cuando haga falta. Un cierre rápido puede
ocurrir entre muestras; un error del colector al perder el PID no prueba por sí
solo un fallo de cierre. Corroborar PID, barreras y finalización de los archivos.
No usar `verify_h13_outputs.py` ni suites que envíen mutaciones durante esta toma.

Usar el lock canónico ya adquirido, bundle fijo, sesión visible y contenido
controlado. La cámara integrada debe estar preparada; la ventana capturada será
**Motive — Fuente controlada**, no el estudio ni el escritorio. Los permisos se
comprueban en su estado real. Si algo no está disponible, conservar el fallo;
no simular autorización ni cambiar ajustes globales para completar una casilla.

Los textos siguientes son labels/tooltips que existen en el código. **No son
selectores AX comprobados**. Los nombres de dispositivos se toman del inventario
actual. Registrar el árbol/estado nativo al ejecutar antes de automatizar clicks.

## Mapa de navegación real

| Acceso | Texto o tooltip existente |
|---|---|
| Menú del proyecto, cabecera | **Mi producción** |
| Engranaje, cabecera | Tooltip **Preferencias y diagnóstico** |
| Sliders, cabecera | Tooltip **Perfiles de salida** |
| Sliders junto a Escenas | Tooltip **Escenas y transiciones** |
| Sliders junto a Audio | Tooltip **Configurar mixer de audio** |
| Barra de Capas | **Añadir fuente**, **Biblioteca** |
| Tres puntos de una capa | Tooltip **Acciones de capa** |
| Ojo de una capa | Tooltip **Ocultar capa** / **Mostrar capa** |
| Salidas, cabecera | **Grabar**, **Transmitir**, **Salidas** |
| Menú macOS Motive | **Salir de Motive**, atajo ⌘Q |

Los formularios generales están ligados a revisión: si aparece **El estado
cambió. Reabre para actualizar los formularios.**, cerrar y reabrir el panel antes
de editar. En overlays usar **Recargar inspector** cuando se indique. Un click
rechazado no cuenta como operación realizada. H12 conservó una toma con Cut
porque el Fade intentado no quedó aplicado: verificar el estado después del click.

## 1. Preparar 1080p30, dos escenas y una captura de cada dispositivo

Partir del estudio controlado en reposo, con la escena inicial y mixer vacío.
Ninguna salida, transición o animación puede estar pendiente.

1. Abrir **Preferencias y diagnóstico**. En **Video de producción**, pulsar
   **1080p** y después **30 FPS** si no estaba seleccionado. Observar
   **Composición y salida: 1920 × 1080 · 30 FPS** y `video.available=true`.
   Mantener **16:9** en el estudio. El espacio de edición continúa en 960×540.
   Comando: `ConfigureVideo`; no editar campos de resolución dentro de perfiles.
2. **Mi producción** → **Nombre de escena** = `H13 A ventana` →
   **Renombrar actual**. Así se reutiliza la escena inicial; no se crea una tercera.
   Comando: `RenameScene`.
3. **Mi producción** → **Abrir ventana controlada**. Mantener abierta
   **Motive — Fuente controlada** y devolver el foco a **Motive — Estudio local**.
   Comando: `SetTestWindow { open: true }`.
4. **Añadir fuente** → **Ventana** → **Motive — Fuente controlada**.
   Observar la capa **Captura de ventana** y movimiento/contador real en el preview.
   Comando: `AddSource(Window)`. Registrar el ID; no añadir de nuevo esta captura.
5. **Añadir fuente** → **Webcam** → el nombre visible del UID integrado preparado.
   Observar la capa **Cámara** y el objeto controlado. Comando: `AddSource(Camera)`.
   Registrar su ID; no seleccionar otra cámara por posición en la lista.
6. Seleccionar cada fila de **Capas** y configurar sus campos inline. Textos
   visibles **X**, **Y**, **An**, **Al**; `aria_label` definidos: **Posición X**,
   **Posición Y**, **Ancho**, **Alto**. Confirmar **cada campo con Enter**: Blur
   descarta el gesto numérico, no lo confirma. Valores de escena A:
   ventana `(0,0,960,540)`; webcam `(640,32,288,162)`. Si hace falta, en
   **Acciones de capa** usar **Subir capa** para dejar la webcam encima.
   Comando: `SetTransform`. Ocultar el overlay clásico inicial si tapa la toma.
7. Completar los widgets de la sección 2 en A antes de crear B.
8. **Mi producción** → **Nombre de escena** = `H13 B cámara` → **Crear escena**.
   Comando: `CreateScene`; verificar que B sea ahora la escena activa.
9. En B, **Añadir fuente** → **Reutilizar una fuente existente**: elegir la cámara
   ya creada y la ventana ya creada, por sus nombres/IDs registrados. Comando:
   `AddLayer`, no `AddSource`. Cámara `(0,0,960,540)` y ventana `(640,32,288,162)`.
10. Reutilizar también los tres widgets ya creados, por **Biblioteca** → **Fuentes**
    → fila correspondiente → **Añadir capa en esta escena**, o desde la lista de
    fuentes existentes. Ajustar sus layouts a los de A. Los IDs de fuente deben
    ser iguales entre escenas; solo cambian los items/capas y sus transforms.
11. Seleccionar A en la lista **Escenas**. Confirmar ambos layouts y conservar
    una captura de cada uno. El contador debe avanzar dentro del preview, no
    solamente en la ventana de origen. Una captura congelada es un fallo real.

## 2. Lower third, countdown y alerta H11

Hacer esta preparación con salidas detenidas. Al terminar una creación, pulsar
**Volver a la biblioteca** si el panel aún muestra su inspector.

| Orden | Ruta y valores controlados | Resultado que debe verse |
|---|---|---|
| 1 | **Biblioteca** → **Presets** → **Professional Lower Third** | Crea la fuente `Message`, de tipo **Lower third**, y abre su inspector. Comando `InstantiateOverlayPreset`. |
| 2 | **Contenido**: **Título** = `H13 A`; **Subtítulo** = `Producción controlada`; **Aplicar propiedades** | `UpdateOverlay`; conservar el ID. El textarea de título tiene `aria_label` **Texto del overlay** y el subtítulo **Subtítulo del widget**. |
| 3 | **En vivo** → **Mostrar** | `OverlayEvent(Show)`; visible realmente. El preset empieza oculto. Layout esperado `(32,368,640,140)`. |
| 4 | **Volver a la biblioteca** → **Crear** → **Cuenta regresiva** | Borrador de nueva fuente. **Nombre de fuente** = `H13 countdown`; **Título** = `Tiempo H13`; **Duración · milisegundos** = `30000`; **Ancho del contenido** = `280`; **Alto del contenido** = `130`; **Crear overlay**. |
| 5 | Capa `H13 countdown`: campos inline `(32,32,280,130)` | `SetTransform`; mantenerla preparada para iniciar durante grabación. No confundir ancho del contenido con ancho de capa. |
| 6 | **Biblioteca** → **Crear** → **Alerta local** | **Nombre de fuente** = `H13 alerta`; **Título** = `ALERTA H13`; **Duración · milisegundos** = `4000`; contenido `280×110`; **Crear overlay**. |
| 7 | Capa `H13 alerta`: campos inline `(340,32,280,110)` | Dejarla preparada; el evento durante la toma será **En vivo** → **Lanzar alerta**. |

Para volver a editar un widget: sus **Acciones de capa**, o **Biblioteca** →
**Fuentes** → **Editar fuente**. El ojo controla la capa de esa escena; los eventos
de **En vivo** afectan la fuente compartida en ambas escenas.

## 3. Micrófono + aplicación: mixer global

El helper existente **Motive Audio Fixture** (`local.motive.audiofixture`) debe
estar abierto en una única instancia. Su tono predeterminado es 997 Hz a −24 dBFS
peak. Un WAV propio reproducido por otro helper puede estimular físicamente el
micrófono con 440 Hz; no cambiar el dispositivo ni el volumen global. Registrar
ambos estímulos y cualquier captación acústica del tono de aplicación por el mic.

1. Abrir **Configurar mixer de audio** → **Añadir <nombre del micrófono>**,
   correspondiendo al UID confirmado. `AddAudioInput(Microphone)`.
2. En **Audio de aplicaciones y escritorio**, pulsar **Consultar aplicaciones y
   pantallas** o **Actualizar aplicaciones y pantallas**, según el estado visible.
   En **Aplicaciones**, **Añadir Motive Audio Fixture**.
   `AddAudioInput(SystemApplication)`; no elegir escritorio, que duplicaría el
   ámbito de la aplicación. Guardar el bundle ID y PID observado por separado.
3. En los canales de **Audio**, llevar el micrófono a **0 dB** y la aplicación a
   `−6.0 dB` mediante su fader. Para ajuste exacto: enfocar el fader y usar flechas
   (1 dB por paso); su label es **Ganancia <nombre de entrada>**. El arrastre se
   confirma al soltar. Comando: `SetAudioGain`.
4. En el panel de Audio verificar ambas entradas **Recibiendo audio**/`phase=ready`, P/R independientes y master
   con margen. Los medidores de entrada son **post-fader / pre-mute**; master es
   **post-mute**. Silenciar una entrada conserva su medidor; no es una avería.
5. **Guardar mixer** (`SaveAudioMixer`). No añadir un tono libobs extra a esta toma
   mínima. Cada entrada se conserva al hacer Cut/Fade; monitoreo permanece off.

Si el nombre mostrado o la identidad no coincide, detener esta preparación.
**Revisar permiso de micrófono** y **Revisar permiso de pantalla y audio** son
controles reales, pero su presencia no acredita permiso ni paquetes recibidos.

## 4. Perfiles distintos y receptor loopback

Preparar ambos perfiles y el endpoint antes de iniciar cualquier salida.

1. Abrir **Perfiles de salida**. Crear `h13-ui-rec`: **ID del perfil (a-z, 0-9, -, _)**,
   **VideoToolbox**, **Bitrate CBR (250–20000 kb/s)** = `6000`,
   **Keyframes (1–10 segundos)** = `1`, **Reordenamiento: desactivado**.
   Pulsar **Crear / actualizar perfil**. Si el ID ya existe, usar otro ID único
   o revisar el reemplazo concreto antes de **Confirmar**.
2. En su fila pulsar **Grabación**; debe cambiar a **✓ Grabación**.
3. Crear `h13-ui-rtmp` con VideoToolbox, `4000` kb/s, keyframe `1`, reordering off.
   En su fila **RTMP** → **✓ RTMP**. Pulsar **Guardar perfiles**.
   Comandos: `UpsertOutputProfile`, `SelectOutputProfile`, `SaveOutputProfiles`.
4. El helper externo abre un receptor FFmpeg propio, puerto libre >1023,
   escucha exclusivamente `127.0.0.1`, destino `/live/motive`, y escribe un
   archivo nuevo para cada conexión. No sondear TCP conectándose al listener,
   pues puede consumir su única aceptación; comprobar listener/PID.
5. **Salidas** → bajar a **Receptor de transmisión** → **RTMP** →
   **Puerto local (1024–65535)** = puerto real → **Configurar receptor local**.
   Observar **Configurado: rtmp · puerto …**. `ConfigureStream`.
6. En cada tarjeta, **Comprobar** (`PreflightOutput`). El mensaje de éxito solo
   valida configuración; todavía no prueba red ni medios. Observar perfil
   seleccionado correcto en **Grabación MKV** y **Transmisión RTMP local**.
7. **Mi producción** → **Guardar proyecto**. Comprobar proyecto v5 con video 1080p30;
   los perfiles se guardan en su store v1 y el mixer de aplicación en su store v2.

## 5. Toma mínima real con ambas salidas

Registrar segundos monotónicos/revisiones por paso. Mantener cada intervalo
estable al menos 8 s, salvo la transición/alerta; no silenciar las dos entradas
a la vez. El observador debe conservar acciones **UI · …** y los mismos IDs.

| Paso | Acción exclusivamente UI | Observación y medio pendiente |
|---|---|---|
| T1 | Cabecera **Grabar** | `StartOutput(recording)`; tarjeta **Activa**, path y attempt ID. Mantener 8 s antes de RTMP. |
| T2 | Cabecera **Transmitir** | `StartOutput(streaming)`; **Conectando** puede preceder **Activa**. Cabecera **Grabando + RTMP**. Confirmar perfiles efectivos 6000/4000, no solo seleccionados. |
| T3 | Esperar 8 s con mic + aplicación activos | Ambas señales audibles y niveles coherentes; no clipping nativo. Duraciones independientes aumentan desde `active_duration_ms`. |
| T4 | Canal aplicación: fader de −6 a −18 dB; esperar 8 s; volver a −6 | `SetAudioGain`; delta solicitado −12 dB verificable en PCM, mic continúa. |
| T5 | Mic: **Silenciar**, esperar 8 s; **Activar** | `SetAudioMute`; aplicación sola en mezcla, medidor mic pre-mute puede seguir moviéndose. |
| T6 | Aplicación: **Silenciar**, esperar 8 s; **Activar** | Mic solo; no corte del encoder. No contar silencio acústico de la fixture como defecto de transporte. |
| T7 | **Escenas y transiciones** → **Cut**; cerrar panel; click B; esperar; click A | `ConfigureTransition(Cut)`, `SelectScene`; confirmar configuración/escena realmente aplicada y cambios decodificados. |
| T8 | Reabrir **Escenas y transiciones**; **Duración de Fade (100–5000 ms)** = `1500`; **Aplicar Fade**; comprobar configuración; cerrar; B y después A | Ver `transition_configuration={kind:fade,duration_ms:1500}`, fases y terminal. Pixels intermedios en ambos medios; audio continuo. No animar widgets a la vez. |
| T9 | Lower third: **Acciones de capa** → **Contenido**, recargar si corresponde; título `H13 B`; **Aplicar propiedades** | `UpdateOverlay`; texto cambia en ambos medios sin nueva instancia de fuente/captura. |
| T10 | Countdown: **En vivo** → **Iniciar / continuar**; esperar ≥5 s; **Pausar**; esperar; **Iniciar / continuar** | `TimerStart/TimerStop`; `Restante` proviene del núcleo. Glyphs decodificados cambian y se congelan durante pausa. |
| T11 | Alerta: **En vivo** → **Lanzar alerta** | `Trigger`; aparición y desaparición real conforme a duración. Registrar el intervalo. |
| T12 | **Salidas** → tarjeta RTMP → **Detener** | Diálogo **Confirmar operación**: primero **Cancelar** y verificar que ambas continúan. Repetir **Detener** → **Confirmar**; RTMP pasa por Finalizando a Detenida, MKV sigue ≥8 s. |
| T13 | Helper abre otro receptor en el mismo puerto; UI **Transmitir** | Nuevo intento RTMP/archivo. Recording conserva attempt ID, perfil e instancias. Ambos activos ≥8 s. |
| T14 | **Salidas** → tarjeta MKV → **Detener** → **Confirmar** | RTMP continúa ≥8 s; MKV termina y conserva duración/path del intento. |
| T15 | UI **Grabar**; esperar ambos activos; **Salidas** → **Detener todas las salidas** → **Confirmar** | `CancelAllOutputs`; ambos terminales y `native_busy=false`. El estudio permanece abierto. Decodificar todos los segmentos y ambos MKV. |

Los botones de cabecera cambian a **REC hh:mm:ss** y **RTMP hh:mm:ss** mientras
están activos; pulsarlos también pide detener ese destino. Para evitar confundir
el destino durante QA, usar los botones **Detener** dentro de su tarjeta.

Cancelación H9 adicional: aplicar Fade de `5000` ms, seleccionar la otra escena,
reabrir **Escenas y transiciones** y pulsar **Cancelar transición** mientras esté
preparing/running. Registrar el `operation_id`, estado terminal y escena segura;
no aceptar la cancelación por la desaparición del botón solamente. Restaurar el
Fade de `1500` ms antes de continuar la toma y mantener ambas entradas de audio.

## 6. Error, recuperación y cancelación de conexión

Hacer una toma aparte para conservar el fallo y no mezclarlo con la finalización
limpia de T1–T15. Reutilizar composición/perfiles y modificar Motive solo por UI.

1. Iniciar receptor propio, **Grabar**, **Transmitir**. Dejar ambos activos ≥8 s.
2. El helper termina exclusivamente su receptor. Observar el error RTMP retenido,
   por ejemplo `OUTPUT_DISCONNECTED`, mientras recording continúa. Si quedan
   workers, UI muestra **Finalizando** y recovery aún no está disponible.
3. Con `streaming.native_busy=false`, pulsar **Recuperar RTMP** en cabecera o
   **Recuperar** en la tarjeta RTMP. `RecoverOutputTarget(streaming)` reconoce
   el fallo; no inicia automáticamente. Recording mantiene su intento.
4. Abrir nuevo receptor externo en el mismo puerto; UI **Transmitir**. Ambos
   vuelven a activos. Detener RTMP por su tarjeta y conservar recording para el
   caso siguiente. Registrar audio decodificado del MKV alrededor de la pérdida,
   recovery y nuevo arranque.
5. Helper independiente acepta TCP loopback pero no completa handshake RTMP.
   UI **Transmitir** → **Conectando**; tarjeta RTMP **Cancelar inicio** →
   **Confirmar**. Se solicita `CancelOutputTarget`; no se presenta detenido
   mientras siga `native_busy` ni se habilita recovery. Observar
   **Cancelación pendiente de conexión** / **RTMP · Finalizando**.
6. Liberar/cerrar el peer silencioso propio. Esperar el terminal real; recuperar
   por UI si quedó error. Recording debe continuar durante todo el intervalo.
7. UI **Detener todas las salidas** → **Confirmar** y esperar barreras.

No importar/ejecutar `verify_h8_lifecycle.py` como helper en este recorrido:
envía comandos al núcleo. Usar solo un listener propio independiente. La
recuperación UI del slot recording ante pérdida de su muxer queda como caso
adicional explícito si root lo ejecuta; el éxito RTMP no cubre ese botón ni disco
lleno/permisos. Conservar esa casilla pendiente aunque el backend ya tenga prueba.

Para recuperar audio de aplicación por UI: con mic activo, cerrar exclusivamente
la fixture; esperar error de esa entrada; reabrir la misma fixture única; Audio
→ fila de aplicación → **Reconectar**. El ID estable permanece; la instancia de
esa captura puede cambiar. Esto es un ensayo separado y no debe atribuirse al
intervalo de IDs invariables de la toma sana.

## 7. Guardar/restaurar y borrador obsoleto

Con ambos destinos detenidos, sin transición/animación:

1. Establecer escena A y configuración final deseada; **Mi producción** →
   **Guardar proyecto**, Audio → **Guardar mixer**, Perfiles → **Guardar perfiles**.
   Guardar snapshots de las tres estructuras por consultas de solo lectura.
2. Cambiar X de una capa por UI; **Mi producción** → **Restaurar proyecto guardado**
   → **Confirmar**. Debe restaurar el documento exacto y video 1080p30, dejando
   mixer/perfiles iguales. No debe iniciar ninguna salida.
3. Silenciar aplicación; Audio → **Restaurar mixer…** → **Confirmar**. Comparar
   store guardado y verificar proyecto/perfiles intactos.
4. Perfiles: **Editar** el perfil propio, cambiar bitrate, **Crear / actualizar
   perfil** → **Confirmar**; luego **Restaurar perfiles…** → **Confirmar**.
   Recuperar definiciones exactas, sin modificar escenas ni mixer.
5. Borrador obsoleto solo por UI: en Contenido del lower third escribir un título
   sin aplicar; pasar a **En vivo** y **Mostrar**; volver a **Contenido**.
   Si esa operación cambió revisión, observar el aviso de núcleo cambiado y
   **Aplicar propiedades** bloqueado. **Recargar inspector** descarta el borrador
   y devuelve el contenido efectivo. Si no cambió revisión, no contar el caso.

Tras cerrar y reabrir el proceso, verificar primero que el arranque no captura ni
emite automáticamente. Abrir **Mi producción** → **Abrir ventana controlada**
antes de restaurar el proyecto que la referencia. Mantener cámara y app fixture
disponibles; restaurar proyecto, mixer y perfiles mediante sus controles.
Comparar IDs persistidos, no instance IDs del PID anterior. Los widgets no deben
inventar continuidad del reloj del proceso cerrado.

La selección de perfiles por destino y el endpoint son runtime: tras reiniciar,
volver a elegir **Grabación**/**RTMP** y **Configurar receptor local** por UI.
`Guardar perfiles` guarda definiciones v1; no prometer que restaure endpoint o
que el proyecto guarde el mixer. La ventana controlada tiene un nuevo window ID
normal; el documento debe resolver su identidad estable al restaurar.

## 8. Quit/cierre y confirmaciones

| Caso | Secuencia exacta | Gate pendiente |
|---|---|---|
| Q1: cancelar salida de app | Ambos activos; ⌘Q o menú **Motive → Salir de Motive**. Diálogo **Finalizar producción y salir** → **Seguir produciendo** | Ninguna salida se detiene; mismo PID/attempt IDs y audio continuo. |
| Q2: confirmar cierre dual | Repetir ⌘Q → **Finalizar y salir** | `RequestShutdown` con origen UI; Motive espera ambas barreras, finaliza medios y después sale. No guarda cambios automáticamente. |
| Q3: botón rojo | En otra apertura, con salidas activas, botón rojo de **Motive — Estudio local** → primero **Seguir produciendo**, después repetir y **Finalizar y salir** | Mismo contrato que ⌘Q; no cierre que omita el owner del núcleo. |
| Q4: cierre con handshake | Recording activo + RTMP con peer silencioso; ⌘Q → **Finalizar y salir** | Mensaje **Cierre pendiente: esperando salidas, conexiones e importaciones. La aplicación permanecerá abierta hasta terminar.** Liberar peer; PID sale después del terminal nativo. |
| Q5: confirmación obsoleta | Si cambia revisión mientras el diálogo está abierto —por ejemplo el receptor propio falla— confirmar | Debe mostrar **La producción cambió; vuelve a solicitar el cierre para revisar el estado actual.** Volver a solicitarlo sobre el estado actual. No usar una mutación MCP para fabricar este caso. |
| Q6: cierre idle | Ambas salidas detenidas y sin transición/animación; ⌘Q | Solicita shutdown directamente; no se espera diálogo. |

Al cerrar por Q2/Q3/Q4, conservar el observador, stdout/stderr y archivos antes de
abrir otra sesión. Un segundo click durante cierre pendiente no debe saltarse la
barrera ni abrir una segunda confirmación. Dock Quit normal es un caso adicional;
Force Quit no acredita finalización controlada y no forma parte de esta prueba.

## 9. Gates de evidencia y casillas para completar

| Gate | Resultado / enlace pendiente |
|---|---|
| UI 1440×980 y 1024×780: ambos controles visibles, tarjetas/scroll/diálogos operables | Pendiente |
| Acciones de producción exclusivamente UI; consultas CLI/MCP corroboran mismo PID/revisión | Pendiente |
| Dos archivos H.264 1920×1080/30 + AAC 48 kHz estéreo, decode completo sin errores | Pendiente |
| Dos señales reales; ganancias, mute/unmute e independientes RMS/peak coherentes | Pendiente |
| Cut/Fade, título editado, countdown/alerta visibles en ambos medios | Pendiente |
| Stop/restart de un destino mantiene audio/frames y attempt ID del superviviente | Pendiente |
| Fallo receptor, recuperación dirigida y cancelación pendiente con barrera real | Pendiente |
| Cero clipping nativo inesperado; peak PCM y gaps interiores/finales reportados por separado | Pendiente |
| Fuentes/capturas compartidas, IDs/instance IDs estables en toma sana; sin captura duplicada | Pendiente |
| Restauración de proyecto v5/mixer v2/perfiles v1 sin arranques implícitos | Pendiente |
| Quit/cancelar/confirmar/cierre pendiente observados y archivos finales decodificados | Pendiente |

La validación de medios debe usar IDs/etapas reales de esta toma. No pasar los
archivos 1080p/dos salidas al analizador H12 como si fueran su fixture original
960×540/salidas separadas. Se puede reutilizar FFprobe/FFmpeg y sus gates, con
geometría, canales y frecuencias reales explícitas. Comparar eventos en el
intervalo común de ambos intentos, sin tratar sus segundos cero como simultáneos.
Muestreo de UI, frames/FPS y duración de slot no son sincronización A/V exacta a
una muestra. Registrar gaps, margen y limitaciones, incluidos los fallos.

Fuentes leídas: `src/ui/studio/{chrome,panels,configuration,devices,sources,audio,outputs,forms,lifecycle}.rs`,
`src/ui/studio/creative/{library,inspector,runtime,draft}.rs`, `src/ui/editor/mod.rs`,
`src/overlays/presets.rs`, `scripts/fixtures/h13_audio_app.m`,
[contrato H13 de salidas](h13-output-contract.md),
[contrato H12](h12-creative-studio-contract.md) y
[verificación H12](h12-creative-studio-verification.md).
