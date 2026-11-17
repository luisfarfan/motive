# H13 — referencias de medición para las regresiones H10

Estado: **piloto y mixer físicos PASS con las referencias corregidas**.
Los fallos previos y el reanálisis offline permanecen separados. Este documento
no convierte los archivos anteriores en PASS.
Los cambios afectan únicamente a `scripts/verify_h10_audio.py` y
`scripts/verify_h10_mixer.py`; no modifican libobs, el tono, la captura física,
los encoders ni los umbrales numéricos existentes.

## Fallos originales conservados

Ambos ensayos físicos usaron el bundle
`d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93`.

| Ensayo original | Resultado conservado | Medición que falla |
| --- | --- | --- |
| [Piloto H10](../var/evidence/h13-regressions-1794938328448756000/reports/verify_h10_audio.py/h10-pilot.json) | FAIL | Cambio de amplitud 440 Hz entre `tone_lower` y `mic_muted`: +0,517757758 dB; límite original `abs(delta) < 0,5 dB`. El cambio de ganancia mezclado −12,540899 dB sí cumplía −12 ±1 dB. |
| [Mixer H10](../var/evidence/h13-regressions-1794939220662892000/reports/verify_h10_mixer.py/h10-mixer.json) | FAIL | Ganancia estimada entre `both` y `lower`: −9,621392 dB; rango original −13…−11 dB. |

Los medios originales permanecen intactos:

- Piloto: `var/recordings/motive-1794938943817090.mkv`, SHA-256
  `641028247d701aba7780fb64237f0b51ce2c7fe9a14fc5f9d2ba74a4a4c7891d`.
- Mixer: `var/recordings/motive-1794939224154059.mkv`, SHA-256
  `9203e5ab05b9b6282ec273e25a55ff4cc3432bac2e7f5a1120c9b4efe90d8086`.

El [diagnóstico del piloto](../var/evidence/h13-h10-pilot-audio-diagnosis-1794939269396896000/report.json)
reproduce exactamente el cálculo original. La amplitud Hann de 440 Hz pasa
de 0,010577463 con micrófono abierto a 0,011227147 con micrófono silenciado.
Los dos tramos aislados, micrófono silenciado y desconectado, difieren solo
−0,008151 dB. Hay energía cercana a 440 Hz con el micrófono abierto y un
transitorio de banda ancha en `mic_unmuted`: una ventana de 100 ms alcanza
0,062261 a 440 Hz, mientras las restantes rondan 0,011. El RMS nativo del tono
permanece entre −45,104 y −44,933 dBFS. El pico mono máximo del clip es 0,385639.

El [diagnóstico del mixer](../var/evidence/h13-h10-mixer-audio-diagnosis-1794939476988910000/report.json)
reproduce amplitudes 0,031489361 y 0,010401458 en los dos tramos mezclados.
El tono aislado a −18 dB mide 0,007938532 y, tras desconectar el micrófono,
0,007933415: diferencia +0,005600 dB al comparar silenciado/desconectado.
Con el tono silenciado todavía se observa amplitud 0,000991159 en la banda
de 440 Hz; por tanto, esa medición de la mezcla no identifica exclusivamente
al generador digital. El pico global es −4,349231 dBFS.

La evidencia es compatible con interferencia no estacionaria y con su
representación al codificar la mezcla. No aísla una causa acústica concreta,
procesamiento del micrófono o algoritmo AAC. Las proyecciones coherentes de
un segundo se conservaron como diagnóstico; no reemplazan el estimador Hann
ni justifican declarar PASS. El primer artefacto offline del mixer,
`h13-h10-mixer-audio-diagnosis-1794939451029840000/report.json`, conserva su marca
`INVALID_DIAGNOSTIC_HARNESS`: una función local omitía devolver el resultado.
El diagnóstico válido enlazado arriba lo referencia expresamente.

## Procedimiento corregido

La ganancia digital necesita referencias donde el micrófono no aporte energía
a la misma banda. Las referencias se graban dentro de la misma salida real y
usan la misma captura física, que sigue abierta aunque su entrada esté muteada.
Cada referencia dura al menos tres segundos. Después se restablece tono −6 dB
y micrófono abierto a +6 dB antes de ejecutar la secuencia original.

| Referencia | Micrófono | Ganancia del tono | Uso |
| --- | --- | ---: | --- |
| `tone_reference_high` | Mute; captura abierta | −6 dB | Referencia alta de ganancia en piloto, MKV y RTMP. |
| `tone_reference_low` | Mute; captura abierta | −18 dB | Referencia baja y comparación con `mic_muted`; también desconexión en el piloto. |
| `tone_reference_continuity` | Mute; captura abierta | 0 dB | Solo mixer: referencia de los tramos posteriores de desconexión, recuperación y Cut/Fade. |

