# H12 — integración creativa y verificación

Rama local `codex/h12-creative-studio`, worktree `motive-h12`; base integrada
`d2fb22e574dcb8d9cccb8b8409fceda93d81fa43`. Sin push, merge ni release.
La evidencia privada vive en `var/evidence/`; no se publica contenido capturado.

**Resultado al 17 de noviembre de 2026:** integración funcional verificada desde
GPUI, incluyendo medios reales de grabación y RTMP local. Las 22 suites H1–H11
tienen PASS en su ejecución más reciente sobre el bundle H12. Se conserva una
reserva de estabilidad: el primer ABBA final falló con 2 frames de render lag;
el ABBA completo posterior pasó sin cambios al producto. Su causa sigue sin
aislarse; no se declara corregida ni se elimina ese fallo. Ver resultados finales,
matriz de aceptación y [auditoría visual](h12-native-ui-audit.md) al final.

## Baseline integrado exacto

Bundle construido con fuente limpia y firma existente. Ejecutable SHA-256
`9e519f749f56eecfef3070e63941e59145c47c7fd66a622f4406c47b5853c42e`.
Manifiesto: `var/evidence/h12-baseline/build-manifest.json`; copia preservada del
bundle en `var/evidence/h12-baseline/Motive.app`.

Sesión observada desbloqueada, permisos normales; sin cambios globales. Todos
los ensayos físicos son seriales bajo el lock compartido de Motive.

- **Verificado:** 15 suites H1–H10 independientes de cámara, incluyendo captura
  de ventana propia, H9 faults, H8 lifecycle/keychain, CLI/MCP, entrega de control,
  perfiles, recuperación, RTMP/RTMPS local y H10 pilot. Manifiesto original:
  `var/evidence/h11-regressions-1794920805458950000/manifest.json`.
- **Verificado:** encoding ABBA, cuatro grabaciones completas de 60 s
  (x264/VideoToolbox/VideoToolbox/x264), gate original de cero lag intacto.
  H9 faults pasó en 30,1 s y encoding en 252,6 s. Esto verifica el main integrado
  en esta sesión; no demuestra por sí solo la causa de los fallos del bundle H11
  anterior en una sesión bloqueada.
- **Verificado:** H11 runtime con grabación y RTMP, visuales con video, lifecycle
  con pérdida/recuperación/persistencia. Manifiesto con hashes de los informes:
  `var/evidence/h12-baseline/h11-manifest.json`. Suites originales sin cambios.
- **Bloqueo inicial resuelto:** H1 cámara, scenes y H9 transitions pasaron tras
  la confirmación del usuario de cámara preparada; detalle y manifiesto abajo.
- **Fallos iniciales conservados:** H10 mixer, RMS de micrófono aislado. Primer ensayo pasó grabación
  (error RMS 0,226 dB); RTMP falló con 4,273 dB frente al margen de 2 dB. Segundo
  ensayo falló en grabación (5,665 dB). Ambos informes y medios se conservan;
  segundo manifiesto `h11-regressions-1794921883020606000/manifest.json`.
  No se repite a ciegas ni se modifica el umbral. Diagnóstico adicional del
  primer fallo: señal física variable (aprox. −32 a −47 dB); la mediana temporal
  de dB y el segundo de audio comparado difieren. Al agregar energía sobre un
  intervalo común, diferencia 0,187 dB. Esto apoya una hipótesis sobre muestreo,
  no reemplaza el gate ni prueba toda la implementación. Evidencia:
  `h12-baseline/h10-rms-diagnostic.json`.

El cierre posterior del baseline se documenta abajo; la aceptación final de H12
requiere además el bundle final y la producción conjunta.

## Incremento 1 — biblioteca e importación nativa

Implementado: selector nativo GPUI, copia en worker a inbox privado, importación
por el mismo `ImportAsset` y su operation ID, confirmación solo al observar
`completed`, limpieza por RAII al finalizar/rechazar/cancelar, inventario con
uso por escenas y eliminación protegida por referencias. Verificado después con el bundle firmado, como se detalla abajo.

