# H18 — binding visual y bootstrap

Adaptador independiente ejecutado con el **owner de prueba offline**, el contrato
real de Show Control y Goal Celebration original. No crea autoridad de Production,
no instala contenido de terceros y no ejecuta CEF. El dispatcher CEF queda pendiente.

## Componentes reutilizados

| Componente | Uso verificable |
|---|---|
| `motive-show-control::model::Event` | Parser y validación reales, sin copiar enums |
| `VerifiedIngress::simulation` / `AcceptedEvent` | Autoridad fuera del JSON para eventos sintéticos propios |
| H16 `projection::goal_message` | Proyección `goal-scored` → `goal.scored`, solo team/home/away |
| H16 `ipc::Gate` | Tipos, propiedades, secuencias, tamaño, deadline y cuota |
| H16 `Lifecycle` | Estado, cancelación, completion por secuencia y deadline |
| H16 `AssetBroker` + SDK `validate_web` | Inventario inmutable y hashes originales |
| Goal Celebration `goal.mjs` / `runtime.mjs` | Archivos originales sin modificación; API MotiveElement v1 |

`OfflineOwner::review_goal_fixture(FixtureReview)` crea una aprobación en memoria,
ligada a identidad del owner, sesión, revisión, binding, definición/hash e
instancia/generación. Ni el owner ni su aprobación implementan Deserialize.
Una revisión concurrente invalida la aprobación. El owner conserva un registro
acotado de generaciones por instancia: nunca reemite una generación usada y una
aprobación nueva invalida los handles anteriores. El único constructor es de QA
en el namespace `simulation.`; un identificador o `simulated:true` recibido de un
paquete nunca crea autoridad. El caller debe entregar un manifiesto previamente
validado por el broker; Gate valida el subcontrato que consume, no reemplaza el
schema/importador de Element Lab. El hash del manifiesto vincula sus inventarios
de assets, pero no prueba autoría, licencia ni confianza.

Antes de permitir el evento se entregan las propiedades revisadas y se exige su
acuse visual. El evento se admite solo en Ready y con el origen de ingress
aprobado. El crate Show Control conserva deduplicación, cooldown y scheduling;
este adaptador no crea otro bus, otro caché de eventos ni otro reloj audiovisual.
Los timestamps son monotónicos de control. La cola de acuses de JS tiene ocho
plazas; cancel/dispose liberan pendientes y conservan su entrada.

Un ACK solo informa `RendererAcknowledged`. No mueve la revisión del owner ni
termina la operación nativa. `visual_complete` únicamente libera el lifecycle
visual con identidad/secuencia vigente. Cancelación descarta esa secuencia;
revocación/cierre rechazan respuestas atrasadas. No hay replay automático ni
constructor de restart que acepte un booleano del renderer: se requiere otro
binding revisado y generación nueva después del reap externo.

## Bootstrap ejecutado

`web/port-adapter.mjs` es un módulo fijo del host. Adjunta un MessageChannel a la
ventana exacta del iframe con scripts y origen opaco. Transfiere el manifiesto y
un puerto mediante el bootstrap existente; los eventos y properties viajan como
objetos, jamás como texto JavaScript construido desde el payload. Respuestas son
formas finitas y acotadas, sin diagnósticos libres o comandos de Production.
Un iframe/MessagePort y CSP son defensa de interfaz; **no son un sandbox OS**.

`serve_fixture.py` sirve solo la fixture propia sobre `127.0.0.1`, con inventario
exacto y un proceso Rust `fixture_host` por generación. Su API verifica Host,
Origin y cabecera de fixture; el Origin opaco `null` del widget no la puede usar.
La API no acepta rutas, eventos arbitrarios ni código. Reutiliza los bytes del
broker H16; cambia únicamente `frame-ancestors` a `'self'` para admitir al padre
controlado y añade CORS a los assets del iframe opaco. No modifica el broker
original. No es un servidor de producto ni se expone a otras máquinas.

La conexión de HTTP a Rust tiene tamaño y deadline; al reiniciar se cierra stdin
y espera el proceso anterior, con terminación acotada si fuera necesaria. Los
tests prueban reap real de ese proceso Rust propio. No prueban procesos Chromium.
La comprobación de expiración del adaptador web usa el tiempo de admisión devuelto
por el fixture; **no certifica latencia/deadline extremo a extremo de IPC CEF**.
El host nativo debe usar un origen monotónico común y medir edad al recibir.

## Reproducir

Desde el worktree H18, con dependencias del lock disponibles localmente:

```sh
cargo test --offline --locked --manifest-path creator-runtime-lab/binding/Cargo.toml
cargo clippy --offline --locked --manifest-path creator-runtime-lab/binding/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path creator-runtime-lab/binding/Cargo.toml -- --check
cargo build --offline --locked --manifest-path creator-runtime-lab/binding/Cargo.toml --example fixture_host
node --test creator-runtime-lab/binding/tests/port-adapter.test.mjs
python3 -m unittest discover -s creator-runtime-lab/binding/tests -p 'test_*.py' -v
python3 creator-runtime-lab/binding/serve_fixture.py 8788
```

Usar **solo proxima-browser MCP** para abrir `http://127.0.0.1:8788/` y recorrer
los botones. `tests/browser-checks.js` contiene el procedimiento de 11 checks.
En esta Mac el MCP permite archivos bajo el checkout principal y su caché, pero
no el worktree hermano; se suministró el mismo procedimiento con el argumento
`code` soportado por `browser_run_code_unsafe`. No se cambiaron raíces, permisos,
AGENTS ni archivos de main. Detener el servidor con Ctrl-C al terminar.

## Evidencia y gates

