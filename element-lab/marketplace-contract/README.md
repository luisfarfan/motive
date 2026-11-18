# Catálogo local v1 · base de marketplace

Contrato estricto en `catalog.schema.json`, ocho entradas reales en `catalog.json`
y paquetes reproducibles en `packages/`. Distingue elemento individual/pack y
contenido nativo/web. Cada entrada contiene autor no autenticado, versión,
categoría/tags, preview interno, licencia, capacidades, versiones de contratos,
baseline de compatibilidad, tamaño/hash del archivo y política de actualización.
No hay backend, cuentas, pagos, descargas automáticas, telemetría ni moderación online.

```sh
python3 element-lab/sdk/motive_elements.py catalog-validate element-lab/marketplace-contract/catalog.json
```

El verificador compara metadata con los bytes del paquete y el preview, y vuelve
a aplicar los contratos nativos/web. IDs/versiones duplicados se rechazan. El
catálogo no concede permisos: `official_installation: pending` y
`author.identity: unverified` son obligatorios en esta versión experimental.

Distribución offline: copiar archivo + entrada de catálogo, verificar digest
contra una fuente elegida por el usuario, revisar contenido/licencia/permisos y
entregar al instalador oficial cuando exista soporte. Un catálogo remoto futuro
puede envolver el mismo contrato, sin incorporarse al runtime ni ser obligatorio.

Actualizaciones: paquete completo con ID estable y nueva versión; comparar base
instalada, nueva y cambios locales. Preservar properties solo cuando ID/tipo/
semántica sigan compatibles; conflictos requieren revisión. `replaces_versions`
es informativo: no ejecuta migraciones. No auto-update, rollback anunciado ni
confianza heredada de un hash. Downgrade, autor distinto y paso de declarativo a
web requieren revisión explícita como contenido nuevo. No convertir `.motivepack`
v1 en ejecutable.

Proceso de revisión futuro: procedencia y licencia por recurso, inventario y
hashes, contratos/quotas, inspección de código (solo web), prueba en host aislado,
revisión humana del resultado y consentimiento de instalación. Una firma futura
atestaría una clave del autor; su confianza y revocación serían capas separadas.