`AssetCatalog::stage_selected_file` es una capacidad Rust de la UI, no un comando
serializable. Solo recibe la selección explícita del panel nativo. Lectura
no-follow/no-block del archivo final, regular y hasta 64 MiB, copia acotada,
comparación de metadatos antes/después, permisos 0600, nombre interno exclusivo.
El guard conserva descriptores y no elimina un inode reemplazado; nunca elimina
el original. No constituye aislamiento entre procesos del mismo UID. Un cierre
abrupto del proceso puede dejar una copia huérfana: no se borra por PID inferido.

Nueva consulta compartida `asset_inventory` (CLI/MCP/UI), sin argumentos:
`result.assets[] = {asset: Asset, error: string | null}`. Permite recuperar un
objeto perdido sin ocultar los demás. `list_assets`, `resolve` y la validación del
render siguen siendo estrictos. Importar bytes idénticos repara el mismo asset ID;
la reconexión de fuentes continúa siendo explícita y requiere salida detenida.

Validación incremental: 54 tests Rust PASS (51 previos + 3 de staging), incluyendo
original intacto, importación/recuperación real de PNG, symlink/FIFO/directorio,
archivo vacío/grande y limpieza que preserva una entrada reemplazada.

Verificación nativa incremental: selector NSOpenPanel -> PNG controlado 96×96 ->
«Recurso disponible · importación 1» observado en GPUI; consulta pasiva confirma
worker `completed`, `last_action` UI y cero copias `picked-*` restantes. Informe
`h12-baseline/increment1-native-import.json` con hash del bundle. Clippy PASS.
Una captura inmediata al cerrar NSOpenPanel devolvió SCK −3812; el árbol AX y
la siguiente captura de la ventana principal funcionaron. La selección genérica
por nombre de app resolvió accidentalmente el bundle H10: se cerró su proceso
idle enseguida, sin pruebas físicas concurrentes. Las siguientes selecciones
usan la ruta completa del bundle H12.

## Incremento 2 — edición y ejecución nativas

Biblioteca con Crear/Recursos/Presets/Fuentes; texto multilínea, imagen, video,
rectángulo/círculo, countdown/alerta y catálogo original de presets. Inspector
Contenido/En vivo/Animación. Los comandos son `CreateOverlay`, `UpdateOverlay`,
`OverlayEvent`, `AnimateOverlay` y `CancelOverlayAnimation`, todos mediante el
mismo `Studio.command`/`Production.apply`. `SetOverlayColor` solo aparece para
el overlay clásico sin `definition`. Reutilizar añade una capa de la fuente
existente. Los borradores tienen revisión propia y recarga explícita; los estados
nativos se consultan independientemente de esa revisión.

**Verificado nativamente:** crear texto UTF-8 y multilineal, grabar VideoToolbox,
Slide out 3000 ms, Fade in 3000 ms, editar el texto durante esa misma grabación,
finalizar con el diálogo nativo y guardar proyecto v4. Ninguna operación de
producción de este flujo se envió por terminal; CLI solo observó estado.

Evidencia en `var/evidence/h12-ui/`: capturas 01–04, estados
`first-recording-live.json`/`first-recording-stopped.json`, informe
`first-recording-media.json`, fotogramas original/hidden/edited y MKV referenciado.
SHA-256 ejecutable de ese ensayo:
`34f469a968b38a8bd5b34f7caef53bc645b6295a99667590f6723e06c43b9c01`.
105,733 s, 3171 frames H.264, AAC 48 kHz; decodificación completa sin errores.
PTS interiores máximos 34 ms, cola final 67 ms (se conserva, no se oculta);
DTS monotónicos. Cero render lag, drops de salida y skipped encoder frames en
la observación durante salida. Un source ID, una instancia nativa de texto y
un hijo FT2 después de editar. ROI fija decodificada: 986/0/1126 píxeles claros
antes/oculto/editado; 2721 píxeles cambiaron entre los dos textos. Este clip
contiene silencio AAC: no verifica el mixer ni sustituye la producción conjunta.

