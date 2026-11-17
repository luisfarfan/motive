# Validación independiente

Desde el checkout:

```sh
python3 creator-experience/validation/validate.py
python3 creator-experience/validation/test_validation.py
```

La ruta del comando presupone el checkout; el script resuelve archivos desde
su propia ubicación. Requiere Python 3.10+ y Cargo/Rust compatible con el crate
Show Control. Usa solo Python stdlib y las dependencias ya bloqueadas de Rust.
`--offline --locked` evita downloads/resolución nueva durante la verificación.
El target se mantiene en `validation/target/`, ignorado por Git.

La primera compilación ya dispone de `Cargo.lock`. `Cargo.toml` enlaza
`../../show-control`, la implementación normativa real; no una copia de tipos.
No importa el crate raíz de Motive ni libobs. Para una futura extracción del
repo, sustituir únicamente este adaptador por un crate de contratos versionado
según el plan de extracción; no inventar un JSON Schema permisivo.

Gates:

- `CreatorPack::from_json`, `plan`, `set_property`; `Deck::from_json` y
  `Config::from_json`; referencias de reglas/Deck y `actions::prepare`.
- Rechazo de código/campos extra, versión futura, paths, referencias rotas,
  exceso global de capas, presupuesto insuficiente y easing Fade no admitido.
- Property inválido no muta el original; confirmación/pending/cooldown/reloj
  monotónico de `DeckRuntime`, siempre en modo simulación.
- Basenames, bytes, SHA-256, dimensions, CRC de todos los chunks PNG,
  descompresión acotada de todas las filas, ausencia de animación PNG.
- Fuentes SVG sin scripts, handlers, entidades ni dependencias externas;
  geometría dentro de ambos canvases y z-order sin empates de esta colección.
- Estimación nativa adicional y máximo 4 videos, separados del cálculo del plan.

La suite Python ejecuta siete controles de bytes: PNG válido, CRC corrupto,
descompresión superior a dimensiones, filtro inválido, bytes añadidos, SVG
activo/remoto y symlink/traversal. El harness Rust ejecuta trece controles
adversariales/de estado por colección y ensaya cada botón habilitado con las
condiciones de su regla real. Todos son ensayos independientes, con cero
comandos live.

Para contrastar el crate H14 en un checkout existente, en solo lectura:

```sh
python3 creator-experience/validation/check_h14.py ../motive-h14
```

Se compila el mismo harness contra ese crate; el target y manifest temporal
permanecen en `validation/target/`. Los hashes antes/después y commit quedan
en `evidence/contracts-h14-snapshot.json`, el resultado en
`contracts-h14-compatibility.json`. No prueba su instalador MATCHDAY ni el
owner. Si H14 cambia durante el chequeo, falla el gate de snapshot estable.

Los archivos `evidence/contracts-*.json` contienen los resultados ejecutados.
`--skip-rust` es una ayuda de iteración y siempre informa PARTIAL aunque el resto
pase. No usarlo como evidencia final.

Este es un verificador de materiales controlados de autoría; no un sandbox ni
instalador de paquetes hostiles. No garantiza rendering de FreeType, decodificación
nativa, confianza del autor, permisos de captura, RSS, operaciones live o calidad
visual. Esas fronteras se documentan en `docs/audit.md`.

## Navegador independiente

`browser-checks.js` contiene una función `(page, {artifactDir})`. Ejecutarla
únicamente mediante `proxima-browser.browser_run_code_unsafe`, envolviéndola con
una función que pase el `page` del MCP y un directorio de artefactos permitido
por ese servidor. El servidor local debe estar activo en 127.0.0.1:8768.
No ejecutarla con otra instancia de Playwright ni un navegador por CDP.

El MCP de esta sesión permite su cache de screenshots, pero no escribir en el
worktree hermano. Por eso se capturó en ese cache y después se copiaron los PNG
a `evidence/`. El script no fija ninguna ruta del checkout; `artifactDir` se
selecciona al invocarlo. El reporte archivado usa rutas relativas de entrega.