Ver [checks](../evidence/binding/checks.json), [recorrido](../evidence/binding/browser-summary.json),
[trace](../evidence/binding/browser-trace.json), [consola](../evidence/binding/browser-console.json)
y [red](../evidence/binding/browser-network.json).

- **PASS:** 12 Rust, 5 Node, 5 Python; Clippy y formato. Son contratos/transportes offline.
- **PASS:** 11 comprobaciones DOM reales; H/V, evento proyectado, propiedades,
  cancel/resume, finalización visual, dispose y restart. Check adicional de
  movimiento reducido observado; capturas [H](../evidence/binding/goal-horizontal.png)
  y [V](../evidence/binding/goal-vertical-reduced.png). Cero errores de consola y
  requests del recorrido con HTTP 200; esto no acredita aislamiento de egress.
- **FAIL conservado:** la primera espera del test exigía visible a un widget
  cancelado, correctamente oculto. Se corrigió a attached sin cambiar el widget.
  Se conserva también el rechazo de lectura del archivo fuera de raíces MCP.
- **PARTIAL:** integración Show Control. Se usa su tipo/ingress/proyección real,
  pero el owner es de prueba y los eventos son sintéticos, no el scheduler vivo.
- **BLOCKED:** dispatcher CEF, peer/main-frame authentication, aislamiento OS,
  cualquier tercero y prueba de píxeles CEF/libobs/stream. Un ACK nunca acredita esos gates.

## Handoff mínimo

1. Tras handoff H17, implementar la construcción de autoridad desde la aprobación
   local real del owner, vinculada a definición, hash, source/instance, revisión,
   sesión y binding; no exportar el constructor de QA a MCP.
2. Integrar el módulo fijo en un documento externo controlado y enlazar la
   frontera de datos con `CefProcessMessage`, comprobando browser/frame/proceso,
   generación y peer, y usando Gate antes del renderer. No eval/ExecuteJavaScript
   con strings de payload. La fixture nativa H16 sigue con su inventario propio.
3. Registrar por separado admission, respuesta JS, paint y consumo libobs. Conservar
   incertidumbre/reconciliación; no inferir un resultado terminal de la respuesta visual.
4. Restablecer solo configuración revisada, desarmada, con generación nueva y sin
   eventos históricos; demostrar reap, deadlines y restricciones de procesos antes
   de autorizar terceros. Este crate no altera ningún formato de proyecto.

### Revalidación de la versión final

Después del cambio de generaciones `3ee09a1` se reconstruyó y repitió el recorrido
completo contra el binario actual: **11/11 DOM PASS**, movimiento reducido,
consola 0 errores/0 avisos y 37 requests HTTP 200. El
[manifiesto de procedencia](../evidence/binding/browser-final-provenance.json)
registra el SHA-256 del ejecutable, 46 archivos de fuente/dependencias locales,
HEAD observado y hashes de los resultados y capturas. Las fuentes y el binario
no cambiaron durante la prueba; los cinco assets originales coinciden con sus
hashes declarados. El resultado está en [browser-final.json](../evidence/binding/browser-final.json),
con capturas [horizontal](../evidence/binding/goal-final-horizontal.png) y
[vertical reducido](../evidence/binding/goal-final-vertical-reduced.png).
Se observó `disposed`, MessagePort cerrado y ausencia de los dos procesos propios
servidor/fixture después del cierre. Los resultados anteriores se conservan.

### Documento fijo para el candidato CEF — etapa separada

`web/native-bootstrap.html`, `.css` y `.mjs` preparan el documento externo
controlado del candidato CEF. El host sirve el HTML en `/host/index.html` y sus
módulos bajo `/host/`; los bytes originales del widget se autorizan como inventario
exacto bajo `/widget/`. El módulo no carga URLs suministradas por el creador.
Comprueba que identidad/generación, ubicación del host y entrada coincidan.

El renderer principal recibe del adaptador CEF una única función nativa
`motiveNativePostStatus`. El módulo captura esa referencia, publica el objeto
inmutable `MotiveNativeVisual` y envía `{kind:'bootstrap_loaded'}`. El browser
puede entonces invocar `initialize({identity,contract,entry})`,
`deliver(envelope, nowMs)` y `revoke()` mediante **valores CefV8Value**, sin eval ni
strings de JavaScript interpolados. La implementación C++ debe verificar
browser/frame/proceso emisor y generación antes de invocar esos métodos. Todas
las respuestas posteriores conservan los tipos existentes `renderer_ready`,
`visual_ack` y `visual_state`; no prueban un resultado terminal nativo.

[Cinco tests Node](../evidence/binding/native-bootstrap.json) pasan con
MessageChannel real y el runtime MotiveElement original: datos tipados incluyendo
texto con delimitadores de script, finalización visual/secuencia, cancelación,
reanudación, disposición, supresión de completion tardía, rechazo de generación
antigua y URLs/configuraciones ajenas. Son pruebas del adaptador y del contrato;
**no se ejecutó este nuevo documento en CEF ni en otro navegador**. El candidato
nativo separado requiere su propia evidencia de compile/link en `web-host-lab/`
y una autorización específica para cualquier ejecución de Goal Celebration.
Una excepción concedida para la fixture H16 original no lo cubre.

La fixture DOM anterior, su binario y sus 46 archivos registrados no cambiaron
al añadir este módulo; su evidencia final permanece acotada al recorrido de
`fixture.mjs`. No se extrapola a este documento, a OnPaint, sandbox, libobs o
Production. Reproducir el nuevo contrato sin navegador:

```sh
node --test creator-runtime-lab/binding/tests/native-bootstrap.test.mjs
```
