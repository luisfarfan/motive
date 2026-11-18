# H14 · B3: repetición con ventanas agrupadas

**El gate de foco/captura sigue abierto.** La confirmación del usuario permitió
observar ventanas completas y obtener dos tomas nuevas, pero no demostrar el
cambio real de foco fixture→estudio→fixture. No se ejecutaron B ni A2 de esta
repetición: ampliar la duración no corrigió la contradicción entre CUA y la
metadata propia de la fixture. Se conservan intactos el
[A→B→A anterior](h14-collection-b3-verification.md) y el índice final histórico.

## Condiciones y resultados físicos

Ensayo local del 17 de noviembre de 2026 (18 de noviembre UTC), con el mismo
bundle B3 fuera del checkout, SHA-256 del ejecutable
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
El owner fue PID 37049. Cada toma nueva usó una fixture firmada nueva; ambas
con `collectionBehavior=0`. El único audio fue el tono interno, con ganancia
−12 dB sobre su nivel base de −24 dBFS. No se seleccionaron cámara, micrófono,
captura del escritorio ni destino externo.

| Intento | Fixture PID / window ID | Resultado original | Observación |
|---|---|---|---|
| Preparación inicial | 37125 / 13069 | FAIL | ID de perfil con mayúscula rechazado antes de seleccionar captura o iniciar salidas; sin medios |
| A1, 60 s | 37125 / 13069 | PARTIAL | MKV y RTMP local; studio-front contradicho por metadata |
| A1 ampliado, 180 s | 41238 / 13159 | FAIL | MKV y RTMP local; faltan dos marcadores de foco, deliberadamente no inventados |

En la toma de 60 s, fixture-front queda corroborado: 27 observaciones y
26.595 s de intervalo. Studio-front tiene **21/21 observaciones incompatibles**:
la fixture conserva `app_active=true` y `key_window=true`. El regreso se marca
a +57.903 s, dejando sólo 2.150 s hasta el final y ninguna muestra interior
tras el guard de dos segundos. Una captura completa del estudio y controles
accionables no acreditan que la aplicación tenga el foco del sistema.

La toma de 180 s concede tres intervalos previstos de 60 s. Se conserva sólo
el marcador inicial; los intentos de Raise, Cmd-Tab, clic y Tab no corroboran
la activación del estudio. El runner finaliza por duración y registra
`All three root focus markers are required`. Hubo 324 snapshots, 5202 muestras
SCK complete y cero errores/suspended/regresiones de PTS en el terminal.
Estas métricas describen callbacks, no sustituyen el análisis de píxeles.

## Cambios acotados del instrumento

El commit `676dfe3` valida IDs antes de mutar el núcleo: 1–33 caracteres ASCII
minúsculos, dígitos, guiones o guiones bajos, con al menos un carácter
alfanumérico. El ID compuesto con `h14-collection-` respeta el límite de
48 bytes del perfil. También admite duraciones enteras de 45–180 s y propone
180 s para dar margen a las acciones CUA. Doce pruebas puras pasaron.

Se conservan los mismos criterios: guard de foco de dos segundos, al menos
tres muestras y cinco segundos por fase, gap máximo de 2.5 s, umbrales de
píxeles, validación del primer paquete, preflight de cinco segundos y cierre
acotado a veinte segundos. No se recompiló ni modificó B3.

El primer análisis congelado de 180 s conserva FAIL: su lector todavía
limitaba los medios a 90 s, antes de decodificar píxeles. El commit `1af7c01`
corrige exclusivamente ese límite de trabajo a `seconds + 30`, con manifest
válido y tope de 210 s. Para 60 s sigue siendo 90 s; no es una tolerancia de
frescura ni de entrega. Trece pruebas puras pasan, incluidos valores límite,
NaN/infinito, booleanos y manifiestos inválidos. Los nuevos análisis se guardan
en directorios separados, conservando los informes congelados.

## Píxeles decodificados, separados del foco

Los análisis corregidos de [60 s](../var/evidence/h14-collection-b3-followup-01/offline-60s-durationfix/analysis.json)
y [180 s](../var/evidence/h14-collection-b3-followup-01/offline-180s-durationfix/analysis.json)
usan exclusivamente FFmpeg/ffprobe de B3. Muestrean uno de cada seis frames
(5 Hz a 30 fps) y decodifican los bits del contador de la fixture con la misma
geometría y umbrales del ensayo original.

