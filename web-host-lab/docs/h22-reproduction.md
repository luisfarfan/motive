# H22 — reproducción y evidencia

Las ejecuciones nativas requieren el alcance autorizado del laboratorio: CEF
propio fijado, contenido compilado propio, perfiles privados, supervisor externo,
sandbox activo, backend mock de laboratorio y lock físico canónico. Estos comandos
no autorizan Production, contenido de terceros ni credenciales reales.

## Compilación separada

Desde la raíz del worktree H22, con el SDK ya verificado por
`research/sources.lock.json`, usar un nombre nuevo que no tenga informe previo:

```sh
python3 web-host-lab/tools/h22_with_lock.py python3 web-host-lab/tools/build_native.py \
  --build-name h22-native-multi-repro1-ephemeral \
  --multi --mock-keychain --network-lab
```

El build verifica CEF, compila las listas originales del wrapper, sella ad-hoc
el bundle local y conserva fuente/hash. No ejecuta CEF. Para Lower Third/Alert,
añadir `--widgets` y otro nombre; para Goal original usar `--bridge` y un nombre
como `h22-native-multi-goal-repro1-ephemeral`. No sobrescribir candidatos.
No se modifica el SDK ni se instala nada globalmente.

## Un ensayo acotado

```sh
python3 web-host-lab/tools/h22_trial.py \
  --build h22-native-multi-repro1-ephemeral \
  --name H22-repro1 --scenario steady --instances 3 \
  --seconds 72 --width 640 --height 360 --generation 300000
python3 web-host-lab/tools/h22_audit.py web-host-lab/evidence/H22-repro1 \
  --output web-host-lab/evidence/H22-repro1/analysis.json
```

Trial toma el lock; retorno 75 significa slot ocupado **antes** de lanzar, sin
borrar el OWNER. Retorno 78 impide el perfil de red antiguo. El runner también
rechaza ese perfil al invocarlo directamente. Un ensayo fallido no se repite
silenciosamente: conservar salida y diagnosticar; después de dos intentos sin
progreso, cambiar de hipótesis o registrar el bloqueo.

Para eventos intermitentes, ejecutar además `h22_workload_check.py` sobre el
mismo directorio, con otro output nuevo. Distingue ventanas activas completas,
interrupciones, hide/cancel/resume y peers. El auditor general conserva gaps
all-time; los segundos idle de un evento terminado no acreditan un freeze.

`h22_suite.py` fija los binarios y casos de cada matriz antes de medir y conserva
`plan.json` y su propia fuente. Sus suites son capacity, widgets, lifecycle y
soak. Cada caso libera el lock; por defecto un FAIL detiene la suite para
diagnóstico. `--start-index` selecciona sólo el resto de un plan cerrado en
un directorio nuevo. `--continue-performance-failures` permite avanzar tras
un FAIL de cadencia únicamente si native, red y funcionalidad pasan; jamás
convierte el FAIL en PASS ni vuelve a ejecutar ese caso para reemplazarlo.
Los nombres de matriz y ensayos son inmutables. Una continuación debe conservar
el plan original e identificar exactamente los casos restantes, sin borrar
resultados ni seleccionar sólo ventanas favorables.

Para profiling separado: `--scenario steady --instances 3 --seconds 600
--memory-profile`. `h22_memory_check.py` compara vmmap por PID/nacimiento y hash;
heap es opcional y su ausencia queda explícita. No aceptar FPS de ese ensayo.
No usar `heap` sobre otra identidad ni capturar contenido de memoria.

## Contratos sin CEF/Production

```sh
python3 web-host-lab/tools/h22_with_lock.py python3 web-host-lab/tools/h22_verify_contracts.py \
  --name H22-contracts-repro1
python3 web-host-lab/tools/h22_with_lock.py python3 -m unittest discover \
  -s web-host-lab/tests -p 'test_h22_*.py' -v
```

El replay usa un frame Goal real retenido y tres procesos propios. El contrato
OBS compila/enlaza con libobs 33.0.1 de `.deps` en modo solo lectura y prueba
validación/contexto nulo; no ejecuta GPU ni otro motor. La ruta local de esa
dependencia se documenta en `h22_verify_contracts.py`; no se instala globalmente.

## Qué conserva un resultado

