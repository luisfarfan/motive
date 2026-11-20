# H21 — lifetime de captura y límites de recuperación

La [revisión C8](h21-c8-root-cause.md#obs-original-y-master) compara OBS 33.0.1
con master fijado el 2026-11-20 y conserva este bloqueo de reconstrucción live.
La nueva historia de estados es observabilidad; no constituye una barrera de
callbacks ni cambia la política de recuperación descrita aquí.

Revisión: 2026-11-19, America/Lima. **Reconstrucción SCK en vivo: BLOCKED**.
No se cambiaron el módulo de captura, su cola, el reloj ni buffering de audio
para convertir una hipótesis en un PASS. La candidata C4 conserva el runtime
integrado H19/H20 de `25aca10`.

## Evidencia de código y documentación

Se inspeccionaron las fuentes originales OBS 33.0.1 y los parches Motive.
El archivo fijado
[`mac-sck-video-capture.m`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-video-capture.m)
solicita stop asíncrono en `destroy_screen_stream`; después libera configuración,
texturas/superficies, stream y evento. La destrucción de la fuente libera el
delegate, destruye el mutex y libera `screen_capture`. El completion de stop
registra errores, pero no actúa como barrera de esa destrucción.

El delegate mantiene un puntero a `screen_capture` y lo usa tanto al recibir
samples como en `didStopWithError`. Revisar ese orden revela una obligación de
lifetime pendiente; **no demuestra que C4 haya sufrido UAF**, ni que Apple haya
entregado un callback después de liberar el objeto en una ejecución observada.

Apple documenta un completion que devuelve el error de parada en
[`stopCapture`](https://developer.apple.com/documentation/screencapturekit/scstream/stopcapture(completionhandler:)).
[`removeStreamOutput`](https://developer.apple.com/documentation/screencapturekit/scstream/removestreamoutput(_:type:))
retira un receptor. Las páginas consultadas no establecen una barrera explícita
para todos los callbacks que ya están ejecutándose o encolados. La consulta de
Context7 solo aportó descripciones generales; no se infirió una garantía adicional.
Se consultaron también las fuentes y headers locales del SDK.

`obs_wait_for_destroy_queue` espera trabajo de OBS; no certifica el completion
de SCStream. Tampoco lo certifican un sleep, una caída de RSS, el exit de un
test de geometría ni un enum de estados. Los tests ASan existentes instrumentan
sus fixtures, no las bibliotecas cerradas de Apple ni todo libobs precompilado.

## Política conservada para captura de video

- Crear, sustituir o reconectar una captura requiere outputs detenidos.
- Un stop intencional no dispara reinicio. Edad de buffer o contenido estático
  no se convierten en fallo confirmado ni autorizan capturar un display.
- El respaldo explícito hace un Cut a una escena válida sin capturas; conserva
  los mismos outputs, encoders y mixer. No reconstruye el SCStream averiado.
- Window conserva ID/PID exactos; Application conserva bundle único, PID de
  sesión y display explícito. Ninguna identidad ausente se aproxima a otra.

El PASS físico acotado de C4 prueba continuidad durante el respaldo y cierre
normal de sus procesos. No demuestra seguridad de reemplazo concurrente,
ausencia de fugas, permisos revocados o suspensión del sistema.

### Límite adicional localizado en audio SCK durante C8

La política anterior no debe extenderse automáticamente al mixer histórico.
`motive_poll_audio` aísla un canal fallido y llama a `audio_detach`; la API
`ReconnectAudioInput` permite recuperación por entrada sin el guard `idle` que
usan añadir/eliminar entradas. Esas rutas también alcanzan `sck_audio_capture`.
El primer ensayo 3D prolongado C8 observó la destrucción del canal fallido antes
de parar los outputs. Las regresiones H13 ejercitan recuperación funcional,
pero no prueban la barrera de callbacks de ese módulo.

`signal_handler_disconnect`, el retiro de callbacks de audio y la cola de
destrucción OBS no demuestran por sí solos que toda referencia de SCStream
haya terminado. No se observó un UAF en C8 y no se lo declara como bug confirmado.
La obligación de lifetime incluye **audio y video**; no se certifica reconexión
SCK live por el PASS funcional de H13. C8 no añade otra ruta de reconstrucción,
ni usa el fallo de pantalla como permiso para reconectar automáticamente.
La guía pide detener salidas antes de la recuperación explícita; eso delimita
el uso ensayado y no constituye una prueba del lifetime nativo pendiente.

## Experimento requerido antes de abrir reconstrucción en vivo

Hace falta una generación de stream y un contexto de callbacks cuya revocación
se sincronice con callbacks activos. Registrar por identidad/generación: entrada
y salida de cada callback, petición y completion de stop, retiro de outputs,
referencias pendientes y liberación final. Probar reemplazo, error de fuente,
stop de usuario, shutdown y callbacks tardíos sin bloquear el hilo gráfico ni
esperar la cola de callbacks desde esa misma cola. Un timeout debe cerrar el
intento y conservar el contexto necesario, sin reconexiones infinitas ni liberar
memoria todavía prestada.

Ese diseño no se presenta como implementado. Requiere un nuevo módulo nativo
identificado, instrumentación real, pruebas adversas y regresión de audio y
salidas. C4 mantiene la restricción existente, tal como permite la misión H21.

## CAP-01 y outputs

El FAIL de foco H17 sigue siendo evidencia válida. El contraste H20 C1 usa
módulos original/parcheado dentro del mismo owner Motive: no equivale a probar
OBS Studio completo. Una repetición sin congelamiento solo permite afirmar
«no reproducido en esa secuencia».

La traza de paquetes está antes del plugin. El cutoff de mux/RTMP y la cola
asíncrona de VideoToolbox son etapas distintas; un conteo de encoder no prueba
entrega remota. Se conserva la clasificación entre paquetes anteriores a stop,
posteriores al bracket de stop y receptor interrumpido deliberadamente. Los
FAIL históricos AAC pre-stop no se borran porque C4 no los reproduzca.
