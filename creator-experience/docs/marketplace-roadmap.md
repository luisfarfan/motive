# Motive Hub · decisiones antes de infraestructura

**Concepto futuro.** Motive sigue siendo gratuito, local-first, sin cuenta
obligatoria y usable offline. Abrir un pack local conserva el mismo recorrido de
validación que una descarga. No hay backend, autenticación, pagos ni telemetría
en esta entrega.

| Incremento futuro | Resultado verificable | Gate |
|---|---|---|
| 1 · Distribución local | Un paquete viaja entre dos Macs y conserva personalización | Importador oficial, integridad y recuperación parcial verificados |
| 2 · Índice estático opcional | Catálogo consultable con copia offline y descarga explícita | Licencias, versión/capacidad y hashes verificables; sin auto-fetch de assets |
| 3 · Curaduría | Colecciones destacadas, perfiles y reportes revisados | Política de atribución, moderación y retirada sin borrar archivos del usuario |
| 4 · Actualizaciones revisables | Comparación de versiones y cambios locales | Identidad/confianza del publicador y migraciones declarativas ratificadas |

Catálogo: buscar nombre, autor y tags; filtrar categoría, orientación, licencia y
capacidades. Ordenar destacados/nuevos sin disfrazar patrocinio. Mostrar 6 escenas,
fuentes/capas necesarias, memoria estimada y requisitos de importador antes de
descargar. «Validado contra contrato» no significa «aceptado en vivo».

Perfiles: autor declarado, enlaces opcionales, colecciones y licencia por versión.
Un nombre no equivale a identidad verificada. Métricas de descarga, si existen,
serán agregados del catálogo, nunca una condición para instalar localmente.

Ficha de versión: changelog, digest, tamaño, licencia, previews, propiedades,
capacidades, alcance de QA y compatibilidad comprobada. Un reporte de recurso
incompatible incluye versión, error tipado y contexto mínimo opt-in; nunca logs
completos, secretos, contenido de cámara o inventarios privados por defecto.

Verificación: integridad antes de staging; firma/procedencia como dimensión
separada. Packs declarativos no ejecutan shell, JavaScript, MCP, URLs, sockets ni
plugins. Cualquier extensión ejecutable necesitaría otro modelo de permisos y
otro ciclo de seguridad. No cabe como «asset avanzado» dentro de este formato.
