# H14 — activación y entrada de widget en una operación

Estado: candidato de fuente para B3. B1 mostró una discontinuidad real de
geometría; B2 es un bundle inmutable anterior a esta corrección. Este documento
no acredita todavía un build, una animación completa ni una grabación B3.

## Problema observado

La regla MATCHDAY enviaba `Widget Trigger` y luego `Animate`. El scheduler admite
una acción por heartbeat y cada animación instala su geometría inicial en el
siguiente tick de video. La alerta podía aparecer a tamaño normal antes de
reducirse a `scale_from=0.8`. El MKV y el receptor RTMP B1 contienen ese salto,
con PTS continuos. Acelerar el scheduler no haría atómicas las dos operaciones.

## Contrato único UI, CLI y MCP

Nueva acción Show Control:

```json
{
  "type": "trigger_animated_widget",
  "source_id": "source-15",
  "scene_id": "scene-2",
  "layer_id": "layer-16",
  "animation": {
    "kind": "scale_in",
    "easing": "ease_out",
    "duration_ms": 450,
    "distance": 120,
    "scale_from": 0.8
  }
}
```

El comando directo usa exactamente esos campos y `"op":
"trigger_animated_widget"` en lugar de `type`. La CLI acepta el JSON por su
canal `motive ctl '<JSON>'`; MCP publica `trigger_animated_widget` con
schema estricto. La respuesta aceptada contiene `result.operation_id`. Consultar
`overlay_state` para el estado nativo; aceptación no significa presentación ni
finalización. GPUI usa el mismo owner y muestra la acción en la revisión local.
Los identificadores del ejemplo son ilustrativos: usar los bindings del owner
actual, no IDs de una sesión o grabación anterior.

Restricciones comunes, incluidas las llamadas directas: fuente lista de tipo
`alert` o `lower_third`, escena activa sin transición, capa vinculada exactamente
a esa fuente, una sola referencia a la fuente en esa escena, capacidad de
animación disponible, y entrada `fade_in`, `slide_in` o `scale_in`. Se mantienen
los límites H11 de duración, easing, distancia y escala. Se rechazan campos
desconocidos. Una fuente puede seguir reutilizada en escenas inactivas; el
evento de widget sigue perteneciendo a la fuente, no a una copia por escena.

## Ejecución y observación

1. El owner revalida el snapshot y escribe/fsync un único intent completo antes
   del dispatch. No fusiona de forma implícita acciones antiguas.
2. libobs reserva un único job y retiene fuente, escena y capa. Guarda la
   generación de control de la fuente al admitir la operación.
3. En el primer tick de video, bajo `obs_scene_atomic_update`, captura baseline,
   instala geometría inicial y activa el widget antes de exponer el resultado
   al render. El callback de libobs precede el render de salidas y previews.
4. Si la generación cambió entre admisión y primer tick, el job falla con
   `WIDGET_CHANGED_BEFORE_TRIGGER`; no dispara la alerta y restaura la capa.
5. El terminal restaura geometría y transiciones anteriores, cierra la
   atribución de la fuente y publica `pending_ack`. El owner reconcilia el
   modelo y confirma ese operation ID antes de permitir continuar.

Además de los campos H11, cada job informa `trigger_source_id` y
`widget_triggered`. Para una operación compuesta, `completed` solo se acepta
si la fuente coincide y `widget_triggered=true`.

Cancelación es una solicitud asíncrona. Si el tick aún no empezó, se cancela
sin disparar (`widget_triggered=false`). Una solicitud que compite con un tick
ya iniciado puede llegar después del disparo: `widget_triggered=true`, se
restaura la geometría y la alerta ya iniciada conserva su ciclo normal. No hay
rollback implícito del widget ni segundo trigger. El estado distingue ambos
casos. Reset/shutdown sincronizan la retirada del callback antes de liberar
referencias.

## Recibos y concurrencia

Cada fuente expone un recibo escalar `lifecycle` con `revision`,
`from_revision`, `operation_id`, `control_generation` y `exhausted`. Los tres
primeros describen el último tramo continuo de cambios atribuibles a una misma
operación; eventos y actualizaciones externos rompen el tramo, incluso cuando
no cambian el texto de la fase. La fuente solo mantiene esa atribución mientras
la animación compuesta está activa. La expiración autónoma posterior queda sin
owner (`operation_id=0`).

El owner exige que todo el intervalo desde su última observación esté contenido
en ese tramo y que el par source ID / operation ID esté ligado al action key
original. Gaps, agotamiento, IDs desconocidos y cualquier cambio externo
intermedio impiden adoptar la revisión. El snapshot nativo lee jobs antes de
fuentes: observar un terminal implica leer después el último estado de su
fuente, antes del ack y del recibo del owner.

La nueva acción exige recibos válidos tanto de admisión como de finalización en
ejecución real. Si faltan, el job pasa a `needs_reconciliation`, conserva el
token conocido y no ejecuta el contador siguiente ni reintenta el trigger.
La observación y la reconciliación no reconstruyen un recibo a partir de una
revisión agregada posterior. Los backends de simulación siguen identificados
como simulados y no constituyen evidencia multimedia.

## Compatibilidad e integración

`Widget`, `Animate`, el formato de escena y los perfiles de salida conservan
su semántica. Las instalaciones MATCHDAY nuevas usan la acción compuesta en
`deck-goal` y `deck-celebrate`, seguida por el contador. No se reescriben ni
guardan configuraciones existentes automáticamente. Para probar B3 se necesita
instalar/bindear explícitamente la configuración nueva; restaurar una regla
antigua `Trigger → Animate` conserva su comportamiento anterior.

No se añaden reloj GPUI, temporizadores por frame, DSP, encoders, capturas ni
lógica de repetición en CLI/MCP. El journal conserva una intención compuesta,
un operation ID y sus recibos exactos.

## Verificación requerida

Tests de dominio y owner añadidos: forma estricta, límites y bindings, rechazo
de referencias duplicadas, recibo completo frente a cambio externo/gap,
atribución terminada antes de fases futuras, contador tras recibo válido,
ausencia de continuación sin recibo y terminal/cancelación coherentes. Son
tests de contrato; no acreditan frames, libobs ni medios reales.

Antes de cerrar B3: compilar/tests/clippy cuando terminen las mediciones B2;
grabar MKV + receptor RTMP con la entrada completa, hold y salida; inspeccionar
los primeros frames de varios triggers y confirmar que no aparece tamaño 1.0
antes de 0.8; comprobar contador exactamente una vez, cancelación antes y después
de iniciar, edición concurrente, desconexión MCP con animación en curso y
reconciliación sin replay. Mantener hashes, PTS y PCM. Los gates de suavidad,
audio, tail y recuperación solo se cierran con esa evidencia real.