| Medio | Frames decodificados | Muestras válidas / totales | Intervalo muestreado | Avance |
|---|---:|---:|---:|---:|
| 60 s · MKV | 1779 | 297 / 297 | 59.2 s | 591 ticks |
| 60 s · RTMP | 1773 | 296 / 296 | 59.0 s | 590 ticks |
| 180 s · MKV | 5389 | 899 / 899 | 179.6 s | 1796 ticks |
| 180 s · RTMP | 5383 | 898 / 898 | 179.4 s | 1794 ticks |

Los cuatro contadores globales pasan: sin muestras inválidas, repeticiones
entre muestras, saltos inesperados ni huecos de decode. Los PTS de video son
crecientes y su gap máximo es 34 ms. Esto demuestra avance del contenido
muestreado; no certifica cada frame ni el cambio de foco solicitado.

En los cuatro medios, el guard de tamaño/keyframe del primer paquete
nativo frente al contenedor sigue rechazando la correspondencia. No se
relajó ni reutilizó una explicación de framing de otro clip. Por ello no hay
alineación de píxeles por fases ni conclusión de entrega completa a partir de
`tail_accounting`. El análisis de 60 s queda **INCONCLUSIVE**; el de 180 s
conserva **FAIL** del ensayo, con medios individualmente INCONCLUSIVE.

La [vinculación de medios y contadores](../var/evidence/h14-collection-b3-followup-01/media-binding.json)
retiene las diferencias sin ajustar cifras. En RTMP de 60 s hay 1774 paquetes
de video observados antes del plugin y 1773 frames decodificados. En los otros
tres archivos coinciden esos dos conteos; eso por sí solo no prueba identidad
ni entrega completa. Los frames codificados son 1781/1775 y 5391/5385,
respectivamente, y no se equiparan a los entregados.

El [análisis global de audio/video](../var/evidence/h14-collection-b3-followup-01/offline-av-global-01/report.json)
decodifica los cuatro archivos completos sin errores. Conservan H.264
1920×1080/30 y AAC estéreo de 48 kHz. En PCM, el pico máximo observado es
−34.989 dBFS, RMS entre −39.025 y −39.019 dBFS, cero muestras no finitas y
cero clipping (`abs(sample) ≥ 0.999`). No hay ventanas interiores de 100 ms
por debajo de −80 dBFS, excluyendo dos ventanas de cada borde. Los PTS/DTS de
audio son crecientes; el gap máximo de AAC es 22 ms. Son medidas globales del
tono, sin aislamiento de fuentes ni certificación de sincronía A/V.

## Cierre y límites

Los dos receptores terminaron con código 0. En 60 s, las salidas alcanzaron
quiescencia a los 156/165 ms de solicitar parada (MKV/RTMP); en 180 s, a los
175/140 ms. Son latencias de lifecycle, no certificación de entrega completa.
Se restauraron patrón, overlay, video y mixer vacío antes de cerrar. Las
fixtures terminaron con Cmd+Q normal; Motive mediante `request_shutdown`
después de verificar quiescencia, sin señales forzadas.

El [recibo de cierre](../var/evidence/h14-collection-b3-followup-01/cleanup.json)
confirma procesos ausentes y hashes/permisos persistentes idénticos para
proyecto, mixer, perfiles, Show Control, destinos y reconciliación de
credenciales. No se cambió el grupo de ventanas mediante preferencias globales.
El [lock se liberó](../var/evidence/h14-collection-b3-followup-01/lock-release.json)
después del cierre y del análisis multimedia, sin otro ensayo físico pendiente.

El [índice de este seguimiento](../var/evidence/h14-collection-b3-followup-01/index.json)
vincula informes originales, análisis congelados y corregidos, medios, scripts,
tests, revisión independiente y recibos de cierre mediante hashes. El índice
histórico H14 permanece idéntico.

No se atribuye causalidad a Stage Manager, App Nap o WindowServer. Esta
repetición tampoco compara `CanJoinAllApplications`: no hay brazo B nuevo.
La aceptación beta permanece **NOT_ACCEPTED**.
