# Motive

Estudio local-first, gratuito y open source para macOS ARM64. Leer README.md,
docs/plan.md y docs/decisions.md antes de continuar. Conservar evidencia real;
no declarar hitos completos mediante mocks. No publicar, hacer push, emitir
públicamente ni cambiar el entorno global sin autorización.

Rust + GPUI Kit + libobs. UI, CLI y MCP deben controlar una sola instancia del
núcleo. MCP nunca transporta video ni marca el reloj multimedia. Mantener REA
fuera del producto; investigar primero documentación oficial y código abierto.
No copiar código, recursos ni diseños propietarios de Meld.

Para cualquier trabajo de navegador usar únicamente proxima-browser MCP.
Nunca conectar a Dia ni usar CDP, DevToolsActivePort, puerto 9222,
connectOverCDP o chrome-devtools-mcp. Si proxima-browser falla, informar y
detener ese trabajo, sin otro navegador. Dia solo lo maneja el propietario.

Capturas únicamente con contenido controlado y permisos normales de macOS.
No exponer secretos a overlays, logs ni MCP. Después de dos intentos sin
progreso en el mismo fallo, cambiar de hipótesis o documentar el bloqueo.

Diseño: la fuente de verdad visual son los lienzos de Claude Design; su copia
de solo lectura está en design/claude-design/ (ver design/README.md). Implementar
desde ahí y design/direction.md; no editar esa copia a mano.
