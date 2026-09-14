from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from .config import ConfigError, Settings
from .http_server import HomeworkHTTPServer
from .service import HomeworkService
from .source import PronoteSource
from .state import RuntimeState


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Pronote homework to JSON over HTTP and MQTT"
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("serve", help="run the HTTP server and scheduler")
    subcommands.add_parser("once", help="refresh the JSON snapshot once and exit")
    subcommands.add_parser(
        "create-token",
        help="create renewable token credentials from password authentication",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _arguments()
    command = args.command or "serve"

    try:
        settings = Settings.from_env()
        source = PronoteSource(settings)

        if command == "create-token":
            path = source.create_token_credentials()
            print(f"Token credentials written to {path}")
            print("Set PRONOTE_AUTH_MODE=token before normal operation.")
            return 0

        state = RuntimeState(settings.output_path)
        service = HomeworkService(settings, state, source=source)

        if command == "once":
            service.refresh(raise_errors=True)
            return 0

        stop_event = threading.Event()
        scheduler = threading.Thread(
            target=service.run_scheduler,
            args=(stop_event,),
            name="pronote-refresh",
            daemon=True,
        )
        scheduler.start()

        server = HomeworkHTTPServer(
            (settings.http_host, settings.http_port),
            state,
            settings.api_key,
            completion_handler=service.set_homework_done,
            events_provider=service.completion_events,
        )

        def stop(_signal: int, _frame: object) -> None:
            stop_event.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        logging.getLogger(__name__).info(
            "Serving homework JSON on http://%s:%d/homework.json",
            settings.http_host,
            settings.http_port,
        )
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            stop_event.set()
            server.server_close()
            scheduler.join(timeout=5)
        return 0
    except (ConfigError, OSError, RuntimeError, ValueError) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
