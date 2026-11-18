# H14 · B3: colección de ventanas A→B→A

El ensayo **no demuestra una mejora causal de captura ni cierra el bloqueo de
foco**. A1 falla el preflight inicial, B entrega dos archivos con un contador
real avanzando pero queda INCONCLUSIVE, y A2 no alcanza una observación válida
del primer foco. Se conservan esos resultados; no se incorporó ninguna
preferencia de colección al producto.

La [repetición posterior con ventanas agrupadas](h14-collection-b3-followup.md)
conserva estos resultados históricos. Obtiene dos tomas adicionales del brazo
default, pero sigue sin corroborar el foco del estudio y no cierra el gate.

| Brazo | Fixture PID / window ID | Medios | Resultado original | Análisis separado |
|---|---|---|---|---|
| A1 · default | 89834 / 12258 | Ninguno | FAIL | **FAIL** |
| B · join-all | 93077 / 12336 | MKV + RTMP loopback | PARTIAL | **INCONCLUSIVE** |
| A2 · default | 94238 / 12381 | Ninguno | FAIL | **FAIL** |

Los tres usan el mismo owner B3, PID 88708, ejecutable SHA-256
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`,
la misma fixture firmada y el mismo módulo SCK
`122d0ddd60ada200d2986ebe3920fcb574f029ae388673da1f815d0b2ca69fd8`.
Cada brazo tiene proceso e ID de ventana nuevos. La fixture default conserva
`collectionBehavior=0`; join-all fija únicamente el grupo mutuamente excluyente
en `CanJoinAllApplications` (`262144`). No se cambiaron preferencias globales,
permisos, clases de ventana, nivel, renderer ni método de captura.

## A1: superficie tardía y marcador no corroborado

El [informe original](../var/evidence/h14-collection-b3-A1-run/report.json) conserva
14 respuestas `CAPTURE_NOT_READY` y ninguna solicitud `start_output`.
La fuente comienza running con un callback suspended sin IOSurface. No se
observa ningún callback de estado `started`; running es la fase del stream.

La [auditoría de JSON y fuente](../var/evidence/h14-collection-b3-A1-audit/findings.md)
sitúa la última muestra sin superficie en el bracket host
`[76411.210197,76411.228417] s` y la primera con superficie en
`[76411.737824,76411.769036] s`, ya con cinco samples complete y tamaño 680×272.
La primera llegada reconstruida es OBS `76411601941625 ns`, **12.820361 s después
de crear la fuente**. Se obtiene de la fórmula pública de FPS de vida y coincide
en 85 snapshots; no es un timestamp de primera superficie exportado directamente.

La calibración retenida del RPC de creación tiene una incertidumbre de
**254.186 ms**. Sitúa la llegada en host `[76411.508673,76411.762859] s`, después
del deadline inicial `76403.427067 s`. La superficie posterior no provoca
reintento automático de salidas ni convierte el preflight previo en PASS.
El terminal contiene 1418 superficies complete, una suspended y cero errores;
esto sigue siendo metadata, no prueba de píxeles decodificados.

El único marcador `fixture_front` se emitió a host `76398.427067 s`, con una
nota de CUA sobre ventana completa y tick 1885. Las muestras propias que lo
rodean dicen `app_active=false`, `key_window=false`, bounds CG **196×97**, ticks
1981/1991. La fixture había perdido key **6.444 s antes** del marcador. Recupera
app/key a uptime `76410.949324 s`; el intervalo calibrado de primera superficie
queda **0.559–0.814 s después**. Es una relación temporal, sin atribución causal.

Los intentos de elevar/clicar el estudio y Cmd-Tab constan en
[observación CUA](../var/evidence/h14-collection-b3-A1-run/root-cua-observation.json),
pero no tienen timestamps individuales y no pueden alinearse con esos eventos.
No hay marcadores de studio-front ni fixture-return. **Foco NOT_OBSERVED**.

## B: contenido real avanzado, foco y alineación pendientes

En B, los preflights pasan y ambas salidas comienzan. La primera muestra ya
contiene cuatro superficies complete. La primera superficie reconstruida,
consistente en 110 snapshots, llega **104.486 ms después de la creación**.
El terminal contiene 1825 superficies complete, ninguna suspended, sin errores
ni regresiones de PTS. Esto describe este brazo; no aísla por sí solo el efecto
de la preferencia de colección.

El [análisis multimedia separado](../var/evidence/h14-collection-b3-offline-01/B/analysis.json)
usó exclusivamente los binarios FFmpeg/ffprobe del B3 y decodificó el contador
binario real de 16 bits a 5 Hz, una muestra de cada seis frames a 30 fps.

| B | MKV local | RTMP recibido |
|---|---:|---:|
| Frames de video decodificados | 1787 | 1782 |
| Muestras del contador válidas / totales | 298 / 298 | 297 / 297 |
| Intervalo muestreado | 59.4 s | 59.2 s |
| Avance del contador | 594 ticks | 591 ticks |
| Repetición máxima observada | 0.200 s | 0.200 s |
| Saltos inesperados / huecos de decode | 0 / 0 | 0 / 0 |
| Intervalo máximo de PTS de video | 34 ms | 34 ms |
| Gate global del contador | PASS | PASS |

Los PTS de video son estrictamente crecientes. Los samples del contador están
en [MKV](../var/evidence/h14-collection-b3-offline-01/B/recording-counter.json) y
[RTMP](../var/evidence/h14-collection-b3-offline-01/B/streaming-counter.json).
El muestreo no certifica frescura de cada frame ni entrega completa.

Hay dos límites independientes:

1. **Foco no corroborado.** Aunque las tres observaciones CUA describen ventanas
   completas, los samples interiores de las fases fixture-front y fixture-return
   conservan app_active/key=false: **26/26 y 6/6** observaciones incompatibles.
   Studio-front tiene 15/15 samples de fixture inactiva, corroborando ese marcador
   junto con la observación CUA. Inactividad por sí sola no identifica otra app
   al frente. La calibración fixture/host tiene incertidumbre de 5.583 µs y
   conserva el guard de dos segundos alrededor de los cambios.
2. **Alineación por fase inconclusa.** El guard existente de tamaño/keyframe del
   primer paquete nativo frente al contenedor rechaza la correspondencia. No se
   debilitó, no se desplazó el origen y no se reutilizó automáticamente la prueba
   de framing de otro clip. Por ello no se atribuyen intervalos del contador a
   cada fase. El campo exploratorio `tail_accounting` se calculó antes de ese
   guard; no constituye aquí evidencia validada de entrega final.

El resultado continúa **INCONCLUSIVE**, aunque el contador global decodificado
avance correctamente. No es un A/B de foco válido ni una demostración de causa.

## A2 y cierre

A2 agotó el timeout esperando el primer marcador. CUA solo observó una miniatura
tras Raise y el clic devolvió `windowNotFoundAtPosition`. No se inventó un
marcador, no se seleccionó una captura y no se inició salida. El owner permaneció
con su patrón. Los contadores de outputs conservados en su estado pertenecen
al intento B anterior; no representan medios nuevos de A2.

El [análisis A2](../var/evidence/h14-collection-b3-offline-01/A2/analysis.json)
mantiene FAIL y foco NOT_OBSERVED; no hay contador de píxeles que decodificar.
Las tres fixtures se cerraron normalmente. Tras cleanup, owner sin capturas,
ambas salidas idle/quiescent, ningún worker de salida pendiente; el receptor B
terminó con código 0. No se hicieron reintentos físicos adicionales.

## Evidencia y límites

Los análisis se ejecutaron en serie A1→B→A2, con códigos 1/0/1. El código 0 de B
significa que terminó el análisis con INCONCLUSIVE, no PASS. Los comandos y
stderr están en [commands.json](../var/evidence/h14-collection-b3-offline-01/commands.json).
Originales, scripts y producto permanecen intactos.

| Archivo B | SHA-256 |
|---|---|
| MKV | `9674006b079c2a4f9917868f457959c4e1218f0481f22c466e999717805a66b7` |
| RTMP recibido | `6f394ec1b4f27e8def31b793b0f4fd1af743d1a7304bb61da6cdd9d89d4762ed` |

La secuencia no permite concluir que `CanJoinAllApplications` corrija la captura,
que una función de gestión de ventanas cause la suspensión, ni que A2 reproduzca
la ausencia inicial de buffers de A1: A2 nunca inició captura. El gate general
de recuperación/foco sigue pendiente. Este pase mide video y contador; no
verifica PCM, sincronía A/V ni la totalidad de paquetes de salida.
