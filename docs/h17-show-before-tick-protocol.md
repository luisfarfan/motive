# H17 — cancelación anterior al primer tick: protocolo acotado

Estado físico: **NOT_EVALUATED**. El modo opt-in
`verify_h17_show_recovery.py --cancel-before-tick-only` no cambia el producto
ni la ruta por defecto que conserva la cancelación posterior al tick B7.
Los siete tests offline verifican clasificación y recibos; no son una
cancelación nativa real.

La ventana no está cerrada estructuralmente. `overlay_animation_start`
publica `running` con `started=false`. El tick OBS comprueba `CANCEL_PENDING`
antes de inicializar; una cancelación que llegue a tiempo puede conservar
`started=false` y `widget_triggered=false` al terminar. El heartbeat de Show
Control y el tick OBS son independientes. La serialización y fsync del
journal consumen parte de esa ventana; no se promete poder observarla.

Cada invocación requiere un owner nuevo con escena por defecto y crea su
propia fixture, sesión y configuración durable. Tras admitir el botón hace
como máximo 32 consultas normales o un segundo, sin sleeps entre observar y
cancelar, sin pausar heartbeat y sin modificar los 450 ms. Sólo solicita
cancelación si existe el token exacto en `awaiting_completion`, y el snapshot
nativo aún tiene `started=false`, `widget_triggered=false`, `start_ns=null`,
elapsed/progress cero. `elapsed_ms=0` con `started=true` no basta.

**PASS** requiere el mismo token y owner, terminal nativo `cancelled` con
`pending_ack=false` y todavía sin empezar/disparar widget; cursor y contador
intactos; ningún registro del segundo action; y exactamente un dispatch,
cancel_intent y completion durable, ordenados, con terminal receipt correcto.
Si el tick gana después de observar, el resultado es **BLOCKED**. Si sólo
se ve un job en cola o ya empezado, no se cancela como sustituto: se deja
terminar la propia operación y se conserva el contador que realmente resulte.

Ejecutar únicamente después de recibir el lease físico explícito y comprobar
que el owner anterior cerró normalmente. B10 debe estar listo y fijado por
hash; no se hereda evidencia B7/B9:

```sh
python3 scripts/h15_run_owned.py \
  --app /Users/luisfarfan/Developer/motive-h17-portable/b10/Motive.app \
  --output var/evidence/h17-before-tick-b10-owner-01 --timeout 60 \
  python3 scripts/verify_h17_show_recovery.py \
  --output var/evidence/h17-before-tick-b10-01 --cancel-before-tick-only
```

Máximo dos invocaciones coordinadas, cada una con nuevo owner/sesión/fixture
y rutas nuevas (`-02` para la segunda). Antes de repetir: examinar la causa,
owner_exit=0, cleanup vacío, stores restaurados a los bytes originales
actuales y ningún proceso pendiente. Un gate BLOCKED devuelve exit 1 aunque
la limpieza sea correcta; `FAIL_RUNNER` no debe ocultar esa distinción.
Después de dos ventanas no observadas se conserva el bloqueo sin tercer
intento, cambio de duración o pausa de scheduler. Los journals propios e
históricos se retienen; no se carga un proyecto del usuario.

Evidencia offline de los gates y rechazo del B7 post-tick como supuesto
pre-tick: `var/evidence/h17-before-tick-contract-01/`. Las respuestas completas,
brackets del socket y journal de una futura ejecución quedarán en su carpeta
nueva. Ningún test de esta preparación modifica el bundle B9 o abre apps,
devices, outputs o receivers.