**Estado al cerrar este incremento, antes del ensayo final:** resto de tipos, importación video,
controles widgets/presets, cancelación, RTMP conjunto y recuperación desde picker.
55 tests Rust y Clippy PASS. La revisión visual de este flujo identificó acciones
al final de formularios largos: el siguiente build mueve Aplicar arriba y pone
el último recibo/cancelación antes de las opciones de animación. Al cambiar de
pestaña/fuente se reinicia el ámbito del scroll; los borradores se conservan.

## Cierre de los cinco grupos originales del baseline

El usuario confirmó cámara preparada y contenido controlado. Se repuso el bundle
preservado de `main`, verificando nuevamente su SHA-256 exacto antes de ejecutar
las suites. `h11-regressions-1794923384149322000/manifest.json`: H1 PASS 25,2 s,
scenes PASS 34,3 s y H9 transitions PASS 51,9 s. H1 físico: 8,566 s,
368.764 píxeles de contenido fuera del overlay (gate >10.000), RMS 0,002470.
Junto con encoding y H9 faults, los cinco grupos abiertos de H11 ahora pasan.
No hubo cambio de dispositivo, relajación de aserciones o ampliación de timeout.
La diferencia observada es una sesión desbloqueada y un fixture de cámara
preparado. No se atribuye causalidad exclusiva a una corrección de código.

## Corrección del verificador RMS de H10

La implementación oficial incorporada en `.deps/obs-studio-33.0.1/libobs/`
`obs-audio-controls.c:462` calcula `magnitude = sqrt(sum / data->frames)` por
bloque. La implementación Motive publica esa medida post-fader/pre-mute.
El verificador comparaba la **mediana** de lecturas de esos bloques durante
aproximadamente 2,5 s con el **RMS energético** de un segundo diferente. Ambas
estadísticas divergen para una señal física no estacionaria aun con medidor
correcto. No se modificó el mixer ni se añadieron filtros o DSP.

`isolated_rms` ahora compara la mediana nativa original con la mediana de bloques
PCM decodificados de 20 ms sobre exactamente el intervalo entre la primera y
última observación utilizadas. Conserva el umbral absoluto <2 dB, el RMS energético
anterior como métrica, y todos los gates de gain, mute, continuidad, clipping y
timestamps. Añade mínimos de muestras/bloques y rechazo de valores no finitos.
No es calibración sample-exact del retardo de captura/AAC; su alcance es una
comparación muestreada del medidor con el mismo estadístico.

Los seis canales aislados de los tres medios archivados pasan la comparación
corregida, errores absolutos 0,011–0,791 dB. Los informes fallidos originales
permanecen intactos y sus hashes están en `h10-corrected-statistic.json`.
Tres tests unitarios del verificador (no aceptación física) demuestran la
contradicción con una señal transitoria, rechazan un error de ganancia de 6 dB y
rechazan audio truncado: `scripts/test_h10_meter_statistic.py`, PASS.

Nueva ejecución física completa sobre el mismo baseline:
`h11-regressions-1794923671006964000/manifest.json`, PASS en 92,4 s.
Grabación/RTMP: 37,973/37,739 s; ganancia tono −12,101/−11,981 dB; ganancia mic
−12,041/−11,928 dB; errores RMS mic −0,069/+0,630 dB y tono −0,061/+0,022 dB;
picos −21,765/−22,400 dBFS. Pasan mute/unmute, liberación/reapertura nativa de
micrófono, audio continuo durante Cut/Fade, clipping intencional separado,
persistencia y ambos transportes. Desenchufe físico sigue sin simularse.

`h12-baseline/manifest.json` agrega manifiestos y hashes de scripts base/actuales.
Las 19 suites H1–H10 y las 3 suites H11 del baseline tienen resultado PASS tras
la corrección documentada del estadístico; se preservan los fallos previos.
Esto no reemplaza la aceptación del bundle H12 final ni la producción conjunta.

## Rendimiento medido (incremento 3)

