# Tldraw Verifiers Environment

This repo contains a Verifiers environment (`tldraw`) backed by a local tldraw agent UI that acts as the validator. The environment drives the UI with Playwright and scores model outputs based on whether action validation succeeds.

## Quickstart

Install the environment and run a small eval:

```bash
prime env install --path ./environments/tldraw
prime eval run tldraw -m openai/gpt-4.1-mini -n 1 -r 1 \
  -a '{"validator_url":"http://127.0.0.1:5173/validator.html","pool_size":1,"headless":true}'
```

### Bootstrap behavior

When `validator_url` points to localhost, the environment will:

- Install Node.js via `nvm` (Node 24)
- Install JS dependencies in `environments/tldraw/tldraw-agent`
- Start the Vite dev server (serves `validator.html`)
- Ensure Playwright Chromium is installed

If `validator_url` points to a remote host, the environment will **not** start a server; you must ensure the validator page is already reachable.

## System Prompt

The environment reads a fixed system prompt from:

```
environments/tldraw/system_prompt.py
```

## Docker smoke test

A helper script is provided to validate on a clean Linux container:

```bash
export PRIME_INTELLECT_API_KEY=...
./run_docker_eval.sh
```

The script copies the repo into the container (no bind mount), installs dependencies, installs the env, and runs a one‑shot eval.
