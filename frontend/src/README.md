# Finanzas — Design Tokens

Drop-in tokens that match the visual reference. Everything lives in `src/index.css`.

## Where the tokens live

- **`src/index.css`** — single source of truth. Targets **Tailwind v4** (`@theme` directive) and also exports plain CSS custom properties on `:root` so non-Tailwind code (styled-components, inline styles, vanilla CSS) can read them too. Includes a few utility classes (`.display`, `.label`, `.tag`, `.bar-track`, `.leader`) that are awkward to express purely in Tailwind.
- A second `@theme inline { … }` block in the same file aliases shadcn's abstract tokens (`background`, `foreground`, `primary`, …) to the design tokens, so shadcn primitives in `src/components/ui/` consume the design system without per-component overrides.

## Quick start (Tailwind v4)

`src/main.tsx` already imports `./index.css` — nothing else to wire up. Use the utilities directly:

```tsx
<div className="bg-paper text-ink p-16">
  <span className="label">Balance del mes</span>
  <h1 className="display text-hero">+ $ 692.750</h1>
  <span className="num text-sm text-ink-mute">tasa de ahorro 32%</span>
</div>
```

The `@theme` block generates `bg-paper`, `text-ink`, `text-shame`, `font-serif`, `text-hero`, `rounded-pill`, etc. automatically. The shadcn-style names (`bg-background`, `text-foreground`, `bg-primary`, …) also work and resolve to the same colors via the alias layer.

## Fonts

Three families, loaded from `@fontsource*` npm packages (self-hosted, no CDN). Already imported at the top of `src/index.css`:

- `@fontsource-variable/geist` — all UI text (sans).
- `@fontsource/instrument-serif` (regular + italic) — hero numbers, page titles.
- `@fontsource-variable/jetbrains-mono` — every cifra in a list/bar (with `.num` for tabular figures).

## Token map

### Color roles
| Token | Hex | Use |
|---|---|---|
| `paper` | `#f3efe6` | Page background |
| `paper-2` | `#ece7da` | Elevated surfaces (insight rows, chart wrappers, chips) |
| `paper-3` | `#e3ddcc` | Bar tracks, divider fills |
| `ink` | `#1a1814` | Primary text, primary buttons |
| `ink-2` | `#3a3530` | Body text |
| `ink-mute` | `#7a736a` | Secondary text |
| `ink-faint` | `#a8a094` | Tertiary text, axis ticks |
| `rule` | `#d8d1c0` | Solid hairlines |
| `rule-soft` | `#e5dfd0` | Inner-list hairlines |
| `link` | `#1f3d6b` | Meta progress, links |
| `income` | `#355e3b` | Ingresos, on-pace status |
| `expense` | `#6b2418` | Egresos |
| `shame` | `#c43d2a` | Over budget, alerts |
| `warn` | `#b6791f` | Approaching limit |

### Categories (semantic — never reassign)
Vivienda, Comida, Transporte, Servicios, Salud, Ocio, Educación, Otros — each gets a fixed hue. See `--color-cat-*` in `src/index.css`.

### Type
- **Instrument Serif** — hero numbers, page titles, goal names. Italic for emphasis.
- **Geist** — all UI text. Weights 400/500/600.
- **JetBrains Mono** — every cifra in a list or bar (with `font-feature-settings: "tnum"` enabled via `.num`).

### Scale
- Hero 96 · Display 64 · H1 32 · Body 14 · SM 13 · XS 12 · Tag 11 · Micro 10
- Radii: xs 4 · sm 8 · md 12 · lg 14 · xl 16 · 2xl 24 · pill 999

## Principles (carry these into the build)

1. **Sin chrome** — no header, no footer, no avatar.
2. **El dato es la UI** — typography and color do the separation. Cards only when truly needed (insight rows, chat bubbles, chart wrappers).
3. **Vergüenza, no bloqueo** — `shame` continues past 100% as a hatched overrun. Never cap.
4. **Una fuente por trabajo** — never use serif for UI, never use sans for cifras. Mono numerics align vertically.
5. **Color = significado** — link/income/expense/shame/warn are semantic. Don't decorate with them.