`verify_h12_performance.py` mide RSS/CPU reales por libproc a 20 Hz y conserva
tanto muestras completas como estado estable. Convierte los ticks Mach usando
`mach_timebase_info` y contrasta CPU acumulada con `ps TIME` (error máximo 0,3 s).
Un primer ensayo detectó una conversión errónea de unidades: se conserva como
fallo del instrumento, corregido antes de aceptar resultados. Muestreo a 50 ms
puede omitir picos más cortos; presupuesto visual y RSS son métricas separadas.

Informe completo: `h12-performance-1794924031260448000/report.json`. Cuatro videos
1080p visibles: RSS mediana 633,4 MiB y CPU 64,4%; ocultos: 662,1 MiB y 60,4%.
Ocultar no pausa los decodificadores: el reloj media continúa y la UI explica
Pause/Stop. Se conserva la semántica existente de libobs. Reconciliar cuatro IDs
nuevos llegó a 901,9 MiB en la fase posterior (el informe contiene además el pico
muestreado durante la operación: 910,25 MiB). Primer video: 483,2 ms; siguientes
36,2–38,5 ms; reconciliar cuatro: 490,8 ms. Una instancia/hijo por video, audio del video
desactivado. Cancelación y finalización de Scale de 10 s verificadas por op ID.

Tres ciclos de reapertura/liberación dieron medianas activas 896,9 / 861,6 /
695,0 MiB; después de liberar y esperar 20 s, mediana 263,1 MiB. No hubo crecimiento
monótono en estos tres ciclos, pero no constituye prueba formal de ausencia de
fugas ni compromiso de RSS inmediato. **Cero render lag en todas las fases**,
incluyendo creación, reconciliación y animaciones. El script restaura proyecto,
fuentes y catálogo; no modifica perfiles ni preferencias globales.

Rust: 55 PASS; Clippy all-targets con warnings como errores: PASS. Verificador
RMS: 3 tests PASS. El observador `observe_h12_native.py` solo consulta status MCP
a 4 Hz, guarda revisiones/origen/IDs/medidores/outputs y no controla producción.

## Reproducción del bundle H12

Ejecutar serialmente con el lock compartido, sesión desbloqueada y cámara
apuntando a contenido controlado. No reconstruir el bundle entre suites.

```sh
cargo test --all-targets
cargo clippy --all-targets -- -D warnings
python3 -m unittest discover -s scripts -p test_h10_meter_statistic.py
python3 scripts/verify_h12_regressions.py --camera-id ID_CONTROLADO --microphone-id ID_CONTROLADO
```

El runner no instala dependencias ni cambia permisos: requiere el bundle firmado
existente y `var/verify-python` preparado con `requirements-h11.txt`. Guarda hash
del ejecutable, commit, scripts, salida de cada suite y copias de los informes.
`--stage legacy` ejecuta los 19 gates H1–H10; `--stage overlays`, las tres suites
H11 (runtime ambos transportes, visuales con video y lifecycle). Visuales conserva
su fixture x264 explícito y restaura Auto después. Un fallo de preparación detiene
el runner para no interrumpir una salida ajena o un fixture sin limpiar.

`verify_encoding.py` ahora conserva `in_progress_trial` si una aserción falla
antes de devolver el ensayo. No añade polling ni I/O durante la grabación y
conserva el gate de cero lag, las duraciones y la decodificación originales.
La primera batería H12 registró 2 frames de render lag en el tercer ensayo VT;
el fallo y medios se mantienen en `h11-regressions-1794924688808193000`. No hubo
frames omitidos por encoder ni drops de salida. El resultado de la investigación
y repetición se conserva en la sección final siguiente.

Para observar un recorrido realizado íntegramente desde GPUI:

```sh
python3 scripts/observe_h12_native.py --seconds 1200
```

El observador solo consulta status; el operador crea/edita, importa, anima,
configura mixer y controla salidas con los controles nativos. Un receptor FFmpeg
externo escucha únicamente loopback. El informe debe vincular sus medios con
las revisiones de origen UI y decodificar píxeles, audio y timestamps; no basta
con una captura del preview o una respuesta de comando aceptado.

## Bundle final y regresiones

