# H14 B3 — producción GPUI real

**Resultado: PARTIAL.** La sesión demuestra producción desde GPUI, grabación continua durante una desconexión RTMP inducida, recuperación explícita del streaming, widgets y transiciones visibles en medios reales, guardado/restauración de proyecto y mixer, y cierre normal. Conserva el fallo del colector al salir, la configuración nueva de Show Control cuyo guardado no se observó, una transición visual inconclusa y cobertura pendiente de accesibilidad y revisión completa de la interfaz. No declara H14 completo.

## Evidencia y alcance

- [Setup, fixture y receptores propios](../var/evidence/h14-native-b3-setup-01/manifest.json), [notas CUA](../var/evidence/h14-native-b3-setup-01/ui-observation-notes.json) y [mapa de tres medios](../var/evidence/h14-native-b3-setup-01/media-manifest.json).
- [Observador original](../var/evidence/h13-native-1794963312312022000/report.json): PID 10022, 1.795 muestras, 34 cambios de `last_action`. SHA-256 `8b7ecb3359cc5dd76af891a0e44b50646d27ead6ed085200e63d262b20f8ed28`.
- [Índice de hechos y hashes](../var/evidence/h14-native-b3-audit-01/fact-index.json), reproducible mediante [index.py](../var/evidence/h14-native-b3-audit-01/index.py), SHA-256 `1a5604eca845371b1b883fd51b7ca4fa6624e199f26c8ed9fb4f5a89f44d5a77`.
- [Análisis estructural completo](../var/evidence/h13-native-analysis-1794964640281051000/report.json), [análisis audiovisual](../var/evidence/h14-native-b3-analysis-02/report.json), [metodología y resultados detallados](../var/evidence/h14-native-b3-analysis-02/findings.md), [revisión visual de root](../var/evidence/h14-native-b3-analysis-02/root-visual-review.json) e [índice compacto de medios](../var/evidence/h14-native-b3-audit-01/media-index.json). Este último verifica hashes coincidentes entre ambos análisis y las imágenes revisadas, sin volver a decodificar.

Se utilizó el bundle portable B3 fuera del checkout, ejecutable SHA-256 `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`. La fixture de audio/ventana era propia, PID 11699. La cámara apuntaba a contenido controlado; la revisión del medio muestra un techo sin personas. Los dos receptores fueron loopback; esta sesión no efectuó streaming externo. Las pruebas físicas se hicieron serialmente con el lock compartido.

La observación CLI/MCP leyó el estado del mismo owner; las acciones de producción se accionaron mediante GPUI y CUA. Un `last_action` observado acredita la mutación registrada por el núcleo, pero una pulsación sin cambio confirmado no se convierte en aceptación. El muestreo tuvo mediana 0,554 s y máximo 1,046 s; no registra todos los estados intermedios.

## Operaciones observadas

| Operación | Evidencia y resultado |
| --- | --- |
| Preparar estudio | GPUI configuró 1920×1080 a 30 fps y añadió cámara, micrófono físico, audio de la fixture y su ventana. Micrófono `audio-1` instancia 1; aplicación `audio-2` instancia 2. |
| Instalar MATCHDAY | Revisión/instalación local completó **73/73** pasos, sin error. El receipt no afirma por sí mismo presentación visual; esta se comprobó después en los medios. |
| Perfil de salida | Se intentó escribir 6000 kb/s, pero no se observó una mutación confirmada. Los tres intentos usaron realmente `standard`, **2500 kb/s**, CBR, keyframe 2 s, reorder desactivado y VideoToolbox hardware, sin fallback. No se afirma que el perfil de 6000 se aplicara. |
| Preflight | Hubo pulsaciones, pero no se retuvo texto AX que confirme su resultado. **NOT_OBSERVED** para ese gesto; el inicio posterior no sustituye su verificación. |
| Iniciar REC y RTMP | `UI · start_output` revisiones 105 y 107; un intento REC y dos intentos RTMP en toda la sesión. |
| Live Deck | Cinco jobs finalizados: dos `deck-goal`, un countdown, un lower third y `deck-brb`. Eventos `ui-10022-1`…`ui-10022-5`; contador final **goals=2**. |
| Cooldown | CUA observó el botón de gol deshabilitado con «Espera 10s» y otra pulsación a unos 5 s, sin job adicional. No hay receipt de rechazo del backend: se acredita el estado deshabilitado observado. |
| Editar composición | `UI · set_transform`, revisión 139: ventana propia pasó de X=640 a X=32 en coordenadas de diseño, conservando Y=32 y tamaño 288×162. El medio revisado muestra la ventana a la izquierda, sin el solapamiento anterior. |
| Mixer en vivo | Micrófono pasó de −6 a −19 dB, revisión 141; mute en 142 y unmute en 147. Audio de aplicación siguió a −6 dB. No se reiniciaron sus instancias nativas durante las muestras. |
| Cambiar escenas | Cut y Fade accionados desde GPUI y desde Show Control; las comprobaciones de píxeles se detallan abajo. |
| Guardar | `UI · save_audio_mixer`, revisión 163, y `UI · save_project`, revisión 164, con archivos guardados y restauración exacta verificados. |
| Revelar grabación | Finder mostró seleccionado `motive-1794964037703259.mkv`, según la ruta AX exacta retenida en las notas CUA. No se abrió el archivo como reproductor para acreditar este gesto. |

