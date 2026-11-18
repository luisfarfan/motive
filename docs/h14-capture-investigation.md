# H14 — investigación de captura y recuperación

Estado del gate: **FAIL**, con instrumentación y un ensayo dual exitosos.
La causa de la suspensión y la recuperación tras reemplazar una ventana siguen
abiertas. No se atribuye el fallo a Stage Manager sin evidencia causal.

Estos ensayos corresponden al binario intermedio SHA-256
`2ddcbabd37c8299f53170705a97598b9f996670e592d68881a0ba3b28674a443`,
y al módulo de captura
`9205128a4c59fdf2743dec302e4a989e39e7233a0fa1d80528e89268b06b154d`.
No certifican el futuro bundle final H14. Todos los directorios siguientes
están bajo `var/evidence/` del worktree H14 y conservan sus fallos originales.

## Comparación de productores

| Ensayo | Observación | Resultado |
|---|---|---|
| `h14-capture-1794950097659998000` | Fixture AppKit propia: callback SCK `suspended`, cero superficies, dimensiones cero | FAIL; preflight `CAPTURE_NOT_READY`, sin iniciar salidas |
| `h14-capture-1794950954829815000` | Owner nuevo, fixture al frente según el usuario; persiste la misma suspensión | FAIL; se cambia de hipótesis/productor |
| `h14-capture-gpui-control-1794951056342689000` | Ventana GPUI propia, mismo binario/módulo; superficies, consumo OBS y contenido avanzan | Ensayo dual verificado; no resuelve la fixture anterior |

La fixture AppKit registraba draws aproximadamente a 30 Hz, ventana visible y
occlusion visible. Eso no demuestra que WindowServer publicara nuevos buffers.
La herramienta de UI la veía como miniatura inclinada y fallaba al activarla.
Ni esos logs ni la apariencia de la herramienta identifican la causa de SCK.

En el ensayo GPUI, cinco callbacks iniciales suspended dieron paso a superficies
normales. Por eso `suspended` aislado no se transforma en error fatal. El conteo
de callbacks y las dimensiones tampoco bastan como prueba de frescura.

## Medios del ensayo GPUI

`media-analysis.json` conserva FFprobe, decodificación completa, PTS y hashes.
MKV: **999** frames, RTMP recibido: **996** frames, H.264 1920×1080/30 sin
B-frames, AAC estéreo a 48 kHz. Máximo hueco interior de PTS: **34 ms** en ambos.
RMS PCM: **0.06305 / 0.06271**. Son medidas decodificadas, no equivalencias
entre contadores de OBS y frames escritos.

Se extrajeron muestras en 2, 7, 12, 17, 22 y 27 segundos. Sus hashes de píxeles
son diferentes, con aproximadamente 12.6–12.8 mil canales que cambian más de
25 niveles entre pares. La hoja `contact-sheet.png` fue inspeccionada: contador
visible **32, 78, 125, 170, 217, 263** y marcador móvil. Esa observación sí
demuestra contenido cambiante en ese intervalo controlado.

## Pérdida y recuperación

`h14-capture-loss-1794951188992347000/report.json` conserva el cierre intencional
de la ventana capturada. `SOURCE_UNAVAILABLE` detuvo ambas salidas de forma
controlada: parada a quiescencia nativa aproximadamente **162 ms** en MKV y
**196 ms** en RTMP. Los archivos parciales se retienen para inspección.

Reabrir la ventana asignó otro ID de macOS. Reintentar la identidad antigua
falló, como corresponde. `recovery-followup.json` registra la nueva ventana
10108 y su selección explícita aceptada; aun así permaneció `CAPTURE_NOT_READY`
con SCK suspended y cero superficies durante la espera. Recuperación: **FAIL**.
La excepción final no incluye otro snapshot terminal; se conserva esa limitación
del harness, sin convertir la selección aceptada en recuperación exitosa.

El owner confirmó cierre normal antes de detener la fixture. No se modificaron
permisos, reloj, timestamps ni métodos de captura para mejorar estos resultados.

## Tratamiento vigente y trabajo restante

La fuente sin primer buffer bloquea el preflight. La pérdida de una ventana y
los errores fatales observados conservan la parada controlada. Tras un primer
buffer, `NO_RECENT_CAPTURE_BUFFER` advierte ausencia de buffers nuevos después
de tres segundos; no declara pérdida por una imagen estática. La UI debe mostrar
ese aviso y el usuario debe poder inspeccionar/reseleccionar la fuente.

Pendiente: aislar suspensión del productor frente a ciclo de vida SCK, repetir
con el bundle integrado y verificar recuperación real mediante nuevos píxeles
en preview, MKV y RTMP. No se declara beta estable con este fallo abierto.
