# H14 — Live Deck y revisión local en GPUI

`src/ui/studio/show_control.rs` presenta el modelo compartido de Show Control;
no ejecuta reglas, calcula cooldowns ni controla el reloj de audio/video. El
heartbeat del estudio llama `Production::poll_show_control()` una vez por tick
de 33 ms, después del bloque periódico de salud y antes de lifecycle y de la
cola de comandos. No se llama desde `apply` ni `poll_health`.

El botón **Live Deck** de la barra abre grupos y botones ordenados según el
deck del owner. Se muestran estados de admisión/cooldown, hasta 16 trabajos con
sus últimos códigos, cancelación, revisión de resultados inciertos e historial
de hasta 64 entradas. Estos son resultados de control; no certifican pixels
decodificados ni entrega de streaming. La UI usa `ButtonState` y `JobState` del
crate compartido y el snapshot acotado del owner.

Los clics capturan la sesión visible y rechazan una sesión reemplazada antes
del evento. Los comandos de cancelación/reconciliación también conservan esa
sesión, evitando aplicar un `job_id` antiguo a otro trabajo después de cargar
una producción. Los IDs de eventos UI son `ui-<pid>-<counter>` con contador
monótono comprobado; la sesión y deduplicación pertenecen al núcleo.

Los botones sensibles llaman `prepare_show_control_confirmation`. La UI
muestra `label()` y `actions()` del token real, después consume una única
`Rc<RefCell<Option<LocalDeckConfirmation>>>` en la confirmación afirmativa.
Cancelar descarta el token; la confirmación no crea un booleano de confianza ni
una ruta remota. El owner revalida proceso, revisión, sesión y vencimiento.

Los atajos configurados solo se procesan cuando el foco está en el contenido
de Live Deck. Coinciden exactamente en tecla y modificadores; se ignora la
repetición de una tecla mantenida. El handler no opera desde formularios de
otros paneles ni mientras un diálogo de confirmación está abierto. Admisión y
cooldown se vuelven a comprobar en el owner. La comprobación física del foco y
de VoiceOver sigue perteneciendo al informe general H14.

**Guardar** usa el store Show Control separado. **Restaurar** tiene revisión
local previa y el owner restaura la producción desactivada. **Activar
producción** envía el PID y revisión actuales al método compartido; no inicia
salidas. La UI advierte si `bindings_current` dejó de coincidir y conserva los
errores estructurados del owner.

## MATCHDAY

`src/ui/studio/creator_packs.rs` incorpora la revisión de instalación dentro de
Live Deck. Usa exclusivamente `prepare_matchday_install`,
`LocalPackReview::summary`, `install_matchday_local` y `creator_packs_status`.
La confirmación muestra cantidades, pasos, presupuesto de texturas y los límites
emitidos por el núcleo; consume el token una vez y no construye proyectos ni
bindings por su cuenta.

Una instalación parcial conserva el informe, pasos y recursos creados; la UI no
finge rollback ni reintenta. `restore_accepted` se describe como solicitud de
regreso a la escena anterior, sin inferir finalización de transición o pixels.
La instalación no guarda automáticamente proyecto ni Show Control. El usuario
dispone de **Guardar proyecto** y del guardado de Live Deck y selecciona la
escena MATCHDAY mediante el selector de escenas habitual.

## Aviso de captura

Preferencias/diagnóstico muestra `NO_RECENT_CAPTURE_BUFFER` solo cuando la
fuente está activa y el owner proporciona `freshness_notice`, junto a la edad
del último buffer si está disponible. El texto pide comprobar contenido y
visibilidad. No interpreta el tiempo como una imagen congelada, no crea un fallo
fatal y no solicita detener salidas.

## Comprobaciones

El check integrado de destinos pasó y la suite posterior inicial pasó 101 tests.
Live Deck y el heartbeat pasaron después la suite integrada de 105 tests. Esas
ejecuciones anteceden al último enlace de MATCHDAY y su diagnóstico; el check
final coordinado se registra en el informe general H14. Ninguna prueba de dominio
equivale a validación física de los paneles, foco, Keychain o medios externos.
