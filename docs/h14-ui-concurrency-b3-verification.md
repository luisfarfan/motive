# H14 · B3: edición concurrente real desde GPUI

La edición de ganancia mediante GPUI durante una operación nativa quedó
verificada en el caso independiente con animación de **3000 ms**. La prueba
estándar MATCHDAY de **450 ms permanece NOT_OBSERVED**: el segundo clic llegó
cuando esa animación ya había terminado. No se intercambian sus resultados.

Los cuatro archivos reales decodificaron completos, sin errores, discontinuidad
de PTS/DTS, clipping ni silencio interior. El escalón de ganancia medido fue
**12.009–12.014 dB**. La comprobación geométrica estricta del caso de 3000 ms
conserva un **FAIL** por cuatro variaciones de un píxel en el borde de su máscara;
la inspección derivada explica su sensibilidad al umbral sin cambiar ese gate.

## Alcance y procedencia

Bundle portable B3, ejecutable SHA-256
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
Se usaron exclusivamente el proyecto MATCHDAY controlado, un tono local de
440 Hz y grabación MKV + RTMP loopback. No hubo capturas físicas, destino
externo, acceso a credenciales ni emisión durante estos dos ensayos.

- [Original stock450](../var/evidence/h14-ui-concurrency-b3-stock-01/report.json): PID 84030,
  evento `ui-84030-1`, configuración guardada sin modificar.
- [Original custom3000](../var/evidence/h14-ui-concurrency-b3-custom-01/report.json): PID 86084,
  evento `ui-86084-1`, cambio público temporal de `deck-goal.actions[0].animation.duration_ms`
  de 450 a 3000; no se guardó.
- Los clics reales y la lectura AX nueva del botón de ganancia constan en
  [CUA stock](../var/evidence/h14-ui-concurrency-b3-stock-01/root-cua-observation.json)
  y [CUA custom](../var/evidence/h14-ui-concurrency-b3-custom-01/root-cua-observation.json).
  El harness no envió comandos con origen UI falsificado.

Los informes originales permanecen intactos. El derivado reproducible está en
[media-analysis.json](../var/evidence/h14-ui-concurrency-b3-offline-01/media-analysis.json),
con [analizador](../var/evidence/h14-ui-concurrency-b3-offline-01/analyze.py),
comandos, stderr, hashes, paquetes, frames, PCM y ROI conservados. Los cuatro
medios se procesaron secuencialmente con `ffmpeg`/`ffprobe` del propio bundle
B3, en una ventana offline coordinada. No se ejecutó otra prueba física en
paralelo.

## Control, recibos y ausencia de replay observado

La [auditoría independiente del journal y snapshots](../var/evidence/h14-ui-concurrency-b3-offline-01/journal-audit.json)
encuentra en cada sesión un header, un intent, un dispatch aceptado y una
completion, para un único `action_key` y operación nativa. No hay segundo
dispatch registrado. Esto prueba unicidad en el journal retenido y la ventana
observada, no una garantía universal de ejecución como máximo una vez.

| Evidencia | Stock 450 ms | Custom 3000 ms |
|---|---|---|
| Separación observada entre clics CUA | 1048 ms | 605 ms |
| Muestras con ganancia 0 dB y nativo todavía running | 0 | 33 |
| Primera muestra de edición durante running | No observada | `elapsed_ms=566`, mismo operation_id |
| Acción registrada | `UI · set_audio_gain` | `UI · set_audio_gain · revisión 39` |
| Job final | completed, cursor 2 | needs_reconciliation, cursor 0 |
| Contador goals | 0→1 | 0→0 en todas las muestras |
| Completion de la operación nativa | completed | completed, recibo final null |
| Resultado del gate concurrente | **NOT_OBSERVED** | **PASS** |

En custom, `MISSING_MUTATION_RECEIPT` conserva la incertidumbre de la cadena
de revisiones: la edición UI entra mientras la primera acción sigue pendiente,
y la segunda acción de incrementar contador no se ejecuta. La animación nativa
termina normalmente, `pending_ack=false`, y la alerta queda hidden. El harness
no reconcilia, reintenta ni reproduce la operación. Nueve snapshots posteriores
cubren aproximadamente 0.94 s entre la primera solicitud y la última respuesta,
sin incremento tardío ni otro dispatch observado.

Las dos salidas mantienen attempt 1 durante 353 muestras activas en stock y
260 en custom. Terminan idle, sin `native_busy`; los receptores salen con código
0. Los cinco hashes de stores before/after coinciden. Permanece solo el endpoint
loopback seleccionado en runtime, porque no existe operación para deseleccionarlo;
no se guardó. Proyecto, perfiles, mixer, configuración de Show Control y destinos
persistidos no cambiaron.

## Medios y audio decodificado

Los cuatro archivos contienen H.264 1920×1080 a 30 fps sin B-frames y AAC
estéreo a 48 kHz. FFprobe decodificó todos los frames; FFmpeg decodificó video y
PCM completos con `-xerror`, salida 0 y stderr vacío. Los PTS/DTS son iguales
entre sí y estrictamente crecientes: máximo 34 ms entre paquetes/frames de video
y 22 ms entre paquetes AAC, sin huecos sobre los límites originales de 50/23 ms.

