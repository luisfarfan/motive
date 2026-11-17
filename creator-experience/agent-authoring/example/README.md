# Podcast de dos cámaras · ejemplo de autoría mínimo

Ejemplo didáctico, no una tercera colección premium. El [brief generado](brief.json)
pide una conversación sobre software, nombres de host/invitado, dos cámaras
seleccionadas después por la persona y una pantalla de pausa, en 16:9 y 9:16.
No contiene dispositivos ficticios ni abre cámaras.

El [manifest v1](manifest.json) contiene **2 escenas, 6 fuentes nativas y 7 capas**.
Las dos selecciones de cámara de [recipes.json](recipes.json) añadirían dos fuentes
y dos capas: **2 escenas, 8 fuentes y 9 capas** sobre un proyecto inicialmente vacío.
Las reservas tienen transformaciones independientes y órdenes libres, por debajo
de los límites globales 8/16/32. Un proyecto existente necesita otro cálculo.

Los nombres usan widgets lower third editables; título de episodio y pausa usan
texto nativo. El fondo es una forma. Los recursos externos son cero: no PNG,
video, Browser Source, fuente descargada, shell ni ejecutable en el manifest.
El generador Python es una herramienta de autoría y jamás se instala como contenido.

## Del brief a los contratos

La [instantánea de capacidades](../capabilities-baseline.json) registra commit y
SHA-256 de los contratos leídos. Es un baseline estático del código de Motive,
**no una consulta de capacidades runtime**. Solo se usan Text, Shape, Widget,
LayerAnimation y SceneTransition. Capturas no existen en `VisualDefinition` de
packs; su selección queda en la receta, fuera del manifest.

El [Deck](deck.json) contiene cinco botones: mostrar nombres, ocultarlos, entrada
del host, pausa y regreso. Las [reglas](rules.json) tienen condiciones explícitas
`manual.button_pressed` y los [cuatro eventos](events.jsonl) declaran
`simulated: true`. Pausa/regreso piden confirmación en el Deck. No hay proveedores.

Show/Hide del widget y animación de capa son operaciones diferentes. El botón de
entrada dice «after Show»: una animación no revela un lower third internamente
oculto. Movimiento reducido: Show/Hide para nombres y Cut para escena; no enviar
una animación de duración cero. Un futuro adaptador debe esperar los recibos del
propietario; este ejemplo no implementa ese adaptador.

## Generar y validar

Desde el checkout:

```sh
python3 creator-experience/agent-authoring/generate_example.py
python3 creator-experience/agent-authoring/verify_example.py
```

La generación usa solo Python estándar y la licencia local. El verificador compara
una segunda generación byte a byte, comprueba hashes de los contratos, geometría
incluyendo las cámaras reservadas, presupuesto estimado y seguridad de SVG.
Luego ejecuta el harness Rust existente contra esta carpeta con Cargo offline/locked.
No compila el crate de Motive ni enlaza libobs.

Resultado ejecutado: [verification.json](evidence/verification.json) **PASS**;
[contracts.json](evidence/contracts.json) **PASS**, con 12 controles adversariales,
cinco ensayos de botones y cuatro eventos parseados. `live_commands_sent: 0`.
El caso de recurso traversal no aplica porque no hay descriptores de recursos;
no se cuenta entre los doce controles.

## Previews documentales

- [Conversación horizontal](previews/podcast-live-horizontal.svg).
- [Conversación vertical](previews/podcast-live-vertical.svg).
- [Pausa horizontal](previews/podcast-brb-horizontal.svg).
- [Pausa vertical](previews/podcast-brb-vertical.svg).

Los rectángulos discontinuos son guías del documento; no son fuentes ni recursos
del manifest. Las identidades se ilustran después de Show y la tipografía es
aproximada. El verificador comprueba estructura y límites; estos SVG no acreditan
render nativo, captura real ni revisión visual en Motive.

## Revisión e instalación futura

La persona revisa brief, textos, ambas composiciones, licencia y plan. Solo el
instalador oficial podría crear recursos y devolver bindings reales. El instalador
H14 observado admite únicamente MATCHDAY: **este ejemplo tampoco está instalado
ni es admitido por ese selector**, aunque tenga cero recursos. No se suministra
un instalador alternativo. La aprobación del contenido no autoriza emitir, arrancar
capturas por nombre inventado ni reanudar temporizadores.

GPL-3.0-or-later; texto y composición originales. Las fuentes del sistema se
referencian por enum y sus archivos no se distribuyen.
