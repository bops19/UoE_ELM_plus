import base64
import threading
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse


def _safe_get(obj, *path, default=None):
    current = obj
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
            continue
        try:
            current = getattr(current, key)
        except Exception:
            return default
    return current if current is not None else default


class ComputerRunError(Exception):
    def __init__(self, message: str, error_code: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status = status
        self.extra = extra or {}


def is_computer_use_preview_model(model: str, *, normalize_text, preview_model: str) -> bool:
    normalized = normalize_text(model or "")
    return bool(normalized) and normalized.startswith(preview_model)


def computer_run_event(now_ms, stage: str, status: str, detail: str | None = None, extra: dict | None = None) -> dict:
    event = {
        "timestamp": now_ms(),
        "stage": stage,
        "status": status,
    }
    if detail:
        event["detail"] = detail
    if isinstance(extra, dict) and extra:
        event.update(extra)
    return event


def _normalize_key_name(key_name: str, *, normalize_text) -> str:
    normalized = normalize_text(key_name).upper()
    key_map = {
        "ENTER": "Enter",
        "RETURN": "Enter",
        "ESC": "Escape",
        "ESCAPE": "Escape",
        "TAB": "Tab",
        "SPACE": "Space",
        "BACKSPACE": "Backspace",
        "DELETE": "Delete",
        "DEL": "Delete",
        "HOME": "Home",
        "END": "End",
        "PAGEUP": "PageUp",
        "PAGEDOWN": "PageDown",
        "UP": "ArrowUp",
        "ARROWUP": "ArrowUp",
        "DOWN": "ArrowDown",
        "ARROWDOWN": "ArrowDown",
        "LEFT": "ArrowLeft",
        "ARROWLEFT": "ArrowLeft",
        "RIGHT": "ArrowRight",
        "ARROWRIGHT": "ArrowRight",
        "CTRL": "ctrl",
        "CONTROL": "ctrl",
        "SHIFT": "shift",
        "ALT": "alt",
        "OPTION": "alt",
        "META": "Meta",
        "CMD": "Meta",
        "COMMAND": "Meta",
    }
    return key_map.get(normalized, key_name)


def execute_computer_action(page, action: dict, *, normalize_text, sleep_fn=time.sleep):
    action_type = normalize_text(_safe_get(action, "type", default=""))
    if not action_type:
        raise ComputerRunError("Missing computer action type.", "computer_action_missing_type", 400)

    if action_type == "click":
        x = int(_safe_get(action, "x", default=0) or 0)
        y = int(_safe_get(action, "y", default=0) or 0)
        button = normalize_text(_safe_get(action, "button", default="left")) or "left"
        page.mouse.click(x, y, button=button)
        return

    if action_type == "double_click":
        x = int(_safe_get(action, "x", default=0) or 0)
        y = int(_safe_get(action, "y", default=0) or 0)
        button = normalize_text(_safe_get(action, "button", default="left")) or "left"
        page.mouse.dblclick(x, y, button=button)
        return

    if action_type == "type":
        text_value = str(_safe_get(action, "text", default="") or "")
        page.keyboard.type(text_value)
        return

    if action_type in {"keypress", "key"}:
        raw_keys = _safe_get(action, "keys", default=None)
        if isinstance(raw_keys, list) and raw_keys:
            keys = [_normalize_key_name(str(key), normalize_text=normalize_text) for key in raw_keys if str(key).strip()]
            if not keys:
                raise ComputerRunError("keypress action requires at least one key.", "computer_action_invalid_keypress", 400)
            page.keyboard.press("+".join(keys))
            return
        single_key = normalize_text(_safe_get(action, "key", default=""))
        if not single_key:
            raise ComputerRunError("keypress action requires key or keys.", "computer_action_invalid_keypress", 400)
        page.keyboard.press(_normalize_key_name(single_key, normalize_text=normalize_text))
        return

    if action_type == "scroll":
        x = int(_safe_get(action, "x", default=0) or 0)
        y = int(_safe_get(action, "y", default=0) or 0)
        scroll_x = int(
            _safe_get(action, "scroll_x", default=None)
            or _safe_get(action, "delta_x", default=None)
            or 0
        )
        scroll_y = int(
            _safe_get(action, "scroll_y", default=None)
            or _safe_get(action, "delta_y", default=None)
            or 0
        )
        page.mouse.move(x, y)
        page.mouse.wheel(scroll_x, scroll_y)
        return

    if action_type == "wait":
        wait_ms = _safe_get(action, "duration_ms", default=None)
        if wait_ms is None:
            wait_sec = float(_safe_get(action, "duration", default=1.0) or 1.0)
            wait_ms = max(0, int(wait_sec * 1000))
        sleep_fn(max(0.0, float(wait_ms) / 1000.0))
        return

    if action_type == "drag":
        path = _safe_get(action, "path", default=[])
        if not isinstance(path, list) or len(path) < 2:
            raise ComputerRunError("drag action requires a path with at least 2 points.", "computer_action_invalid_drag_path", 400)
        normalized_points = []
        for point in path:
            if isinstance(point, dict):
                normalized_points.append((int(point.get("x", 0)), int(point.get("y", 0))))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                normalized_points.append((int(point[0]), int(point[1])))
        if len(normalized_points) < 2:
            raise ComputerRunError("drag action path points are invalid.", "computer_action_invalid_drag_path", 400)
        first_x, first_y = normalized_points[0]
        page.mouse.move(first_x, first_y)
        page.mouse.down()
        for x, y in normalized_points[1:]:
            page.mouse.move(x, y)
        page.mouse.up()
        return

    raise ComputerRunError(
        f"Unsupported computer action type: {action_type}",
        "computer_action_unsupported",
        400,
    )


def _computer_action_to_payload(action, *, transcription_value_to_python) -> dict:
    converted = transcription_value_to_python(action)
    return converted if isinstance(converted, dict) else {}


def normalize_acknowledged_safety_checks(raw_checks, *, transcription_value_to_python) -> list[dict]:
    if not isinstance(raw_checks, list):
        return []
    output: list[dict] = []
    for item in raw_checks:
        converted = transcription_value_to_python(item)
        if isinstance(converted, dict):
            output.append(converted)
    return output


def normalize_start_url(start_url: str | None, *, normalize_text) -> str | None:
    value = normalize_text(start_url or "")
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ComputerRunError(
            "startUrl must be an absolute http(s) URL.",
            "computer_run_invalid_start_url",
            400,
        )
    return value


def extract_computer_response(
    response,
    *,
    normalize_text,
    transcription_to_dict,
    transcription_value_to_python,
    response_text,
    usage_payload,
) -> dict:
    output_items = _safe_get(response, "output", default=[]) or []
    next_call_id = None
    next_action = None
    pending_safety_checks: list[dict] = []

    for item in output_items:
        item_type = normalize_text(
            _safe_get(item, "type", default=None)
            or _safe_get(transcription_to_dict(item), "type", default=None)
            or ""
        )
        if item_type != "computer_call" or next_action:
            continue
        item_data = transcription_to_dict(item)
        next_call_id = normalize_text(
            _safe_get(item, "call_id", default=None)
            or _safe_get(item_data, "call_id", default=None)
            or _safe_get(item, "id", default=None)
            or ""
        ) or None
        next_action = _computer_action_to_payload(
            _safe_get(item, "action", default=None)
            or _safe_get(item_data, "action", default=None)
            or {},
            transcription_value_to_python=transcription_value_to_python,
        )
        raw_checks = (
            _safe_get(item, "pending_safety_checks", default=None)
            or _safe_get(item_data, "pending_safety_checks", default=None)
            or []
        )
        pending_safety_checks = normalize_acknowledged_safety_checks(
            raw_checks,
            transcription_value_to_python=transcription_value_to_python,
        )

    return {
        "responseId": normalize_text(_safe_get(response, "id", default="")) or None,
        "finalText": response_text(response),
        "nextCallId": next_call_id,
        "nextAction": next_action,
        "pendingSafetyChecks": pending_safety_checks,
        "usage": usage_payload(_safe_get(response, "usage", default=None), responses_api=True),
    }


@dataclass
class ComputerRunManagerDeps:
    normalize_text: callable
    now_ms: callable
    request_id: callable
    db_factory: callable
    append_token_usage_log: callable
    usage_cost: callable
    ensure_session: callable
    insert_message: callable
    refresh_session_title: callable
    update_message: callable
    response_text: callable
    usage_payload: callable
    transcription_to_dict: callable
    transcription_value_to_python: callable
    security_log: callable
    openai_timeout_sec: float
    preview_model: str
    preview_environment: str


class ComputerRunManagerCore:
    def __init__(self, openai_client_factory, playwright_factory, deps: ComputerRunManagerDeps):
        self._openai_client_factory = openai_client_factory
        self._playwright_factory = playwright_factory
        self._deps = deps
        self._runs: dict[str, dict] = {}
        self._closed_status: dict[str, str] = {}
        self._lock = threading.Lock()

    def _openai_client(self):
        if callable(self._openai_client_factory):
            return self._openai_client_factory()
        return self._openai_client_factory

    def _tool_spec(self, run: dict) -> list[dict]:
        return [{
            "type": "computer_use_preview",
            "display_width": run["displayWidth"],
            "display_height": run["displayHeight"],
            "environment": self._deps.preview_environment,
        }]

    def _register_closed_status(self, run_id: str, status: str):
        self._closed_status[run_id] = status
        if len(self._closed_status) > 500:
            oldest = next(iter(self._closed_status.keys()))
            self._closed_status.pop(oldest, None)

    def _add_timeline(self, run: dict, stage: str, status: str, detail: str | None = None, extra: dict | None = None):
        run["timeline"].append(computer_run_event(self._deps.now_ms, stage, status, detail, extra=extra))
        run["updatedAt"] = self._deps.now_ms()

    def _screenshot_data_url(self, page) -> str:
        raw = page.screenshot(full_page=True)
        if not raw:
            raise RuntimeError("Screenshot capture returned empty bytes.")
        return f"data:image/png;base64,{base64.b64encode(raw).decode('utf-8')}"

    def _close_handles(self, run: dict):
        for key in ("page", "context", "browser", "playwright"):
            handle = run.get(key)
            if not handle:
                continue
            try:
                close_method = getattr(handle, "close", None)
                if callable(close_method):
                    close_method()
                elif key == "playwright":
                    stop_method = getattr(handle, "stop", None)
                    if callable(stop_method):
                        stop_method()
            except Exception:
                pass
            run[key] = None

    def _remove_active_run(self, run_id: str):
        with self._lock:
            self._runs.pop(run_id, None)

    def _store_active_run(self, run: dict):
        with self._lock:
            self._runs[run["runId"]] = run

    def _get_active_run(self, run_id: str) -> dict | None:
        with self._lock:
            return self._runs.get(run_id)

    def _finalize_message(self, run: dict, *, status: str):
        assistant_message_id = run.get("assistantMessageId")
        if not assistant_message_id:
            return
        elapsed_sec = max(0.0, time.monotonic() - run["startedMonotonic"])
        usage_data = run.get("usage")
        response_cost = self._deps.usage_cost(usage_data, run["model"]) if usage_data else None
        if status == "complete":
            content = run.get("finalText") or "Computer run completed."
        elif status == "interrupted":
            content = run.get("finalText") or "[Computer run cancelled]"
        else:
            content = run.get("finalText") or "[Computer run failed]"
        with self._deps.db_factory() as conn:
            self._deps.update_message(
                conn,
                assistant_message_id,
                content=content,
                usage=usage_data,
                usage_model=run["model"],
                usage_cost=response_cost,
                elapsed_sec=elapsed_sec,
                status=status,
            )
            conn.commit()
        if usage_data and response_cost is not None:
            self._deps.append_token_usage_log({
                "timestamp": self._deps.now_ms(),
                "sessionId": run["sessionId"],
                "assistantMessageId": assistant_message_id,
                "useCase": "computer",
                "model": run["model"],
                "usage": usage_data,
                "cost": response_cost,
            })

    def _snapshot(self, run: dict) -> dict:
        payload = {
            "runId": run["runId"],
            "status": run["status"],
            "nextAction": run.get("nextAction"),
            "timeline": list(run.get("timeline", [])),
            "finalText": run.get("finalText") or "",
            "usage": run.get("usage"),
            "requestId": self._deps.request_id(),
        }
        if run.get("error"):
            payload["error"] = run["error"]
            payload["errorCode"] = run.get("errorCode") or "computer_run_failed"
            if run.get("errorDetail"):
                payload["errorDetail"] = run["errorDetail"]
        return payload

    def _apply_response(self, run: dict, response):
        parsed = extract_computer_response(
            response,
            normalize_text=self._deps.normalize_text,
            transcription_to_dict=self._deps.transcription_to_dict,
            transcription_value_to_python=self._deps.transcription_value_to_python,
            response_text=self._deps.response_text,
            usage_payload=self._deps.usage_payload,
        )
        run["previousResponseId"] = parsed.get("responseId") or run.get("previousResponseId")
        run["usage"] = parsed.get("usage") or run.get("usage")

        next_call_id = parsed.get("nextCallId")
        next_action = parsed.get("nextAction")
        pending_safety_checks = parsed.get("pendingSafetyChecks") or []
        if next_call_id and isinstance(next_action, dict) and next_action:
            run["status"] = "needs_action"
            run["pendingCallId"] = next_call_id
            run["nextAction"] = next_action
            run["pendingSafetyChecks"] = pending_safety_checks
            action_type = self._deps.normalize_text(_safe_get(next_action, "type", default="")) or "unknown"
            self._add_timeline(run, "awaiting_action", "active", f"Model requested action: {action_type}")
            return

        run["pendingCallId"] = None
        run["nextAction"] = None
        run["pendingSafetyChecks"] = []
        final_text = self._deps.normalize_text(parsed.get("finalText") or "")
        if final_text:
            run["status"] = "completed"
            run["finalText"] = final_text
            self._add_timeline(run, "completed", "done", "Model produced a final answer")
            return

        run["status"] = "failed"
        run["error"] = "Model response contained neither action nor final text."
        run["errorCode"] = "computer_response_invalid_shape"
        run["finalText"] = "Computer run failed: model response was not actionable."
        self._add_timeline(run, "completed", "error", "Model response missing next action or final text")

    def _start_browser(self, run: dict):
        if not self._playwright_factory:
            raise ComputerRunError(
                "Playwright is not available on this server. Install `playwright` and browsers first.",
                "computer_run_playwright_unavailable",
                503,
            )
        bootstrap = self._playwright_factory()
        playwright = bootstrap.start() if callable(getattr(bootstrap, "start", None)) else bootstrap
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={
                "width": run["displayWidth"],
                "height": run["displayHeight"],
            }
        )
        page = context.new_page()
        run["playwright"] = playwright
        run["browser"] = browser
        run["context"] = context
        run["page"] = page
        if run.get("startUrl"):
            page.goto(run["startUrl"], wait_until="domcontentloaded")

    def start_run(
        self,
        *,
        session_id: str,
        user_text: str,
        model: str,
        display_width: int,
        display_height: int,
        start_url: str | None,
        reasoning_summary: str | None = None,
    ) -> dict:
        normalized_session_id = self._deps.normalize_text(session_id or "")
        normalized_user_text = self._deps.normalize_text(user_text or "")
        normalized_model = self._deps.normalize_text(model or "") or self._deps.preview_model
        if not normalized_session_id:
            raise ComputerRunError("sessionId is required", "computer_run_missing_session_id", 400)
        if not normalized_user_text:
            raise ComputerRunError("userText is required", "computer_run_missing_user_text", 400)
        if not is_computer_use_preview_model(
            normalized_model,
            normalize_text=self._deps.normalize_text,
            preview_model=self._deps.preview_model,
        ):
            raise ComputerRunError(
                f"Legacy route only supports `{self._deps.preview_model}`.",
                "computer_run_model_not_supported",
                400,
            )

        with self._deps.db_factory() as conn:
            self._deps.ensure_session(conn, normalized_session_id, "computer")
            self._deps.insert_message(conn, normalized_session_id, "user", normalized_user_text, status="complete")
            self._deps.refresh_session_title(conn, normalized_session_id)
            assistant_message_id = self._deps.insert_message(conn, normalized_session_id, "assistant", "", status="pending")
            conn.commit()

        run = {
            "runId": uuid.uuid4().hex,
            "sessionId": normalized_session_id,
            "status": "starting",
            "model": normalized_model,
            "displayWidth": display_width,
            "displayHeight": display_height,
            "startUrl": start_url,
            "assistantMessageId": assistant_message_id,
            "timeline": [],
            "pendingCallId": None,
            "nextAction": None,
            "pendingSafetyChecks": [],
            "previousResponseId": None,
            "finalText": "",
            "lastScreenshotUrl": None,
            "usage": None,
            "error": "",
            "errorCode": "",
            "createdAt": self._deps.now_ms(),
            "updatedAt": self._deps.now_ms(),
            "startedMonotonic": time.monotonic(),
            "threadId": threading.get_ident(),
            "runLock": threading.Lock(),
            "playwright": None,
            "browser": None,
            "context": None,
            "page": None,
        }
        self._add_timeline(run, "run_start", "active", "Initializing browser and model call")
        self._store_active_run(run)

        try:
            self._start_browser(run)
            self._add_timeline(run, "browser_ready", "done", "Playwright browser context is ready")
            initial_image_url = self._screenshot_data_url(run["page"])
            run["lastScreenshotUrl"] = initial_image_url
            self._add_timeline(run, "screenshot", "done", "Captured initial screenshot")

            content_blocks = [{"type": "input_text", "text": normalized_user_text}]
            if initial_image_url:
                content_blocks.append({"type": "input_image", "image_url": initial_image_url})

            request_payload = {
                "model": normalized_model,
                "tools": self._tool_spec(run),
                "input": [{"role": "user", "content": content_blocks}],
                "truncation": "auto",
                "store": False,
            }
            summary_mode = self._deps.normalize_text(reasoning_summary or "")
            if summary_mode in {"concise", "detailed"}:
                request_payload["reasoning"] = {"summary": summary_mode}

            self._add_timeline(run, "model_request", "active", "Requesting first action from model")
            response = self._openai_client().with_options(timeout=self._deps.openai_timeout_sec).responses.create(**request_payload)
            self._add_timeline(run, "model_request", "done", "Received first response")
            self._apply_response(run, response)

            if run["status"] == "completed":
                self._finalize_message(run, status="complete")
                self._close_handles(run)
                self._remove_active_run(run["runId"])
                self._register_closed_status(run["runId"], "completed")
            elif run["status"] == "failed":
                self._finalize_message(run, status="error")
                self._close_handles(run)
                self._remove_active_run(run["runId"])
                self._register_closed_status(run["runId"], "failed")
            return self._snapshot(run)
        except ComputerRunError as exc:
            run["status"] = "failed"
            run["error"] = exc.message
            run["errorCode"] = exc.error_code
            run["finalText"] = f"Computer run failed: {exc.message}"
            self._add_timeline(run, "run_start", "error", exc.message)
            self._finalize_message(run, status="error")
            self._close_handles(run)
            self._remove_active_run(run["runId"])
            self._register_closed_status(run["runId"], "failed")
            return self._snapshot(run)
        except Exception as exc:
            self._deps.security_log("CUA START  ", f"{type(exc).__name__}: {str(exc)[:300]}")
            detail = self._deps.normalize_text(f"{type(exc).__name__}: {str(exc)}") or "Unexpected runtime failure"
            run["status"] = "failed"
            run["error"] = f"Computer run failed during start: {detail[:300]}"
            run["errorCode"] = "computer_run_start_failed"
            run["finalText"] = f"Computer run failed during startup: {detail[:300]}"
            run["errorDetail"] = detail[:1000]
            self._add_timeline(run, "run_start", "error", detail[:300])
            self._finalize_message(run, status="error")
            self._close_handles(run)
            self._remove_active_run(run["runId"])
            self._register_closed_status(run["runId"], "failed")
            return self._snapshot(run)

    def step_run(self, run_id: str, acknowledged_safety_checks: list[dict] | None = None) -> dict:
        run = self._get_active_run(run_id)
        if not run:
            raise ComputerRunError("Unknown runId.", "computer_run_not_found", 404)
        if run.get("threadId") and run["threadId"] != threading.get_ident():
            raise ComputerRunError(
                "This computer run is bound to a different server thread. Restart with single-thread mode (threaded=False).",
                "computer_run_thread_mismatch",
                409,
            )
        with run["runLock"]:
            if run.get("status") != "needs_action" or not run.get("pendingCallId") or not run.get("nextAction"):
                raise ComputerRunError(
                    "Run is not waiting for an action step.",
                    "computer_run_not_waiting_for_action",
                    409,
                )
            try:
                action_payload = run["nextAction"]
                action_type = self._deps.normalize_text(_safe_get(action_payload, "type", default="")) or "unknown"
                self._add_timeline(run, "action_execute", "active", f"Executing action: {action_type}")
                execute_computer_action(run["page"], action_payload, normalize_text=self._deps.normalize_text)
                self._add_timeline(run, "action_execute", "done", f"Executed action: {action_type}")

                self._add_timeline(run, "screenshot", "active", "Capturing post-action screenshot")
                screenshot_url = self._screenshot_data_url(run["page"])
                run["lastScreenshotUrl"] = screenshot_url
                current_url = self._deps.normalize_text(getattr(run["page"], "url", "") or "")
                self._add_timeline(run, "screenshot", "done", "Captured post-action screenshot")
                step_input = {
                    "type": "computer_call_output",
                    "call_id": run["pendingCallId"],
                    "acknowledged_safety_checks": normalize_acknowledged_safety_checks(
                        acknowledged_safety_checks or [],
                        transcription_value_to_python=self._deps.transcription_value_to_python,
                    ),
                    "output": {
                        "type": "computer_screenshot",
                        "image_url": screenshot_url,
                    },
                }
                if current_url:
                    step_input["current_url"] = current_url

                self._add_timeline(run, "model_request", "active", "Requesting next step from model")
                response = self._openai_client().with_options(timeout=self._deps.openai_timeout_sec).responses.create(
                    model=run["model"],
                    previous_response_id=run["previousResponseId"],
                    tools=self._tool_spec(run),
                    input=[step_input],
                    truncation="auto",
                    store=False,
                )
                self._add_timeline(run, "model_request", "done", "Received step response")
                self._apply_response(run, response)

                if run["status"] == "completed":
                    self._finalize_message(run, status="complete")
                    self._close_handles(run)
                    self._remove_active_run(run["runId"])
                    self._register_closed_status(run["runId"], "completed")
                elif run["status"] == "failed":
                    self._finalize_message(run, status="error")
                    self._close_handles(run)
                    self._remove_active_run(run["runId"])
                    self._register_closed_status(run["runId"], "failed")
                return self._snapshot(run)
            except ComputerRunError as exc:
                run["status"] = "failed"
                run["error"] = exc.message
                run["errorCode"] = exc.error_code
                run["finalText"] = f"Computer run failed: {exc.message}"
                self._add_timeline(run, "action_execute", "error", exc.message)
                self._finalize_message(run, status="error")
                self._close_handles(run)
                self._remove_active_run(run["runId"])
                self._register_closed_status(run["runId"], "failed")
                return self._snapshot(run)
            except Exception as exc:
                self._deps.security_log("CUA STEP   ", f"{type(exc).__name__}: {str(exc)[:300]}")
                detail = self._deps.normalize_text(f"{type(exc).__name__}: {str(exc)}") or "Unexpected runtime failure"
                run["status"] = "failed"
                run["error"] = f"Computer run failed during step execution: {detail[:300]}"
                run["errorCode"] = "computer_run_step_failed"
                run["finalText"] = f"Computer run failed while executing the latest action: {detail[:300]}"
                run["errorDetail"] = detail[:1000]
                self._add_timeline(run, "action_execute", "error", detail[:300])
                self._finalize_message(run, status="error")
                self._close_handles(run)
                self._remove_active_run(run["runId"])
                self._register_closed_status(run["runId"], "failed")
                return self._snapshot(run)

    def close_run(self, run_id: str) -> dict:
        run = self._get_active_run(run_id)
        if not run:
            if run_id in self._closed_status:
                return {"ok": True, "runId": run_id, "status": "closed"}
            raise ComputerRunError("Unknown runId.", "computer_run_not_found", 404)

        with run["runLock"]:
            run["status"] = "cancelled"
            run["finalText"] = run.get("finalText") or "[Computer run cancelled]"
            self._add_timeline(run, "run_close", "done", "Run closed by client")
            self._finalize_message(run, status="interrupted")
            self._close_handles(run)
            self._remove_active_run(run_id)
            self._register_closed_status(run_id, "cancelled")
            return {"ok": True, "runId": run_id, "status": "cancelled"}
