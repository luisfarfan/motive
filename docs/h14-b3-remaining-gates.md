# H14 — B3: ejecución pendiente y rutas de verificación

Este documento planifica pruebas posteriores al soak B3; **no declara nuevas
aceptaciones físicas**. El PID 32487 está reservado para lifecycle 1080p60 y
dual-soak de 1800 s en `var/evidence/h14-memory-b3-60-soak-01`. No ejecutar
otro runner, fixture, análisis FFmpeg o build mientras el coordinador no
libere esa ventana. El binario B3 permanece sin cambios.

## Adaptación portable de los runners existentes

[verification_paths.py](../scripts/verification_paths.py) separa bundle,
cliente, datos y grabaciones de `ROOT` (checkout, fixtures y evidencia). Sin
variables conserva las rutas históricas de desarrollo. Para portable requiere
las tres variables, rutas absolutas, marcador/plist válidos, ejecutable dentro
del bundle y datos/grabaciones correspondientes exactamente al HOME actual.
No modifica HOME, permisos, `.deps`, bundle ni enlaces de `target`.

```sh
env MOTIVE_TEST_APP=/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app \
  MOTIVE_TEST_DATA_ROOT='/Users/luisfarfan/Library/Application Support/local.motive.studio' \
  MOTIVE_TEST_RECORDINGS_ROOT=/Users/luisfarfan/Movies/Motive \
  python3 scripts/verify_h13_regressions.py --lock-held \
  --suite verify_control.py --suite verify_control_delivery.py
```

Las variables deben llegar también a los subprocesos de suites. No existe
override de socket: se deriva de `DATA_ROOT/run/motive.sock`. Cliente CLI/MCP y
owner portable usan el mismo ejecutable firmado. Evidencia, venv de pruebas y
fixtures continúan en el worktree; FFmpeg, Python/Pillow y herramientas de
fixture son dependencias del **harness**, no de Motive.

Se adaptaron 34 scripts/helpers mediante cambios de rutas. La auditoría AST
conserva **751 asserts** y sus constantes numéricas. Cuatro asserts cambian
expresión: tres validaciones de lock y una comparación de bytes persistidos
que ahora apunta al store real. El runner H13 registra las rutas y admite el
lock canónico H14 con worktree exacto solo en modo portable. Añade barreras
previas para destino seleccionado, enrollment/reconciliación pendiente y Show
Control configurado. La comprobación de ownership de outputs H13 limita MKV
al directorio de grabaciones y RTMP recibido al directorio propio del ensayo.
No se cambiaron duraciones, tolerancias, recortes, medios ni asserts de audio
y video. Ocho tests del resolver y sintaxis Python pasan; esto **no prueba la
ejecución portable de las suites**.

Evidencia offline: `var/evidence/h14-portable-runner-static/` contiene
`mechanical-edits.json` y `semantic-audit.json`. Se validaron las rutas reales
del B3 y el lock leyendo marker/plist, sin abrir ni consultar el owner.

## Secuencia H1–H12 recomendada

Usar `verify_h13_regressions.py`, que verifica firma/UUID/hash, hace backup de
los tres stores con bytes/modos, reinicia un owner default por suite, espera
ambas barreras nativas y conserva un manifiesto nuevo. El estado inicial debe
ser disposable: patrones/overlay legado, mixer vacío, sin recuperación ni
credenciales seleccionadas. No ejecutar sobre MATCHDAY configurado. No usar
los coordinadores H10/H11/H12/UI antiguos: tienen barreras históricas más
limitadas; el de UI además exige su lock antiguo `UI task:`.

Los tiempos siguientes son las últimas entradas PASS **históricas de H13**,
no promesas ni resultados B3. Suman 1091 s (18 min 11 s) sin preparación ni
reinicios; reservar 25–35 minutos más contingencias. El timeout del runner es
420 s por legado y 900 s por overlay/performance. Se puede reanudar con
`--suite` repetido en un manifiesto nuevo, conservando el fallo anterior.

