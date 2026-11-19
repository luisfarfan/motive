# H17 — cancelación anterior al primer tick: protocolo acotado

Estado físico tras dos intentos B10: **BLOCKED**; ninguno demuestra cancelación
anterior al primer tick. El modo opt-in
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
nueva. Ningún test offline de esta preparación modifica el bundle B9 o abre apps,
devices, outputs o receivers.

## Dos intentos reales B10

Binario SHA-256
`1390fa6834c22c7df002b72d3f3e3c9c7d2bb993149663ac07334b4282f279c9`.
Se ejecutó el protocolo sin alterar heartbeat, duración, producto o tiempos
de espera. Cada intento tuvo nuevo owner, sesión y fixture; no hubo un tercero.
Los wrappers son `var/evidence/h17-before-tick-b10-owner-01/` y `-02/`;
las respuestas completas y journals están en `h17-before-tick-b10-01/` y
`-02/`. `h17-before-tick-b10-summary/report.json` conserva ambos resultados.

| Intento | Owner | Primera operación observada | Acción / terminal | Contador | Gate |
|---|---:|---|---|---:|---|
| 1 | 78895 | Consulta 3: started=true, widget_triggered=true, elapsed_ms=0 | No se envió cancel; completó normalmente. | 0→1 | BLOCKED |
| 2 | 90797 | Consulta 3: started=false, widget_triggered=false, start_ns=null, elapsed_ms=0 | Se pidió cancel; terminal cancelled, pending_ack=false, pero started=true y widget_triggered=true. | 0→0 | BLOCKED |

La primera observación prueba por qué `elapsed_ms=0` no basta. El segundo
intento prueba que la ventana sin iniciar sí es observable, pero el tick ganó
entre observar y cancelar. No se atribuye un PASS pre-tick al terminal que ya
había disparado el widget. El job del segundo intento quedó cancelled,
cursor=0, con sólo el registro nativo y sin ejecutar el contador.

Los brackets del socket usan `python.time.monotonic`:

- Intento 1, snapshot previo: `[126593.829888125, 126593.840418625]` s.
- Intento 2, snapshot previo: `[126634.611957208, 126634.621283208]` s;
  petición cancel: `[126634.629893166, 126634.634503291]` s.

Se conservan los `start_ns` nativos en el JSON, sin hacer una resta entre
relojes no alineados. La conclusión procede de los flags nativos antes y
después, no de inferir el primer tick a partir del tiempo de la petición.

La sesión 1 es `02971a8083ac6214f39b23a828564b9f`; su journal tiene cuatro
entradas y completion `completed`, sin cancel_intent. SHA-256:
`30445759c612f960216ed3bd15b2d5b267598c81f941de2d3b8f5841448e9bf8`.
La sesión 2 es `f033f30f55e877b6d79e5b5bdf132fb3`; su journal tiene cinco
entradas: header, dispatch_intent, dispatch, cancel_intent y completion.
El token `f033f30f55e877b6d79e5b5bdf132fb3:animation:1:1` y el mismo action_key
aparecen en la cancelación y el terminal receipt del PID 90797; completion
es `cancelled` y receipt de mutación es null. SHA-256 del journal:
`c10dc8ea2c847534504375a30fa99e723d7234840add358c1f4397603f96098c`.
Esto confirma cancelación nativa posterior al tick, no el gate pre-tick.

Ambos owners cerraron con exit 0, cleanup PASS y sin errores. Los cinco
stores coinciden byte por byte con los originales actuales registrados al
abrir cada runner; journals históricos y propios permanecen. Los wrappers
dicen FAIL_RUNNER porque la cobertura BLOCKED devuelve exit 1: no hubo
fallo de cleanup ni un error de producto en estos intentos. La evidencia B7
posterior al tick permanece intacta y no se reetiqueta como anterior al tick.
