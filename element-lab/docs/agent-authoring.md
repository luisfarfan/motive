# Autoría para personas y agentes

La interfaz es una CLI local con entradas JSON y contratos versionados. No exige
LLM, cuenta, suscripción, framework ni servidor MCP. Las capacidades son un
snapshot estático del baseline, no una consulta a la aplicación.

## Ejemplo completo: alerta de donación

Brief: «Alerta elegante, fondo oscuro, texto configurable, movimiento suave y
variante vertical». El agente elige Community Alert nativa, porque el widget
alert y slide_in ya existen. Conserva su PNG original, properties tipadas y ambos
layouts. Cambia el binding a viewer.donation sin conectar ningún proveedor.
La entrada completa está en `sdk/examples/donation-brief.json`; el script
reproducible usa las mismas órdenes públicas que usaría una persona:

```sh
python3 element-lab/sdk/motive_elements.py capabilities
python3 element-lab/sdk/examples/author_from_brief.py element-lab/sdk/examples/donation-brief.json --output element-lab/.scratch/donation-delivery
```

Se genera `element/element.json`, recurso y licencia, se valida con Rust, se
previsualiza H/V, se exporta `candidate/`, se combina con Lower Third en
`composition/`, se prepara `donation-alert.motivepack` y se verifica su inventario.
`workflow-report.json` registra propiedades, presupuesto e integridad. Todo queda
desarmado. El resultado de una ejecución real está en
`evidence/L-agent-authoring.json`; el workflow también es una prueba de integración.
No repetir sobre la misma carpeta: elegir otro output.

Para trabajar sin el script:

```sh
python3 element-lab/sdk/motive_elements.py new element-lab/.scratch/my-alert --template community-alert --id my-alert
python3 element-lab/sdk/motive_elements.py validate element-lab/.scratch/my-alert --set 'title="Gracias, Lucía"' --set 'entry-duration=650'
python3 element-lab/sdk/motive_elements.py pack element-lab/.scratch/my-alert --set 'title="Gracias, Lucía"' --set 'entry-duration=650' -o element-lab/.scratch/my-alert-candidate
python3 element-lab/sdk/motive_elements.py preview element-lab/.scratch/my-alert-candidate -o element-lab/.scratch/my-alert-preview
python3 element-lab/sdk/motive_elements.py package element-lab/.scratch/my-alert-candidate -o element-lab/.scratch/my-alert.motivepack
python3 element-lab/sdk/motive_elements.py verify-package element-lab/.scratch/my-alert.motivepack
```

`--set` no edita el documento original. Para reutilizar las decisiones, guardar
los defaults en element.json o conservar la orden de exportación. IDs de recursos
y acciones deben existir; consultar inspect/report antes de entregar. Las salidas
de validación son JSON; un error de contenido produce exit 1 y stderr
`{"status":"FAIL","error":{"code":"...","message":"..."}}`. Errores de sintaxis
de la propia CLI siguen el formato estándar de argparse, exit 2.

## Ejemplo completo: celebración web

El proyecto completo está en `web-elements/goal-celebration/`: index.html, goal.css,
goal.mjs, runtime.mjs, preview.svg, LICENSE y web-element.json. Usa animaciones WAAPI
originales, texto/score dinámicos, entrada/permanencia/salida y movimiento reducido.
La API propuesta es el mismo `MotiveElement` del contrato, no un binding Production.

```javascript
MotiveElement.on('goal.scored', async (event, context) => {
  // El ejemplo real actualiza textContent y espera sus animaciones.
  // context.signal cancela la secuencia; no hacer llamadas al estudio.
});
const properties = MotiveElement.getProperties();
const unsubscribe = MotiveElement.onPropertiesChanged(properties => {
  // Aplicar únicamente estado visual tipado.
});
```

Consultar `goal.mjs` para el código ejecutable completo. Tras editar los archivos
propios, `build_example.py` actualiza la copia del runtime y su inventario/hash:

```sh
python3 element-lab/web-elements/build_example.py
python3 element-lab/sdk/motive_elements.py web-validate element-lab/web-elements/goal-celebration
python3 element-lab/sdk/motive_elements.py serve --port 8776
```

Abrir el harness local con proxima-browser, aplicar properties y pulsar Probar
gol. Para reproducción automatizada, el archivo `tests/browser-checks.js`
se pasa como función a `proxima-browser.browser_run_code_unsafe`; no lanzar otro
navegador ni un cliente CDP. Luego preparar y verificar el archivo:

```sh
python3 element-lab/sdk/motive_elements.py package element-lab/web-elements/goal-celebration --web -o element-lab/.scratch/goal.motiveweb
python3 element-lab/sdk/motive_elements.py verify-package element-lab/.scratch/goal.motiveweb
```

## Ver la respuesta a Show Control

```sh
python3 element-lab/sdk/motive_elements.py rehearse element-lab/native-elements/goal-celebration --events element-lab/tests/fixtures/goal-events.json --enable-for-simulation
```

El crate real admite el fixture y prepara un trigger_animated_widget; reporta
simulation_only y live_commands_sent=0. La opción habilita reglas solo en la copia
en memoria del ensayo. Sin ella, las reglas permanecen desarmadas y no hay jobs.
Un evento marcado como real se rechaza. El harness web recibe una proyección
sintética de team/home/away; el bridge futuro se documenta en
[integration-contract.md](integration-contract.md).

## Entrega para revisión

Entregar el documento editable, paquete, licencia, hashes, informe y previews,
explicando qué está compilado, qué se verificó y qué requiere backend futuro.
Revisar variantes, solapamientos y triggers remapeados. La aprobación de contenido
y la instalación oficial ocurren después en Motive; el SDK no inicia esos pasos.
