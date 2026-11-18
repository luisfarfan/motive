# H16 — decisión y evidencia final

**Resultado global: PARTIAL.** El laboratorio entrega auditoría de fuentes,
contratos ejecutables y fixture CEF comprobado contra dos APIs. La suite estática
es **PASS**. Renderizado nativo, aislamiento de terceros y benchmarks siguen
**BLOCKED**; no se afirma que exista un Browser Engine integrado en Motive.

La dirección elegida es **C: CEF con su wrapper upstream, host AppKit separado y
patrones seleccionados de OBS Browser**. Motive mantiene políticas, lifecycle,
canales acotados y el futuro adaptador libobs. No mantiene un fork completo del
plugin ni incorpora Qt. Es una decisión sobre responsabilidades y mantenimiento;
todavía no demuestra una mejora de CPU, GPU o memoria.

Fecha: 2026-11-18. Worktree: `/Users/luisfarfan/Developer/products/motive-h16`.
Rama: `codex/h16-browser-engine`. Base remota verificada:
`130b626168cbe1336afb85c3810fa6be5e6b2b11`. La copia local de main estaba en
`6019ad0acac4b52dcf1ebc44f2006406fde533f8`; se usó el main remoto descendiente,
sin modificar main ni el checkout de H15. Véase [baseline.json](../evidence/baseline.json).

## Respuestas a los trece criterios

1. **Porcentaje funcional aprovechable — NOT_EVALUATED.** Hay 4 componentes
   REUSE y 6 ADAPT de 20 filas, es decir 50% de una clasificación sin ponderar.
   No es un porcentaje funcional ni de código ahorrado. Falta definir un corpus
   funcional y demostrar equivalencia nativa. No se trasplantó implementación
   del plugin OBS; el motor, wrapper y sandbox de CEF son la reutilización
   principal. El boilerplate Cocoa/helper adaptado de CEF tiene atribución.
   Evidencia: [matriz de reutilización](../research/upstream-reuse-matrix.md).

2. **Eliminar Qt sin romper lifecycle — PARTIAL.** Ambas revisiones OBS conservan
   Qt Widgets y su loop/tareas en macOS, incluso sin panels. El fixture propio
   usa AppKit y el loop CEF sin Qt ni frontend OBS; fixture y helper pasan las
   cuatro comprobaciones de API. El crate verifica cierre final, cancelación,
   deadlines y generaciones. No se ha enlazado ni ejecutado ese lifecycle CEF,
   por lo que aún falta probar create/close/crash y cleanup de helpers.
   Evidencia: [auditoría](../research/obs-browser-analysis.md),
   [API nativa](../evidence/I-native-api.json), [pruebas Rust](../evidence/M-rust-tests.log).

3. **Implementación de menor riesgo — PARTIAL, recomendación C.** Eliminar Qt,
   perfiles, frontend, bindings de control y permisos de un fork amplio deja
   muchas superficies que Motive tendría que mantener. C conserva el motor y
   wrapper y reduce el código propio a una frontera explícita. B sirve para
   extraer fragmentos concretos cuando aporten valor; no se sostiene un segundo
   renderer permanente. La elección no clasifica rendimiento aún no medido.
   Evidencia: [comparación A/B/C](../research/upstream-reuse-matrix.md),
   [arquitectura](../architecture/browser-host.md).

4. **Frames transparentes por API soportada — PARTIAL.** Los headers fijados
   documentan OnPaint BGRA completo, origen superior izquierdo y fondo
   windowless transparente. El fixture copia los bytes antes de retornar y
   configura alpha cero. Rust prueba ownership, coalescing, bounds, freshness y
   revocación. La interpretación premultiplicada debe confirmarse con píxeles
   reales y composición; no hay evidencia nativa de alpha, color o FPS.
   Evidencia: [versiones/APIs](../research/cef-version-matrix.md),
   [fixture](../poc/browser-host/native/fixture.mm), [contrato de frames](../poc/browser-host/src/frame.rs).

5. **Coste de tres/cinco Web Elements — BLOCKED.** No hay CPU, RSS/footprint,
   GPU, latencia o coste incremental medidos. A 640×360, el límite lógico de
   tres buffers completos por instancia suma 8,294,400 bytes para tres y
   13,824,000 para cinco. Es aritmética de buffers propios; excluye Chromium,
   allocator, transporte y texturas, y no estima RSS del árbol. Diez escenarios,
   resoluciones, repeticiones y umbrales están fijados antes de ejecutar.
   Evidencia: [protocolo](../benchmarks/README.md),
   [presupuesto aritmético](../evidence/J-buffer-budget.json).

