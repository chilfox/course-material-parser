"""Load and validate ``settings.toml`` from the skill directory.

The default path is derived from the install location, so the CLIs behave the same from
any working directory. Callers (tests) can inject another path. Every mistake is a
``settings_error`` whose message says what to fix.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from course_material_parser.cli_output import CliError

SKILL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = SKILL_DIR / "settings.toml"

Device = Literal["cpu", "mps", "cuda"]
DEVICES: tuple[str, ...] = get_args(Device)


@dataclass(frozen=True)
class Settings:
    """Settings shared by both CLIs.

    ``library_root`` is an absolute path, with ``~`` expanded, to an existing directory, and
    ``device`` is one of ``DEVICES``. Optional keys take the defaults below when absent.
    """

    library_root: Path
    device: Device
    allow_ocr: bool = True
    combined_read_max_chars: int = 60000


def load_settings(path: Path | None = None) -> Settings:
    """Read and validate the settings file at ``path`` (default: the skill's ``settings.toml``).

    Device availability is not checked here; see ``require_device_available``.

    Raises:
        CliError: ``settings_error`` when the file is missing or not valid TOML, has an
            unknown key, lacks a required key, or has an invalid value.
    """
    path = path or DEFAULT_SETTINGS_PATH
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _error(
            "settings.toml not found: copy settings.example.toml to settings.toml "
            "and set library_root and device"
        ) from None
    except tomllib.TOMLDecodeError as error:
        raise _error(f"settings.toml is not valid TOML: {error}") from None

    unknown = sorted(set(raw) - {"library_root", "device", "allow_ocr", "combined_read_max_chars"})
    if unknown:
        raise _error(f"settings.toml has unknown key(s): {', '.join(unknown)}; remove them")
    missing = [key for key in ("library_root", "device") if key not in raw]
    if missing:
        raise _error(f"settings.toml is missing required key(s): {', '.join(missing)}")

    optional: dict[str, Any] = {}
    if "allow_ocr" in raw:
        optional["allow_ocr"] = _allow_ocr(raw["allow_ocr"])
    if "combined_read_max_chars" in raw:
        optional["combined_read_max_chars"] = _max_chars(raw["combined_read_max_chars"])
    return Settings(
        library_root=_library_root(raw["library_root"]), device=_device(raw["device"]), **optional
    )


def device_available(device: Device) -> bool:
    """Return whether PyTorch can use ``device`` on this machine.

    Imports torch, which takes about half a second, so only ``parse`` calls this: the
    reader never runs a model and must start fast.
    """
    if device == "cpu":
        return True
    import torch

    if device == "mps":
        return torch.backends.mps.is_available()
    return torch.cuda.is_available()


def require_device_available(settings: Settings) -> None:
    """Refuse a configured ``device`` this machine can't use, so it never falls back silently.

    Raises:
        CliError: ``settings_error`` naming the device when it isn't available.
    """
    if not device_available(settings.device):
        raise _error(
            f"settings.toml device {settings.device!r} is not available on this machine; "
            "set device to one that is (cpu always works)"
        )


def _library_root(value: Any) -> Path:
    if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
        raise _error(
            f"settings.toml library_root must be an absolute path (~ allowed), not {value!r}"
        )
    root = Path(value).expanduser()
    if not root.is_dir():
        # Never created here, so a typo can't scatter material somewhere unexpected.
        raise _error(
            f"settings.toml library_root {root} is not an existing directory; "
            "create it or fix the path"
        )
    return root


def _device(value: Any) -> Device:
    if value not in DEVICES:
        raise _error(f"settings.toml device must be one of {', '.join(DEVICES)}, not {value!r}")
    return value


def _allow_ocr(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _error(f"settings.toml allow_ocr must be true or false, not {value!r}")
    return value


def _max_chars(value: Any) -> int:
    # bool is an int subclass in Python, but `true` is not a size.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _error(
            f"settings.toml combined_read_max_chars must be a positive integer, not {value!r}"
        )
    return value


def _error(message: str) -> CliError:
    return CliError("settings_error", message)