| Suite | H13 aprox. s | Dispositivo/fixture y efectos relevantes |
|---|---:|---|
| `verify_control.py`, `verify_control_delivery.py` | 1 + 1 | CLI/MCP/socket; sin dispositivos |
| `verify_h1.py` | 22 | Cámara + micrófono explícitos, fixture de ventana y altavoz propio |
| `verify_scenes.py` | 34 | Cámara/ventana; guarda proyecto y reinicia |
| `verify.py` | 79 | Ventana de prueba propia; MKV/UDP local; guarda proyecto |
| `verify_encoding.py` | 251 | Patrones/tono; x264/VT, PCM, perfiles |
| `verify_encoding_fallback.py` | 12 | Reinicia con `open --env MOTIVE_DISABLE_VIDEOTOOLBOX`; restaura modo |
| `verify_output_recovery.py` | 11 | Error/recuperación de salida controlado |
| `verify_rtmp.py`, `verify_rtmps.py` | 44 + 1 | Loopback; rechazo TLS, no destino externo |
| `verify_connect_stop.py`, `verify_vt_stop.py` | 1 + 63 | Connecting/cancelación y cierre VT |
| `verify_profiles_restart.py` | 2 | Guarda/restaura perfiles/proyecto; reinicia |
| `verify_h8_lifecycle.py` | 48 | Receptor/proxy propios; fallos y reapertura |
| `verify_h8_keychain.py` | 2 | Keychain con claves aleatorias propias; firma ad hoc de copia de helper; no cambia B3 |
| `verify_h9_transitions.py` | 48 | Cámara/ventana, Cut/Fade y persistencia/reinicio |
| `verify_h9_faults.py` | 28 | Pérdida de fixture y recuperación; reinicia |
| `verify_h10_audio.py` | 33 | Micrófono explícito + sonido propio en altavoz; guarda mixer |
| `verify_h10_mixer.py` | 110 | Micrófono + tono, ganancia/mute, RTMP, desconexión lógica y reinicio |
| `verify_h11_runtime.py --transport both` | 101 | Animaciones/widgets/presets; MKV/RTMP; Pillow |
| `verify_h11_visuals.py --with-video` | 35 | PNG/video propios; importación; el coordinador selecciona x264 |
| `verify_h11_lifecycle.py` | 11 | Assets ausentes/migración/persistencia; escrituras de store y reinicio |
| `verify_h12_performance.py` | 154 | Cuatro decodificadores; crea clip antes de medir, carga proyectos por API |

`--stage legacy` incluye los primeros 19; exige `--camera-id ID
--camera-prepared --microphone-id ID`. `--stage overlays` incluye los tres H11;
`--stage performance` ejecuta H12. IDs proceden del inventario real observado,
sin selección automática. Las fixtures H1/H9 pueden construir/abrir su propia
app; ninguna reconstruye Motive. Las pruebas de micrófono reproducen tonos
por el altavoz, por lo que no son equivalentes a pruebas silenciosas de mixer.

**No importar estos scripts para descubrir opciones ni invocarlos con
`--help` sin revisión:** varios legados ejecutan operaciones al nivel de módulo.
El planificador debe mantener una lista declarativa; solo `execute` inicia
sus procesos. Todas las ejecuciones físicas son seriales.

## H13/H14 adicionales después del soak

