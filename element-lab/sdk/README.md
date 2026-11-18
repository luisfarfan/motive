# SDK local v0.1

Python 3 (stdlib) y Rust/Cargo con serde/serde_json fijados en Cargo.lock.
No instala comandos globales. `cargo build --offline --locked` solo compila el
adaptador y el crate de Show Control; nunca el binario Motive ni libobs.
Una máquina sin caché Cargo necesita preparar esas dependencias antes del uso
offline. La ejecución no descarga ni llama a servicios externos.

```sh
python3 element-lab/sdk/motive_elements.py capabilities
python3 element-lab/sdk/motive_elements.py new element-lab/.scratch/my-lower --template lower-third --id my-lower
python3 element-lab/sdk/motive_elements.py validate element-lab/.scratch/my-lower --set 'title="Alex"'
python3 element-lab/sdk/motive_elements.py preview element-lab/.scratch/my-lower -o element-lab/.scratch/my-preview
python3 element-lab/sdk/motive_elements.py compose element-lab/native-elements/lower-third element-lab/native-elements/community-alert --single-scene -o element-lab/.scratch/my-composition
python3 element-lab/sdk/motive_elements.py pack element-lab/.scratch/my-lower -o element-lab/.scratch/my-pack
python3 element-lab/sdk/motive_elements.py inspect element-lab/.scratch/my-pack
```

`pack` exporta una carpeta candidata; `package` prepara el ZIP experimental de
revisión. Nada instala contenido en Production. Los outputs existentes se
rechazan. Borrar solo outputs propios o elegir otro nombre para repetir.

stdout: JSON de resultado. Errores de contenido en stderr:
`{status:"FAIL",error:{code,message}}`, exit 1. Uso inválido de argumentos:
ayuda estándar de argparse, exit 2.
Entradas con claves duplicadas, NaN, campos/versiones desconocidas, paths no
relativos, symlinks y referencias inválidas fallan. `--set` recibe valores JSON
(tipados, sin coerción). Los presets crean recursos originales localmente.

`compose` conserva escenas separadas salvo `--single-scene`. Este último conserva
geometría y remapea orden; puede haber solapamiento visual deliberado: revisar el
preview. `--occupied occupied.json` suma escenas, sources, layers, texture_bytes y
video_sources del proyecto existente a los límites globales. Es un cálculo sobre
un snapshot proporcionado, no una consulta a Production ni reserva real.

Las propiedades marcadas compile_time se hornean en la definición exportada.
Las cuatro properties v1 del pack conservan exactamente su contrato. Estados son
metadatos; referencias animation_ref se resuelven en acciones existentes. No hay
keyframes, código ejecutable, expresiones ni motores adicionales.

Órdenes adicionales: `select` extrae escenas/fuentes de un pack, `rehearse` admite
fixtures en el simulador real de Show Control, `web-validate` revisa el contrato
web, `package` recibe una carpeta candidata nativa o una web con `--web`,
`verify-package` verifica integridad/contrato sin instalar, `catalog-validate`
revisa entradas locales y `serve` abre el harness loopback. Ver `--help` de cada
orden. [Ejemplos completos de autoría](../docs/agent-authoring.md).
