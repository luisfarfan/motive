# H14 — verificación real de Show Control B3

Resultado global: **PARTIAL**. La entrada compuesta ya se observa completa y
sin el salto de escala de B1 en los dos medios. Quedan sin demostrar la
cancelación anterior al primer tick y una edición concurrente desde GPUI.
No se afirma entrega íntegra desde encoder hasta archivo ni sincronía labial.

## Identidad y evidencia

- Bundle portable firmado B3, proceso real `11038`, ejecutable SHA-256
  `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
- Sesión owner `c5cc3c2f0f6266f7ae7eeb81efd4e5ca`.
- MATCHDAY instalado mediante revisión y confirmación GPUI: 73/73 pasos.
  Root observó el clic real «Celebración de gol», admisión del job 1,
  cooldown y `GOOOAL! / HOME / 24′` visible mientras ambas salidas estaban activas.
- [Informe original](../var/evidence/h14-show-control-b3-01/report.json),
  [observación GPUI](../var/evidence/h14-show-control-b3-01/root-gpui-observation.json)
  y [análisis derivado](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/derived-report.json).
  Los originales B1/B2/B3 no se editaron. Los hashes de los medios coinciden
  antes/después del análisis y con el manifest del harness.

| Medio | Duración contenedor | Video decodificado | Audio AAC | SHA-256 |
|---|---:|---:|---:|---|
| MKV local | 75.775 s | 2,273 frames | 3,552 paquetes | `ae4c54e1d9de03830e92775f166a2b9e756df30b9fd8f8b94632dcb4e496ce01` |
| Receptor RTMP loopback | 75.554 s | 2,266 frames | 3,541 paquetes | `8111871323eb0f261aafa37b6e120f98636177a39cf88a8dd5cabc63849f38ef` |

Ambos contienen H.264 1920×1080 a 30 fps, sin B-frames, y AAC estéreo 48 kHz.
La grabación está en `/Users/luisfarfan/Movies/Motive/motive-1794956586218721.mkv`;
el receptor está en `var/evidence/h14-show-control-b3-01/loopback.mkv`.
Los perfiles y encoders de salida son independientes. Se conserva un único
attempt `1` por cada target durante la toma, sin reinicios ni drops de output
notificados. La diferencia de duración corresponde a arranques/paradas separados;
no se exige igualdad artificial entre archivos.

## Entrada, hold y salida observados

Se analizaron tres ejecuciones completas: clic GPUI (op 1), MCP (op 2) y
celebración que continuó tras salir MCP (op 8). Cada acción pidió 450 ms de
`scale_in/ease_out`; libobs informó terminal a 466 ms, el siguiente tick de
30 fps después del plazo solicitado. El contador avanzó después del recibo
terminal, no de la mera admisión.

| Evento | Primer frame visible MKV | Primer frame visible RTMP | Oculto otra vez MKV / RTMP |
|---|---:|---:|---:|
| GPUI | 22.200 s | 21.854 s | 26.667 / 26.321 s |
| MCP | 32.400 s | 32.054 s | 36.867 / 36.521 s |
| Después de desconectar MCP | 70.633 s | 70.287 s | 75.100 / 74.754 s |

Las marcas son PTS de los medios, no tiempo de llegada del RPC. Para localizar
el evento se usó `start_ns` nativo frente al primer paquete de video con
`sys_dts_usec`, conservando el origen medido del contenedor; el inicio se
corroboró en los pixels. Este mapeo sirve de localizador y no equivale a una
medición de sincronía A/V.

La región controlada es `(240,360,1440,360)` en 1080p, reducida a 360×90 para
medir diferencias respecto al frame 150 sin alerta. En las seis entradas, el
ancho del contenido medido evoluciona así:

`296 → 306 → 315 → 323 → 330 → 336 → 342 → 347 → 351 → 354 → 357 → 358`.

La altura crece de 75 a 90; no hay pasos negativos de ancho ni altura. El
resultado se conserva con umbrales RGB acumulados 12, 30 y 60, requiriendo
diferencia media mayor que 1/255 y más de 1,000 pixels de máscara. El primer
frame medible corresponde al tick posterior al inicio: no se pretende medir
0.8 exactamente cuando la opacidad inicial es cero. Se revisaron los contactos
decodificados: texto y fondo entran creciendo, sin frame a tamaño normal antes
de la reducción que se vio en B1.

La alerta mantiene contenido visible y sale mediante su fade nativo. La
diferencia media de la región cae de aproximadamente 165.3 a menos de 0.021
al terminar; vuelve a fondo entre 4.4997 y 4.5004 s desde el inicio localizado.
Esto cubre entrada, hold y salida de las tres celebraciones, además del
terminal nativo. No evalúa todos los presets, variantes o futuras animaciones.

- [Entrada GPUI, MKV](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/recording-ui_goal-entry.png)
- [Entrada MCP, MKV](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/recording-mcp_goal-entry.png)
- [Entrada tras desconexión, RTMP](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/loopback-disconnect_goal-entry.png)
- [Geometría por frame MKV](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/recording-event-geometry.json)
  y [RTMP](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/loopback-event-geometry.json).

## Audio y continuidad

Los PTS/DTS de paquetes son estrictamente crecientes y coinciden entre sí.
El máximo intervalo de video es 34 ms y el de AAC 22 ms; no hay discontinuidad
de timestamps durante acciones, cancelaciones o desconexión MCP.

| PCM decodificado por canal | MKV | RTMP |
|---|---:|---:|
| Muestras | 3,636,224 | 3,625,984 |
| RMS global | −39.016 dBFS | −39.017 dBFS |
| Peak | −34.951 dBFS | −34.929 dBFS |
| Muestras con amplitud absoluta ≥0.99999 | 0 | 0 |
| RMS por ventanas interiores de 100 ms | −39.044 a −38.014 dBFS | −39.043 a −38.023 dBFS |

Todas las muestras son finitas. El tono de 440 Hz tiene amplitud pico medida
de 0.015826 / 0.015821 en el segundo inicial de análisis. El incremento de
aproximadamente 1 dB corresponde al cambio CLI de ganancia empleado para la
prueba concurrente, seguido de restauración. Las ventanas interiores excluyen
los primeros/últimos 200 ms de frontera AAC; se conservaron también las
ventanas completas. Un tono continuo no permite medir sincronía labial.

## Recibos, cancelación y autonomía

La [auditoría independiente](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/receipt-geometry-audit.json)
releyó el journal y 544 snapshots del mismo PID/sesión:

- Seis intents, seis dispatches, cinco completions y un cancel intent. Cada
  action key se despachó una sola vez; cada dispatch sigue a su intent durable.
- Las tres celebraciones completadas tienen cursor 2: acción compuesta y
  contador local. Cada una tiene un único token y exactamente dos recibos
  contiguos: GPUI `232→234→237`, MCP `239→241→244`, desconexión
  `295→297→300`. El journal confirma un solo comando compuesto por intent.
- El contador observado evoluciona únicamente `0→1→2→3`. Cooldown y evento
  duplicado no vuelven a disparar el contador.
- Cancelación nativa después de empezar: `cancelled`, `widget_triggered=true`,
  66 ms observados y contador `2→2`. Cancelación vía Show Control: op 6 estaba
  `running`, terminó `cancelled` a 33 ms, el journal conserva un cancel intent
  y la reconciliación dejó job cancelado/cursor 0, contador `2→2`.
- Los dos intentos anteriores al primer tick llegaron después del disparo:
  ambos tienen `started=true`, `widget_triggered=true`. Resultado
  **NOT_OBSERVED**, sin repetir indefinidamente ni reclamar ese gate.
- La edición CLI concurrente de ganancia ocurrió mientras op 7 estaba
  aceptada. El job quedó `needs_reconciliation`, cursor 0 y
  `MISSING_MUTATION_RECEIPT`; reconciliar conserva esa incertidumbre. No hay
  acción de contador ni replay. La operación nativa puede terminar sin que
  ello autorice adoptar revisiones ajenas.
- MCP salió con código 0. Una consulta CLI posterior todavía observó op 8
  `running`, a 66 ms; después obtuvo terminal y contador 3. Ambas salidas
  continuaron. No se infiere autonomía solo del cierre de stdin.
- Hashes de escenas, mixer, perfiles, configuración Show Control y registro
  de destinos permanecieron iguales; cleanup no reportó errores. El historial,
  los contadores y el job concurrente incierto se conservan deliberadamente.

La prueba concurrente es **MCP/CLI**, no una edición GPUI simulada. El clic GPUI
real tiene su evidencia aparte y no acredita la concurrencia UI pendiente.

## Últimos paquetes: evidencia acotada

Los traces iniciales se tomaron tras tres paquetes de video y audio presente,
con secuencia inicial 1, cero pérdidas y cero sobrescrituras. Los finales se
guardaron tras quiescencia, antes de restaurar configuración; cada uno conserva
256 registros contiguos, sin registros perdidos. La sobrescritura del historial
intermedio es esperada para el ring acotado.

El correlador usa el primer PTS real de cada medio para calcular el origen y
una tolerancia de cuantización de 1.1 ms. En cada salida encontró los 100
paquetes de video retenidos al final y 155 de 156 paquetes AAC retenidos.
El único AAC ausente tiene timestamp de sistema posterior al retorno de
`stop_output`: aproximadamente +18.54 ms en grabación y +8.90 ms en RTMP.
Clasificación: **STOP_BOUNDARY_PACKETS_NOT_DELIVERED**; no se encontró una
ausencia previa al límite de parada en ese tramo. Esto es compatible con el
cutoff documentado de parada, pero no convierte el paquete ausente en entregado.

| Cuenta | MKV | RTMP |
|---|---:|---:|
| Encoder counter / paquetes video observados | 2,275 / 2,273 | 2,268 / 2,266 |
| Video observado / contenedor / decodificado | 2,273 / 2,273 / 2,273 | 2,266 / 2,266 / 2,266 |
| AAC observado / contenedor | 3,553 / 3,552 | 3,542 / 3,541 |
| Solicitud stop → quiescencia | 141 ms | 144 ms |

La diferencia de dos unidades encoder→observador por salida sigue sin
localización temporal: este trace comienza **antes del plugin de salida**, no
en cada emisión interna del encoder. No demuestra entrega de todo el pipeline.
El correlador acredita los paquetes retenidos y sus límites, no el contenido
completo del ring ya sobrescrito.

[Correlación MKV](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/recording-tail-correlation.json)
· [Correlación RTMP](../var/evidence/h14-show-control-b3-01/offline-analysis-v1/loopback-tail-correlation.json).

## Reproducción offline

Dentro del mismo worktree, con los medios conservados:

```sh
python3 var/evidence/h14-show-control-b3-01/offline-analysis-v1/analyze.py
python3 var/evidence/h14-show-control-b3-01/offline-analysis-v1/audit_receipts.py
```

El primer script solo lee medios y evidencia, ejecuta FFprobe/FFmpeg y escribe
en `offline-analysis-v1`; no abre Motive ni dispositivos. El segundo solo
relee JSON. No ejecutarlos junto a mediciones físicas o de rendimiento. Los
artifacts privados de `var/` están ignorados por Git; este informe conserva
ubicaciones, hashes, método y límites sin publicar los medios.
