# H21 — candidata local y primer ensayo personal

**C8.2 todavía no es PERSONAL STREAM READY.** Consulta el
[informe de la candidata C8](h21-c8-verification.md) para sus escenarios exactos,
hashes y limitaciones. Conserva el respaldo renovado por retorno explícito y
la identidad ID/PID de ventanas; añade historia escalar de estados SCK y corrige
el origen de las trazas del verificador. C8.1 también corrige una falsa pérdida
de audio de aplicación al desaparecer su entrada del catálogo de macOS. C8.2
aplica la misma identidad OS a video Application y al rearmado explícito del respaldo.
La sincronía física horaria y una
conversación remota real siguen sin certificar. La sesión de macOS debe estar
desbloqueada y la pantalla disponible; Motive no cambia esa política.
Las [tres horas C7](h21-personal-streaming.md) permanecen como evidencia histórica,
sin trasladar automáticamente sus PASS o FAIL a esta candidata.

El ensayo privado supervisado validado en C8.2 usa Application en la pantalla
integrada estable, SuperTuxKart 1.5 en ventana con su audio, overlays, Cut/Fade,
VideoToolbox y MKV + RTMP local durante una hora completamente decodificada.
No incluye micrófono/cámara ni conversación remota. La recepción externa requiere
el flujo y comprobación propios descritos abajo. Window tiene un piloto C8.2;
la hora Window corresponde al binario C8.1 anterior.

Las horas C7/C8 se ensayan con una aserción externa de reposo autorizada. Para
repetir esa condición durante una prueba local, puedes ejecutar
`caffeinate -d -i -t 3900` en Terminal: dura como máximo 65 minutos y termina
sin cambiar preferencias permanentes. No desactiva un bloqueo manual. Motive
C8 no incorpora esa aserción automáticamente.

## Abrir y preparar

1. Cierra normalmente cualquier Motive anterior y espera a que termine el ensayo
   que tenga el lock canónico. Abre
   `motive-h21-c8/target/h21/Motive-H21-C8-2.app`. No abras dos owners portables.
2. Mantén la escena inicial con patrón a canvas completo como respaldo. En
   **Escenas y transiciones**, elige **Usar actual como respaldo**. Crea después tu escena
   principal; el respaldo debe seguir sin cámara ni captura, incluso ocultas.
3. Con salidas detenidas, selecciona **1080p60** para gaming o **1080p30** para
   podcast/charlas en **Preferencias y diagnóstico**. En los perfiles de salida,
   usa VideoToolbox y frame reordering desactivado. Comprueba en diagnósticos que
   el encoder efectivo es hardware; la selección automática puede hacer fallback.
4. En **Añadir fuente**, elige la ventana o aplicación exacta. Application incluye
   las ventanas de esa app en el display elegido. Display incluye toda la pantalla:
   úsalo solo cuando hayas confirmado que todo lo visible puede grabarse.
5. En Audio, añade cada micrófono/app de forma explícita, prueba gain y mute y
   observa entrada y master. La captura visual no añade automáticamente audio.
   No combines audio desktop con una app ya capturada: se rechaza el solapamiento.
   Espera a que todos los canales reciban muestras y desaparezca `AUDIO_NOT_READY`
   antes de iniciar; añadir un canal no significa que ya esté listo.
   Una ventana recién creada puede aparecer antes que su aplicación en el
   selector de audio. Deja que termine de iniciar y actualiza el selector;
   no sustituyas una app ausente por audio de todo el escritorio.
   El audio de una app también queda vinculado a la pantalla principal al
   iniciar la captura. Mantén esa pantalla conectada durante la sesión:
   desconectarla o cambiar la principal puede dejar el canal en error aunque
   el juego y su video sigan abiertos. En ese caso detén las salidas y reconecta
   explícitamente el canal; no se selecciona otra pantalla automáticamente.
   Si se cierra o reinicia la app seleccionada, su canal no sigue al nuevo
   proceso automáticamente. Detén las salidas y pulsa **Reconectar**. Haz lo
   mismo si Motive informa que no pudo verificar su identidad.
   Si aparece `AUDIO_INPUT_CLIPPING`, revisa el nivel físico de entrada y la
   distancia al micrófono: el aviso mide antes del fader de Motive. Bajar ese
   fader no recupera una señal que ya llegó saturada. El ruido ambiente y una
   saturación puntual son observaciones distintas; el aviso no identifica por
   sí solo el origen del sonido ni detiene automáticamente las salidas.
   La resolución de salida no garantiza la misma resolución de cada fuente:
   la cámara integrada se observó a 1280×720 en C6 y C7 y se escala al lienzo 1080p.
   Comprueba sus dimensiones efectivas en diagnósticos al preparar otra sesión.
