# H14 — B3: ejecución pendiente y rutas de verificación

Este documento planifica las pruebas restantes; **no declara nuevas
aceptaciones físicas**. El soak B3 ya terminó y el PID 32487 salió normalmente.
Su análisis conserva el resultado PARTIAL; véase
[la verificación de memoria/soak](h14-memory-b3-soak-verification.md).
Las 23 regresiones H1–H12 seleccionadas ya tienen evidencia B3 consolidada en
[su informe](h14-b3-regressions-verification.md), con el primer fallo preservado.
Cada siguiente ventana física pertenece exclusivamente al coordinador; este
plan no autoriza ejecutar durante otro ensayo. El binario B3 permanece sin cambios.

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
y video. Ocho tests del resolver y sintaxis Python pasaron en ese checkpoint;
la ejecución física posterior se documenta por separado en el informe B3.

Evidencia offline: `var/evidence/h14-portable-runner-static/` contiene
`mechanical-edits.json` y `semantic-audit.json`. Se validaron las rutas reales
del B3 y el lock leyendo marker/plist, sin abrir ni consultar el owner.

## Secuencia H1–H12 conservada como referencia

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

## H13/H14 adicionales

| Gate / runner | Flags y duración mínima orientativa | Prerrequisitos / límites |
|---|---|---|
| Canvas H/V y Cut/Fade: `verify_h13_video.py` | `--matrix`: 7 tomas de ~10 s, más decodificación (reservar 3–5 min) | Pattern/tone/PNG. **Guarda proyecto y no restaura graph/assets**; backup externo y owner disposable obligatorios |
| Dual + recuperación: `verify_h13_outputs.py` | `--lock-held --stage all`; reservar 4–8 min, no repetir soak | Incluye receiver-loss y muxer-loss intencionales sobre procesos propios; acepta medios parciales solo en esos casos |
| Audio aplicación: `verify_h13_system_audio.py` | `--stage pilot --stage rtmp --stage recovery --stage transitions --stage persistence`; ~2–4 min más decode | Fixture H13 precompilada, permiso normal de pantalla/audio; reproduce audio propio y reinicia solo fixture |
| Silencio/A-V: mismo runner | `--stage silence --stage av`; 36 s por secuencia más setup/decode | A/V depende de frescura de ventana; falla o queda parcial si continúa suspended; no saltar ese gate |
| Mic + sistema: mismo runner | `--stage microphone --microphone-id ID` | Captura física autorizada; separar de otras pruebas |
| Exclusión del propio proceso: `verify_h13_self_audio_exclusion.py` | `--display-uuid UUID --motive-log LOG --controlled-desktop-audio`; reservar 1–3 min | Owner específico iniciado con `MOTIVE_TEST_SELF_AUDIO=1`; después cerrar/reabrir sin ese env. No reutilizar owner ordinario sin emisor |
| Piso de audio: `verify_h13_self_audio_floor.py` | Secuencia 24 s; flags de owner/log explícitos | Control condicionado, **no aceptación de exclusión**; sin test emitter y desktop controlado |
| Cola de cierre: `verify_h13_shutdown_queue.py` | `--lock-held --attempt 1`; segundo intento solo si hace falta, con owner distinto; ~30–60 s cada uno | Máximo dos intentos; cierra el owner y no recupera automáticamente una app viva no responsiva |
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

## Secuencia concreta de los H13 independientes

Revisión estática de los runners, sin ejecutarlos. Los comandos siguientes son
**pasos separados**, con comprobación y restauración entre ellos; no un bloque
para ejecutar sin supervisión. El intérprete existente incluye Pillow, que
`video` y `outputs` importan incluso antes de procesar argumentos. `python3`
del sistema no lo sustituye. No instalar paquetes ni modificar el bundle.

