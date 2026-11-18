# H14 — Voice Commands opcional: experimento offline

Estado: **PARTIAL**. Hay un corpus WAV propio y un runner aislado. No hay tap
del mixer, captura adicional, detección en vivo, instalación obligatoria ni
comandos multimedia emitidos. El experimento no modifica Motive, sus permisos
o el bundle. Los modelos y resultados permanecen en `target/voice-offline`.

## Opciones investigadas

| Opción | Español / ejecución local | Coste y límites | Decisión H14 |
|---|---|---|---|
| whisper.cpp multilingüe v1.9.5 | Modelos sin sufijo `.en`; CLI local CPU | tiny-q5_1: 32,152,673 bytes; base-q5_1: 59,707,625 bytes. ASR general; no es un detector especializado de gritos | Benchmark tiny-q5_1 autorizado; no integra el producto |
| Apple SFSpeechRecognizer | Comprobar permiso existente y `supportsOnDeviceRecognition`; forzar `requiresOnDeviceRecognition=true` | Disponibilidad depende de locale/dispositivo/assets del sistema; no tenemos tamaño/hash administrable del modelo Apple | Helper aislado; aborta sin permiso, sin diálogo ni fallback de red |
| Vosk small-es-0.42 | Modelo español y gramática restringible | 39,817,833 bytes; Apache-2.0. Es ASR restringido, no KWS dedicado. Catálogo oficial solo publica MD5 | Candidato posterior; falta SHA-256 verificable y benchmark |
| Porcupine | KWS dedicado con español y macOS ARM64 documentados | Requiere AccessKey y modelo de palabra/plataforma; modelo personalizado y condiciones de distribución pendientes | No instalado ni integrado; no se pidió ninguna credencial |
| openWakeWord / sherpa KWS | openWakeWord documenta inglés; sherpa no acredita un modelo KWS español en las fuentes revisadas | No basta que sus runtimes sean multilingües para afirmar KWS español | No se presentan como soluciones españolas verificadas |

