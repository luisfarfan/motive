# Motive design

Sistema de diseño y experiencia de Motive. Se diseña en **Claude Design** y se
implementa en Rust con GPUI Kit. Nada de lo que hay aquí se ejecuta dentro de
la app: es la referencia de aspecto y comportamiento para Codex.

## Flujo

```
Claude Design (lienzo, fuente de verdad)
   │  pull: skill .claude/skills/design-pull + design/tools/finalize_pull.py
   ▼
design/claude-design/<lienzo>/   artboards .dc.html, canvas.json, assets, manifest.json
design/direction.md              decisiones y reglas (prevalece ante ambigüedad)
design/prototype/                comportamiento fino (HTML/JS de referencia)
   │
   ▼
Codex → Rust + GPUI Kit
```

Para cambiar el diseño: edítalo en el lienzo, apruébalo y pide a Claude
"pull del diseño". No edites `design/claude-design/` a mano.

## Fases

| Fase | Estado | Entregable |
|---|---|---|
| 1. Dirección artística | **En revisión** | [Lienzo](https://claude.ai/artifact/Xz4yhpz6kQhy13EGLVBDav) → [copia](claude-design/studio-fase-1/), [direction.md](direction.md), [prototipo](prototype/studio/index.html), [capturas](screens/phase-1/) |
| 2. Sistema fundamental | Pendiente de aprobar la Fase 1 | Lienzo de sistema de diseño → `foundations/`, `components/` |
| 3. Experiencia completa | Pendiente | `patterns/`, `screens/` |
| 4. Validación | Pendiente | Revisión de consistencia y accesibilidad |
| 5. Entrega | Pendiente | `handoff/`, ZIP |

## Abrir el prototipo

```sh
cd design/prototype/studio
python3 -m http.server 8731 --bind 127.0.0.1
# http://127.0.0.1:8731/
```

No tiene dependencias ni recursos externos. Solo se verificó servido por HTTP
local; la apertura directa por `file://` no se ha probado.

Licencia: GPL-3.0-or-later, igual que el repositorio. Todos los recursos son
originales y se generan con código.