| Gate / runner | Flags y duración mínima orientativa | Prerrequisitos / límites |
|---|---|---|
| Canvas H/V y Cut/Fade: `verify_h13_video.py` | `--matrix`: 7 tomas de ~10 s, más decodificación (reservar 3–5 min) | Pattern/tone/PNG. **Guarda proyecto y no restaura graph/assets**; backup externo y owner disposable obligatorios |
| Dual + recuperación: `verify_h13_outputs.py` | `--lock-held --stage all`; reservar 4–8 min, no repetir soak | Incluye receiver-loss y muxer-loss intencionales sobre procesos propios; acepta medios parciales solo en esos casos |
| Audio aplicación: `verify_h13_system_audio.py` | `--stage pilot --stage rtmp --stage recovery --stage transitions --stage persistence`; ~2–4 min más decode | Fixture H13 precompilada, permiso normal de pantalla/audio; reproduce audio propio y reinicia solo fixture |
| Silencio/A-V: mismo runner | `--stage silence --stage av`; 36 s por secuencia más setup/decode | A/V depende de frescura de ventana; falla o queda parcial si continúa suspended; no saltar ese gate |
| Mic + sistema: mismo runner | `--stage microphone --microphone-id ID` | Captura física autorizada; separar de otras pruebas |
| Exclusión del propio proceso: `verify_h13_self_audio_exclusion.py` | `--display-uuid UUID --motive-log LOG --controlled-desktop-audio`; reservar 1–3 min | Owner específico iniciado con `MOTIVE_TEST_SELF_AUDIO=1`; después cerrar/reabrir sin ese env. No reutilizar owner ordinario sin emisor |
| Piso de audio: `verify_h13_self_audio_floor.py` | Secuencia 24 s; flags de owner/log explícitos | Control condicionado, **no aceptación de exclusión**; sin test emitter y desktop controlado |
| Cola de cierre: `verify_h13_shutdown_queue.py` | `--lock-held --attempt 1` y `2`, owners distintos; ~30–60 s cada uno | Cierra el owner; no recupera automáticamente una app viva no responsiva |
| Importación durante cierre: `verify_h13_import_shutdown.py` | `--lock-held --clip CLIP --timeout-seconds 90` | Clip propio bajo evidencia; cierra owner, puede conservar asset importado y receipt no observado |
| Contabilidad H14: `verify_h14_output_integrity.py` | `--app EXE --store-root DATA --lock-held`, casos del `--plan`; 15 × 8 s activos más cierre/decode | Separar stop/cancel/receiver-loss/shutdown y VT reorder on/off/x264; no heredar PASS de H13/B2 ni normalizar deficits |
| Captura/foco: `verify_h14_collection.py` | `run/mark/analyze`, A→B→A, 45–60 s cada brazo | PID/window exactos, fixture separada, marcas de foco del root. Análisis posterior; no atribuye causa global a Stage Manager |
| Show Control/MATCHDAY: `verify_h14_show_control.py` | `--app EXE --data-dir DATA --lock-held --await-ui-goal --output NUEVO` | Instalación/revisión GPUI y evento real; no owner default del bloque legacy. Conservar MKV/RTMP y cooldown/duplicados/concurrencia |
| Portable: `verify_portable.py` | Bundle B3 + `--smoke-tools`; segundos | Solo después de medir; no firma ni rebundle. Firma/closure locales no equivalen a notarización/segunda Mac |

Las rutas explícitas H14 `--app` esperan el ejecutable; `MOTIVE_TEST_APP` del
helper espera el bundle. Los nuevos runners H14 conservan sus contratos de
flags; esta adaptación no los cambia. Para H13 independientes, aplicar las
mismas variables del helper y preparar/restaurar stores de forma explícita:
no todos ofrecen el backup completo del coordinador H1–H12.

## Gates de entrega que siguen separados

El índice `h14-beta-verification.md` contiene estados previos B1/B2 y necesita
reconciliación final, sin borrar fallos originales. B3 dispone de persistencia
real GPUI en `var/evidence/h14-persistence-b3-01`: el coordinador informó
igualdad exacta de proyecto/reglas tras reabrir y ausencia de outputs
automáticos. No sustituye el recorrido GPUI completo ni VoiceOver/Dock Quit.

- Captura: no cerrar el P0 mientras la congelación/suspensión reproducible
  permanezca sin diagnóstico/tratamiento seguro y prueba de píxeles frescos
  en MKV/RTMP. El ensayo A/B no es una corrección por sí mismo.
- Outputs: conservar diferencia entre integridad audiovisual, cutoff,
  contadores previos al plugin y entrega. Reordering con fallo reproducible
  mantiene su clasificación aunque el perfil por defecto lo evite.
- Memoria: B3 30 FPS está documentado; el soak/60 FPS no tiene resultado hasta
  finalizar, decodificar y analizar. El presupuesto RPC sigue excedido.
- RTMPS: la prueba privada B2 tiene observación del usuario y MKV; no es
  decodificación remota ni aceptación sobre B3. Cualquier repetición requiere
  la autorización local específica del destino/inicio, no una regla ni el suite.
- Distribución: firma/closure/rutas son gates locales; notarización, segunda
  Mac y reconstrucción del material correspondiente permanecen explícitos.
- Voz: benchmark sintético offline parcial, fiabilidad insuficiente y voz en
  vivo no implementada. Es opcional P2 y no debe convertirse en dependencia.
- Aceptación final: identificar binario, scripts, hashes y resultados de cada
  gate sobre B3. Un `control PASS`, un test estático o un runner legacy verde
  no declara la beta aceptada.
