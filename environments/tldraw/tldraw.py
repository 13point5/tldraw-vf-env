import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import verifiers as vf
from datasets import Dataset
from dataset import get_example_prompts
from bootstrap_env import (
    ensure_playwright_chromium,
    ensure_node_via_nvm,
    ensure_tldraw_agent_deps,
    ensure_validator_server,
    run_blocking,
)
from system_prompt import SYSTEM_PROMPT
from validator_client import ValidatorClient


def parse_response_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "Response does not contain JSON"

    try:
        return json.loads(text[start : end + 1]), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"


async def render_and_score(
    completion,
    state: vf.State,
    prompt=None,
    validator: ValidatorClient | None = None,
) -> float:
    def log_parse_error(message: str, response_text: str) -> None:
        if validator is None:
            return
        user_prompt = None
        if isinstance(prompt, list):
            for message_item in reversed(prompt):
                if message_item.get("role") == "user":
                    user_prompt = message_item.get("content")
                    break
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "errors": [{"stage": "parse", "message": message}],
            "user_prompt": user_prompt,
            "raw_completion": response_text,
        }
        validator.log_error_payload(payload)

    if validator is None:
        validator = state.get("validator")

    if not completion:
        state["render"] = {"errors": [{"message": "Empty completion"}]}
        log_parse_error("Empty completion", "")
        return 0.0

    response_text = completion[-1].get("content", "")
    data, error = parse_response_json(response_text)
    if error:
        state["render"] = {"errors": [{"message": error}]}
        log_parse_error(error, response_text)
        return 0.0

    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list):
        state["render"] = {"errors": [{"message": "Missing actions array"}]}
        log_parse_error("Missing actions array", response_text)
        return 0.0

    if validator is None:
        state["render"] = {"errors": [{"message": "Validator client not available"}]}
        return 0.0

    try:
        result = await validator.validate(actions)
    except Exception as exc:
        state["render"] = {"errors": [{"message": f"Validator failed: {exc}"}]}
        return 0.0

    has_errors = bool(result.get("errors")) or bool(result.get("action_errors"))
    if has_errors:
        if result.get("errors"):
            logging.getLogger(__name__).warning("Validator errors: %s", result["errors"])
        if result.get("action_errors"):
            logging.getLogger(__name__).warning(
                "Validator action errors: %s", result["action_errors"]
            )
        user_prompt = None
        if isinstance(prompt, list):
            for message in reversed(prompt):
                if message.get("role") == "user":
                    user_prompt = message.get("content")
                    break
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "errors": result.get("errors"),
            "action_errors": result.get("action_errors"),
            "user_prompt": user_prompt,
            "actions": actions,
            "image": result.get("image"),
            "image_dir": result.get("image_dir"),
            "image_source": result.get("image_source"),
        }
        error_log_path = validator.log_error_payload(payload)
        if error_log_path:
            result["error_log_path"] = error_log_path
    state["render"] = result
    state["actions"] = actions
    return 1.0 if not has_errors else 0.0


def load_environment(
    validator_url: str = "http://localhost:5173/validator.html",
    pool_size: int = 5,
    headless: bool = True,
    save_screenshots: bool = True,
    screenshot_dir: str = "outputs/screenshots",
    log_errors: bool = True,
    error_log_dir: str = "outputs/errors",
) -> vf.Environment:
    prompts = get_example_prompts()

    dataset = Dataset.from_list([{"question": prompt} for prompt in prompts])

    agent_dir = Path(__file__).resolve().parent / "tldraw-agent"
    run_blocking(ensure_playwright_chromium)
    run_blocking(ensure_node_via_nvm)
    run_blocking(ensure_tldraw_agent_deps, agent_dir)
    run_blocking(ensure_validator_server, validator_url, agent_dir, 60000)

    validator = ValidatorClient(
        url=validator_url,
        pool_size=pool_size,
        headless=headless,
        save_screenshots=save_screenshots,
        screenshot_dir=screenshot_dir,
        log_errors=log_errors,
        error_log_dir=error_log_dir,
    )

    rubric = vf.Rubric(funcs=[render_and_score])
    rubric.add_class_object("validator", validator)

    return vf.SingleTurnEnv(
        dataset=dataset,
        rubric=rubric,
        system_prompt=SYSTEM_PROMPT,
    )