6. **Aislamiento seguro para terceros — BLOCKED.** El broker probado entrega
   solo bytes inmutables del inventario y el protocolo acepta operaciones
   visuales limitadas. El fixture prepara rechazo de navegación, requests,
   permisos y popups; mantiene `no_sandbox=false` y el loader oficial antes
   de cargar CEF en el helper. Nada de ello prueba confinamiento del proceso
   browser, HOME, Keychain, egress o recursos del OS. RequestContext separado,
   CSP y búsqueda de URLs no son un sandbox. La API del broker mantiene
   deshabilitada la ejecución de terceros. Se requiere evidencia sobre el
   bundle exacto, incluyendo canales que pueden eludir callbacks ordinarios.
   Evidencia: [modelo de seguridad](../architecture/security-model.md),
   [9 pruebas de importación/política](../evidence/M-security.log).

7. **Mejoras demostrables frente a la referencia — PARTIAL.** El código propio
   muestra colas de frames acotadas, generaciones, límite y deadline absoluto
   de paquetes, rechazo de claves duplicadas, allowlists, rate limit y patches
   atómicos. No incorpora bindings `obsstudio` de grabación/streaming ni el
   esquema que abre rutas arbitrarias. Son propiedades de contratos probados y
   diferencias de código; no una prueba comparativa de aislamiento nativo o
   velocidad. Porcentaje de mejora de rendimiento: **NOT_EVALUATED**.
   Evidencia: [diff OBS](../evidence/obs-browser.diff),
   [IPC](../architecture/ipc-contract.md), [suite final](../evidence/M-static-summary.json).

8. **Limitaciones que permanecen — PARTIAL.** Chromium aporta payload,
   procesos y mantenimiento de seguridad; CPU-copy mueve imágenes completas y
   libobs deberá subir texturas. El host privilegiado sigue siendo una superficie
   de ataque. Compartir procesos amplía el alcance de un fallo y requiere pruebas
   antes de pooling. No están resueltos HDR/wide gamut, equivalencia de fuentes,
   todas las APIs web, 60 FPS, GPU zero-copy ni confinamiento del browser process.
   OnAcceleratedPaint/IOSurface no autoriza retener el recurso tras el callback.
   Evidencia: [procesos](../architecture/process-model.md),
   [mantenimiento](maintenance.md), [API CEF](../research/cef-version-matrix.md).

9. **Eventos de Show Control — PARTIAL.** Se probó la proyección del fixture
   existente `goal-scored` a `goal.scored`, limitada a team/home/away, a través
   del Gate Rust y del runtime JS original. El owner debe autenticar binding,
   sesión/revisión y dedup; un `origin` en JSON no concede autoridad. El ejemplo
   real necesita bootstrap con MessagePort, ausente al abrir su HTML directamente
   en CEF. El puente confiable está diseñado, no implementado. No se cambió el
   schema de Element Lab ni se despachó un evento en Production.
   Evidencia: [integración](integration-plan.md),
   [mensaje generado](../evidence/K-goal-message.json), [interop JS](../evidence/M-runtime.log).

10. **Qué necesita libobs — PARTIAL, diseño.** Una fuente video-only de dibujo
    propio, manager del owner, transporte binario acotado y textura propiedad del
    contexto gráfico OBS. Consume el último frame válido según identidad,
    generación, epoch, índice y edad bajo el reloj OBS. El timestamp observado
    no es PTS. Revocación/cierre invalidan frames y texturas; upload y destrucción
    respetan el contexto gráfico. Falta el transporte/FFI real C++→Rust→libobs.
    Evidencia: [contrato del adaptador](../architecture/libobs-adapter-contract.md).

11. **Impacto en Motive.app — PARTIAL.** El framework instalado de referencia
    contiene 319,928,674 bytes (305.11 MiB), y sus cuatro ejecutables helper
    añaden 2,233,520 bytes. Los árboles Release descargados A/B contienen
    321,164,707 y 321,133,294 bytes respectivamente, sin AppleDouble. Esto sitúa
    el payload del runtime alrededor de 305–307 MiB antes del paquete propio;
    no es el delta medido de Motive.app. No se multiplica por número de widgets.
    Tamaño final/compresión: **NOT_EVALUATED**.
    Evidencia: [inventario de distribución](../evidence/L-distribution.json),
    [revisión](../research/license-review.md).

12. **Firma y notarización — PARTIAL.** Quedan bundle/helper identifiers,
    wrapper y dylibs coincidentes, recursos Chromium, entitlements por rol/JIT,
    firma de código anidado y prueba portable fuera del checkout. Hardened
    runtime/notarización no sustituyen sandbox. No se tocó Keychain, certificados,
    TCC, SIP, Gatekeeper ni se firmó/publicó un binario. Debe revisarse la lista
    completa de licencias y corresponding source del paquete definitivo.
    Evidencia: [licencias y gates de distribución](../research/license-review.md).