| Caso / salida | Duración | Frames | Paquetes AAC | Escalón RMS | Peak máximo |
|---|---:|---:|---:|---:|---:|
| Stock / MKV | 31.423 s | 942 | 1473 | 12.014 dB | −23.884 dBFS |
| Stock / RTMP | 31.087 s | 932 | 1457 | 12.009 dB | −23.925 dBFS |
| Custom / MKV | 21.909 s | 657 | 1027 | 12.012 dB | −23.894 dBFS |
| Custom / RTMP | 21.524 s | 645 | 1009 | 12.011 dB | −23.942 dBFS |

Ambos canales coinciden. Todas las muestras son finitas; hay cero muestras
con amplitud absoluta ≥0.999 y cero ventanas interiores de 100 ms por debajo
de −80 dBFS. Los niveles estables pasan de aproximadamente −39.03 a −27.01 dBFS
RMS. La amplitud de 440 Hz, medida en ventanas independientes de un segundo,
pasa aproximadamente de 0.01582 a 0.06306; el escalón espectral es 12.004–12.014 dB.

El escalón se localiza en el PCM con ventanas de 100 ms, sin usar el reloj de
llegada del RPC como reloj multimedia. Frente al inicio nativo localizado en
PTS, aparece entre **+0.833 y +1.079 s** en stock, después de su entrada de 450 ms;
en custom aparece entre **+0.433 y +0.646 s**, durante la entrada de 3000 ms.
Es una corroboración temporal en los medios, no una medición de sincronía labial.

## Animación, límite del borde medido y FAIL conservado

Se estudió la región `(240,360,1440,360)`, reducida a 360×90, comparada con el
frame 60 anterior al evento. El localizador utiliza `start_ns` de la animación
y `sys_dts_usec` del primer paquete de video, ambos de OBS, más el primer PTS
real del contenedor. No se restaron relojes Python/RAW con bases distintas.

- Stock: primer contenido medible **296×75**, crecimiento hasta **358×90**,
  near-full a aproximadamente **0.400 s**, sin descensos de caja durante la entrada.
- Custom: primer contenido medible **287×72**, crecimiento hasta **358×90**,
  near-full a aproximadamente **2.533 s**. El texto y el fondo entran creciendo.
- En los cuatro medios hay hold visible y la alerta vuelve al fondo alrededor
  de **4.500 s**. No se observó un frame inicial a tamaño completo seguido de
  reducción. El tick exacto con opacidad cero no permite medir escala visible.

El criterio estricto `no_negative_entry_steps` falló en custom: dos descensos
de altura de un píxel por salida, sin descenso de ancho. La
[inspección de los cuatro pares afectados](../var/evidence/h14-ui-concurrency-b3-offline-01/geometry-boundary-inspection.json)
mostró que la fila extrema de la máscara con umbral RGB-suma 30 contenía solo
**2, 1, 1 y 1 píxeles**. En el siguiente frame esos píxeles dejan de superar
ese umbral y la caja pierde una fila; las cajas con umbrales 12 y 60 conservan
su altura en los mismos pares. Esto documenta sensibilidad del borde medido,
sin demostrar contracción de la escala nativa. El **FAIL del análisis original
se conserva**; no se amplió tolerancia ni se cambió el gate para convertirlo en PASS.

Contactos extraídos de los medios:
[stock MKV](../var/evidence/h14-ui-concurrency-b3-offline-01/stock-recording/goal-contact.png),
[stock RTMP](../var/evidence/h14-ui-concurrency-b3-offline-01/stock-streaming/goal-contact.png),
[custom MKV](../var/evidence/h14-ui-concurrency-b3-offline-01/custom-recording/goal-contact.png),
[custom RTMP](../var/evidence/h14-ui-concurrency-b3-offline-01/custom-streaming/goal-contact.png).

## Límites y hashes

El gate de concurrencia stock450 queda pendiente de observación. El custom3000
verifica el conflicto real UI y su manejo seguro, sin sustituir aquel caso.
Este pase no analiza entrega completa de la cola ni resuelve diferencias entre
encoder, observer y contenedor. No se infiere igualdad de frames de una
decodificación limpia. La sincronización A/V carece de un marcador compartido.
La unicidad de dispatch está acotada a estas sesiones y journals retenidos.

| Medio | SHA-256 |
|---|---|
| Stock MKV | `3bae20320fec476ce178b10553b79f9eb241468a4417a41904866ce43ba935dd` |
| Stock RTMP | `963dde18620c265c09efd54386c6d0689229935a30246c95d6065dad01d6a3c7` |
| Custom MKV | `8dc65646d982b16ce752448820057bb52cc1e4d42dc46d2e378df85da005e0df` |
| Custom RTMP | `5a82155b7421e60be6b531bf132b67078569ee6ca30ed868ee1aa15cc881ab05` |
| Auditoría de journal | `cef79aa85e2fdcccbfc8baf6eb5232752f16d9deb2152b753880f3b6f9eb759f` |
