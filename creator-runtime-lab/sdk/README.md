# Creator Runtime SDK local

La CLI revisa paquetes reales y propone insertarlos en escenas existentes. Usa
el importador verificable y el crate Rust de este laboratorio. **Todas las
operaciones del owner, IDs y recibos generados son del modelo offline.** No se
conecta a Motive, no dibuja frames ni instala elementos en Production.

Desde la raíz del worktree:

```sh
python3 creator-runtime-lab/sdk/runtime.py catalog
python3 creator-runtime-lab/sdk/runtime.py review element-lab/marketplace-contract/packages/lower-third.motivepack
python3 creator-runtime-lab/sdk/runtime.py plan element-lab/marketplace-contract/packages/lower-third.motivepack --set 'lower-third-title="Samira"'
python3 creator-runtime-lab/sdk/runtime.py simulate element-lab/marketplace-contract/packages/lower-third.motivepack --store-output creator-runtime-lab/.scratch/lower-state.json
```

`catalog` presenta siete candidatos declarativos verificados y el Web Element
como **BLOCKED** para instalación/ejecución. `review` muestra identidad, hash,
licencia, propiedades tipadas, layouts H/V, previews aproximados, capacidades,
presupuesto y limitaciones. Los previews son los SVG pasivos empaquetados;
esta CLI no promete una vista previa del renderer nativo.

`plan` y `simulate` revisan los bytes, crean staging privado, ejecutan el modelo
estricto y verifican/limpian el staging. `plan` presenta las operaciones propuestas;
`simulate` incluye recibos, snapshot y sidecar experimental. Ambos evalúan
revisiones futuras mediante el modelo secuencial: nunca constituyen una reserva
ni una confirmación local del owner real. El formato original sigue experimental.

Sin `--snapshot` se usa una fixture vacía con una escena `fixture-scene` y las
capacidades contractuales de Element Lab, explícitamente sin observación live.
`--snapshot archivo.json` aporta un snapshot local tipado; Rust vuelve a validar
identidades, referencias y cuotas. `--scene` elige una escena existente y puede
repetirse para colocar las mismas fuentes en varias escenas. No se crea ninguna
escena nueva. Las fuentes compartidas comparten propiedades/estado; distintas
instancias conservan propiedades independientes. Los assets idénticos admiten
reutilización solo tras verificar hash, dimensiones, formato y licencia.

`--instance` permite nombrar cada instancia; de lo contrario se usa
`instance-1-ID`, `instance-2-ID`, etc. `--set PROPERTY=JSON` conserva el tipo del
contrato existente y sirve para un solo paquete. Para composiciones,
`--overrides` lee un mapa por ID de instancia con `properties` tipadas y `layouts`
H/V. No admite scripts, rutas de recursos ni campos adicionales. Ejemplo:
[integration-fixtures/H18-mixed-overrides.json](../integration-fixtures/H18-mixed-overrides.json).
Los órdenes se normalizan para añadir capas encima de las existentes; las
coordenadas y visibilidad H/V permanecen independientes. Revisar solapamientos
con el renderer nativo sigue pendiente.

La composición requerida conserva una escena con dos fuentes de captura
reservadas en el modelo, añade Creator Tech y después Lower Third, Community
Alert y Goal Celebration a esa misma escena:

```sh
python3 creator-runtime-lab/sdk/runtime.py simulate \
  element-lab/marketplace-contract/packages/creator-tech-minimal.motivepack \
  element-lab/marketplace-contract/packages/lower-third.motivepack \
  element-lab/marketplace-contract/packages/community-alert.motivepack \
  element-lab/marketplace-contract/packages/goal-celebration.motivepack \
  --snapshot creator-runtime-lab/integration-fixtures/H18-capture-snapshot.json \
  --scene fixture-creator-tech-scene \
  --overrides creator-runtime-lab/integration-fixtures/H18-mixed-overrides.json
```

Resultado offline: **1 escena, 14 fuentes y 14 capas**; las dos reservas de
captura conservan sus IDs y no se abre ningún dispositivo. No se amplían los
límites 8/16/32/4 ni la estimación visual de 256 MiB. El presupuesto no mide RSS.

## Persistencia y recuperación

`--output` guarda el informe completo; `simulate --store-output` guarda solo el
sidecar experimental. Ambos requieren un destino nuevo, crean archivos 0600
mediante descriptores sin seguir symlinks y sincronizan archivo/directorio.
Nunca sobrescriben archivos ajenos. Las dos salidas se guardan individualmente:
no se promete una transacción atómica de múltiples archivos ni un journal
persistido antes de cada operación simulada. El futuro owner real debe guardar
intenciones duraderas antes de despachar y reconciliar resultados inciertos.

Si el staging contiene una entrada ajena, un inode reemplazado o bytes alterados,
la CLI conserva **también el contenedor exterior**, informa
`STAGING_RECONCILIATION` y entrega `staging_recovery_path`. Solo retira directorios
propios vacíos cuya identidad sigue coincidiendo; no hay limpieza recursiva del
workspace. La persona/owner debe revisar ese estado antes de retirarlo o volver a
importar. La prueba de intrusión verifica esta conservación tanto al planificar
como al evaluar una restauración.


`restore` revalida el sidecar con `Store::parse`, vuelve a revisar los paquetes
reales y produce **solo una evaluación**. No restaura recursos ni ejecuta eventos:

```sh
python3 creator-runtime-lab/sdk/runtime.py restore \
  creator-runtime-lab/integration-fixtures/H18-mixed-store.json \
  element-lab/marketplace-contract/packages/creator-tech-minimal.motivepack \
  element-lab/marketplace-contract/packages/lower-third.motivepack \
  element-lab/marketplace-contract/packages/community-alert.motivepack \
  element-lab/marketplace-contract/packages/goal-celebration.motivepack \
  --snapshot creator-runtime-lab/integration-fixtures/H18-mixed-snapshot.json
```

Un hash en el sidecar no basta. Un paquete no proporcionado queda pendiente de
reverificación; capacidades ausentes, fuentes/capas alteradas o operaciones
pendientes se informan como incompatibilidad/reconciliación. Siempre requiere
revisión local, deja Show Control desarmado y registra cero scripts/eventos
históricos ejecutados. Proyectos nativos v1–v5 permanecen intactos.

La CLI emite JSON en stdout; errores de entrada en stderr y exit 1. Una
evaluación válida con cuestiones pendientes devuelve JSON `PARTIAL` en stdout
y exit 1. `catalog` conserva candidatos inválidos como errores visibles.

```sh
python3 -m unittest discover -s creator-runtime-lab/tests -p test_sdk.py -v
python3 creator-runtime-lab/sdk/verify_examples.py
```

El último comando regenera únicamente las fixtures/informes propios `H18-sdk-*`
y `H18-*snapshot/store/overrides.json`. Guarda hashes originales, seis casos
individuales y la composición requerida, recibos modelados y evaluación de
restauración. Ninguna fixture constituye evidencia de grabación o streaming.