```sh
cd /Users/luisfarfan/Developer/products/motive-h14
H14_VERIFY_PYTHON=/Users/luisfarfan/Developer/products/motive-h12/var/verify-python/bin/python
motive_h14_test() {
  env MOTIVE_TEST_APP=/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app \
    MOTIVE_TEST_DATA_ROOT='/Users/luisfarfan/Library/Application Support/local.motive.studio' \
    MOTIVE_TEST_RECORDINGS_ROOT=/Users/luisfarfan/Movies/Motive \
    "$H14_VERIFY_PYTHON" "$@"
}
```

Conservar el FFmpeg/FFprobe histórico del **harness** en PATH y registrar sus
rutas, versiones y hashes. Los receptores RTMP de estos runners usan ese
FFmpeg; cambiarlo al portable sería una variante del ensayo. La opción
`--disable-network` de `target/portable-tools/manifest.json` **no demuestra**
que el binario portable carezca de RTMP: se compilan los programas, enlazados
con las dylibs oficiales OBS sin reconstruirlas
(`scripts/build_portable_media_tools.py:96–108`). De hecho el manifest de
`h14-collection-b3-B-run` identifica el receptor B3 y produjo `received.mkv`
por RTMP. Se conserva PATH por continuidad de H13, no por una incapacidad
de red del bundle. Las herramientas externas son dependencias del ensayo,
no dependencias externas del producto.

### Aislamiento y restauración comunes

Antes de cada owner de ensayo: verificar el lock canónico H14 y el ejecutable
B3 SHA-256 `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
Retener PID, ruta y estado inicial. Ambas salidas deben estar idle y
`native_busy=false`, sin recuperación, importación, animación, shutdown,
enrollment/reconciliación, destino seleccionado ni Show Control armado o
configurado. Usar proyecto default v3 / 960×540 / 30 FPS, una escena con
pattern/overlay legado y mixer vacío. No cargar MATCHDAY para estos runners.

El coordinador conserva antes los bytes, existencia y modos de
`project.json`, `audio-mixer.json` y `output-profiles.json`, y un inventario/hash
del catálogo `assets/index.json`; las reglas Show Control y los destinos deben
permanecer intactos. Preparar el default sin llamar `configure_video`, porque
eso promueve el proyecto a v5 y elimina la precondición v3 de import/shutdown.
No confiar en que cerrar/reabrir por sí solo revierta un `save_project`.

Después de cada runner: retener su report, exit code, logs y hashes; verificar
ambas barreras nativas, mixer y recursos propios, y terminar normalmente el
owner exacto antes de restaurar stores mediante reemplazo atómico y comprobar
bytes/modos/existencia. Abrir un owner nuevo y verificar que no se inicia
ninguna salida. Si hay un owner vivo no responsivo o un worker activo, dejar
los backups intactos y registrar el bloqueo; no forzar cierre ni restaurar
stores sobre ese proceso. No sobrescribir ni borrar todo el catálogo de
assets: registrar las adiciones/deduplicaciones y conservarlas salvo que se
demuestre que son propias y que no están referenciadas. Ninguno de los seis
runners reemplaza este aislamiento externo completo.

### 1. Matriz de video

```sh
motive_h14_test scripts/verify_h13_video.py --matrix
```

Usar exactamente los defaults junto a `--matrix`: siete casos, VT 720p30 y
1080p30/60 H/V más x264 1080p30 H. Combinar `--matrix` con un preset inicial
distinto puede duplicar un caso y omitir 720p30 H por cómo se construye la lista
(`verify_h13_video.py:165`). No tiene flag ni verificación interna de lock;
lo garantiza el coordinador.

**Gate externo obligatorio:** siete trials `ok=true`, `report.ok=true`, sin
`error` ni `cleanup_error`, más ambas barreras idle. El `finally` solo intenta
detener la salida y cerrar MCP; no elimina escenas, overlays, tono o asset ni
restaura proyecto, encoder o transforms. Además puede conservar `ok=true` y
exit 0 cuando registra `cleanup_error` (`:219–226`). Guarda el proyecto en
cada caso, por lo que se restaura el backup antes del siguiente owner. Sus
tolerancias históricas del tail no prueban entrega completa H14.

### 2. Outputs, recuperación y supervivencia de la otra salida

```sh
motive_h14_test scripts/verify_h13_outputs.py --lock-held --stage all \
  --recording-encoder videotoolbox --streaming-encoder videotoolbox