Se mantiene el estimador original: amplitudes de Hann de 100 ms y agregado
RMS de esas amplitudes sobre el segundo interior de cada etapa. Se guardan
todas las ventanas, sus tiempos y los controles de entrada. No se eligen
subventanas según su resultado. Las muestras de estado verifican el mute del
micrófono y la ganancia de cada referencia.

El cambio de ganancia exige el mismo intervalo estricto −13…−11 dB usando
`tone_reference_low / tone_reference_high`. El piloto conserva el límite
estricto de 0,5 dB para `mic_muted` y `mic_disconnected`, ahora contra la
referencia aislada a −18 dB. El mixer conserva 0,6 dB para esas comparaciones:
mute temprano contra −18 dB y desconexión posterior contra 0 dB.

En el mixer, el tono de `mic_disconnected`, `mic_recovered` y `video_changes`
cambia de −18 a 0 dB. Se declara este cambio de estímulo porque aumenta la
relación entre el tono conocido y el contenido del micrófono cercano a 440 Hz.
La recuperación y los cambios Cut/Fade se ejecutan con el micrófono físico
abierto a +6 dB. No se sustituyen por etapas con el micrófono silenciado.
La continuidad conserva cada ventana original de 100 ms, margen de 0,2 s
en extremos y condición `amplitud_440 > referencia_0_dB × 0,55`. La referencia
usa el mismo nivel del tono que las etapas comprobadas.

Se conservan como diagnósticos las estimaciones mezcladas de ganancia y la
variación entre referencias mezcladas y etapas aisladas. Los informes explican
que no permiten atribuir por sí solas la amplitud al tono digital. La duración
de la reproducción 997 Hz propia aumenta a 60 s en el piloto y 240 s en el
mixer para cubrir las referencias y ambas salidas; el proceso propio se
termina en `finally`.

Los demás requisitos permanecen: presencia de ambas fuentes, mute/unmute,
ganancia del micrófono por 997 Hz, medidores RMS con tolerancia de 2 dB,
instancias e identidad del núcleo, recuperación, clipping global, timestamps,
video Cut/Fade, persistencia, CLI y MCP. Las salidas de aceptación siguen
exigiendo ausencia de clipping; el ensayo deliberadamente saturado permanece
separado. No se cambian las conversiones de canal ni el decodificador.

Tras la repetición descrita al final, el gate de mute del tono usa también una
comparación aislada: `both_muted / tone_reference_continuity < 0,03`. Ambas
etapas tienen micrófono muteado y tono a ganancia 0 dB; solo cambia el mute del
tono. Cada snapshot comprueba esos controles, incluido tono no muteado en la
referencia. Se mantiene el límite original 0,03 y la exigencia más fuerte ya
existente `both_muted RMS < −100 dBFS`.

`tone_muted`, con el micrófono abierto, conserva todas las mediciones y el
ratio 440 Hz contra `tone_before_mute` como diagnóstico no identificable. Se
exige explícitamente que su amplitud física de 997 Hz supere 0,4 veces la de
`both`, además de la comparación original de RMS del micrófono con tolerancia
de 2 dB. Así se conservan los estados independientes: micrófono silenciado con
tono audible, tono silenciado con micrófono audible y ambas entradas
silenciadas. La supresión cuantitativa de 440 Hz se acredita en el estado
aislado; no se afirma poder atribuir cada componente residual de 440 Hz de
una mezcla con micrófono abierto. Los medidores por entrada son pre-mute y
no demuestran por sí mismos el silencio posterior al mute.

## Control adicional de continuidad en referencias aisladas

`isolated_tone_continuity` recorre ventanas PCM de 960 muestras (20 ms), con
paso de 480 (10 ms), a 48 kHz. Excluye 0,2 s en cada extremo por los cambios
de control y AAC; conserva todas las ventanas restantes y exige al menos 50.
Cada RMS debe estar a menos de 1 dB del nivel esperado, calculado a partir del
tono conocido, no ajustado a una ventana que haya pasado:

```text
RMS esperado = 0,0630957344 × 10^(ganancia_dB / 20) × factor_decode / sqrt(2)
```

El mixer conserva `pan=mono|c0=c0`, factor 1: niveles esperados −33,0103,
−45,0103 y −27,0103 dBFS para ganancias −6, −18 y 0 dB. El piloto conserva
su conversión histórica `-ac 1`, que suma los canales idénticos con factor
sqrt(2): sus referencias esperan −30 y −42 dBFS. Ese factor aparece
explícitamente en cada resultado.

