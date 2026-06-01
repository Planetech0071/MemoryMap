"""
MemoryMap — Entry Point
CLI for running the engine, asking queries, and starting the API server.

Usage:
  python main.py --source 0                    # webcam
  python main.py --source /path/to/video.mp4   # video file
  python main.py --query "Where are my keys?"  # one-shot query
  python main.py --api-only                    # API server, no camera
  python main.py --backend claude              # use Claude Vision
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()


def _setup_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level=level,
        colorize=True,
    )
    logger.add(
        "data/logs/memorymap.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )


@click.command()
@click.option("--source",   default="0",    show_default=True, help="Camera device ID or video file path.")
@click.option("--backend",  default=None,                      help="Detection backend: 'yolo' or 'claude'.")
@click.option("--query",    default=None,                      help="Run a one-shot query and exit.")
@click.option("--phone",    is_flag=True,                      help="Accept frames from your phone camera over Wi-Fi.")
@click.option("--api-only", is_flag=True,                      help="Start API server without local camera loop.")
@click.option("--api-port", default=8000,   show_default=True, help="Main API server port.")
@click.option("--verbose",  is_flag=True,                      help="Enable debug logging.")
def main(source, backend, query, phone, api_only, api_port, verbose):
    """MemoryMap — a second brain for physical space."""
    _setup_logging(verbose)

    from core.engine import MemoryMapEngine
    from core.config import PHONE_STREAM_PORT

    engine = MemoryMapEngine(source=source, backend=backend)

    # ── One-shot query mode ────────────────────────────────────────────────
    if query:
        engine.store.start()
        answer = engine.ask(query)
        console.print(f"\n[bold cyan]Q:[/bold cyan] {query}")
        console.print(f"[bold green]A:[/bold green] {answer}\n")
        engine.store.stop()
        return

    # ── Get LAN IP for display ─────────────────────────────────────────────
    lan_ip = _get_lan_ip()

    # ── API-only mode (no local camera) ───────────────────────────────────
    if api_only:
        engine.store.start(phone_stream=phone) if phone else engine.store.start()
        if phone:
            from vision.phone_stream import PhoneStreamServer
            PhoneStreamServer(engine, port=PHONE_STREAM_PORT).run_in_thread()
        _print_startup_banner(lan_ip, api_port, PHONE_STREAM_PORT, phone)
        _start_api(engine, port=api_port)
        return

    # ── Full mode ─────────────────────────────────────────────────────────
    _print_startup_banner(lan_ip, api_port, PHONE_STREAM_PORT, phone)

    engine.start(phone_stream=phone)

    def _shutdown(sig, frame):
        console.print("\n[yellow]Shutting down…[/yellow]")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    import threading
    api_thread = threading.Thread(
        target=_start_api, args=(engine,), kwargs={"port": api_port}, daemon=True
    )
    api_thread.start()

    console.print("\n[dim]Type a query and press Enter, or Ctrl+C to quit.[/dim]\n")
    while True:
        try:
            user_input = input("MemoryMap › ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break
            answer = engine.ask(user_input)
            console.print(f"  [bold green]→[/bold green] {answer}\n")
        except EOFError:
            break

    engine.stop()
    console.print("[green]Goodbye.[/green]")


def _start_api(engine, port: int = 8000) -> None:
    """Start the FastAPI server (blocking)."""
    import uvicorn
    from api.server import create_app

    app = create_app(engine)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def _print_memory_table(engine) -> None:
    """Print the current memory state as a Rich table."""
    records = engine.store.all()
    if not records:
        console.print("[dim]Memory is empty.[/dim]")
        return

    table = Table(title="MemoryMap — Current Memory", show_lines=True)
    table.add_column("Label",    style="cyan")
    table.add_column("Zone",     style="yellow")
    table.add_column("Conf",     justify="right")
    table.add_column("Last Seen")
    table.add_column("Obs", justify="right")
    table.add_column("Stale")

    for r in sorted(records, key=lambda x: x.last_seen, reverse=True):
        stale_str = "[red]✗[/red]" if r.is_stale else "[green]✓[/green]"
        table.add_row(
            r.label,
            r.location.zone,
            f"{r.confidence:.2f}",
            r.last_seen.strftime("%H:%M:%S"),
            str(r.observation_count),
            stale_str,
        )

    console.print(table)


if __name__ == "__main__":
    # Add project root to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()