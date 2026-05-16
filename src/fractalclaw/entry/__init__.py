"""FractalClaw Entry Module - Application entry points."""

__version__ = "0.1.0"


def __getattr__(name):
    if name == "FractalClawApp":
        from .main import FractalClawApp
        return FractalClawApp
    if name == "app":
        from .cli import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FractalClawApp", "app"]
