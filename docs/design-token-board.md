# HarnessDiff Design Token Board

HarnessDiff uses a calm, professional teaching-workbench direction. The UI should feel like a reliable comparison instrument, not a marketing page or analytics dashboard.

## Primary Question

Can the user immediately compare the same chat task with and without Harness?

## Color Tokens

| Token | Value | Usage |
|---|---|---|
| `--color-bg` | `#f6f8fb` | App background |
| `--color-surface` | `#ffffff` | Workbench panels |
| `--color-border` | `#cbd5e1` | Structural dividers |
| `--color-text` | `#0f172a` | Primary text |
| `--color-muted` | `#64748b` | Secondary text |
| `--color-action` | `#2563eb` | Primary actions and active controls |
| `--color-harness` | `#0f766e` | Harness pane identity |
| `--color-neutral-pane` | `#64748b` | NoHarness pane identity |
| `--color-warn` | `#d97706` | Token and cost deltas |
| `--color-danger` | `#b91c1c` | Errors |

## Layout Tokens

| Token | Value | Usage |
|---|---|---|
| `--radius-panel` | `8px` | Pane and toolbar radius |
| `--space-1` | `4px` | Tight internal gaps |
| `--space-2` | `8px` | Control gaps |
| `--space-3` | `12px` | Compact group gaps |
| `--space-4` | `16px` | Default section spacing |
| `--space-6` | `24px` | Workbench padding |
| `--topbar-height` | `64px` | Fixed control row |
| `--composer-height` | `148px` | Stable input surface |

## Type Tokens

| Token | Value | Usage |
|---|---|---|
| `--font-body` | `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | Interface text |
| `--text-xs` | `12px` | Metadata |
| `--text-sm` | `14px` | Controls and helper text |
| `--text-md` | `15px` | Chat text |
| `--text-lg` | `18px` | Pane headings |

## Interaction Rules

- First viewport keeps one primary workbench, one status summary, and one composer.
- Harness settings are exposed through a drawer in later stages, not a persistent side rail.
- Analysis details are deferred behind a summary toggle so the chat comparison remains the visual center.
- Mobile keeps the composer visible and stacks panes vertically without horizontal overflow.

