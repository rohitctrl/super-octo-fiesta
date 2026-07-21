"""CrocBridge entry point: python -m crocbridge [--port N] [--config PATH] [--host ADDR]"""

import argparse
import atexit
import logging
import signal
import sys
from pathlib import Path

from .app import create_app
from .config import ConfigManager
from .receiver import ReceiverDaemon
from .sender import SendManager
from .state import AppState

DEFAULT_PORT = 5599
DEFAULT_CONFIG = Path.home() / ".crocbridge" / "config.json"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crocbridge", description="AirDrop-style croc bridge")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="config file path (lets two instances share one machine)")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log = logging.getLogger("crocbridge")

    if args.host not in ("127.0.0.1", "localhost"):
        log.warning("=" * 64)
        log.warning("BINDING TO %s EXPOSES CROCBRIDGE BEYOND THIS MACHINE.", args.host)
        log.warning("There is no authentication on the API. Anyone who can reach")
        log.warning("this port can send your files. Use 127.0.0.1 unless you are")
        log.warning("absolutely sure.")
        log.warning("=" * 64)

    config = ConfigManager(args.config)
    if config.recovered_from_corruption:
        log.warning("config file was corrupted; a backup was kept and defaults restored")
    state = AppState()
    receiver = ReceiverDaemon(config, state)
    sender = SendManager(config, state)

    def shutdown(*_):
        log.info("shutting down; stopping croc processes")
        receiver.stop()
        sender.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    atexit.register(receiver.stop)
    atexit.register(sender.stop)

    if config.get("paired"):
        receiver.start()

    app = create_app(config, state, receiver, sender)
    log.info("CrocBridge on http://%s:%d (config: %s)", args.host, args.port, args.config)
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
