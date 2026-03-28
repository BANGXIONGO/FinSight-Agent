"""
Standalone Flask server for InsightEngine dashboard.
"""

from __future__ import annotations

import os

from flask import Flask, redirect, url_for

from InsightEngine.flask_interface import initialize_insight_engine, insight_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(insight_bp, url_prefix="/insight")

    @app.route("/", methods=["GET"])
    def root():
        return redirect(url_for("insight_engine.dashboard"))

    initialize_insight_engine()
    return app


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5050"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    app = create_app()
    app.run(host=host, port=port, debug=debug, threaded=True)
