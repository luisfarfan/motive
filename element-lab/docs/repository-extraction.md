# Extracción futura del SDK

No se creó otro repositorio ni se publicó contenido. Element Lab permanece en
una rama/worktree local, íntegramente dentro de element-lab/.

La unidad extraíble incluye element-spec/, sdk/, composer/, packager/, ejemplos,
tests, documentación y el contrato de catálogo. No debe llevar src/, native/,
libobs, una copia del owner, diseños propietarios ni un motor audiovisual.

## Dependencias actuales que deben resolverse antes de extraer

| Dependencia de solo lectura | Tratamiento futuro |
|---|---|
| `../../../show-control` desde el adaptador Rust | Publicar o versionar el crate canónico con API estable y lock; nunca copiar sus enums al SDK |
| Creator Tech / Neon Arena en creator-experience/ | Fixtures autorizadas con hashes/licencias y procedencia, o repositorio de ejemplos separado |
| LICENSE del repositorio | Conservar texto/licencia y revisar atribución de ejemplos/recursos |
| Baseline 6019ad0 | Reemplazar compatibilidad fija por una matriz explícita de versiones del crate y capacidades del producto |
| Python y toolchain Rust del host | Documentar versiones soportadas y verificar en CI macOS ARM64; empaquetar dependencias offline por canal autorizado |
| proxima-browser para QA del proyecto | Mantener la política de navegador del repositorio; no añadir Playwright/CDP oculto al SDK |

`common.REPO` localiza la raíz por la posición del SDK. Esta dependencia debe
convertirse en configuración explícita para fixtures, licencia y el crate antes
de mover archivos. Primero ejecutar el mismo corpus negativo y verificar que
los manifiestos/paquetes autorizados conservan hashes o una migración explicada.

## Límites de responsabilidad

El SDK genera y revisa propuestas, no instala ni se adueña de la sesión de Motive.
Un futuro wrapper MCP invoca la misma biblioteca/CLI; no reimplementa semántica.
El catálogo puede distribuir archivos offline sin cuentas. Un servicio opcional
solo indexa metadatos: identidad, firma, confianza y revisión de updates son
decisiones separadas de SHA-256. Nunca actualizar contenido ejecutable de forma
silenciosa ni promover una actualización nativa a web por extensión del archivo.

## Preparación para una extracción autorizada

Fijar contrato y versionado, resolver las dependencias anteriores, reproducir
paquetes en dos entornos, verificar licencias/procedencia, ejecutar QA completo,
documentar límites del preview/host y revisar el API público. Solo después se
decide repositorio, publicación e integración oficial. Esos pasos requieren otro
incremento; no forman parte de los cambios realizados aquí.