Este control de 20 ms aplica **solo a las referencias aisladas**. Los tramos
mixtos conservan la prueba de 100 ms; la sensibilidad demostrada con 20 ms
no se extiende a ellos. Tampoco acredita cada muestra del archivo, los márgenes
excluidos o cualquier interrupción bajo señales arbitrarias. La presencia de
un micrófono más fuerte puede enmascarar o interferir una medición de banda;
los fallos futuros deben conservarse y diagnosticarse.

## Validación offline del control nuevo

El [informe reproducible](../var/evidence/h13-h10-reference-checker-1794940054296064000/report.json)
y su [programa local](../var/evidence/h13-h10-reference-checker-1794940054296064000/validate.py)
extraen solamente las funciones puras. Decodifican cuatro recortes de audio
cerrados de 1,5 s, sin video, y conservan comandos, hashes PCM y todas las
ventanas. SHA-256 del verificador de piloto validado:
`b3a492dfb379f172ea37f2544e16205478870de656e22c98a265e1782ef10511`.

| Recorte real | Ganancia / canal | Ventanas de 20 ms | Error absoluto máximo | Resultado esperado / observado |
| --- | --- | ---: | ---: | --- |
| `motive-1794933992527893.mkv`, primeros 1,5 s; hueco real previo | −6 dB / izquierdo | 109 | 49,405945 dB | FAIL / FAIL |
| `motive-1794933573407156.mkv`, primeros 1,5 s; tono limpio | −6 dB / izquierdo | 109 | 0,110769 dB | PASS / PASS |
| `motive-1794939224154059.mkv`, desde 7,315100875 s; micrófono muteado | −18 dB / izquierdo | 109 | 0,136387 dB | PASS / PASS |
| `motive-1794938943817090.mkv`, desde 8,462185958 s; micrófono muteado | −18 dB / mono histórico | 109 | 0,135163 dB | PASS / PASS |

El primer recorte contiene el hueco real de 1024 muestras estudiado en
[la investigación del arranque](h13-audio-startup-investigation.md). Rechazarlo
confirma que el control adicional detecta aquel defecto aunque los paquetes
AAC tengan timestamps continuos. Los tramos limpios de los dos archivos H10
fallidos solo validan el control local; sus ensayos completos siguen FAIL.

Para cada uno de los tres recortes limpios se crean únicamente en memoria
cuatro copias del PCM y se sustituyen 1024 muestras por cero, comenzando en
las posiciones 28800, 29040, 29279 y 29280. Las 12 copias se rechazan. Los
medios originales, libobs y la captura no se modifican. Estos negativos
comprueban el evaluador; no se presentan como capturas reales ni como
aceptación del producto. En los cuatro recortes, Hann 440/997 Hz devuelve
exactamente el mismo resultado que la función anterior de `HEAD`.

## Repetición física con referencias y nuevo fallo de mute

La [corrida serial](../var/evidence/h13-regressions-1794940354925977000/manifest.json)
usó el mismo bundle `d9b8d702…0e2d93`; su
[log](../var/evidence/h13-build/final-h10-references.log) registra 32,9 s para el
piloto y 50,7 s para el mixer. El manifiesto conserva **FAIL** global:

- [Piloto PASS](../var/evidence/h13-regressions-1794940354925977000/reports/verify_h10_audio.py/h10-pilot.json):
  ganancia aislada −11,990455 dB; referencias de 330/322 ventanas con errores
  máximos 0,110634/0,168425 dB. Pico mono global 0,331215.
- [Mixer FAIL](../var/evidence/h13-regressions-1794940354925977000/reports/verify_h10_mixer.py/h10-mixer.json):
  ganancia aislada −12,002061 dB; las tres referencias pasan con 266/265/275
  ventanas y errores máximos 0,101008/0,148129/0,093622 dB. El gate posterior
  `tone_muted < tone_before_mute × 0,03` falla: 0,002080213 frente al límite
  0,001887161, ratio 0,033068925 y reducción −29,611598 dB. El micrófono
  continúa: amplitud 997 Hz 1,060774 veces la de `both`. El tramo `both_muted`
  mide amplitud 440 Hz cero y RMS −300 dBFS, piso numérico del evaluador.

El MKV del mixer es `var/recordings/motive-1794940392905486.mkv`, SHA-256
`23844105b106b6f846f78d0ba8f22e7ea597a46e21de8f4a77e46282ebc3104c`.
Su pico global medido es −8,142176 dBFS. El ensayo abortó al analizar ese MKV:
no acredita una nueva salida RTMP, persistencia ni gates posteriores que
todavía no habían sido evaluados. El fallo mezclado se conserva aunque la
supresión aislada resulte compatible con silencio.

El [negativo offline de mute](../var/evidence/h13-h10-mute-checker-1794940570051198000/report.json)
evalúa el propio predicado AST del checker nuevo, sin modificar sus números.
Decodifica un segundo del `both_muted` real y comprueba ratio cero. A una copia
en memoria añade una senoide de 440 Hz cuya amplitud es 4 % de la referencia
aislada: ratio medido 0,039999999, rechazado por el límite 0,03. Los originales
no se modifican; esta señal sintética valida el detector, no el producto.