SHA-256 del ejecutable firmado probado:
`dfbfc6527caa21a45f3eb9cce4a0cf3ed1fe9a7468b9bde56be3e906f8d5126f`.
Fuente de producto en `93a4cd6`; commits posteriores añaden documentación e
instrumentos de verificación, sin cambiar ese binario. Manifiestos de fuente,
scripts, suite e informes en `var/evidence/h12-final/`.

| Grupo | Resultado final | Evidencia |
| --- | --- | --- |
| H1–H10, 19 suites | 18 PASS iniciales; encoding PASS en repetición íntegra | `h11-regressions-1794924688808193000/manifest.json` |
| H11 runtime, visuales con video, lifecycle | 3 PASS, 101,5 / 36,2 / 11,3 s | `h12-regressions-1794925449612917000/manifest.json` |
| Encoding ABBA, cuatro clips de 60 s | PASS, 251,8 s; cero lag/skips/drops en los cuatro | `h11-regressions-1794925643060010000/manifest.json` |
| Rust / Clippy / formato | 55 PASS / all-targets `-D warnings` PASS / PASS | build y logs incrementales; sin cambios Rust posteriores |
| Verificador del medidor | 3 PASS; error real final <2 dB | `meter-statistic-tests.log`, informe H10 final |

El primer ensayo final de encoding **falló**: 2 frames de render lag en el tercer
clip VideoToolbox, sin frames omitidos por el encoder ni pérdida de salida. Su
archivo decodifica completo (1819 frames, PTS interior máximo 34 ms y cola 66 ms),
pero eso **no** satisface el gate de cero lag: libobs puede repetir contenido sin
romper PTS. `h12-final/encoding-failed-media.json` conserva ese diagnóstico.
No hay muestras granulares del ensayo original; se añadió su retención al
verificador antes del ABBA aislado. No cambió el producto, los umbrales ni los
tiempos. Temperatura/swap observados no establecen causalidad. El resultado
posterior PASS cierra la ejecución del gate; queda riesgo intermitente sin causa
demostrada y no una promesa de cero lag en cualquier sesión.

## Producción operada desde GPUI

Se crearon tres escenas, texto UTF-8, PNG transparente, video 1080p de seis
segundos en loop, los tres presets originales, countdown y alerta. La fuente
física visual final fue exclusivamente **Motive — Fuente controlada**, una ventana
propia con contador. Se retiró la cámara antes de grabar. Dos entradas globales:
micrófono integrado oyendo un WAV propio de 997 Hz y tono libobs de 440 Hz;
monitoreo desactivado. El video local no aporta audio.

Todas las operaciones de composición, importación, edición, presets, widgets,
animaciones, mixer, inicio/parada de salidas y persistencia de este recorrido
proceden de **UI**. La terminal preparó fixtures/receptor, observó estado y analizó
medios; no controló esos pasos de producción. El receptor escuchó solamente
`rtmp://127.0.0.1:19412/live/motive`. El cierre de procesos al terminar la prueba
usó el comando de shutdown del núcleo después de finalizar las salidas.

Trazas pasivas a 4 Hz:

- `h12-native-1794927491610528000/`: creación final, primera grabación y RTMP.
- `h12-native-1794928693132835000/`: grabación adicional con Fade confirmado.
- `h12-native-1794925951992544000/`: creación inicial de texto/PNG y diagnóstico
  del selector. No contiene una salida final.

La primera grabación (`motive-1794927882107801.mkv`, unos 389 s) conserva composición
completa, edición, alertas, contador, Slide/Fade de texto, Scale y cancelación de
Scale de 10 s por operation ID #4 a los 4599 ms. El análisis detectó que sus tres
cambios de escena fueron **Cut**, aunque se había intentado aplicar Fade. El panel
no dejó esa configuración aplicada; no se acepta el click como prueba. Se conserva
el fallo en `h12-native-media/report.json`. La protección de revisión de los
formularios puede rechazar un borrador si el núcleo cambió; este mecanismo existe
y no basta por sí solo para atribuirle la causa de cada click no aplicado.

Se hizo una toma adicional verificando configuración y finalización reales antes
de continuar. No se cambió el código ni se rebajó el gate. La reparación de un asset
entre tomas reconstruyó fuentes y ocultó el lower third: este evento se verifica
visible en la primera toma y en RTMP, no se atribuye a la toma adicional.

