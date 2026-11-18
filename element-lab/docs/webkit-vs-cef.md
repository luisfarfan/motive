# WebKit / CEF · decisión experimental

Consulta: 18 de noviembre de 2026 (Lima). Se releyó íntegro
`../../docs/h11-browser-spike.md`. No se cargó obs-browser, Qt, CEF ni un WKWebView.
Se inspeccionó el header WebKit del SDK instalado (`../evidence/I-webkit-sdk.json`)
y documentación/código oficiales. El único navegador ejecutado fue el MCP
proxima-browser, conforme a AGENTS. Los tests HTML no verifican ninguno de estos
hosts nativos ni su captura en libobs.

## Matriz

| Aspecto | WebKit / WKWebView | CEF independiente |
|---|---|---|
| Dependencia y bundle | Framework del sistema; menor carga de distribución propia. Versión ligada a macOS | Framework Chromium, recursos y helpers por arquitectura; aplicación responsable de actualizaciones |
| Transparencia | CSS transparente y `underPageBackgroundColor` son controles de presentación; no prueban alfa del frame exportado | OSR documenta fondo transparente; probar alfa premultiplicado y bordes al copiar BGRA |
| Frames | `takeSnapshot` entrega NSImage asíncrona; no ofrece en ese contrato un stream ni SLA de 30/60 FPS | `OnPaint` entrega BGRA y regiones invalidadas; candidato de menor incertidumbre para un primer bridge CPU |
| Sincronización | Cadencia de snapshot, throttling y oclusión sin medir | FPS solicitado/BeginFrame no equivalen a timestamps OBS. Conservar secuencia y edad de frames |
| GPU | WebKit administra su render; no se demostró una API pública para tomar su superficie continua | `OnAcceleratedPaint` describe IOSurface en macOS, pero otro header conserva un comentario Windows-only: fijar versión y probar antes de prometer GPU/zero-copy |
| IPC | Puente tipado con `WKScriptMessageHandler`, nunca Production; proceso de contenido separado | Mensajería CEF entre browser/renderer; broker propio con mensajes estrictos |
| Lectura local | `WKURLSchemeHandler` para un esquema de paquete; no sustituye rechazo de otras rutas/red | Scheme/resource handlers con inventario exacto; denegar navegación y permisos fuera del paquete |
| Aislamiento | Data store no persistente limita persistencia; no es denegación de red. App-Bound Domains limita navegación, no todos los subrecursos | Arquitectura multiproceso y sandbox requieren configuración/verificación macOS; no reutilizar `no_sandbox=true` de obs-browser H11 |
| Lifecycle | Procesar terminación de contenido, invalidar puentes, cancelar cargas y liberar vista/store | Message pump AppKit, cierre de browsers, callbacks finales y shutdown ordenado de helpers |
| Canvas / SVG | Capacidad web esperada, a verificar con corpus fijado en cada macOS | Capacidad Chromium esperada, a verificar por versión y backend OSR |
| Límites | No se midió CPU/RSS/GPU. Enforcement debe vivir fuera de JS | Igual; sumar árbol de procesos, no solo PID del owner |
| Integración libobs | No implementada; no hay contrato probado de frames continuos | No implementada; convertir salida OSR en una fuente del único compositor |
| Licencias y distribución | El prototipo no redistribuye WebKit; revisar fuentes/avisos si cambia esa decisión | CEF BSD y avisos Chromium/terceros; revisar codecs, firma, helpers y notarización del bundle concreto |

Fuentes primarias para captura, transparencia y aislamiento WebKit:
[Snapshot](https://developer.apple.com/documentation/webkit/wkwebview/takesnapshot(with:completionhandler:)),
[fondo bajo la página](https://developer.apple.com/documentation/webkit/wkwebview/underpagebackgroundcolor),
[scheme handler](https://developer.apple.com/documentation/webkit/wkurlschemehandler),
[store no persistente](https://developer.apple.com/documentation/webkit/wkwebsitedatastore/nonpersistent()),
[terminación de proceso](https://developer.apple.com/documentation/webkit/wknavigationdelegate/webviewwebcontentprocessdidterminate(_:)),
[App-Bound Domains](https://webkit.org/blog/10882/app-bound-domains/).
La última fuente advierte que la restricción de dominios se aplica al frame superior;
no puede presentarse como un firewall para paquetes.

Fuentes CEF:
[guía de uso](https://chromiumembedded.github.io/cef/general_usage),
[contrato RenderHandler](https://github.com/chromiumembedded/cef/blob/master/include/cef_render_handler.h),
[tipos macOS](https://github.com/chromiumembedded/cef/blob/master/include/internal/cef_types_mac.h),
[cefclient AppKit](https://github.com/chromiumembedded/cef/blob/master/tests/cefclient/cefclient_mac.mm),
[licencia](https://github.com/chromiumembedded/cef/blob/master/LICENSE.txt),
[actualizaciones de seguridad](https://github.com/chromiumembedded/cef#security-updates).
Se consultó también Context7 con los índices oficiales Apple y chromiumembedded/cef.
La guía general conserva texto antiguo sobre aceleración OSR; el header actual
expone una ruta acelerada. Esa discrepancia es evidencia de incertidumbre de versión,
no permiso para afirmar soporte probado. Los enlaces master son móviles; no
constituyen una versión distribuible fijada.

## Decisión

Mantener ambos hosts como experimentales. **Priorizar un spike CEF OSR CPU
independiente** para la futura fuente de video, por su callback de frames explícito;
considerar WebKit para autoría/preview macOS si prima el coste de empaquetado.
Es una inferencia de contratos, no un benchmark ni una elección irreversible.
No se recomienda construir un bucle de `takeSnapshot` como fuente de 60 FPS sin
medirlo. No usar APIs privadas/KVC para fingir una ruta pública de superficies.

El H11 inspeccionado fijó OBS 33.0.1 / obs-browser 2.27.5 y encontró Qt Widgets,
frontend API, helpers y `no_sandbox=true`. Su ejecutable CEF medía 218.201.312 bytes;
es solo ese binario histórico, no el bundle completo ni RSS. El nuevo host debería
usar CEF directamente; no inicializar a medias el frontend OBS dentro de GPUI.

## Spike futuro acotado

Un proceso host propio, paquete original, esquema administrado y ningún dispositivo.
Primero 640×360/30; después 960×540 y 540×960 a 30/60. Medir alfa con fondo conocido,
frame index visible, intervalos/edad/pérdidas, coste de copia y CPU/RSS/footprint de
todos los procesos. Probar oclusión, minimización, cambio de tamaño, suspensión,
crash, límite de memoria, tormenta de eventos y cierre de cien ciclos. Confirmar
que no quedan helpers ni descriptores. Probar intentos de HTTP, loopback, file,
traversal, popup, descarga, dispositivos y bindings no autorizados.

No guardar handles CEF después del callback: el contrato exige copiar a un recurso
propio antes de devolverlo. Integrar solo tras medir backpressure y lifecycle.
Los gates nativos de H15 y pruebas con libobs son posteriores; este incremento no
los ejecuta ni obtiene el lock físico.
