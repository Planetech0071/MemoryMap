"""
MemoryMap — Simple Question Interface
Ask questions about objects you've seen — by typing or talking.
"""

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

from loguru import logger
from rich.console import Console

console = Console()


# ── TTS / STT helpers ─────────────────────────────────────────────────────

import queue as _queue

# pyttsx3 must live on one persistent thread — calling runAndWait() from
# different threads (or repeatedly from the main thread) corrupts its
# internal event loop after the 2nd/3rd call on macOS and some Linux setups.
#
# _tts_queue carries (text, done_event) pairs.
# _speak() puts a message on the queue and optionally blocks until it finishes,
# so the microphone never opens while the speaker is still talking.
_tts_queue: "_queue.Queue[tuple[str, threading.Event] | None]" = _queue.Queue()
_tts_available = False


def _init_tts() -> bool:
    """
    Spin up a dedicated TTS worker thread.
    Returns True if pyttsx3 is available, False otherwise.
    """
    global _tts_available
    try:
        import pyttsx3
    except ImportError:
        logger.warning("pyttsx3 not installed — TTS disabled. Run: pip install pyttsx3")
        return False

    def _worker():
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 1.0)
            while True:
                item = _tts_queue.get()
                if item is None:          # None = shutdown signal
                    break
                text, done_event = item
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as e:
                    logger.warning("TTS speak error: {}", e)
                finally:
                    done_event.set()      # unblock _speak() caller
        except Exception as e:
            logger.warning("TTS worker failed to start: {}", e)

    t = threading.Thread(target=_worker, daemon=True, name="tts-worker")
    t.start()
    _tts_available = True
    return True


def _speak(text: str, wait: bool = False) -> None:
    """
    Queue text for speaking.
    If wait=True, blocks until the utterance finishes — use this before
    opening the microphone so TTS audio doesn't bleed into the recording.
    """
    if not _tts_available:
        return
    done = threading.Event()
    _tts_queue.put((text, done))
    if wait:
        done.wait()


