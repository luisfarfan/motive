# H17 — candidata portable B7

Estado del empaquetado: **PASS** para la auditoría local descrita. Aceptación
general de beta: **FAIL** por los gates de captura; no es una distribución
notarizada ni una release publicada.

## Identidad inmutable

- App: `/Users/luisfarfan/Developer/motive-h17-portable/b7/Motive.app`.
- ARM64, release optimizada, CFBundleVersion `17`, backend GPUI actual.
- Ejecutable SHA-256: `d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31`.
- mac-capture SHA-256: `cae7b5b1eb8f07d89c93627c1e9eb1de23b68b41f829585d34e813d159ee5792`.
- Commit de preparación: `96b545a1e00b7e0eb7dd0f48be7fd8f5d809dfe7`.
- Firma ad hoc local. No acceso a Keychain, Developer ID ni notarización.

`var/evidence/h17-checks/b7-identity.json` conserva la identidad. No se reutiliza
B6. Los cambios posteriores de verificadores no cambian este ejecutable ni su
plugin empaquetado; otra modificación de runtime necesita otra candidata.

## Evidencia

`b7-release-build.log` conserva el build `cargo build --locked --release`.
`b7-bundle.log` conserva el empaquetado con licencias completas y versión
explícita. `b7-portable.json` tiene auditoría estática **PASS**, cero issues,
verificación estricta de firma y smoke de ffmpeg/ffprobe con exit 0. Incluye
dependencias, plugins, herramientas de medios y rpaths auditados. El campo
runtime de ese informe estático queda `NOT_EVALUATED`: las ejecuciones reales
se registran separadamente y no se altera ese recibo.

Los runners B7 lanzan el ejecutable con cwd `/`, sin variables DYLD, y hablan
con el socket del owner portable verificando PID. La matriz de nueve salidas
de `h17-output-matrix-b7` y la sesión de `h17-show-b7-owner` comprueban este
runtime fuera del checkout; cada caso termina el proceso normalmente. Los
fixtures y receptores son instrumentos externos, no dependencias del producto.
No se ha probado todavía la segunda Mac.

## Fuentes y distribución

`/Users/luisfarfan/Developer/motive-h17-portable/source-candidate-b7/manifest.json`
registra material **PASS**: 25 fuentes nativas, 463 paquetes Rust, avisos
completos, sin materiales bloqueados ni revisión de submódulos pendiente.
El snapshot de Motive es `4398f04`; su runtime es idéntico al de B7 (el siguiente
commit solo instrumenta un verificador de audio). La correspondencia de
materiales no acredita una reconstrucción binaria reproducible: ese gate es
**PARTIAL**. Antes de distribuir deben verificarse instrucciones de rebuild
y el flujo de firma/distribución autorizado.

Los tests de formato de proyectos v1–v5 y reglas guardadas cubren compatibilidad
de lectura; la restauración nativa B7 de Show Control se comprobó desarmada con
armado explícito y recibos durables. Los ensayos conservan journals y restauran
únicamente stores propios mediante comprobación de bytes/hash. El recorrido
GPUI y el recibo final de preservación se documentan en los informes H17.
