# API visual propuesta v1

`runtime.mjs` exporta `createRuntime(contract)` para el harness. El elemento recibe
únicamente `MotiveElement.on(name, callback)`, `getProperties()`,
`onPropertiesChanged(callback)`, `onLifecycle(callback)`, `onCleanup(callback)`,
`getState()` y `reportError()`. Los registros devuelven una función para desuscribir.
Los callbacks de eventos pueden devolver una Promise; la fase activa termina al
resolver todos. Payloads y properties se copian/congelan. La señal AbortSignal
se cancela al cancelar, fallar, disponer o terminar el evento.

El host posee `receive`: envelopes v1 con secuencia monotónica, eventos/payloads
cerrados, patches de propiedades tipados/atómicos, cuota por segundo y bytes
máximos. Cancel/dispose siguen disponibles aunque se agote la cuota. No hay
objetos Production, MCP, rutas privadas, comandos arbitrarios ni secretos.
Todo estado es visual. Las reglas reales de Show Control siguen en Rust.

Bootstrap una sola vez desde parent hacia un iframe `sandbox="allow-scripts"`,
sin same-origin, con MessageChannel. Tras el bootstrap se retira el listener de
window; solo el puerto admite envelopes. El host no interpreta mensajes de la
página como órdenes del estudio. Autostart de eventos está desactivado; testMode
es una vista estática. Ocultar el documento cancela; error detiene; rearmar es
explícito; dispose cierra suscripciones/animaciones/puerto. El host cancela a los
15 s, pero un temporizador JS **no limita CPU ni memoria de un proceso**.

CSP del servidor niega conexiones, frames, workers, medios, objetos y formularios
en el widget. Los archivos se sirven de una allowlist local. Se verificó en el
navegador aprobado el rechazo de fetch externo/loopback y de mensajes fuera del
canal. Esto no acredita seguridad de paquetes arbitrarios, contención de CPU/GPU,
aislamiento OS ni ausencia de escapes del navegador. El harness sirve solo el
contenido propio auditado; no es un sandbox seguro ni host de terceros.

```sh
node --test element-lab/tests/runtime.test.mjs
python3 element-lab/sdk/motive_elements.py serve --port 8776
```

Usar únicamente proxima-browser para abrir `http://127.0.0.1:8776/`. El panel
«Creador nativo» usa el mismo compilador/validador; no crea un segundo motor.
