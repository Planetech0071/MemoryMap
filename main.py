"""
MemoryMap — Simple Question Interface
Just ask questions about objects you've seen.
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import cv2
from loguru import logger
from rich.console import Console

console = Console()


def _get_lan_ip() -> str:
    """Get the local network IP address."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _print_qr_code(url: str) -> None:
    """Generate and display a QR code for easy phone access."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        console.print("\n[cyan]Scan this QR code with your phone:[/cyan]\n")
        qr.print_ascii()
    except ImportError:
        pass
    console.print(f"[cyan]Or visit: {url}[/cyan]\n")


def _setup_logging() -> None:
    logger.remove()
    logger.add(
        "data/logs/memorymap.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )


def main():
    """MemoryMap — Ask questions about your physical space."""
    _setup_logging()

    from core.engine import MemoryMapEngine

    console.print("\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]   MemoryMap — Ask About Your Space[/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    console.print("[cyan]How do you want to add images?[/cyan]")
    console.print("  1) Use your webcam (default)")
    console.print("  2) Stream from your phone camera\n")

    choice = input("Choose [1 or 2]: ").strip()

    engine = MemoryMapEngine(source=0, backend=None)
    engine.store.start()

    if choice == "2":
        # Start iPhone Shortcuts interface
        lan_ip = _get_lan_ip()
        lan_url = f"http://{lan_ip}:8000/phone-stream"
        
        console.print("\n[yellow]📱 iPhone Shortcuts Setup[/yellow]")
        console.print("[dim]Starting API server…[/dim]\n")
        
        console.print("[cyan]Step 1: On your iPhone, open the Shortcuts app[/cyan]")
        console.print(f"[cyan]Step 2: Visit this page for instructions:[/cyan]")
        console.print(f"  [cyan]{lan_url}[/cyan]\n")
        
        _print_qr_code(lan_url)
        
        console.print("[green]Your Computer IP (use in Shortcut):[/green]")
        console.print(f"  [yellow]{lan_ip}:8000[/yellow]\n")
        
        console.print("[cyan]The Shortcut will send photos to:[/cyan]")
        console.print(f"  [green]http://{lan_ip}:8000/observe[/green]\n")
        
        # Start API server in background
        import threading
        import uvicorn
        from api.server import create_app
        
        app = create_app(engine)
        api_thread = threading.Thread(
            target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000, log_level="critical"),
            daemon=True
        )
        api_thread.start()
        
    else:
        console.print("\n[cyan]📷 Webcam mode[/cyan]\n")

    console.print("[green]Examples:[/green]")
    console.print("  • Where are my keys?")
    console.print("  • What's on my desk?")
    console.print("  • What can you see right now?")
    console.print("  • When did I last see my wallet?\n")

    console.print("[yellow]Type 'quit' or 'exit' to stop[/yellow]\n")

    def _shutdown(sig, frame):
        console.print("\n[yellow]Shutting down…[/yellow]")
        engine.store.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        try:
            user_input = input("[bold cyan]❓ Ask:[/bold cyan] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[green]Goodbye![/green]")
                break

            answer = engine.ask(user_input)
            console.print(f"[bold green]✓ Answer:[/bold green] {answer}\n")

        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down…[/yellow]")
            break
        except Exception as e:
            logger.error("Error: {}", e)
            console.print(f"[red]Error:[/red] {e}\n")

    engine.store.stop()


if __name__ == "__main__":
    # Add project root to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()