## Pérdida RTMP y recuperación

Root envió **SIGTERM exclusivamente al receptor propio PID 11716**, tras verificar su argv, y guardó [el evento](../var/evidence/h14-native-b3-setup-01/receiver-loss.json). El streaming 1 pasó a `error`, `native_busy=false`, `OUTPUT_DISCONNECTED`, código nativo −5, recuperación explícita. No se trata de un fallo espontáneo ni de una reconexión automática.

Los snapshots [anterior](../var/evidence/h14-native-b3-setup-01/before-receiver-loss.json) y [posterior](../var/evidence/h14-native-b3-setup-01/receiver-loss-observed.json) mantienen REC1 activo: sus frames de salida avanzan de 2.218 a 2.654. El registro completo conserva 396 muestras REC1 activas, con contador monotónico, atravesando `streaming:1 error → idle → streaming:2 active`.

Se lanzó el receptor propio PID 22087. GPUI registró `recover_output_target` revisión 129 y un nuevo `start_output` revisión 131. RTMP2 terminó posteriormente por acción UI. REC1 continuó hasta su propia detención y acumuló **221.104 ms de duración activa nativa**. La duración activa no equivale a duración decodificada ni a prueba de entrega de todos los paquetes.

## Medios reales

Los tres archivos decodifican completos con exit 0 y stderr vacío: H.264 1920×1080, 30 fps, sin B-frames; AAC estéreo 48 kHz. PTS de video positivos y DTS conocidos monotónicos; máximo gap de video **34 ms** y AAC **22 ms**, incluyendo las colas examinadas. La cadencia estricta del analizador original es **PASS** para los tres. REC1 y RTMP2 tienen integridad/funcionalidad estructural PASS; RTMP1 mantiene **INCONCLUSIVE** por su finalización interrumpida deliberadamente. El agregado estructural y su cobertura permanecen INCONCLUSIVE, con `acceptance=NOT_EVALUATED`.

| Medio | Frames decodificados | Extremo temporal de video¹ | Duración PCM | Pico PCM máximo | RMS PCM aproximado |
| --- | ---: | ---: | ---: | ---: | ---: |
| REC1 | 6.629 | 220,966 s | 220,949333 s | −20,604 dBFS | −33,101 dBFS |
| RTMP1, fallo inducido | 2.002 | 66,754 s | 66,730667 s | −21,994 dBFS | −32,517 dBFS |
| RTMP2, recuperación | 3.253 | 108,454 s | 108,437333 s | −28,876 dBFS | −33,306 dBFS |

¹ Extremo/duración indicado por el contenedor para video; RTMP comienza con PTS 0,021 s. Los últimos PTS de frame son 220,933, 66,721 y 108,421 s respectivamente. No se interpreta la resta entre relojes nativos y estos tiempos como sincronización A/V.