`report.json` vincula build, binario, collector y datos comprimidos. Incluye
solicitud, contabilidad y resumen externo. `instances.json`, traces por época,
`frames.json`, BGRA comprimido y PNG contienen observaciones reales. Supervision
conserva las muestras por identidad, RSS, CPU/footprint y cleanup. NetLog Default
se conserva comprimido; su auditor exige el control de rechazo positivo, cero
intentos TCP/UDP, cero hits a listeners y ningún componente instalado.

Las fuentes de medición se copian por ensayo; snapshots de compilación están
en `evidence/H22-build-sources`. Los informes nuevos pueden auditar datos viejos
sin reescribirlos y deben identificar su hash. Los binarios/cache del SDK quedan
locales e ignorados por Git, sin distribución. Los hashes acreditan identidad de
artefactos observados; no prometen builds bit a bit reproducibles en otra Mac.

## Inventario de entrega

Al cerrar todos los ensayos, `h22_inventory.py --output <archivo nuevo>` registra
SHA-256 y tamaño de los archivos H22 modificados/nuevos, verifica que no hay
cambios fuera del laboratorio y los tres documentos raíz autorizados, comprueba
Production contra la base y compara cada documento/evidencia histórico con Git.
No incluye SDKs, caches, targets ni binarios ignorados. El archivo de salida se
excluye a sí mismo; no ejecutar sobre logs vivos para afirmar un cierre final.

## Conciliación de continuaciones

La matriz mantiene todas las filas de los planes, también las no ejecutadas.
`h22_coverage.py` cruza esa matriz con los planes originales y exige exactamente
una ejecución por caso. Rechaza configuración distinta y ejecución duplicada;
un FAIL no puede ser reemplazado por una repetición posterior. Su PASS sólo
significa cobertura completa, no aceptación A/B/C/D. Los siete tests de
rechazo y conservación de FAIL están en `test_h22_coverage.py`.

```sh
python3 web-host-lab/tools/h22_matrix.py \
  --roots web-host-lab/evidence/H22-capacity-r2 \
  web-host-lab/evidence/H22-widgets-r2 web-host-lab/evidence/H22-widgets-r3 \
  web-host-lab/evidence/H22-widgets-r4 web-host-lab/evidence/H22-lifecycle-r2 \
  web-host-lab/evidence/H22-lifecycle-r3 web-host-lab/evidence/H22-soak-r2 \
  --output web-host-lab/evidence/H22-review-matrix.json
python3 web-host-lab/tools/h22_coverage.py \
  --matrix web-host-lab/evidence/H22-review-matrix.json \
  --original-roots web-host-lab/evidence/H22-capacity-r2 \
  web-host-lab/evidence/H22-widgets-r2 web-host-lab/evidence/H22-lifecycle-r2 \
  web-host-lab/evidence/H22-soak-r2 \
  --output web-host-lab/evidence/H22-review-coverage.json
```

`h22_cleanup_check.py --matrix <matriz> --output <archivo nuevo>` comprueba
PID/nacimiento previamente observados y recibos de liberación del lock y de
la inhibición temporal de idle sleep. No enumera argumentos de procesos ajenos,
no envía señales y no modifica un lock de H21. Ejecutarlo sólo después de que
termine el driver; su alcance no excluye procesos que nunca se observaron.

El contraste `h22_shutdown_probe.py` queda separado de la matriz: repite una
sola vez Goal lifecycle con el mismo binario y límites, y sólo intenta un sample
de un segundo si su host propio continúa dentro de CefShutdown tras 200 ms.
Comprueba ruta de ejecutable y PID/nacimiento. La herramienta sample tiene su
propio timeout de cuatro segundos; no cambia permisos ni toma otro proceso.
Un cierre rápido o un fallo del sampler no resuelve el FAIL histórico. El
contraste instrumentado nunca sustituye la aceptación de cierre original.

`h22_stall_probe.py` ejecuta un único contraste de la mezcla de 600 s con el
mismo binario. El observador atribuye el host al árbol que acaba de lanzar y
verifica ruta y PID/nacimiento; después sigue sólo esa identidad. Si reaparece
un hueco observado de heartbeat ≥200 ms después de 450 s, toma como máximo
un sample de un segundo (comando limitado a cuatro segundos). Conserva los
flags públicos de resource starvation; no los confunde con un estado App Nap.
No modifica energía, prioridades, flags CEF ni permisos. El perfil muestreado
no sustituye la ejecución de capacidad original.
