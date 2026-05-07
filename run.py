"""Entry point — run with: python run.py"""
import os
from app import app, log, _NOFILE_LIMIT_STATUS

if __name__ == "__main__":
    os.environ["FLASK_DEBUG"] = "0"
    print()
    print("╔══════════════════════════════════════════╗")
    print("║       University of Edinburgh ELM+       ║")
    print("╚══════════════════════════════════════════╝")
    print()
    log("✅", "API KEY    ", "Loaded")
    if _NOFILE_LIMIT_STATUS.get("error"):
        log("⚠️ ", "NOFILE     ", f"startup guard failed: {_NOFILE_LIMIT_STATUS['error']}")
    elif _NOFILE_LIMIT_STATUS.get("supported"):
        hard_limit = _NOFILE_LIMIT_STATUS.get("hard", -1)
        hard_display = "unlimited" if hard_limit == -1 else str(hard_limit)
        log(
            "🧰",
            "NOFILE     ",
            f"soft={_NOFILE_LIMIT_STATUS.get('soft')} hard={hard_display} target>={_NOFILE_LIMIT_STATUS.get('target')}",
        )
    else:
        log("ℹ️ ", "NOFILE     ", "resource module unavailable on this platform")
    log("🚀", "SERVER     ", "running at http://localhost:9595")
    log("⏳", "WAITING    ", "for requests...")
    print()
    app.run(
        port=9595,
        debug=False,
        threaded=False,
        use_reloader=False,
        use_debugger=False,
    )