PCM estéreo completo: cero muestras no finitas, cero muestras con magnitud ≥0,999 y cero ventanas interiores de 100 ms por debajo de −80 dBFS en ambos canales; el criterio de silencio excluye las dos primeras y dos últimas ventanas. El contador nativo de clipping también permaneció en cero. Esto acredita ausencia de saturación y silencios totales bajo esos criterios; no descarta cortes menores de 100 ms, **no aísla la contribución del micrófono, no calibra los medidores contra una fuente aislada y no demuestra sincronización A/V**. La variación de ganancia y mute tiene evidencia de UI/estado; su efecto independiente sobre la mezcla acústica conserva cobertura pendiente.

| Archivo | SHA-256 |
| --- | --- |
| `motive-1794964037703259.mkv` | `f93bb4d95a9930ffe8961375befa197fe1bf689d1027237f03086feabfe41805` |
| `received-1.mkv` | `8403bbe68a26790ed2a0d4ef62c8015df94567ea8654cababc9919a9ba1c4774` |
| `received-2.mkv` | `6a61b542fe574e441c9665974e03873e8f03c145eb4a17b788b1b85faad42585` |

Los contadores finales codificado/salida/decodificado fueron REC1 **6632/6629/6629**, RTMP1 **2005/2003/2002** y RTMP2 **3255/3253/3253**. Se mantienen sus diferencias: `frames_written`, entrega total y equivalencia entre contadores no se deducen de ellas. Esta prueba no reemplaza la [matriz de contabilidad y cola B3](h14-output-matrix-b3-verification.md).

El analizador estructural usó FFmpeg/ffprobe 9.0.2 de su entorno; el analizador visual/PCM empleó las rutas explícitas del bundle B3. Ambos preservan sus herramientas y comandos, y coinciden en los hashes de los tres medios y las métricas PCM. No hubo recompilación del producto para estos análisis.

## Widgets, transiciones y captura visible

Las dos celebraciones se localizaron en cada archivo por sus píxeles, usando las duraciones nativas solo como estimación de búsqueda. Hay cuatro observaciones: gol1 en REC1/RTMP1 y gol2 en REC1/RTMP2. Las cuatro pasan el criterio geométrico existente: 19 frames de revisión de entrada, caja de 296×75 a 358×90 en la ROI reducida, sin pasos negativos; 99–100 frames de hold y desaparición aproximadamente 4,467 s después del primer frame visible. Las 19 muestras cubren 600 ms desde el primer contenido medible; no miden una entrada nativa de 600 ms ni certifican por sí solas la duración del contrato ScaleIn de 450 ms. No se afirma observar el tick inicial de opacidad cero.

Cut operación 2 pasa en REC1/RTMP1 y Cut operación 4 en REC1/RTMP2, sin frames intermedios en la sonda fija. Fade operación 5, de 1.000 ms, pasa en REC1/RTMP2 con 24 frames intermedios y 24/23 niveles de mezcla redondeados a centésimas. Fade final operación 6 pasa en REC1 con 24 frames intermedios y 24 niveles. **Fade operación 3 entre escenas MATCHDAY sigue INCONCLUSIVE** en REC1/RTMP1: los extremos de la ROI elegida tienen contraste cero; no se cambió la región después de ver los píxeles.

La revisión visual de root sobre PNGs extraídos confirma «GOOOAL!», lower third «ALEX RIVERA», countdown de 03:09 a 03:05, el Fade de cámara/ventana a MATCHDAY y la cámara con contenido controlado. En nueve muestras REC1, PTS 131,233…216,933 s, el contador de la ventana avanza de **33572864 a 37686272**. El intervalo en MATCHDAY se omite; estos contactos no certifican frescura de cada frame ni resuelven los [fallos anteriores de captura](h14-collection-b3-verification.md).

El primer análisis visual [analysis-01](../var/evidence/h14-native-b3-analysis-01/report.json) conserva su fallo de instrumentación: dos timestamps de `showinfo` frente a un frame RGB. [analysis-02](../var/evidence/h14-native-b3-analysis-02/analyze.py) conserva ambos timestamps filtrados y asocia el primero al único frame emitido con passthrough; no cambia los criterios de píxeles ni sustituye el informe fallido.

