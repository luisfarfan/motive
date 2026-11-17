# Copias de Claude Design

Copias de solo lectura de los lienzos de Claude Design de Motive. **La fuente
de verdad es el lienzo**; esta carpeta se regenera con la skill
`.claude/skills/design-pull` (Claude) y `design/tools/finalize_pull.py`. No
edites estos archivos a mano.

| Carpeta | Contenido | Lienzo |
|---|---|---|
| [studio-fase-1](studio-fase-1/) | Fase 1: pantalla principal del estudio y dirección artística | https://claude.ai/artifact/Xz4yhpz6kQhy13EGLVBDav (privado) |

## Cómo leer un lienzo (para Codex)

Cada carpeta tiene:

- `manifest.json`: versión descargada, artboards en orden, sha256 de cada
  archivo y el mapa de recursos `/_blob/<id>` → `assets/<id>.jpg` con su rol.
- `project/canvas.json`: el índice del lienzo. `boards` da el tamaño de cada
  artboard (`w`×`h`, en px CSS); `expand: "fill"` significa pantalla fluida
  (ventana redimensionable), sin él es un tamaño fijo.
- `project/*.dc.html`: un artboard por archivo. Son HTML con una capa mínima
  de plantillas; **no se ejecutan en Motive**, describen aspecto y
  comportamiento:
  - Los estilos van en línea (`style="…"`). Los valores en `var(--…)` son
    tokens; los define el `themeVars` del `<script>` de `Main.dc.html`
    (versión clara y oscura).
  - `{{nombre}}` es un valor calculado en `renderVals()` dentro del
    `<script type="text/x-dc">` del mismo archivo. Ahí está la lógica de
    estados (en directo, listo, fuente perdida; propuesta pendiente, visible,
    aplicada).
  - `<sc-if value="{{x}}">` = se muestra si `x` es verdadero.
    `<sc-for list="{{xs}}" as="x">` = repetir por elemento.
  - `<dc-import name="Program" scene="taller">` = instancia del componente
    `Program.dc.html` con esas propiedades (atributo `cam-state` → prop
    `camState`).
  - `data-props` en el `<script>` declara las propiedades configurables y sus
    valores posibles.
  - `/_blob/<id>` es un recurso subido: búscalo en `manifest.json` → `blobs`.

## Relación con el resto de `design/`

- `design/direction.md`: decisiones, tokens, reglas y qué está implementado
  frente a qué es futuro. Prevalece sobre cualquier detalle visual ambiguo.
- `design/prototype/studio/`: prototipo HTML con las interacciones finas
  (arrastre con imán, deshacer, modo Hoy/Visión). El lienzo es la referencia
  visual; el prototipo es la referencia de comportamiento.
- `design/screens/`: capturas renderizadas.
