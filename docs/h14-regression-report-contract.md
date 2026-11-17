# H14 — Contrato de informes primarios de regresión

El wrapper `scripts/verify_h13_regressions.py` exige ahora tres comprobaciones
independientes antes de aceptar cada suite: el proceso termina con código cero,
el owner observado satisface la barrera nativa existente, y la copia nueva de su
informe principal reconoce éxito sin fallos de limpieza reportados. Las
aserciones originales y las tolerancias de medios no se modifican.

El gate cierra un falso positivo real: H1, scenes, encoding, encoding fallback,
RTMP, RTMPS, connect-stop, VT-stop, profiles-restart, H9 transitions, H9 faults,
H10 audio y H10 mixer podían escribir `ok: true` junto con `cleanup_error` y salir
con código cero. H8 Keychain utilizaba `cleanup_required_reference`. Recuperar
el estado desde el wrapper no convierte en exitosa esa limpieza fallida.

## Selección de evidencia

Solo son elegibles las copias que el wrapper acaba de retener en
`reports/<suite>/…` porque el archivo fue creado o cambió durante ese proceso.
La selección requiere exactamente un informe con el nombre de la tabla. No
busca el informe histórico más reciente ni usa un alias actualizado después de
la copia. Los directorios dinámicos requieren un sufijo decimal y exactamente
dos componentes de ruta; no aceptan informes de subetapas.

| Suite | Informe principal relativo a `var/evidence` |
|---|---|
| `verify_control.py` | `control-integration.json` |
| `verify_control_delivery.py` | `h9-control-delivery.json` |
| `verify_h1.py` | `h1-acceptance.json` |
| `verify_scenes.py` | `scene-acceptance.json` |
| `verify.py` | `acceptance.json` |
| `verify_encoding.py` | `encoding-comparison.json` |
| `verify_encoding_fallback.py` | `encoding-fallback.json` |
| `verify_output_recovery.py` | `output-recovery.json` |
| `verify_rtmp.py` | `h7-rtmp.json` |
| `verify_rtmps.py` | `h7-rtmps.json` |
| `verify_connect_stop.py` | `h7-connect-stop.json` |
| `verify_vt_stop.py` | `h7-vt-stop.json` |
| `verify_profiles_restart.py` | `h7-profiles-restart.json` |
| `verify_h8_lifecycle.py` | `h8-lifecycle.json` |
| `verify_h8_keychain.py` | `h8-keychain.json` |
| `verify_h9_transitions.py` | `h9-transitions.json` |
| `verify_h9_faults.py` | `h9-faults.json` |
| `verify_h10_audio.py` | `h10-pilot.json` |
| `verify_h10_mixer.py` | `h10-mixer.json` |
| `verify_h11_runtime.py` | `h11-runtime.json` |
| `verify_h11_visuals.py` | `h11-visuals.json` |
| `verify_h11_lifecycle.py` | `h11-lifecycle-*/report.json` |
| `verify_h12_performance.py` | `h12-performance-*/report.json` |

En H11 runtime y visuals se usa el alias fijo que escribe la misma invocación;
las copias de `run/report.json` y los informes de subetapas permanecen como
evidencia adicional.

## Resultado separado del proceso

Cada entrada del manifest conserva `exit_code` y añade `primary_acceptance` con
`status`, `path`, `evidence_relative`, SHA-256, `issues` y el alcance de la
comprobación. Se verifica el hash de la copia antes de leer su JSON. Un informe
faltante, ambiguo, modificado, mal formado o sin `ok` booleano verdadero falla.
Cuando el informe contiene `app_sha256` o `bundle_sha256`, también debe coincidir
con la identidad que ya validó el wrapper.

Se rechazan exclusivamente estos indicadores de fallo en el nivel superior:
`error`, `cleanup_error`, `cleanup_errors` no vacío,
`cleanup_required_reference`, `reopen_error` y `app_sha256_error`. No se recorre
el árbol buscando palabras como `error` o `failure`: rechazos TLS, respuestas
negativas de validación, pérdidas deliberadas y errores de fixtures pueden ser
el resultado esperado de una prueba. `cleanup_note` informativo tampoco falla.
Las cadenas privadas del error no se duplican en la evaluación; siguen en el
informe original retenido.

Un fallo conserva el manifest fallido y todos los originales copiados. No
reescribe evidencia histórica ni rebaja una aserción del runner. La ausencia de
un campo de fallo por sí sola no demuestra que toda limpieza ocurrió: siguen
siendo necesarias las barreras y la restauración observadas por el wrapper.

## Limpieza del fixture H8 Keychain

La prueba comprueba ahora el recibo de borrado (`ok` booleano verdadero,
`result == 0`, referencia esperada). Un rechazo o excepción conserva la
referencia opaca que necesita limpieza y un código acotado; no copia el payload
ni el dummy secreto. Los fallos al deseleccionar la credencial y cerrar el
cliente se registran. Si solo falla la limpieza, la aserción final falla después
de guardar el informe. Si ya falló el cuerpo de la prueba, su excepción original
se propaga después de `finally` y no queda reemplazada por esa aserción.

## Verificación del contrato

- 13 pruebas JSON/archivos temporales del mapa, frescura, fallos principales,
  errores negativos anidados permitidos, hashes y copias inmutables.
- 6 pruebas del recibo de borrado y el bloque `finally` aislado mediante AST:
  ack rechazado, informe anterior a la excepción, conservación de la excepción
  original, cierre/deselección fallidos y ausencia de payload privado.
- Ninguna prueba importa el runner legacy ni llama a Motive, Keychain, PTY,
  dispositivos, FFmpeg o una salida. Las pruebas físicas siguen pendientes de
  la ejecución coordinada sobre el bundle candidato.