## Persistencia, biblioteca y cierre

Tras Cmd+Q del owner 10022, el proceso reabierto 24634 comenzó con proyecto v3 por defecto, mixer vacío y salidas idle. Se cargaron por GPUI el proyecto v5 y el mixer v2 guardados. El contenido JSON restaurado es exactamente igual al archivo guardado y al estado previo a salir, incluidos IDs y ganancia final −19 dB del micrófono. Los estados están en [reopened-initial](../var/evidence/h14-native-b3-setup-01/reopened-initial.json), [project-restored](../var/evidence/h14-native-b3-setup-01/project-restored.json) y [fully-restored](../var/evidence/h14-native-b3-setup-01/fully-restored.json).

Las pulsaciones «Guardar» de Show Control **no dejaron evidencia de guardar la nueva configuración**. El archivo mantuvo su SHA-256 previo `6f54a1d66cbfdef8327f27b4d8d06ea8c5d6d38d2db90bb5851b2a89f95a4e17`: fingerprint persistido `c4fa0860…`, frente al de la configuración en memoria `81f5fbbd…`. Al cargar se restauró esa configuración anterior, `configured=true`, `armed=false`, `bindings_current=false`, `jobs=[]`. Un intento de activar no cambió ese estado y no produjo un receipt de error retenido. Esto confirma estado seguro desarmado con referencias antiguas; **no demuestra un fallo del mecanismo de persistencia ni un rechazo específico del backend**. Guardar la configuración nueva desde ese flujo sigue NOT_OBSERVED.

La biblioteca permitió revelar en Finder el basename exacto de REC1 mediante la API nativa. No se atribuye a la biblioteca una validación multimedia automática ni estado «completo» por existir el archivo.

Ambos owners salieron con Cmd+Q normal, con salidas ya idle y `native_busy=false`. Se conservaron los receipts [10022, revisión 165](../var/evidence/h14-native-b3-setup-01/normal-ui-shutdown.json) y [24634, revisión 21](../var/evidence/h14-native-b3-setup-01/normal-restored-ui-shutdown.json), ambos con `delivery_verified=false`. La fixture también cerró normalmente. [Cleanup](../var/evidence/h14-native-b3-setup-01/cleanup.json) confirma ausencia de los cinco procesos propios —dos owners, fixture y dos receptores— y restauración exacta de todos los hashes iniciales de stores.

Root [liberó el lock físico](../var/evidence/h14-native-b3-setup-01/physical-lock-release.json) después de confirmar que los procesos de prueba y el lease de etapa estaban ausentes; no quedan pruebas físicas activas de esta sesión.

El colector original conserva **`collector_ok=false` y `STUDIO_UNAVAILABLE`**: al salir desde idle, el owner desapareció antes de que el polling de 0,5 s observara `shutdown_pending`. La [observación de salida](../var/evidence/h14-native-b3-setup-01/ui-quit-observation.json) y los receipts son evidencia separada del cierre normal; no convierten ese resultado del colector en PASS. Esta sesión tampoco prueba cierre con salidas activas, cierre desde Dock ni toda la barrera H8.

## Límites conservados

- Revisión visual del estudio GPUI a tamaño completo y VoiceOver: **NOT_OBSERVED**. CUA devolvió miniaturas de Stage Manager; los medios reales sí fueron revisados, sin atribuir causalidad a Stage Manager.
- Perfil de 6000 kb/s, resultado visual de preflight y guardado nuevo de Show Control: no confirmados.
- Fade3 visual, sincronización A/V e impacto independiente de la ganancia/mute sobre PCM: cobertura inconclusa.
- RTMP1 fue interrumpido deliberadamente; sus bytes decodificables no equivalen a finalización limpia ni entrega completa.
- Los buenos samples de audio/captura de esta sesión no eliminan el [fallo secuencial de identidad de aplicación](../var/evidence/h14-system-audio-b3-failure-audit-01/findings.md), ni los fallos de captura y cola de otros ensayos.

No se modificó producto, umbrales ni informes primarios para redactar este documento. Los índices derivados enlazan cada hecho con sus entradas y hashes; no autorizan publicación, push, merge ni release.
