# H12 — integración creativa (en curso)

Rama local `codex/h12-creative-studio`, worktree `motive-h12`; base integrada
`d2fb22e574dcb8d9cccb8b8409fceda93d81fa43`. Sin push, merge ni release.
La evidencia privada vive en `var/evidence/`; no se publica contenido capturado.

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

**Implementado, pendiente de prueba nativa:** resto de tipos, importación video,
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
muestreado durante la operación). Una instancia/hijo por video, audio del video
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
