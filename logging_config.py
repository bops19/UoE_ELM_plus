import logging
import os
import sys

from flask import Flask


def configure_logging(app: Flask):
    if getattr(app, "_elm_logging_configured", False):
        return

    level = logging.DEBUG if app.debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
    app.logger.propagate = False
    app._elm_logging_configured = True


def configure_sentry(app: Flask):
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except Exception as exc:
        app.logger.warning("SENTRY_DSN is set but sentry-sdk is unavailable: %s", exc)
        return

    traces_sample_rate_raw = (os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "0.1").strip()
    try:
        traces_sample_rate = float(traces_sample_rate_raw)
    except ValueError:
        traces_sample_rate = 0.1

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=max(0.0, min(1.0, traces_sample_rate)),
    )
    app.logger.info("Sentry integration enabled")
