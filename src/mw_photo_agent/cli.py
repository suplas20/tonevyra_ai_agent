"""CLI entry point for the local photo correction agent."""

from pathlib import Path

import typer

from mw_photo_agent.agent.runner import ensure_runtime_dirs
from mw_photo_agent.core.config import Settings, get_settings

app = typer.Typer(no_args_is_help=True, help="Local MW photo correction agent.")


@app.command()
def init() -> None:
    """Create required local runtime directories."""
    settings = get_settings()
    ensure_runtime_dirs(settings)
    typer.echo("Initialized local runtime folders.")


@app.command()
def doctor() -> None:
    """Check basic local configuration."""
    settings = get_settings()
    ensure_runtime_dirs(settings)
    typer.echo(f"Runtime directory: {settings.runtime_dir}")
    typer.echo(f"Vision backend: {settings.vision_backend}")
    typer.echo("Database check: pending")
    typer.echo("Lightroom bridge check: pending")


@app.command()
def start(once: bool = typer.Option(False, "--once", help="Run one agent pass for harness/test use.")) -> None:
    """Start the MVP agent loop."""
    mode = "one pass" if once else "continuous"
    typer.echo(f"Agent start is not implemented yet: {mode}.")


@app.command()
def status() -> None:
    """Show current task status summary."""
    typer.echo("Status is not implemented yet.")


@app.command()
def scan(
    path: Path | None = None,
    once: bool = typer.Option(False, "--once", help="Accepted for harness compatibility; scan is one-shot."),
) -> None:
    """Scan input folder for supported photos."""
    settings = get_settings()
    scan_path = path or settings.input_dir
    typer.echo(f"Scan is not implemented yet: {scan_path}")


@app.command()
def retry(task_id: str) -> None:
    """Retry a failed or reviewed task explicitly."""
    typer.echo(f"Retry is not implemented yet: {task_id}")


@app.command("test-lightroom")
def test_lightroom() -> None:
    """Test the Lightroom JSON bridge."""
    typer.echo("Lightroom bridge test is not implemented yet.")


@app.command("test-vision")
def test_vision() -> None:
    """Test the configured vision backend."""
    typer.echo("Vision backend test is not implemented yet.")


def get_app_settings() -> Settings:
    return get_settings()
