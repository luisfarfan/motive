# Contrato de integración futura

**Diseño experimental; ningún endpoint descrito aquí está implementado en
Production por Element Lab.** H15 conserva src/, native/, GPUI, libobs, Show
Control runtime y el instalador. No se modificaron esos componentes.

## Importación nativa

1. La UI oficial elige un archivo local y muestra tipo, contenido, licencia,
   autor no verificado, capacidades, cambios y presupuesto. Un `.motivepack`
   declarativo nunca activa ejecución de HTML/JS.
2. El importador valida versión, entradas ZIP, integridad, límites, recursos y
   compatibilidad usando los contratos reales. La revisión del laboratorio es
   adicional; no sustituye el decoder/importador autorizado de Motive.
3. El owner consulta capacidades y snapshot vigente con revisión/generación.
   Suma el grafo existente, assets y fuentes de captura antes de preparar el plan.
   Una revisión obsoleta exige recalcular; los IDs simbólicos no son IDs vivos.
4. El broker autorizado importa recursos y devuelve IDs reales. El owner crea
   escenas/fuentes/capas con esos recibos y mantiene un mapa símbolo → ID real.
   La aplicación decide cómo registrar un fallo parcial y retirar solo objetos
   creados por esa operación. No prometer una transacción atómica inexistente.
5. Revalida y vincula properties, reglas y acciones usando IDs/revisión recibidos.
   No inicia timers, animaciones ni salidas durante la importación. Reglas
   desarmadas por defecto; el creador revisa los triggers remapeados.
6. La verificación nativa posterior observa frames y lifecycle con el proceso
   de pruebas autorizado del producto. El éxito de Element Lab no la acredita.

El adaptador actual de `src/creator_packs.rs` admite el pack MATCHDAY embebido y
rechaza recursos de estos ejemplos. Por ello **no hay una orden de instalación
oficial que pueda ejecutarse ahora para estos paquetes**. El formato experimental
de revisión `motive_review_package` no redefine el importador `.motivepack` v1.

## Evento Show Control → visual web

El ejemplo demuestra dos hechos separados: el crate admite un evento simulado
`motive.custom_event` con nombre `goal-scored` y prepara la acción nativa; el
harness web admite `goal.scored` y anima un DOM real. Todavía no existe un bridge
en Motive que conecte ambos.

Un bridge futuro, propiedad del host, debe admitir solo un binding previamente
revisado. Ejemplo de proyección (no forwarding del envelope completo):

```json
{
  "version": 1,
  "seq": 17,
  "kind": "event",
  "name": "goal.scored",
  "payload": {"team": "Club del Puerto", "home": 2, "away": 1}
}
```

La entrada puede proceder de Show Control o de un proveedor confiable. El host
verifica origen, identidad de instancia, revisión y permiso de binding; toma
solo team/home/away con sus tipos y límites. No envía tokens, credenciales,
payloads crudos de Twitch/YouTube, rutas privadas, handles de Production ni
comandos. La procedencia confiable no se deduce de un campo booleano aportado
por un paquete. El harness usa datos sintéticos y solo ejercita el lado visual.

## IPC y lifecycle mínimos propuestos

Un canal privado por instancia/generación, distinto del socket del estudio.
El host valida tamaño antes de deserializar, secuencia estrictamente creciente,
allowlist de evento/property, cuota y deadline. El prototipo aplica una parte en
JS; la versión nativa debe aplicar límites antes de entregar al renderer.
Cancel/dispose tienen prioridad aun con la cuota agotada. Nada recibido del
elemento se interpreta como una orden de producción.

Estados visuales: ready → active → ready; cancel → cancelled; error → error;
dispose → disposed. Resume es explícito. Reiniciar proceso crea generación y
canal nuevos; mensajes antiguos se descartan. Al ocultar se cancela; al salir se
revocan puertos, timers, animaciones, assets y buffers. Un watchdog fuera del
renderer termina el proceso si hay bloqueo o abuso de recursos. El timer de
15 segundos del harness no es ese watchdog.

## Host de frames experimental

Paquete inmutable bajo esquema privado y permisos denegados por defecto. CEF
debe inicializarse de forma independiente al frontend Qt/OBS; WKWebView requiere
probar una ruta pública de frames antes de servir como fuente de video. No
reactivar obs-browser con `no_sandbox=true` para saltarse H11.

El futuro contrato de buffer debe fijar explícitamente:

- instancia/generación, frame index, dimensiones, stride, formato BGRA8,
  premultiplicación alfa y espacio de color comprobados;
- ownership y vida útil del buffer/superficie; copia propia dentro del callback
  CEF antes de devolver, nunca retener un handle temporal;
- cola acotada de 2–3 buffers, descarte de frames antiguos y tamaño máximo;
- timestamp monotónico para edad/telemetría, separado del PTS audiovisual;
- CPU-copy inicial y una ruta GPU solo después de demostrar sincronización,
  ownership y recuperación tras resize/crash.

libobs consume el frame disponible en su propio reloj. MCP puede pedir crear,
editar, probar o cancelar mediante las mismas operaciones tipadas del owner;
no transporta pixels, no marca PTS y no controla el pacing del renderer.

## Gates antes de aceptar contenido de terceros

Fijar versión CEF/WebKit/macOS, comprobar soporte real de OSR/superficies y
sandbox, firma/helpers/distribución, red/file/popup/download/device/IPC denegados,
CPU/RSS/GPU con watchdog, alfa/color, 30/60 FPS, backpressure, minimización,
suspensión, crash, cierre repetido y ausencia de procesos huérfanos. Medir con
contenido controlado. Después, en otro incremento autorizado, validación nativa
libobs y presupuestos junto al resto del estudio. Hasta entonces, la confianza
del paquete web es **contenido propio revisado, sin instalación oficial**.