| Métrica decodificada | Grabación adicional | RTMP recibido |
| --- | --- | --- |
| Archivo | `var/recordings/motive-1794928698236478.mkv` | `var/evidence/h12-ui/native-rtmp.mkv` |
| Último PTS video / frames | 138,900 s / 4165 | 104,354 s / 3129 |
| Encoder / audio | VT hardware H.264 / AAC 48 kHz estéreo | VT hardware H.264 / AAC 48 kHz estéreo |
| Mayor intervalo PTS interior | 34 ms | 34 ms |
| Mayor intervalo final, conservado | 133 ms | 67 ms |
| Mayor intervalo de paquetes AAC | 22 ms | 22 ms |
| Pico PCM | −26,160 dBFS | −6,079 dBFS |
| Ganancia tono solicitada / medida | −12 / −11,721 dB | −12 / −11,180 dB |
| Error RMS mic / tono aislados | +0,178 / +0,012 dB | +0,349 / +0,020 dB |
| Píxeles cambiados por edición de texto | 15.008 | 10.814 |
| Píxeles cambiados del countdown | 554 | 392 |
| Movimiento video / ventana propia | 2464 / 1570 píxeles | 2405 / 1534 píxeles |
| Lag / skips encoder / drops salida observados | 0 / 0 / 0 | 0 / 0 / 0 |

Informe completo PASS: `var/evidence/h12-native-media-final/report.json`.
Decodificación completa sin errores; DTS crecientes en ambos streams. Los huecos
de cola se muestran y cumplen el límite previo de 150 ms; no se anuncian como
cadencia perfecta. Muestreo de estado a 4 Hz y alineación por `output_frames/30`
no equivalen a calibración sample-exact de captura/AAC.

Fade de escena se comprueba además en píxeles: una franja fija pasa por luminancia
intermedia entre ambos extremos. Cada cambio Cut/Fade modifica 12.288 píxeles de
esa franja; el RMS mínimo por bloques de 100 ms durante transiciones permanece
por encima de 0,0027, sin huecos de paquetes de audio. Se conserva el tono o el
micrófono, según el mute vigente. La toma adicional incluye 17,4 s con **ambas
entradas silenciadas** durante la secuencia de controles; PCM cero coincide con
esos estados. No se cuenta ese tramo como audio audible continuo ni como corte
del encoder. RTMP y la primera toma mantienen al menos una entrada activa.

La transparencia decodificada muestra RGB `[13,21,35]` / `[22,123,66]` /
`[31,223,95]` en las zonas transparente/semitransparente/opaca del PNG. RTMP muestra
2591 píxeles claros del lower third y 32.555 píxeles cambiados al lanzar la alerta.
Pause del video deja cero píxeles cambiados en su ROI entre dos segundos de muestra;
Restart recupera `playing`. Countdown pausa/reanuda desde estado nativo (por
ejemplo `remaining_ms=51392` durante pausa), sin reloj GPUI. Instancias visuales,
hijos por overlay y ambas entradas de audio permanecen iguales dentro de cada
salida. La reconstrucción explícita por recuperación ocurrió con salida detenida.

Scale en la primera toma aumenta los píxeles de acento de 1574 a 2220 y 3180;
durante Scale out baja a 3002 y cancelar devuelve 3180. Se comprueban los frames
decodificados además del recibo nativo y se conserva el lower third visible allí.

## Importación, recuperación y persistencia finales

NSOpenPanel entregó el video original al worker #1: `completed`, asset
`asset-efc472d4b1d258fc5d37612aae2c8e4659d9a5a62e4f54d5895ef05033a14ff9`.
`h12-ui/native-video-import.json` y captura 05. Antes de ello, el panel había
quedado en una miniatura de Stage Manager: captura blanca, confirmación sin
callback y sin operación en el núcleo. Los intentos fallidos se preservan en
logs; el mismo archivo funcionó cuando el usuario puso el estudio al frente.
No se modificaron permisos ni Stage Manager. Una conexión SCK de la herramienta
también devolvió −3811 y se recuperó al renovar la conexión de observación.

