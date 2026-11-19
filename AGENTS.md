# Motive

Estudio local-first, gratuito y open source para macOS ARM64. Leer README.md,
docs/plan.md y docs/decisions.md antes de continuar. Conservar evidencia real;
no declarar hitos completos mediante mocks. No publicar, hacer push, emitir
públicamente ni cambiar el entorno global sin autorización.

Rust + GPUI Kit + libobs. UI, CLI y MCP deben controlar una sola instancia del
núcleo. MCP nunca transporta video ni marca el reloj multimedia. Mantener REA
fuera del producto; investigar primero documentación oficial y código abierto.
No copiar código, recursos ni diseños propietarios de Meld.

La automatización de Motive debe usar herramientas propias del proyecto, con
procesos y perfiles aislados, contenido controlado y supervisión externa. No
depender de servicios ni sesiones de otro proyecto. Una herramienta que falle
no autoriza recurrir a un navegador personal: informar y detener ese recorrido.
Nunca conectar a Dia ni a otros navegadores personales, ni usar CDP,
DevToolsActivePort, puerto 9222, connectOverCDP o chrome-devtools-mcp.
Dia solo lo maneja el propietario cuando pide mirar algo juntos.

El desarrollo del Browser Host de Motive puede compilar y ejecutar su propio
CEF nativo cuando la tarea requiera verificarlo, sin pedir otra excepción por
cada prueba. Usar contenido propio controlado, inventario cerrado, directorios
locales privados y supervisor externo con límites de tiempo y memoria. Conservar
frames, resultados y fallos reales; comprobar el cierre de los procesos propios.
No desactivar el sandbox ni cambiar permisos o políticas globales para lograr un
PASS. El contenido de terceros sigue bloqueado hasta demostrar aislamiento real.
Esto no autoriza modificar Production sin el handoff acordado ni usar datos,
dispositivos o destinos externos ajenos al alcance de la tarea.

Capturas únicamente con contenido controlado y permisos normales de macOS.
No exponer secretos a overlays, logs ni MCP. Después de dos intentos sin
progreso en el mismo fallo, cambiar de hipótesis o documentar el bloqueo.

Diseño: la fuente de verdad visual son los lienzos de Claude Design; su copia
de solo lectura está en design/claude-design/ (ver design/README.md). Implementar
desde ahí y design/direction.md; no editar esa copia a mano.