6. Guarda **proyecto** y **mixer** por separado. Restaurarlos es explícito y no
   inicia outputs. Haz primero una grabación corta y comprueba movimiento real
   y audio en el archivo, además del preview.

Para perder una fuente durante un ensayo, usa solo una fixture propia o el
contenido/dispositivo aprobado. Si SCK queda suspendido, muestra la ventana y
comprueba movimiento. Si no recupera, mantén el respaldo, detén ambos destinos,
espera `native_busy=false` y reconecta/reselecciona explícitamente. No hay
reconstrucción SCK segura en vivo certificada ni fallback automático a escritorio.
Si la fuente existente vuelve a entregar superficies recientes, selecciona
explícitamente su escena desde el respaldo. C6 renueva entonces una oportunidad
de respaldo para otra suspensión; no reinicia la captura por sí sola.
El retorno debe hacerse con superficies completas recientes al ejecutar la
selección. Una observación previa durante una animación no lo garantiza.
C8.2 observa dos respaldos y retornos en fullscreen de una ventana propia de
10 Hz, con medios completos. Esto no valida fullscreen de cualquier juego;
el escenario 3D se ensaya en ventana sobre la pantalla integrada estable.

`idle` o una ventana fuera de su Space no prueban pérdida ni movimiento nuevo.
Al volver al Space, comprueba que la imagen avance. Si hubo respaldo, el retorno
es explícito. Un contador de renders o un destino activo no prueba frescura de
la imagen. No intentes reconstruir la fuente durante una emisión.

SuperTuxKart 1.5 cerró su modo demo al arrancar sin jugador local inicializado.
La carrera directa y el perfil de prueba inicializado evitaron ese recorrido.
El aviso del tutorial tampoco sirve como carga de juego: entra realmente en
la carrera antes del ensayo. C8 usa su copia y perfil privados; no modifica una
instalación personal ni presenta este resultado como validación de cualquier juego.

## Ensayo de MKV + RTMP local

La emisión de aceptación se queda en `127.0.0.1`; no requiere credenciales.
Antes de **Transmitir**, abre el receptor loopback y selecciona su puerto desde
la configuración local de Motive. Un ejemplo, dentro de este worktree y con el
puerto 19351 libre:

```sh
mkdir -p var/evidence/first-stream-local
target/h21/Motive-H21-C8-2.app/Contents/MacOS/ffmpeg \
  -nostdin -v error -listen 1 -i rtmp://127.0.0.1:19351/live/motive \
  -map 0:v:0 -map 0:a:0 -c copy var/evidence/first-stream-local/received.mkv
```

Usa un directorio nuevo por sesión; no sobreescribas evidencia. El comando queda
escuchando hasta que Motive conecte. Con ambas salidas detenidas, en **Receptor
de transmisión** elige **RTMP**, escribe **19351** en **Puerto local** y pulsa
**Configurar receptor local**. Inicia **Grabar** y **Transmitir** y observa ambos
estados activos. Al terminar, detén
streaming primero y verifica que grabación continúa; luego detén grabación y
espera la finalización de ambos. Cierra Motive normalmente.

