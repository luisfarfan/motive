# H13 — exclusión del audio propio: verificación final

Estado: **ensayo del bundle G FAIL; atribución de la causa INCONCLUSIVE**.
La captura reciente contiene señal adicional de banda ancha que impide
atribuir su residuo a 2011 Hz exclusivamente al emisor de Motive. No se declara
una regresión confirmada de ScreenCaptureKit, ni se conserva el PASS anterior
como prueba de aceptación del bundle final. No se cambian filtros, umbrales,
monitoring, permisos o configuración global para obtener otro resultado.

## Evidencia conservada

| Ensayo | Bundle | Resultado |
| --- | --- | --- |
| [Anterior C](../var/evidence/h13-self-audio-exclusion-1794934285059972000/report.json) | `dc9c38a82d72c86cacd668a88c25ec26f0e12cbbb7b9d0c829d3e820a20ef38f` | PASS; supresión relativa de 2011 Hz −122,744469 dB, estimación próxima al piso numérico. |
| [Final G](../var/evidence/h13-self-audio-exclusion-1794940665168715000/report.json) | `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93` | FAIL; supresión relativa medida −16,412088 dB frente al requisito menor que −45 dB. |

El [diagnóstico offline separado](../var/evidence/h13-self-exclusion-diagnosis-1794940836817878000/report.json)
conserva ambas comparaciones, comandos de decodificación, hashes, proyecciones
y todas sus ventanas. Su
[programa reproducible](../var/evidence/h13-self-exclusion-diagnosis-1794940836817878000/analyse.py)
solo analiza PCM; no reproduce ni transcribe el contenido capturado.

- Medio C: `var/recordings/motive-1794934286513495.mkv`, SHA-256
  `35201cf6dff07b1edb2dc672700f54db62de742f3487f10b43111041577a490d`.
- Medio G: `var/recordings/motive-1794940666424806.mkv`, SHA-256
  `61d0afe3b27c203935d124a8e5c5d9bdbc2ce7feb7fcd7b345c06d409ef23293`.
- Runtime G: `var/evidence/h13-build/final-self-audio-runtime.log`.

El emisor diagnóstico G pertenecía al PID 85959 y la fixture externa a los
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

| Métrica | C anterior | G final |
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

Estos datos demuestran que la captura final no está compuesta únicamente por
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

Una prueba negativa adicional propuesta, **todavía no ejecutada**, es una
captura corta del escritorio con Motive normal sin el emisor diagnóstico y
sin fixture externa. Cuantificar su energía sin reproducirla permitiría saber
si ya existe señal adicional antes de habilitar los dos estímulos. Solo una
sesión con audio controlado permitiría repetir el mismo ensayo 997/2011 Hz
y sus límites originales. No se propone cerrar aplicaciones ajenas, cambiar
volumen o routing global, filtrar el fondo ni repetir indefinidamente.

Hasta disponer de ese control, la conclusión final es: **el gate de exclusión
no pasó en G; el origen de su residuo no está identificado**. El PASS de C y
el FAIL de G permanecen separados y completos.