```

Ejecuta smoke, production, receiver-loss y muxer-loss; conserva holds de 3 s,
steady de 8 s y `--soak-seconds 0`. No repetir el soak de 30 minutos. Los dos
encoders explícitos evitan que un fallback `auto` cambie la interpretación del
ensayo; los perfiles propios usan `frame_reordering=false`. El flag de lock es
una declaración del caller, no valida por sí mismo OWNER.

Gate: exit 0, `ok=true`, cuatro casos verdes, `cleanup_errors=[]`,
`analysis_errors=[]`, hash final idéntico y ambas salidas sanas idle. Este
runner cancela/espera workers y elimina recursos/perfiles propios, pero su
restauración de canvas promueve v3 a v5, avanza IDs y conserva endpoint loopback
cuando el inicial era null (`:638–674`). Usar el siguiente owner fresco. Los
medios parciales de los dos fallos intencionales no equivalen a finalización
limpia ni contabilidad de entrega completa.

### 3. Audio del sistema

Con `H14_MICROPHONE_ID` obtenido del inventario observado, sin selección
automática ni cambio de permisos:

```sh
motive_h14_test scripts/verify_h13_system_audio.py \
  --stage pilot --stage rtmp --stage recovery --stage transitions \
  --stage persistence --stage silence \
  --stage microphone --microphone-id "$H14_MICROPHONE_ID"
```

Este grupo cubre los siete ensayos independientes, incluyendo 36 s reales de
silencio/pausa y la recaptura acústica intencional del fixture por micrófono.
Un fallo corta el resto; solo reanudar los stages todavía no ejecutados en un
report nuevo. No hay `--lock-held`: verifica el OWNER canónico internamente.
Requiere la fixture ya compilada `target/H13AudioFixture.app` y permisos
normales autorizados. Su precondición actual exige exactamente **un display
selectable** para probar rechazo de solapamiento (`:191–195`); si no se cumple,
registrar la limitación del harness sin alterar monitores ni relajar el assert.

En otro owner default, separar A/V para conservar el resultado del grupo
anterior aunque la ventana no publique frames:

```sh
motive_h14_test scripts/verify_h13_system_audio.py --stage av
```

No añadir `--fixture-snapshots` al baseline: hace redraw NSView y cambia la
condición de publicación que se está probando. A/V necesita pulsos de imagen
y sonido medidos, no basta audio continuo; un stream suspended no pasa el gate.

Gate de cada ejecución: todos los trials solicitados presentes/`ok=true`,
`report.ok=true`, sin `error`, `cleanup_error`, `fixture_cleanup_error`,
`receiver_cleanup_error` ni `mcp_cleanup_error`; fixture/receptor terminados,
ambas barreras y mixer vacío comprobados externamente. **Exit 0 no basta:**
cleanup puede cambiar `ok=false` sin cambiar el exit code. En estado agregado
`error` puede omitir la eliminación de recursos. `persistence` respalda bytes
del mixer, pero su restauración interna no verifica modos ni hace reemplazo
atómico; RTMP tampoco restaura endpoint. Aplicar la restauración externa.

### 4. Exclusión del audio del propio proceso

Este ensayo usa un owner distinto, iniciado por el coordinador con
`MOTIVE_TEST_SELF_AUDIO=1`, y una ruta nueva y exacta para stderr. La lectura
de `native/self-audio-fixture.inc` confirma que el JSON del emisor se escribe
a stderr. `H14_SELF_AUDIO_LOG` debe apuntar a ese archivo y
`H14_DISPLAY_UUID` al display principal selectable del inventario de ese PID.

```sh
motive_h14_test scripts/verify_h13_self_audio_exclusion.py \
  --display-uuid "$H14_DISPLAY_UUID" --motive-log "$H14_SELF_AUDIO_LOG" \
  --controlled-desktop-audio