Fuentes primarias: [whisper.cpp y modelos](https://github.com/ggml-org/whisper.cpp/blob/d1be6fde11ac6e0407606b4e42fe72d34add8037/models/README.md),
[metadatos oficiales de pesos](https://huggingface.co/ggerganov/whisper.cpp/tree/5359861c739e955e79d9a303bcbc70fb988958b1),
[Apple soporte on-device](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition),
[Apple petición local obligatoria](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition),
[Apple permisos](https://developer.apple.com/documentation/speech/asking-permission-to-use-speech-recognition),
[Vosk modelos](https://alphacephei.com/vosk/models),
[Vosk gramática restringida](https://github.com/alphacep/vosk-api/blob/master/python/example/test_words.py),
[Porcupine idiomas/plataformas](https://picovoice.ai/docs/faq/porcupine/),
[Porcupine generación y AccessKey](https://picovoice.ai/docs/model-api/porcupine/),
[openWakeWord idiomas](https://github.com/dscripka/openWakeWord#language-support),
[sherpa KWS](https://k2-fsa.github.io/sherpa/onnx/kws/index.html) y
[petición de español sin resolver](https://github.com/k2-fsa/sherpa-onnx/issues/3631).

Whisper publica código y pesos bajo MIT; conservar avisos y procedencia sigue
siendo necesario si se distribuye una extensión. [Licencia oficial](https://github.com/openai/whisper#license).

`scripts/voice-models.json` fija cuatro alternativas Whisper por tamaño y
SHA-256 LFS oficial, además de revisión inmutable del repositorio. El SHA corto
o Git blob OID no sustituye el SHA-256 de los pesos. Solo se autorizó y descargó
tiny-q5_1 para esta prueba: SHA-256
`818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7`.
No hay descarga automática desde Motive ni desde el runner.

## Reproducción

El source oficial es whisper.cpp commit
`d1be6fde11ac6e0407606b4e42fe72d34add8037`, tar SHA-256
`645445da884df6dbd52b30f82d7be7c01d1767c938714e477e786b88d529e9f4`.
La compilación de prueba usa CPU, dos hilos como máximo en inferencia, sin
Metal/BLAS/Accelerate. Si CMake no está instalado, el experimento usa una copia
aislada en target; no modifica herramientas globales. CMake 4.4.5 wheel
universal2: SHA-256
`e07a5716b4233dc9c69d6ca6993f4405eefc7687e718d9f6eebbb6cc1be304ef`.

Con las fuentes/modelo ya autorizados y verificados:

```sh
cmake -S target/voice-offline/whisper.cpp-d1be6fde11ac6e0407606b4e42fe72d34add8037 \
  -B target/voice-offline/build -DCMAKE_BUILD_TYPE=Release \
  -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF \
  -DWHISPER_BUILD_EXAMPLES=ON -DGGML_METAL=OFF -DGGML_BLAS=OFF \
  -DGGML_ACCELERATE=OFF -DWHISPER_BUILD_COMMIT=d1be6fde
cmake --build target/voice-offline/build --target whisper-cli -j2
python3 scripts/benchmark_h14_voice.py prepare \
  --output target/voice-offline/corpus-v1 --voice Paulina
python3 scripts/benchmark_h14_voice.py run \
  --corpus target/voice-offline/corpus-v1/manifest.json \
  --output target/voice-offline/whisper-v1 --backend whisper \
  --executable target/voice-offline/build/bin/whisper-cli \
  --model target/voice-offline/ggml-tiny-q5_1.bin --threads 2
```

Los destinos deben ser nuevos: los scripts nunca reemplazan evidencia. La voz
debe figurar instalada como española en `say -v '?'`. `say` escribe archivos,
no reproduce audio. Ruido y música proceden de fórmulas y semillas propias.
Cada WAV es PCM s16 mono 16 kHz, contiene hash, duración, peak/RMS y saturación.
La voz TTS puede variar entre versiones del sistema; los hashes identifican
el corpus realmente evaluado. Repetir el runner sobre esos WAV permite
comparar motores sin regenerar audio.

```sh
swiftc scripts/voice_apple_offline.swift -o target/voice-offline/voice-apple-offline
target/voice-offline/voice-apple-offline --probe
python3 scripts/benchmark_h14_voice.py run \
  --corpus target/voice-offline/corpus-v1/manifest.json \
  --output target/voice-offline/apple-v1 --backend apple \
  --executable target/voice-offline/voice-apple-offline
```

El helper Apple nunca llama `requestAuthorization`, solicita modelos ni abre
un micrófono. Solo reconoce si el permiso ya existe, el locale está disponible
y Apple declara soporte on-device. Cada petición fuerza procesamiento local.
En esta Mac el probe devolvió **BLOCKED / speech_permission_not_authorized**,
autorización `not_determined`. No se mostró un diálogo ni se inició reconocimiento.
Evidencia: `target/voice-offline/apple-v1/report.json`.

## Corpus y lectura de métricas

El primer corpus contiene **14 WAV / 67.7599375 s**: «gol» normal, lento,
escritura alargada, repeticiones, español normal, palabras parecidas, voces TTS
de fondo, silencio, ruido, ruido tipo videojuego, música original y mezclas.
La escritura «goooooool» no certifica una vocal prolongada humana. No hay
gritos humanos, ruido real de juego ni voces humanas de fondo en esta muestra.

Se miden TP/FN/FP/TN por clip, candidatos, texto, tiempo de pared, factor de
tiempo real, CPU y RSS máximo del proceso. Cada WAV inicia un proceso nuevo;
la latencia incluye carga de modelo. No representa latencia en vivo. La
tasa FP/hora extrapolada de estos pocos segundos es solo descriptiva y no
establece fiabilidad de producción. El clip que menciona «gol» desde una
voz de fondo se separa como desafío: contener la palabra no acredita intención
del creador. No se compara la confianza numérica de motores distintos.

Los resultados solo emiten `voice.keyword_candidate.v1`, palabra, hash de
entrada e índice de candidato; `command_executed=false`. Ningún evento llama
Show Control. La coincidencia exige token completo `go+l` tras normalizar
acentos; «golf», «golpe» y «gorila» no son activadores por substring.

## Resultado medido

Ejecutado en Apple M5 Pro, macOS 27.2, después de terminar las pruebas físicas
y cargo test/clippy del otro agente. CPU solamente, dos hilos. Es una sesión
normal del propietario, no una máquina dedicada: load average 1 min pasó de
6.38 a 6.99. Las cifras describen esa ejecución y no un límite garantizado.

| Métrica | Resultado |
|---|---:|
| WAV procesados / duración | 14 / 67.7599375 s |
| Clips puntuables (desafío de intención separado) | 13 |
| TP / FN / FP / TN | 3 / 3 / 0 / 7 |
| Recall de palabra / precisión en esta muestra | 50% / 100% |
| Tiempo mediano / p95 por WAV, con carga del modelo | 464.6 / 1159.0 ms |
| Factor de tiempo real mediano | 0.0911 |
| RSS máximo del proceso | 134,660,096 bytes |
| Samples saturados / peak máximo del corpus | 0 / −4.54 dBFS |

Detectó «gol» normal, lento y con música sintética. No lo detectó en escritura
alargada (`¡Gabé!`), repeticiones (`¡Vol! ¡Vol!`) o ruido (`¡Buen!`). Los siete
negativos no generaron «gol». En silencio produjo `[Música]`: ausencia de un
evento falso en este clip no equivale a transcripción fiable. El desafío de
voz de fondo produjo «gole», sin candidato; sigue sin demostrar separación de
intención o de hablantes. No se afinó el detector sobre estos resultados.

El gate de detección fiable queda **FAIL para esta configuración y corpus**;
el trabajo de investigación/benchmark queda **PARTIAL** por cobertura
sintética y comparación Apple bloqueada. No se habilita voz en vivo.

Evidencia privada:

- `target/voice-offline/whisper-v1/report.json`: métricas, textos, eventos y hashes.
- `target/voice-offline/corpus-v1/manifest.json`: WAV, etiquetas y métricas PCM.
- `target/voice-offline/provenance.json`: source/modelo/ejecutable, hardware y build.
- `target/voice-offline/apple-v1/report.json`: bloqueo explícito sin solicitud de permiso.

El build de GGML detectó incidentalmente el commit del checkout padre Motive
al estar el tar extraído debajo de ese checkout. Esa etiqueta no identifica
las fuentes Whisper: la revisión y SHA-256 del archivo oficial, registrados
en provenance, son la referencia. No se modificó el source del runtime.

## Contrato propuesto para un incremento posterior

Este contrato todavía **NOT IMPLEMENTED** evita que UI/CLI/MCP creen otra
captura o lógica de ejecución independiente:

- Estados comunes: `disabled`, `not_installed`, `installing`, `ready`,
  `running`, `backpressured`, `failed`. Inicio siempre desactivado; instalar
  y activar requieren elecciones explícitas e independientes.
- Un manifiesto versionado fija origen, tamaño, SHA-256, licencia y runtime.
  Descarga temporal con límite, verificación, rename atómico y limpieza de
  parciales. Desinstalar detiene el worker y elimina solo sus assets propios.
- Tap PCM del mixer existente, con fuente/tap explícitos. Ninguna segunda
  captura ni reconocimiento, locks o asignaciones en el callback. El audio
  global/encoders/transiciones conservan su reloj.
- Cola acotada: propuesta inicial 100 bloques de 20 ms de float32 estéreo a
  48 kHz (768,000 bytes, 2 s). Desbordamiento descarta un bloque entrante
  completo e incrementa discontinuidades; el worker invalida la ventana
  incompleta para no concatenar señales distantes. Conversión a 16 kHz fuera
  del callback; se conserva relación con timestamps originales.
- Proceso worker con dos hilos, presupuesto inicial 512 MiB y parada con
  timeout; esos presupuestos deben validarse con producción concurrente.
  Salud publica profundidad/edad de cola, descartes, RTF, latencia, CPU/RSS,
  reinicios y código de error. Fallo no interrumpe el mixer ni outputs.
- Evento candidato tipado incluye versión, detector/modelo, input ID,
  generación de audio, timestamp y razón/confianza de ese motor. Show Control
  conserva revisión, cooldown, deduplicación y política de activación.
  No se ejecutan comandos multimedia desde el reconocedor.
- Texto y PCM permanecen efímeros por defecto. El corpus sintético de este
  experimento se conserva como evidencia autorizada; guardar voz real o
  transcripciones necesitará una elección explícita.

Antes de habilitar voz en vivo faltan gritos humanos prolongados autorizados,
mucho más audio negativo, intención/voces de fondo, medición concurrente con
producción, desbordamiento/recuperación, limpieza y una acción real verificada
mediante el contrato Show Control. Este trabajo opcional no cierra gates P0.
