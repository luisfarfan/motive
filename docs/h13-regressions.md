# H13 — ejecución de regresiones H1–H12

Estado: adaptación revisada; primera ejecución parcial interrumpida para
corregir el cierre legacy. **H8 lifecycle pasa en el bundle corregido**;
resto de la matriz final pendiente.
El manifiesto final debe referir al bundle firmado integrado, no al resultado
de parsing Python ni a una ejecución H12 anterior.

## Cambios de contrato acotados

| Archivo | Cambio |
|---|---|
| `scripts/verify_rtmp.py` | `canvas.fps_configurable` y `production_resolution_configurable` son `true`; la resolución por perfil sigue prohibida. Verifica los 30 FPS del ensayo. Conserva rechazo de geometría/FPS extra en perfiles, fallos RTMP y controles exclusivos heredados. |
| `scripts/h7_support.py` | `assert_project_format` exige versión exacta: v3/v4 cuando la configuración inicial no tenía `video`; v5 con el mismo snapshot `video` cuando sí lo tenía. No deduce el esperado del documento bajo prueba. |
| `scripts/verify_encoding.py`, `verify_encoding_fallback.py` | Aplican ese check al proyecto guardado, conservando igualdad exacta tras load/restart y todos los gates de encoder/medios. |
| `scripts/verify_h11_visuals.py`, `verify_h11_runtime.py` | Verifican v4 real desde default y admiten la envoltura v5 explícita sin perder configuración. El nombre del artefacto de presets refleja su versión real. |
| `scripts/verify_h11_lifecycle.py` | Verifica la misma regla al guardar; construye y carga una fixture v3 auténtica sin campo `video`, comprueba igualdad exacta y retorno a 540p30 según orientación. Conserva recuperación de recurso, IDs, mixer/perfiles y documento grande. |
| `scripts/verify_h13_regressions.py` | Runner serial, nuevo manifiesto y copia de reportes por suite; preparación/restauración explícitas y lock compartido existente. |

Los guards antiguos de exclusión siguen siendo correctos: `start_recording` y
`start_stream` rechazan `OUTPUT_BUSY` si ya existe una salida ocupada. No se
cambian por las operaciones concurrentes de H13. El rechazo de stop ambiguo con
dos salidas y la supervivencia por destino tienen su propia suite H13.

Los umbrales PCM/RMS, píxeles, frames, PTS/DTS, drops, clipping, errores,
instancias nativas y tiempos de las suites previas no se modificaron.

## Runner y restauración

El runner verifica el owner del lock canónico, la firma y los hashes de ambos
binarios. Compara el UUID Mach-O del cliente legacy con el owner firmado: los
bytes pueden diferir por la firma, pero deben representar el mismo build.
Exige una producción inicial sana con patrones/overlays legacy y mixer vacío.
Guarda los tres stores con bytes y modos, y snapshots del estado controlado.

Antes de cada suite reinicia únicamente con ambos slots nativos quiescentes.
Verifica el arranque real v3 sin `video`, 960×540/30 FPS y mixer vacío; no invoca
`configure_video`. Así las suites H11 continúan creando v4 real. La configuración
v5 y sus migraciones se verifican además mediante `verify_h13_video.py`.

Un fallo detiene la secuencia y conserva reportes/logs. Si vence el timeout, se
termina únicamente el grupo de procesos propio del verificador, incluidos sus
clientes MCP/receptores; la app iniciada por LaunchServices tiene su ciclo
separado. La restauración final solicita cancelación si hay salida ocupada y
espera ambas barreras antes de escribir stores o reiniciar el estudio. Luego
restaura el estado inicial controlado y los bytes/modos originales. Si el owner
no responde o no termina de drenar, registra el bloqueo y conserva los backups;
no considera segura una restauración a ciegas. Las fixtures AppKit iniciadas por
LaunchServices que un timeout haya dejado abiertas requieren inspección manual.

## Ejecución autorizada por el dueño del lock

Desde el worktree H13, con cámara integrada preparada y los IDs ya confirmados:

```sh
python3 scripts/verify_h13_regressions.py --lock-held --camera-prepared \
  --camera-id "$MOTIVE_CAMERA_UID" --microphone-id "$MOTIVE_MIC_UID"
```

`all` incluye las 22 suites del manifiesto H12 y `verify_h12_performance.py`
(23 suites). Los grupos `legacy`, `overlays` y `performance`, o `--suite` repetido,
permiten ejecutar incrementos con sus duraciones originales. Por ejemplo:

```sh
python3 scripts/verify_h13_regressions.py --lock-held --suite verify_rtmp.py
python3 scripts/verify_h13_regressions.py --lock-held --stage overlays
```

No se instalan dependencias: por defecto se usa `var/verify-python/bin/python`
para H11/H12. `--verification-python /ruta/absoluta/al/venv/bin/python` permite
reutilizar explícitamente un venv existente; el coordinador H14 reenvía la misma
opción. Antes de consultar o reiniciar el owner se comprueban, solo para esos
grupos, el intérprete, su prefijo de venv y Pillow 12.0.0 mediante imports aislados
sin escribir bytecode. El manifest conserva `sys.executable`, prefijo, versión
de Python y versión/ruta de Pillow. Los subconjuntos legacy no requieren ese
venv. Se conserva la ruta `bin/python` al ejecutarla: resolver su enlace final
al Python global perdería la selección del entorno.

Cámara y micrófono se validan por los IDs
explícitos contra el inventario y los permisos reales de macOS. La bandera de
cámara declara la preparación ya confirmada, no modifica TCC ni concede permiso.

## Verificación disponible y pendiente

Parsing AST de los ocho archivos modificados/nuevos y `git diff --check`: PASS.
El helper de schema pasó cuatro casos válidos y cuatro rechazos puros, extraído
del AST sin importar suites ni contactar con la app.

Primera ejecución en
`var/evidence/h13-regressions-1794937405785377000/manifest.json` sobre el bundle
`f9e0b286…45570c`: control, entrega de mensajes y H1 pasan (1,8 / 0,9 / 22,4 s).
Root interrumpió el runner durante scenes para reconstruir tras la revisión de
shutdown; no se etiqueta esa suite incompleta como fallo multimedia. El runner
cerró su proceso hijo, esperó las salidas y restauró estado y bytes de stores,
sin errores de cleanup. Manifest global permanece incompleto/FAIL.

La ejecución dirigida posterior de H8 pasa en
`var/evidence/h13-regressions-1794937943048758000/manifest.json`, bundle
`d9b8d702…0e2d93`, 47,6 s y 14 ciclos. Añade comprobaciones de ambos destinos,
preflight e importación tras solicitar cierre; las consultas siguen respondiendo
y el proceso termina después de liberar el peer. Restauración sin errores.

Pendiente: completar la matriz serial real, verificar restauración de bytes/modos
y estado, observar cámara y micrófono preparados, repetir permisos denegados solo
si ese es el estado real de macOS, y conservar límites de desconexión física.
El recorrido nativo H12 (gestos, formularios, stale revision, UI-origin) y su
análisis `verify_h12_native_media.py` continúan siendo gates manuales separados.
La aceptación dual GPUI/H13 y la sesión prolongada tampoco se sustituyen por
este runner.