El MKV portable está en `~/Movies/Motive`; el recibido en el directorio anterior.
Reproduce y decodifica ambos archivos. Un archivo reproducible y cero drops no
acreditan por sí solos entrega completa. La traza está antes del plugin: OBS
puede descartar paquetes posteriores al corte normal. Distingue esa frontera,
una pérdida anterior, un receptor desconectado y metadata incompleta; consulta
la [auditoría C8](h21-c8-root-cause.md#paquetes-terminales).

## Preparar un destino externo

C7 repitió el destino privado existente: el segundo intento de **180,364 s**
pasa runtime, stop independiente y MKV, y el propietario confirmó en YouTube
la etiqueta única, movimiento y tono durante el envío. Es recepción observada
por el usuario, sin copia remota decodificada ni medida numérica de A/V remoto.
El primer intento conserva su confirmación retirada y recepción sin verificar.
Consulta el [seguimiento C7](h21-c7-followup.md).
Esa recepción no certifica un envío nuevo desde C8; requiere su propia comprobación.
El flujo nativo es:

1. Abre **Salidas → Configurar destinos RTMPS**. Introduce el host, puerto y
   aplicación que indique tu proveedor; el host va sin `rtmps://` ni clave.
2. Usa **Guardar y revisar destino** y **Asociar clave…**. Introduce la clave
   únicamente en el asistente seguro de macOS, que la guarda en Keychain.
3. Tras asociarla, usa **Revisar y aprobar**, **Seleccionar** y **Comprobar**.
   La comprobación valida la configuración y el acceso a la clave; no prueba
   conexión ni entrega al proveedor.
4. Pulsa **Transmitir**, revisa destino y perfil y confirma ese inicio local.
   Comprueba también el video y audio recibidos en el panel del proveedor.

En YouTube, abre **YouTube Studio → Crear → Emitir en directo** y verifica la
visibilidad privada y la sala correspondiente al destino configurado. Para un
directo programado, YouTube indica esperar a que aparezca la vista previa y
después pulsar **Emitir en directo**. La imagen identificada, su movimiento y
el sonido deben comprobarse en esa vista previa o en el reproductor remoto;
ver `RTMPS` activo en Motive no sustituye esa comprobación. Si Studio no muestra
señal, conserva el mensaje de estado y revisa la correspondencia entre sala y
configuración antes de repetir. No compartas la clave en el chat.
[Flujo oficial de YouTube para codificadores](https://support.google.com/youtube/answer/2907883?hl=es).

No pongas claves en comandos, overlays, logs o MCP. Esta guía no inicia una
emisión externa. El [contrato de destinos](h14-destination-contract.md) describe
los límites del formato y la confirmación por cada intento.

## Tres sesiones históricas C7 y protocolo de aceptación

| Sesión | Configuración | Resultado local y límite |
|---|---|---|
| Gaming | 1920×1080, 60 FPS, Display explícito, juego + mic, overlays, MKV + RTMP | C7 r2 completa 3600,815 s; medios y A/V PASS, cola final PARTIAL. Carga 2D ligera, textura interna 800×450 |
| Podcast | 1920×1080, 30 FPS, cámara + mic + app de invitado, MKV + RTMP | C7 r2 completa 3600,980 s; medios/referencia A/V PASS. Cámara 720p, guest generado, deriva física sin medir |
| Charlas | 1920×1080, 30 FPS, Window/Application, cambios de escenas, MKV + RTMP | C7 completa 3600,939 s; medios/referencia A/V PASS. Window/Application/Display propios; navegador BLOCKED y cola RTMP INCONCLUSIVE |

Las tres sesiones anteriores completaron **60 minutos efectivos** con supervisión
externa automática y participación física puntual, una reserva del lock por
sesión y candidata/hashes registrados. Para repetirlas, conserva el protocolo
siguiente y una referencia física visible/audible al principio y al final.

| Momento | Acción y evidencia |
|---|---|
| Antes | Hashes, PID/owner, proyecto/mixer, perfil efectivo, permisos normales, targets exactos, receptor y espacio disponible |
| Min 0–5 | Ambos outputs activos, referencia audiovisual medible y primer tramo decodificable |
| Min 5–25 | Uso real, Cut/Fade, overlays, gain/mute; registrar acciones y drops por destino |
| Min 25–35 | Segunda referencia A/V; foco, resize o cambio de escena correspondiente al escenario |
| Min 35–55 | Continuidad bajo carga real; pérdida controlada solo si se acordó y respaldo preparado |
| Min 55–60 | Tercera referencia A/V, finalización independiente de destinos, shutdown y cierre de procesos propios |
| Después | Decode completo de MKV y receptor, continuidad interior, contabilización terminal, reapertura/restauración sin auto-start |

Registrar CPU (% de un núcleo), RSS y physical footprint separadamente; GPU
solo si existe una medición observada. Conservar series, frames, drops, errores,
decodes y trazas, incluyendo fallos. Medir audio−video al principio/medio/final
con referencias verificables; el tono continuo no sirve para medir A/V.

Gate inicial H20: `|audio−video| ≤80 ms` y deriva `≤40 ms/h`. Una prueba corta
con siete pulsos no acredita una hora ni esos tres escenarios. Una referencia
ausente, sesión interrumpida o dispositivo no probado queda PARTIAL/BLOCKED;
no se infiere un PASS. No revocar permisos, cambiar resolución física, Spaces,
Stage Manager, energía o rutas globales como parte de un ensayo sin acordarlo.
