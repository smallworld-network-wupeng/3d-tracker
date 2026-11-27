"""Photo selection, EXIF metadata and shared preview/export image preparation."""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo


PHOTO_LIST = "photo_events.json"
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
DEFAULT_PHOTO_SECONDS = 5.0
PHOTO_READ_ERRORS = (OSError, ValueError, RuntimeError, OverflowError, SyntaxError, EOFError)


def activity_wall_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return parsed


def photo_time(value: str) -> datetime:
    value = value.strip()
    if len(value) < 19 or value[10] not in ("T", " "):
        raise ValueError("Use YYYY-MM-DD HH:MM:SS for the photo time.")
    return activity_wall_time(value)


@dataclass(frozen=True)
class PhotoEvent:
    file: str
    enabled: bool = False
    capture_time: str | None = None  # None follows the source EXIF.
    duration: float = DEFAULT_PHOTO_SECONDS
    framing: str = "fit"
    placement: str = "timeline"  # Saved "end" means immediately after the last selected video.

    def validate(self) -> None:
        if (
            not isinstance(self.file, str) or Path(self.file).name != self.file
            or "\\" in self.file or "\0" in self.file
            or Path(self.file).suffix.lower() not in PHOTO_SUFFIXES
        ):
            raise ValueError("Invalid photo filename.")
        if type(self.enabled) is not bool:
            raise ValueError("Invalid photo selection.")
        if not isinstance(self.duration, (int, float)) or isinstance(self.duration, bool):
            raise ValueError("Invalid photo duration.")
        if not 0.1 <= self.duration <= 3600:
            raise ValueError("Photo duration must be between 0.1 and 3600 seconds.")
        if self.framing not in ("fit", "fill"):
            raise ValueError("Invalid photo framing.")
        if self.placement not in ("timeline", "end"):
            raise ValueError("Invalid photo placement.")
        if self.capture_time is not None:
            if not isinstance(self.capture_time, str):
                raise ValueError("Invalid photo capture time.")
            photo_time(self.capture_time)


def list_photo_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir()
         if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in PHOTO_SUFFIXES),
        key=lambda path: (path.name.casefold(), path.name),
    )


def read_photo_events(path: Path) -> list[PhotoEvent]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("photos"), list):
        raise ValueError("Invalid photo list format.")
    events = []
    names = set()
    for entry in data["photos"]:
        try:
            event = PhotoEvent(**entry)
        except TypeError as exc:
            raise ValueError("Invalid photo list entry.") from exc
        event.validate()
        if event.file in names:
            raise ValueError(f"Duplicate photo: {event.file}")
        names.add(event.file)
        events.append(event)
    return events


def write_photo_events(path: Path, events: list[PhotoEvent]) -> None:
    for event in events:
        event.validate()
    payload = json.dumps({"schema_version": 1, "photos": [asdict(event) for event in events]},
                         ensure_ascii=False, indent=2)
    with NamedTemporaryFile(dir=path.parent, prefix=".photos-", delete=False, mode="w",
                            encoding="utf-8") as temporary:
        staged = Path(temporary.name)
        try:
            temporary.write(payload + "\n")
            temporary.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise RuntimeError("HEIC/HEIF requires pillow-heif.") from exc
    register_heif_opener(thumbnails=False)


def open_photo(path: Path):
    from PIL import Image

    if path.suffix.lower() in (".heic", ".heif"):
        register_heif()
    try:
        return Image.open(path)
    except Image.DecompressionBombError as exc:
        raise ValueError(f"Image is too large: {path.name}") from exc


def read_capture_time(path: Path) -> datetime | None:
    with open_photo(path) as source:
        exif = source.getexif()
        details = exif.get_ifd(34665)  # Exif IFD
        stamp = details.get(36867, exif.get(36867))  # DateTimeOriginal
        offset = details.get(36881, exif.get(36881))  # OffsetTimeOriginal
        subseconds = details.get(37521, exif.get(37521))  # SubSecTimeOriginal
    if not isinstance(stamp, str):
        return None
    try:
        value = datetime.strptime(stamp.strip("\0 "), "%Y:%m:%d %H:%M:%S").isoformat()
        if isinstance(subseconds, str) and subseconds.strip("\0 ").isascii():
            fraction = subseconds.strip("\0 ")
            if fraction.isdecimal():
                value += f".{fraction[:6]}"
        if isinstance(offset, str):
            try:
                return activity_wall_time(value + offset.strip("\0 "))
            except ValueError:
                pass
        return activity_wall_time(value)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def display_p3_to_srgb():
    from PIL.ImageFilter import Color3DLUT

    # Linear P3 -> XYZ D65 -> linear sRGB (W3C CSS Color 4, section 18).
    def linear(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def encoded(value):
        value = max(0.0, min(1.0, value))
        return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055

    def convert(red, green, blue):
        r, g, b = map(linear, (red, green, blue))
        return tuple(map(encoded, (
            1.22494 * r - 0.22494 * g,
            -0.04206 * r + 1.04206 * g,
            -0.01964 * r - 0.07864 * g + 1.09828 * b,
        )))

    return Color3DLUT.generate(33, convert)


def load_photo_image(path: Path, max_edge: int):
    """Decode to oriented, display-ready RGB with black under transparent pixels."""
    from PIL import Image, ImageCms, ImageOps

    with open_photo(path) as source:
        source.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        oriented = ImageOps.exif_transpose(source)
        alpha = oriented.convert("RGBA").getchannel("A")
        rgb = oriented.convert("RGB")
        profile = oriented.info.get("icc_profile")
        nclx = oriented.info.get("nclx_profile", {})
        if profile:
            color = oriented if oriented.mode in ("CMYK", "L", "RGB") else rgb
            try:
                rgb = ImageCms.profileToProfile(color, io.BytesIO(profile),
                                                ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (ImageCms.PyCMSError, OSError, ValueError):
                pass
        elif nclx.get("color_primaries") == 12 and nclx.get("transfer_characteristics") == 13:
            rgb = rgb.filter(display_p3_to_srgb())
        background = Image.new("RGB", oriented.size)
        background.paste(rgb, mask=alpha)
        return background


def frame_photo(image, size: tuple[int, int], framing: str):
    from PIL import Image, ImageFilter, ImageOps

    fill = ImageOps.fit(image, size, Image.Resampling.LANCZOS)
    if framing == "fill":
        return fill
    foreground = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    backdrop = fill.filter(ImageFilter.GaussianBlur(max(size) / 28))
    backdrop.paste(foreground, ((size[0] - foreground.width) // 2, (size[1] - foreground.height) // 2))
    return backdrop