El [reanálisis completo del MKV](../var/evidence/h13-h10-mute-checker-1794940570051198000/full-mkv-reanalysis.json)
ejecuta `analyse` íntegro bajo el checker corregido y pasa todos sus gates,
incluidos los posteriores al fallo original. Ganancia del micrófono:
−11,679701 dB; error RMS tono/micrófono: +0,007539/−0,008114 dB. Las 27, 26 y
57 ventanas de continuidad de desconexión, recuperación y video tienen mínimos
0,063002, 0,060726 y 0,054036, frente al límite 0,034696. Los gaps máximos son
22 ms de audio y 34 ms de video; el análisis visual cuenta 105 frames mint,
40 rojos y 39 colores mezclados distintos.

Ese resultado es un artefacto nuevo de análisis offline. No sobreescribe el
FAIL físico, no ejecuta acciones de control y no acredita RTMP ni persistencia
que el ensayo original no alcanzó. Esas comprobaciones se completaron después
en la nueva corrida física siguiente.

## Corrida física final del mixer

El [manifiesto final PASS](../var/evidence/h13-regressions-1794940880710737000/manifest.json)
y su [informe del mixer](../var/evidence/h13-regressions-1794940880710737000/reports/verify_h10_mixer.py/h10-mixer.json)
conservan la secuencia completa, que duró 109,966 s, sobre el mismo bundle
`d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93`.
El SHA-256 del informe archivado es
`423979f775ae6f9e171e00371e5dd53f3e8ed977cc2c852b5f778e1abba888ed`.

| Medición final | MKV | RTMP local recibido en FLV |
| --- | ---: | ---: |
| Duración de audio decodificado | 47,338667 s | 47,424000 s |
| Ganancia digital aislada | −12,002393 dB | −12,010617 dB |
| Ganancia del micrófono, 997 Hz | −11,628350 dB | −12,046635 dB |
| Error RMS tono aislado / micrófono aislado | +0,026508 / −0,088137 dB | +0,024281 / +0,172369 dB |
| Ventanas de referencia de 20 ms, total | 812 | 810 |
| Mayor error absoluto de las referencias | 0,149499 dB | 0,151555 dB |
| Amplitud 440 Hz con ambas entradas muteadas | 0 | 0 |
| Pico global decodificado | −13,271861 dBFS | −17,744208 dBFS |
| Ventanas de continuidad de 100 ms, total | 110 | 110 |
| Menor amplitud 440 Hz en continuidad | 0,062474 | 0,061449 |
| Umbral de continuidad, referencia ×0,55 | 0,034666 | 0,034681 |
| Máximo gap de audio / video | 22 / 34 ms | 22 / 34 ms |
| Frames mint / rojos / colores mezclados distintos | 105 / 40 / 37 | 107 / 41 / 38 |

Los dos medios mantienen las operaciones de micrófono, cambios de ganancia,
mute/unmute, liberación y reapertura nativa, Cut/Fade, comprobaciones CLI/MCP
e identidad de instancias. No hubo clipping inesperado en las salidas de
aceptación. La prueba separada de saturación activó el aviso esperado y midió
pico decodificado −0,083092 dBFS; no se confunde con las salidas anteriores.

- MKV: `var/recordings/motive-1794940884471664.mkv`, SHA-256
  `329481333065a09b67c3129a8804c88ef9f3677f06e0902cf6caeb76d0c11654`.
- RTMP: `var/evidence/h10-stream-1794940933178028000.flv`, SHA-256
  `09aba7a154b0259399f9d52a8d2a7ef24cb0f8a29e1699d3266c616202c2894f`.

La restauración después del reinicio pasó: tono 440 Hz a amplitud 0,007931986
y micrófono muteado con amplitud 997 Hz de 0,000000013270. La comparación
conservó exactamente los archivos de escenas y perfiles de salida, con hashes
`4449d4307c8956d4bf5dc7b5c52e30b61d6c4c980281fe2dd16291fd5e0e890c` y
`0003952d6158e3f57b929a8fa77f56ea3db8b72e3704ef38312ea481c222a127`.

Este PASS se limita al procedimiento y los medios descritos. La recuperación
probada libera y reabre la captura nativa; no demuestra un desenchufe físico
del dispositivo. La sensibilidad de 20 ms sigue limitada a referencias
aisladas, y los estados mixtos conservan sus ventanas de 100 ms. La exclusión
del audio propio por ScreenCaptureKit tiene su
[informe independiente](h13-system-audio-exclusion-final.md) y no queda
acreditada por estas pruebas H10.
