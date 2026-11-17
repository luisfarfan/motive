# H13 — exclusión del audio propio: verificación final

Estado: **repetición controlada del bundle G PASS**, después de un único
control de piso PASS. El primer ensayo de G conserva su FAIL y la atribución
de su causa sigue INCONCLUSIVE: contenía señal adicional de banda ancha que
impedía atribuir su residuo a 2011 Hz exclusivamente al emisor de Motive.
No se declara una regresión confirmada ni una corrección de producto entre
ambos ensayos. Se conserva el mismo bundle y no se cambian filtros, umbrales,
monitoring, permisos o configuración global para obtener el resultado nuevo.

## Evidencia conservada

| Ensayo | Bundle | Resultado |
| --- | --- | --- |
| [Anterior C](../var/evidence/h13-self-audio-exclusion-1794934285059972000/report.json) | `dc9c38a82d72c86cacd668a88c25ec26f0e12cbbb7b9d0c829d3e820a20ef38f` | PASS; supresión relativa de 2011 Hz −122,744469 dB, estimación próxima al piso numérico. |
| [G, primer ensayo](../var/evidence/h13-self-audio-exclusion-1794940665168715000/report.json) | `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93` | FAIL; supresión relativa medida −16,412088 dB frente al requisito menor que −45 dB. |
| [G, única repetición tras control de piso](../var/evidence/h13-self-audio-exclusion-1794946744795131000/report.json) | `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93` | PASS; supresión relativa medida −123,174221 dB, estimación próxima al piso numérico; todos los gates originales conservados. |

El [diagnóstico offline separado](../var/evidence/h13-self-exclusion-diagnosis-1794940836817878000/report.json)
conserva ambas comparaciones, comandos de decodificación, hashes, proyecciones
y todas sus ventanas. Su
[programa reproducible](../var/evidence/h13-self-exclusion-diagnosis-1794940836817878000/analyse.py)
solo analiza PCM; no reproduce ni transcribe el contenido capturado.

- Medio C: `var/recordings/motive-1794934286513495.mkv`, SHA-256
  `35201cf6dff07b1edb2dc672700f54db62de742f3487f10b43111041577a490d`.
- Medio G fallido: `var/recordings/motive-1794940666424806.mkv`, SHA-256
  `61d0afe3b27c203935d124a8e5c5d9bdbc2ce7feb7fcd7b345c06d409ef23293`.
- Runtime G fallido: `var/evidence/h13-build/final-self-audio-runtime.log`.

El emisor diagnóstico del G fallido pertenecía al PID 85959 y la fixture externa a los
PID 86049/86121. Los procesos propios del ensayo fueron cerrados por el owner.
El inventario posterior no encontró helpers de audio propios aún vivos; esto
no identifica el origen de la señal capturada durante el ensayo.

## Qué se midió

El verificador selecciona explícitamente audio de escritorio del display
principal, con ganancia −6 dB. Solo existe esa entrada de audio; no hay
micrófono, tono interno del mixer ni monitoring. El video es un patrón propio.
En ambas fases el emisor diagnóstico del proceso Motive reproduce 2011 Hz
a pico −30 dBFS. En la fase A, la aplicación fixture externa reproduce 997 Hz
al mismo nivel; en la B se cierra esa fixture y se lanza otra instancia propia
a 2011 Hz como control positivo. Las muestras de estado de ambas fases
conservan el emisor propio activo y su reloj avanzando.

Cada fase se mide en cuatro segundos interiores, comenzando a +1, +2, +3 y
+4 s, mediante el estimador Hann de 100 ms existente. Los intervalos de G
son aproximadamente 1–5 s y 7,752–11,752 s del medio. La segunda fase comienza
a 6,752 s, después de cerrar el PID externo anterior; el análisis no usa
la frontera inmediata de relanzamiento. No se observó un desplazamiento de
índices que colocara esas ventanas en la fase incorrecta.

| Métrica | C anterior | G primer ensayo, fallido |
| --- | ---: | ---: |
| Amplitud mediana 997 Hz en A | 0,015818516 | 0,015827277 |
| Amplitud mediana 2011 Hz en A | 0,000000011534 | 0,002430794 |
| Amplitud mediana 2011 Hz en B | 0,015819752 | 0,016082461 |
| RMS de los segundos interiores de A | −39,124…−39,025 dBFS | −21,644…−18,251 dBFS |
| Pico decodificado del archivo completo | −35,257625 dBFS | −5,831856 dBFS |
| 997 Hz residual B/A | 0,000001461 | 0,248695822 |
| Bloques saturados observados en la entrada, al final | 0 | 3 |

La última proporción de 997 Hz también incumple el gate original `< 0,01`;
el script todavía no lo había evaluado porque se detuvo primero en la
supresión de 2011 Hz. Los niveles nativos de G confirman energía adicional
antes de AAC: la entrada llega a pico +0,253102 dBFS antes del fader y RMS
posterior al fader entre −29,482487 y −13,506955 dBFS en A. La mezcla final
mantiene su propio contador de clipping en cero; ese contador no elimina la
observación de saturación en la señal de entrada.

En A de G, las amplitudes Hann a 2011 Hz son 0,001134–0,003192, comparables a
las bandas vecinas de 1991 y 2031 Hz. Las proyecciones coherentes de un segundo
dan solo 0,000729–0,000873 en 2011 Hz. Al retirar matemáticamente las
proyecciones de 997/2011 Hz y DC para describir el residuo, permanece RMS
−21,721…−18,285 dBFS: casi toda la energía observada. El control positivo sí
muestra un pico estrecho cercano a la amplitud esperada de 0,01585.