Archivo propio inválido: worker #2 `ASSET_FORMAT_UNSUPPORTED`, error visible en
biblioteca (captura 08), original intacto. Pérdida controlada del PNG normalizado:
se movió a evidencia, conservando sus bytes; `ASSET_UNAVAILABLE` visible y Grabar
desactivado (captura 09). Picker reimportó el original, worker #3 restauró el mismo
ID; reconexión explícita devolvió estado listo. Cero `picked-*` después de ambos
resultados; catálogos y stores no fueron reemplazados por fixtures de análisis.

`h12-ui/lifecycle/` conserva estados y hashes: Guardar proyecto produce v4;
Restaurar proyecto desde GPUI conserva exactamente su documento, el mixer y la
configuración de salida. Restaurar mixer después de silenciar una entrada devuelve
su store guardado sin cambiar proyecto/perfiles ni IDs de instancias de audio.
Reapertura de proceso a tamaño compacto arranca sin capturas seleccionadas. Allí
se creó y editó un círculo (borde blanco de 8 px), sin sobrescribir el proyecto v4
guardado. Reapertura repetida de proyectos y recuperación de assets también pasan
las suites H11 lifecycle y el probe de rendimiento descritos arriba.

## Reproducción del análisis nativo

El verificador es específico del fixture de este recorrido (IDs, posiciones y
etapas descritos arriba), no un generador de producción ni una prueba con mocks.
Para repetir el recorrido, operar la UI, conservar su traza y pasar los archivos
resultantes. El archivo inicial que carece de Fade no satisface sus aserciones.

```sh
var/verify-python/bin/python scripts/verify_h12_native_media.py \
  --observer var/evidence/h12-native-1794927491610528000/observations.jsonl \
  --recording-observer var/evidence/h12-native-1794928693132835000/observations.jsonl \
  --recording var/recordings/motive-1794928698236478.mkv \
  --scale-recording var/recordings/motive-1794927882107801.mkv \
  --stream var/evidence/h12-ui/native-rtmp.mkv \
  --out var/evidence/h12-native-media-recheck
```

## Matriz de aceptación y límites

| Estado | Alcance |
| --- | --- |
| **Verificado** | 22 suites H1–H11 en últimas ejecuciones; cinco grupos originales sobre main exacto; UI creativa/importación/presets/widgets/animaciones; composición real, VT y RTMP local; recuperación PNG; v4 y mixer independientes; CPU/RSS reales y cuatro videos; UI clara/oscura 1440×980 y 1024×780 |
| **Implementado, sin cobertura nativa exhaustiva** | Todas las combinaciones de fuente/color/alineación/contorno, importación JPEG/WebP/VP8/VP9 desde picker, catálogo de miles de recursos, recorrido completo con VoiceOver; los límites del núcleo sí conservan sus tests |
| **Bloqueado / fuera del incremento** | RTMPS positivo requiere destino/certificado autorizado ya pendiente en H8; Browser/CEF permanece restringido; no se añade audio de sistema ni de medios |
| **Fallido conservado** | Encoding inicial con 2 lag frames (causa abierta); RMS antiguo comparaba estadísticas distintas (verificador corregido y repetido); primera toma UI sin Fade (repetida con estado confirmado); bloqueos de observación/picker resueltos con foreground |

Permanecen USB hot-unplug físico, sleep/wake, sesiones de muchas horas y matriz
de macOS. RSS de tres ciclos no demuestra ausencia formal de fugas. Ocultar
video no detiene el decoder. No se limpian huérfanos tras crash automáticamente.
La UI conserva límites visuales/accesibles documentados en la auditoría; no se
declara conformidad de accesibilidad. Ninguna emisión pública, cambio global,
merge, push ni release. Procesos de prueba cerrados y lock físico propio liberado.

Índice de entrega con hashes de medios, capturas, informes, scripts y commit:
`var/evidence/h12-final/delivery-manifest.json`. La evidencia multimedia permanece
local e ignorada por Git; el código, los verificadores y estos informes sí se
conservan en commits de la rama H12.