def _listen() -> str | None:
    """
    Record a single voice command from the microphone.
    Uses SpeechRecognition + Google Web Speech (free, no key).
    Returns the recognised text, or None on failure/silence.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        console.print("[red]speech_recognition not installed.[/red] "
                      "Run: pip install SpeechRecognition sounddevice")
        return None

    r = sr.Recognizer()
    r.pause_threshold = 1.0   # seconds of silence before stopping

    try:
        with sr.Microphone() as source:
            console.print("[dim]🎙  Listening… (speak now)[/dim]")
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=8, phrase_time_limit=15)

        console.print("[dim]🔄  Recognising…[/dim]")
        text = r.recognize_google(audio)
        return text

    except sr.WaitTimeoutError:
        console.print("[yellow]No speech detected.[/yellow]")
        return None
    except sr.UnknownValueError:
        console.print("[yellow]Could not understand audio.[/yellow]")
        return None
    except sr.RequestError as e:
        console.print(f"[red]Speech recognition error:[/red] {e}")
        return None
    except Exception as e:
        console.print(f"[red]Microphone error:[/red] {e}")
        return None


# ── Network helpers ────────────────────────────────────────────────────────

def _get_lan_ip() -> str:
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
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data("http://############:8000/phone-stream")
        qr.make(fit=True)
        console.print("\n[cyan]Scan this QR code with your phone:[/cyan]\n")
        qr.print_ascii()
    except ImportError:
        pass
    console.print(f"[cyan]Or visit: http://############:8000/phone-stream [/cyan]\n")


def _setup_logging() -> None:
    logger.remove()
    logger.add(
        "data/logs/memorymap.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )


# ── Detection callback (feature 1) ────────────────────────────────────────

def _make_observe_callback(engine):
    """
    Returns a callback that prints a console summary whenever new objects
    are detected via a submitted frame.  Attached to the API server so it
    fires on every /observe call that finds something.
    """
    def on_detections(labels: list[str], total: int) -> None:
        if not labels:
            return
        label_str = ", ".join(f"[cyan]{l}[/cyan]" for l in labels)
        console.print(
            f"[bold green]📸 Detected:[/bold green] {label_str}  "
            f"[dim](memory: {total} objects)[/dim]"
        )
    return on_detections


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    """MemoryMap — Ask questions about your physical space."""
    _setup_logging()

    from core.engine import MemoryMapEngine

    console.print("\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
    console.print("[bold cyan]   MemoryMap — Ask About Your Space[/bold cyan]")
    console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    # ── Input mode ────────────────────────────────────────────────────────
    console.print("[cyan]How do you want to add images?[/cyan]")
    console.print("  1) Use your webcam (default)")
    console.print("  2) Stream from your phone camera\n")
    cam_choice = input("Choose [1 or 2]: ").strip()

    # ── Voice mode ────────────────────────────────────────────────────────
    console.print("\n[cyan]How do you want to ask questions?[/cyan]")
    console.print("  1) Type  (default)")
    console.print("  2) Voice  (microphone + speaker)\n")
    voice_choice = input("Choose [1 or 2]: ").strip()
    voice_mode = voice_choice == "2"

    # Initialise TTS now so the user gets a warning early if it's missing
    tts_ok = _init_tts() if voice_mode else False
    if voice_mode and not tts_ok:
        console.print("[yellow]⚠  TTS unavailable — answers will be text only.[/yellow]")

    # ── Engine setup ──────────────────────────────────────────────────────
    if cam_choice == "2":
        engine = MemoryMapEngine(source=None, backend=None)
        engine.store.start()

        lan_ip = _get_lan_ip()
        lan_url = f"http://{lan_ip}:8000/phone-stream"

        console.print("\n[yellow]📱 iPhone Shortcuts Setup[/yellow]")
        console.print("[dim]Starting API server…[/dim]\n")

        import uvicorn
        from api.server import create_app

        observe_cb = _make_observe_callback(engine)
        app = create_app(engine, server_ip=lan_ip, on_detections=observe_cb)

        api_thread = threading.Thread(
            target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000, log_level="critical"),
            daemon=True,
        )
        api_thread.start()

        console.print(f"[cyan]Step 1: On your iPhone, open the Shortcuts app[/cyan]")
        console.print(f"[cyan]Step 2: Visit this page for setup instructions:[/cyan]")
        console.print(f"  [cyan]############[/cyan]\n")
        _print_qr_code(lan_url)
        console.print("[green]Your Computer IP:[/green]")
        console.print(f"  [yellow]############:8000[/yellow]\n")

    else:
        engine = MemoryMapEngine(source=0, backend=None)
        engine.start()
        console.print("\n[cyan]📷 Webcam mode — detecting objects…[/cyan]\n")

    # ── Help text ─────────────────────────────────────────────────────────
    console.print("[green]Commands:[/green]")
    console.print("  • Where are my keys?")
    console.print("  • What's on my desk?")
    console.print("  • What can you see right now?")
    console.print("  • [bold]clear[/bold]         — wipe all memory")
    if voice_mode:
        console.print("  • [bold]voice[/bold] / press Enter — speak a question")
    console.print("  • [bold]quit[/bold] / [bold]exit[/bold]    — stop\n")

    # ── Shutdown handler ─────────────────────────────────────────────────
    def _shutdown(sig, frame):
        console.print("\n[yellow]Shutting down…[/yellow]")
        engine.store.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Main loop ─────────────────────────────────────────────────────────
    prompt = "🎙  Press Enter to speak" if voice_mode else "[bold cyan]❓ Ask:[/bold cyan] "

    while True:
        try:
            user_input = input(f"{prompt} ").strip()

            # ── Exit ──────────────────────────────────────────────────────
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[green]Goodbye![/green]")
                _speak("Goodbye!")
                break

            # ── Clear memory ──────────────────────────────────────────────
            if user_input.lower() == "clear":
                engine.store.clear()
                msg = "Memory cleared."
                console.print(f"[bold yellow]🗑  {msg}[/bold yellow]\n")
                _speak(msg)
                continue

            # ── Voice input ───────────────────────────────────────────────
            if voice_mode and user_input == "":
                spoken = _listen()
                if not spoken:
                    continue
                console.print(f"[dim]You said:[/dim] {spoken}")
                user_input = spoken

            if not user_input:
                continue

            # ── Ask the engine ────────────────────────────────────────────
            answer = engine.ask(user_input)
            console.print(f"[bold green]✓ Answer:[/bold green] {answer}\n")
            # wait=True so mic doesn't open while speaker is still talking
            _speak(answer, wait=voice_mode)

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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()