```

No tiene `--lock-held`; verifica el OWNER. Requiere desktop sonoro controlado,
emisor propio 2011 Hz/−30 dBFS vivo y fixture externa primero 997 Hz, después
2011 Hz. Gate: ambas fases decodificadas, reloj del emisor que avanza y todos
los asserts originales, `ok=true`, sin ningún error de cleanup. También aquí
exit 0 puede ocultar cleanup fallido y la limpieza puede omitir recursos si
la salida queda en `error`. Verificar ambas barreras y ausencia del fixture;
cerrar el owner y reabrir **sin** `MOTIVE_TEST_SELF_AUDIO`, porque el runner no
detiene el emisor interno. El control `self_audio_floor` de 24 s es condicional,
no sustituye esta aceptación ni justifica reintentos ilimitados.

### 5. Cola de cierre

```sh
motive_h14_test scripts/verify_h13_shutdown_queue.py --lock-held --attempt 1
```

Owner nuevo normal, sin emisor ni recursos previos. PASS exige rechazo
`SHUTDOWN_PENDING`, attempts sin incremento, cero MKV nuevo, ambas salidas
sin worker y salida del PID. EOF/reset/TIMEOUT es INCONCLUSIVE (exit 2), no
PASS. Solo si hace falta un segundo intento, abrir otro owner y ejecutar
`--attempt 2`; máximo dos intentos ante el mismo fallo. No ejecutarlos juntos
ni suponer que el runner reabre Motive. Una app viva no responsiva permanece
como bloqueo, sin force-quit.

### 6. Importación durante cierre

```sh
motive_h14_test scripts/verify_h13_import_shutdown.py --lock-held \
  --clip /Users/luisfarfan/Developer/products/motive-h14/var/evidence/h12-performance-1794960760985746000/owned-1080p.mp4 \
  --timeout-seconds 90
```

La fixture existente mide 10,979,077 bytes; la evidencia H12 retiene 1920×1080,
6 s. El runner vuelve a validar dimensiones/duración/cuota de 64 MiB y hash.
No usar `target/memory-fixture.mp4`, porque exige una ruta bajo `var/evidence`
de este worktree. El clip ya importado puede deduplicarse o terminar pronto;
eso produce INCONCLUSIVE legítimo, no permiso para ampliar sleeps o inventar
una carga. Si no hay solapamiento, se conserva ese resultado antes de decidir
otro ensayo con una fixture propia adecuada.

Debe ser un **owner fresco v3 sin ninguna importación previa**:
`overlays.import=null`, no solo un owner que haya quedado idle tras la matriz.
PASS exige import running al responder shutdown, al menos un status running
posterior, latencia de cada respuesta activa <1 s y salida real del owner.
Si la importación acaba antes del shutdown, devuelve exit 2 y puede dejar el
owner abierto: comprobar el estado antes de continuar. Gate final: `outcome`
PASS, `ok=true`, `cleanup_errors=[]`, inbox propio eliminado, stores iguales y
hash B3 intacto. Conserva asset de catálogo/deduplicación y no afirma un receipt
terminal que no observó. Un inbox retenido por worker vivo se informa, no se
borra a la fuerza.

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
- Memoria: B3 30 FPS y lifecycle/dual-soak de 1800 s a 60 FPS están documentados.
  Ambos medios del soak decodifican, pero el informe sigue PARTIAL: el
  presupuesto RPC está excedido y la entrega del tail tiene un gate separado.
  No convertir RSS estable ni dos decodes verdes en una afirmación de ausencia
  de fugas, sincronía A/V o entrega completa.
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