Estos datos demuestran que la captura G fallida no está compuesta únicamente por
las dos senoides declaradas. No permiten identificar una aplicación ajena,
atribuir esa señal a un proceso concreto o descartar toda fuga propia debajo
del fondo. No se escuchó el contenido ni se intentó identificarlo. Las
proyecciones alternativas son diagnósticas y no sustituyen el umbral de
aceptación de −45 dB.

## Contrato y límite del diagnóstico

El [módulo oficial fijado de OBS 33.0.1](../.deps/obs-studio-33.0.1/plugins/mac-capture/mac-sck-audio-capture.m)
crea la captura de escritorio mediante `SCContentFilter` y configura
`setCapturesAudio:TRUE` y `setExcludesCurrentProcessAudio:TRUE`.
[El adaptador](../native/audio-mixer.inc) sigue creando `sck_audio_capture`;
[el selector de destinos](../native/system-audio.inc) mantiene la selección
explícita y el rechazo de la aplicación propia. Esta lectura confirma la
configuración solicitada a la API; no demuestra por sí sola el cumplimiento
de la exclusión durante un ensayo con señal adicional.

El monitoring sigue desactivado por defecto y no se habilitó en este ensayo.
La captura de escritorio permanece una elección explícita de alcance amplio;
no se sustituye por captura de aplicación ni se añaden exclusiones automáticas
para mejorar la medición. El emisor diagnóstico está desactivado normalmente
y solo se habilita al arrancar con `MOTIVE_TEST_SELF_AUDIO=1`.

## Control de piso ejecutado una vez

La prueba negativa propuesta se concretó en un
[control de 24 s PASS](../var/evidence/h13-self-audio-floor-1794946499075579000/report.json),
mediante el [harness acotado](../scripts/verify_h13_self_audio_floor.py). Motive
normal PID 58261 no tenía habilitado el emisor propio. La fixture controlada
reprodujo 2011 Hz a −30 dBFS en los positivos y produjo buffers cero o pausó
su engine en los negativos. El escritorio se capturó explícitamente a −6 dB,
con una sola entrada, patrón visual propio y monitoring desactivado.

Las amplitudes positivas fueron 0,015757729 y 0,015831585. Las 20 ventanas
interiores de buffers cero y las 20 de pausa midieron amplitud cero tanto a
2011 como a 997 Hz, con callbacks frescos. El límite conservado de −45 dB
equivalía a amplitud 0,000088612225. No se interpretó ausencia de callbacks
como silencio. Runtime y bytes/modos de los tres stores se restauraron
exactamente, y la fixture propia terminó antes del siguiente ensayo.

Ese control acreditó un piso adecuado durante su intervalo y habilitó una
sola repetición del verificador original; no demostró exclusión por sí mismo.
No se cerraron aplicaciones ajenas ni se identificó el origen del fondo del
ensayo fallido. No se escuchó ni transcribió el contenido.

## Única repetición original del bundle G

La [procedencia y limpieza](../var/evidence/h13-self-exclusion-repeat-owner-1794946728415748000/provenance.json)
registra el cierre normal del PID 58261 mediante `request_shutdown`, seguido
del lanzamiento directo del mismo bundle G en el PID 62121 con
`MOTIVE_TEST_SELF_AUDIO=1`. stdout y stderr quedaron separados en ese
directorio; el verificador recibió el stderr de ese PID. Después se ejecutó
una sola vez `verify_h13_self_audio_exclusion.py` sin modificarlo. Su SHA-256
anterior y posterior coincide:
`f38abcbd7f9cf80da73ab96b1cea7e2b11671883c762188bf16ee7fb6ebc8e42`.

El [nuevo informe PASS](../var/evidence/h13-self-audio-exclusion-1794946744795131000/report.json)
tiene SHA-256
`6fa81dfbbd05489624a38202c347ec905564198ed91878c07b4cfb6dc2a14971`.

| Medición de la repetición | Resultado |
| --- | ---: |
| 997 Hz externo en A | 0,015822155 |
| 2011 Hz residual en A | 0,000000010976 |
| 2011 Hz externo, control positivo B | 0,015818846 |
| Supresión relativa 2011 Hz | −123,174221 dB; requisito `< −45 dB` |
| 997 Hz residual B/A | 0,000001425; requisito `< 0,01` |
| RMS de los segundos interiores de A | −39,032989…−39,022043 dBFS |
| Pico global del medio | −35,317477 dBFS |
| Observaciones del emisor propio activo y con reloj avanzando | 26 |
| Bloques saturados de la entrada / mezcla | 0 / 0 |
| Incrementos de render lag / video skips / output drops | 0 / 0 / 0 |

El medio es `var/recordings/motive-1794946746240954.mkv`, con 13,312 s de audio
decodificado y SHA-256
`8a9b2a7b220f05884319aedc0674ba286f13b329a5bdfaa7f3df80ae7f409943`.
Los gaps máximos de audio y video interior son 22 y 34 ms. Se conserva también
un gap final de video de 133 ms, dentro del límite existente de 150 ms del
verificador; este ensayo no se presenta como prueba de cero pérdida de video.

El diagnóstico PID 62121 salió con código 0 mediante `request_shutdown`,
sin señales forzadas. Se confirmó que los PID 58261/62121 ya no estaban vivos
y que no quedaba una fixture propia. Los hashes y modos de `project.json`,
`audio-mixer.json` y `output-profiles.json` permanecieron inalterados; no quedó
el emisor diagnóstico ni otra prueba corriendo.

La conclusión es limitada y positiva: **la exclusión propia pasó en el mismo
bundle G bajo el control descrito, con 997 Hz externo presente y 2011 Hz
externo detectable en el positivo**. La cifra cercana al piso numérico no es
una garantía universal de atenuación. El primer FAIL de G y su causa no
identificada permanecen archivados; no se atribuye su diferencia a una
corrección de código, cambio de gate o aplicación ajena concreta.
