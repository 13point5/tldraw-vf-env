# tldraw ↔ Verifiers bridge (validator + Playwright)

This document explains how the `tldraw` Verifiers environment validates model actions by driving the `@tldraw-agent` React app via Playwright, while reusing the existing tldraw agent harness with minimal changes.

## Goal and design constraints

- We want a Verifiers environment suitable for evals and RL.
- We want to reuse the tldraw agent harness and action schema “as-is”.
- Validation should happen inside the actual tldraw editor runtime, not in a mock.

## High-level architecture

- **Validator page (React app)** exposes a small window API in the tldraw runtime.
- **Playwright (Python)** opens that page, sends model actions for validation, and reads results.
- **Verifiers environment** uses validator results as the rubric signal and captures rendered images.

Core files:

- `environments/tldraw/tldraw.py` (Python environment + Playwright client)
- `environments/tldraw/tldraw-agent/client/validator/bridge.ts` (window API / validator bridge)
- `environments/tldraw/tldraw-agent/client/validator/ValidatorApp.tsx` (validator app setup)
- `environments/tldraw/tldraw-agent/validator.html` (validator entrypoint)
- `environments/tldraw/tldraw-agent/worker/prompt/buildResponseSchema.ts` (schema from action utils)
- `environments/tldraw/tldraw-agent/shared/AgentUtils.ts` (action list, used by schema)

## End-to-end flow

1. Start the tldraw agent dev server. This serves `validator.html` at `http://localhost:5173/validator.html`.
2. The Verifiers environment starts Playwright and opens the validator page.
3. The validator page exposes `window.__tldrawValidator` with methods: `reset`, `validate`, `getSystemPrompt`.
4. The environment fetches the system prompt directly from the page using a short-lived Playwright session.
5. For each model completion, the environment parses JSON and sends `actions` to `validate`.
6. The validator applies actions through the real tldraw agent harness, renders shapes, and returns structured results.
7. The rubric uses the validator response to decide success and logs images/errors to disk.

## Validator page: window API contract

Defined in `client/validator/bridge.ts` and attached in `ValidatorApp.tsx`.

### `window.__tldrawValidator.reset()`

- Clears all shapes from the current page.
- Resets agent state.

### `window.__tldrawValidator.getSystemPrompt()`

- Returns the exact system prompt string used by the tldraw agent runtime.
- Built with `buildSystemPrompt(...)`, so it stays aligned to any prompt-part or action-level additions.

### `window.__tldrawValidator.validate(actions, imageOptions?)`

Input:

- `actions`: array of agent actions (as defined by action utils)
- `imageOptions` (optional): tldraw `TLImageExportOptions`

Output (`ValidationResult` shape):

- `errors`: validation or export errors (array)
- `action_errors`: per-action sanitize/apply/await errors (array)
- `simpleShapes`: simplified shape list for analysis
- `bindings`: raw binding records
- `rawShapesCount`: count of shapes in editor
- `image` (optional): `{ url, width, height }` data URL snapshot if export succeeded

Key steps inside `validate`:

- Normalizes action type and runs sanitizer via the same action utils the agent uses.
- Executes actions inside `editor.run`, then awaits any async promises.
- Converts resulting shapes to “simple shapes” using shared formatter utilities.
- Optionally exports a raster image from the canvas via `editor.toImage`.

## Verifiers environment: Playwright client

`ValidatorClient` in `tldraw.py` manages a pool of Playwright pages for validation:

- Launches Chromium and opens `validator_url` (default `http://localhost:5173/validator.html`).
- Waits for `window.__tldrawValidator.validate` to exist.
- Provides:
  - `validate(actions, screenshot_path?)` → calls `validate` in the page

Image handling behavior in Python:

- If the page returns a data URL image, it is decoded and saved.
- If no export image is available, it falls back to Playwright `page.screenshot`.
- Images are written to `outputs/screenshots` (configurable).

Error logging:

- If `log_errors` is enabled, failed validations are appended to `outputs/errors/.../errors.jsonl`.

## Rubric integration

In `tldraw.py`:

- `safe_fetch_system_prompt()` loads the validator page in a short-lived Playwright session to fetch the system prompt before validation begins.
- `render_and_score(...)`:
  - Parses model output JSON.
  - Extracts `actions`.
  - Calls `validator.validate(actions)`.
  - Records errors and images in `state["render"]`.
  - Returns `1.0` reward when no validator errors are present, else `0.0`.

This keeps the Verifiers environment aligned to the actual tldraw agent runtime and schema, with minimal duplication.

## Why this preserves the tldraw harness

- Actions are sanitized and applied using the exact same `AgentActionUtil` implementations.
- The response schema is generated from the same action utils list.
- The validator page is just a lightweight adapter on top of the existing tldraw agent code.

## Setup and run

### 1) Start the tldraw validator page

From `environments/tldraw/tldraw-agent`:

```bash
pnpm install
pnpm run dev
```

By default, Vite serves the validator at:

- `http://localhost:5173/validator.html`

### 2) Run a Verifiers eval

From `environments/tldraw`:

```bash
prime eval run tldraw -a '{"validator_url":"http://localhost:5173/validator.html"}'
```

Useful env args:

- `validator_url` (default: `http://localhost:5173/validator.html`)
- `pool_size` (default: `2`)
- `headless` (default: `True`)
- `save_screenshots` (default: `True`)
- `screenshot_dir` (default: `outputs/screenshots`)
- `log_errors` (default: `True`)
- `error_log_dir` (default: `outputs/errors`)

If Playwright browsers are missing, install once:

```bash
uv run playwright install
```

## Notes and troubleshooting

- The validator page must be reachable before the Verifiers environment starts.
- If system prompt fetch fails, environment load will fail.
- Validation errors are surfaced in `state["render"]` and optionally persisted to JSONL.

## Extension points

- Add or remove supported actions in `shared/AgentUtils.ts`.
- The response schema will automatically update to match the action list.
- The validator remains thin, so changes in the core agent harness immediately apply to evals.
