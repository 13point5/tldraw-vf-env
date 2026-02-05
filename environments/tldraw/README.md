# tldraw

## Overview

- **Environment ID**: `tldraw`
- **Short description**: Single‑turn tool‑use environment that validates tldraw actions in a real UI using Playwright.
- **Tags**: tldraw, tool-use, ui-validation

## Dataset

- **Source**: Curated prompt list in `dataset.py` (`get_example_prompts`).
- **Split sizes**: Small fixed set used for local evals.

## Task

- **Type**: Single‑turn tool use
- **Parser**: JSON extraction from model output
- **Rubric**: Parses `actions`, runs them through the validator UI, and returns `reward=1` only when validation returns no errors.

## Quickstart

Install and run an eval:

```bash
prime env install --path ./environments/tldraw
prime eval run tldraw -m openai/gpt-4.1-mini -n 1 -r 1 \
  -a '{"validator_url":"http://127.0.0.1:5173/validator.html","pool_size":1,"headless":true}'
```

## Environment Arguments

| Arg                | Type | Default                                  | Description                                                                  |
| ------------------ | ---- | ---------------------------------------- | ---------------------------------------------------------------------------- |
| `validator_url`    | str  | `"http://localhost:5173/validator.html"` | URL of the validator page. If localhost, the env auto‑starts the dev server. |
| `pool_size`        | int  | `5`                                      | Playwright page pool size.                                                   |
| `headless`         | bool | `True`                                   | Run Chromium headless.                                                       |
| `save_screenshots` | bool | `True`                                   | Save screenshots for validation runs.                                        |
| `screenshot_dir`   | str  | `"outputs/screenshots"`                  | Where screenshots are written.                                               |
| `log_errors`       | bool | `True`                                   | Persist validation errors to JSONL.                                          |
| `error_log_dir`    | str  | `"outputs/errors"`                       | Where error logs are written.                                                |

## Bootstrap behavior

When `validator_url` points to localhost, the environment will:

- Install Node.js via `nvm` (Node 24)
- Install JS dependencies in `tldraw-agent/`
- Start the Vite dev server (serves `validator.html`)
- Ensure Playwright Chromium is installed

If `validator_url` points to a remote host, the environment will **not** start a server; the validator page must already be reachable.

## System Prompt

The environment reads a fixed prompt from:

```
./system_prompt.py
```

## Outputs

- Screenshots: `outputs/screenshots/`
- Error logs: `outputs/errors/`
- Validator logs: `outputs/validator/validator.log`