13. **Cambios mínimos después de H15 — PARTIAL, propuesta.** Un manager dentro
    del owner existente, definición persistente de fuente por paquete/hash y
    propiedades aprobadas, adaptador de video libobs, acción visual tipada de
    Show Control y controles GPUI/CLI/MCP sobre las mismas operaciones del owner.
    Restauración sin replay; health y capacidades deshabilitadas mientras falten
    gates. Añadir el bundle/avisos solo tras validar distribución. No se propone
    otra Production, otro reloj o video sobre MCP.
    Evidencia: [plan ordenado de integración](integration-plan.md).

## Checkpoints y commits locales

PASS significa que el alcance indicado tiene evidencia; no extiende esa evidencia
a CEF ejecutado. PARTIAL separa implementación existente de integración pendiente.
BLOCKED identifica los gates nativos que no se ejecutaron. NOT_EVALUATED indica
un dato que no puede calcularse con lo observado. Ningún fallo conocido de la
suite estática queda abierto; los fallos previos se conservan para trazabilidad.

| Checkpoint | Estado y evidencia | Commit |
|---|---|---|
| A: auditoría | PASS: dos árboles OBS reales, inventario y análisis | `f1488ad` |
| B: versiones/reutilización | PASS: seis pins, hashes, headers y matriz | `de66751` |
| C: arquitectura | PASS como diseño; sandbox/compartición condicionados | `580520a` |
| D: build | PASS Rust independiente; PARTIAL build nativo sin enlace | `ef9219a` |
| E: lifecycle | PASS contrato; PARTIAL acciones/supervisor nativos | `87d8a4f` |
| F: frames | PASS ownership/mailbox; BLOCKED píxeles CEF reales | `e1fc1ee` |
| G: IPC | PASS Gate y UnixStream; PARTIAL autenticación/dispatcher CEF | `e3c846f` |
| H: aislamiento | PARTIAL broker/políticas; BLOCKED aislamiento OS | `f859d8a` |
| I: fixture | PARTIAL: cuatro comprobaciones API PASS; ejecución BLOCKED | `0962740` |
| J: rendimiento | BLOCKED ejecución; protocolo fijado y métricas nulas | `2bfcd2c` |
| K: Element Lab | PARTIAL: proyección/runtime PASS; DOM/CEF pendiente | `5f5fb64` |
| L: distribución | PARTIAL: inventario/revisión; paquete y firma pendientes | `0576147` |
| M: recomendación | PASS informe y suite estática; alcance global PARTIAL | Commit que incorpora este informe |

Ver [instrucciones reproducibles](build-and-test.md). El cierre registra 18
pruebas Rust, 9 Python, 2 Node, 4 comprobaciones API CEF, Clippy y formato PASS.
El resumen incluye hashes de implementación y comprobación de cambios confinados
a `web-host-lab/`. No se ejecutó Motive, CEF, captura, grabación o streaming; no
se adquirió lock multimedia ni se hizo push/merge/rebase/release/publicación.

## Fallos conservados y límites de la evidencia

Los dos intentos de timeouts de socket mediante `set_read_timeout` devolvieron
EINVAL en este entorno. Tras el segundo fallo se cambió a transporte no bloqueante
con deadline absoluto; la causa de plataforma no se dio por demostrada. Se
prueban ahora también cuerpos que llegan lentamente, sin extender el deadline.
Los logs inicial/diagnóstico/segundo intento permanecen en `evidence/G-*`.

La primera prueba Node falló por una ruta de import incorrecta; se corrigió para
usar el runtime original del ejemplo y se conserva el log. Clippy señaló un if
colapsable y una representación de byte innecesaria; ambos están corregidos y
los logs originales se conservan. La revisión final reforzó que un reintento de
cierre no pueda rebajar una eliminación definitiva después de timeout.

La búsqueda inicial del commit CEF B bajo chromiumembedded devolvió 404; el
README/versionado y la fuente oficial OBS identificaron el fork correcto.
El [registro de límites](../evidence/research-limits.json) conserva esa corrección.
El diff completo CEF contiene 21 archivos de implementación cambiados; los
headers relevantes son iguales salvo tablas generadas. B añade denegación de
WebAuthn/Bluetooth y también seguimiento de gamepads en segundo plano: una
versión más reciente no prueba menor superficie de permisos.

No se inició una comparación nativa OBS/CEF ni se mantuvo un segundo renderer.
No hay capturas, buffers reales ni resultados de FPS en este informe. La
autorización específica para ejecutar el fixture sigue ausente; además faltan
entry point/enlace/bundle, supervisor externo y conexiones nativas descritas en
el build. Una futura excepción de ejecución no completaría por sí sola esas
piezas ni autorizaría contenido de terceros.
