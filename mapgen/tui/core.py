"""UI-free form model shared by the terminal and desktop frontends.

A :class:`MapForm` captures exactly what the interactive user can choose and
turns it into a valid ``mapgen make ...`` argument list via :func:`to_argv`.
Keeping this logic free of any widget code means the command preview, the
Textual TUI, and the desktop wrapper all agree on one behaviour (and the
previewed command is always copy-pasteable).

Region coordinates follow the PHP ``mapform`` convention: ``startx``/
``starty`` are entered in **kilometres** on the TWD grid with **TWD67** as the
default datum (a ``TWD97`` toggle switches them, mirroring the ``97datum``
checkbox). Values are scaled to metres internally when producing the CLI
``--region`` argument.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config import PAPER_TYPES, TAIWAN_BOUNDS, list_sources

ALL_DIMS = sorted(PAPER_TYPES["A4"]["dimensions"])
EXTRA_DIMS = ["4x6", "3x4", "2x3"]
ALL_DATUMS = ("TWD97", "TWD67")
DEFAULT_TITLE = "我的地圖"
DEFAULT_OUTDIR_TMPL = "out/YYMMDDHHMMSS_%title%"

# Captured once per process so the auto output dir stays stable while the
# user edits the form (the title-derived part still updates live).
_SESSION_TS = time.strftime("%Y%m%d%H%M%S")


def _slug(title: str) -> str:
    """Filesystem-safe form of ``title`` (keeps CJK, replaces separators)."""
    import re

    t = re.sub(r'[/\\:*?"<>|\r\n\t]+', "_", title)
    t = re.sub(r"\s+", "_", t)
    t = t.strip(" _.")
    return t or "map"


def default_output_dir(title: str, timestamp: str | None = None) -> str:
    """Default output directory: ``out/YYMMDDHHMMSS_<title-slug>``."""
    stamp = timestamp if timestamp is not None else _SESSION_TS
    return f"out/{stamp}_{_slug(title)}"


@dataclass
class MapForm:
    """One interactive map-generation request.

    Required inputs are the four region numbers: ``startx``/``starty`` in
    **kilometres** on the TWD grid, ``shiftx``/``shifty`` in whole whole-km
    units, and a datum (``TWD67`` default, PHP-style). Everything else is
    optional or a selection, mirroring the ``mapgen make`` flags.

    ``dims`` holds *additional* page dimensions selected in the UI; ``5x7``
    (the PHP default) is always included first.
    """

    startx: float = 236
    starty: float = 2578
    shiftx: int = 3
    shifty: int = 3
    datum: str = "TWD67"
    penghu: bool = False
    map_type: str = "2016"
    title: str = DEFAULT_TITLE
    output: str = ""
    gpx: str = ""
    label_trk: int = 0
    label_wpt: int = 0
    keep_color: bool = False
    grid_100m: bool = False
    include_tracks: bool = False
    a3: bool = False
    dims: list[str] = field(default_factory=list)
    font_path: str = ""

    @property
    def region(self) -> str:
        """The ``--region`` value in metres: ``x0,y0,shiftx,shifty[,datum]``."""
        x0 = int(round(self.startx * 1000))
        y0 = int(round(self.starty * 1000))
        base = f"{x0},{y0},{self.shiftx},{self.shifty}"
        if self.datum != "TWD97":
            base += f",{self.datum}"
        return base


class ValidationError(ValueError):
    """Raised when a :class:`MapForm` fails :meth:`MapForm.validate`."""


def validate(form: MapForm) -> list[str]:
    """Return a list of problems with ``form`` (empty when it is runnable).

    Number choices come from the same registries the CLI uses, so
    ``mapgen make`` will accept exactly what validation passes.
    """
    problems: list[str] = []
    if not isinstance(form.startx, (int, float)) or isinstance(form.startx, bool):
        problems.append("startx must be a number in km (e.g. 246)")
    if not isinstance(form.starty, (int, float)) or isinstance(form.starty, bool):
        problems.append("starty must be a number in km (e.g. 2578)")
    if isinstance(form.shiftx, bool) or not isinstance(form.shiftx, int) or form.shiftx < 1:
        problems.append("shiftx must be a whole km >= 1")
    if isinstance(form.shifty, bool) or not isinstance(form.shifty, int) or form.shifty < 1:
        problems.append("shifty must be a whole km >= 1")
    if form.shiftx > 50 or form.shifty > 50:
        problems.append("shiftx/shifty look too large (max ~50 km grid)")
    if form.datum not in ALL_DATUMS:
        problems.append(f"datum must be one of {', '.join(ALL_DATUMS)}")
    if form.map_type not in {k for k, _ in list_sources()}:
        known = ", ".join(k for k, _ in list_sources())
        problems.append(f"map source must be one of {known}")
    for dim in form.dims:
        if dim not in ALL_DIMS:
            problems.append(f"unknown dimension {dim!r} (use {', '.join(ALL_DIMS)})")
    if form.gpx:
        path = Path(form.gpx)
        if not path.exists():
            problems.append(f"GPX file does not exist: {form.gpx}")
    return problems


def hints(form: MapForm) -> list[str]:
    """Advisory, non-blocking notes about ``form`` (shown but never disables Run).

    Currently the TWD bounding-box ranges: a region slightly outside the box is
    still runnable (edge tiles), so it is reported as a note rather than an
    error.
    """
    notes: list[str] = []
    for name, value in (("startx", form.startx), ("starty", form.starty)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        bounds = TAIWAN_BOUNDS["penghu" if form.penghu else "taiwan"]
        isx = name == "startx"
        lo, hi = (bounds["x"] if isx else bounds["y"])
        if not lo <= value <= hi:
            notes.append(f"{name}={value} outside {name} range {lo}-{hi} (hint)")
    return notes


def to_argv(form: MapForm, output_dir: str | None = None) -> list[str]:
    """Build the exact ``mapgen make ...`` argv for ``form``.

    The result round-trips through the real CLI parser, so the previewed
    command in the TUI is guaranteed to be what runs. ``output_dir`` pins the
    output directory (used by the UI to show the live-resolved auto dir);
    otherwise ``form.output`` wins, falling back to the timestamped default.
    """
    output = output_dir or form.output or default_output_dir(form.title)
    argv = [
        "mapgen",
        "make",
        "--region",
        form.region,
        "--output",
        output,
        "--map-type",
        form.map_type,
        "--title",
        form.title,
    ]
    if form.keep_color:
        argv.append("--keep-color")
    if form.penghu:
        argv.extend(["--penghu", "1"])
    if form.gpx:
        argv.extend(["--gpx", f"{form.gpx}:{form.label_trk}:{form.label_wpt}"])
    if form.grid_100m:
        argv.append("--grid-100m")
    if form.include_tracks:
        argv.append("--include-tracks")
    if form.a3:
        argv.append("--a3")
    if form.font_path:
        argv.extend(["--font-path", form.font_path])
    for dim in ["5x7", *form.dims]:
        argv.extend(["--dims", dim])
    return argv


def command_line(form: MapForm, output_dir: str | None = None) -> str:
    """The ``mapgen make ...`` command as a single shell line for preview/copy."""
    import shlex

    return " ".join(shlex.quote(a) for a in to_argv(form, output_dir=output_dir))


def with_overrides(form: MapForm, **kwargs) -> MapForm:
    """Return a copy of ``form`` with the given dataclass fields replaced."""
    return replace(form, **kwargs)


def parse_cli_args(argv: list[str]) -> tuple[MapForm, list[str]]:
    """Turn ``mapgen make ...``-style args into a prefilled :class:`MapForm`.

    Flags the caller actually supplied override the UI defaults; everything
    else keeps its built-in default. Returns ``(form, errors)`` — a non-empty
    ``errors`` list means the UI should refuse to start (e.g. unknown flag or
    a malformed ``--region``).
    """
    import argparse

    from ..cli import _add_make_args, _parse_region

    argv = list(argv)
    if argv and argv[0] in ("make", "legacy"):
        argv = argv[1:]

    parser = argparse.ArgumentParser(
        prog="mapgen-tui",
        description=(
            "Launch the interactive map generator. Any 'mapgen make' flag may "
            "be given to prefill the form; everything else keeps its default."
        ),
    )
    _add_make_args(parser, legacy=False)
    base = parser.parse_args([])
    args, unknown = parser.parse_known_args(argv)

    errors: list[str] = [f"unknown option: {tok}" for tok in unknown]
    form = MapForm()

    if args.region is not None:
        try:
            region = _parse_region(args.region)
            form.startx = region["x0"] / 1000.0
            form.starty = region["y0"] / 1000.0
            form.shiftx = region["shiftx"]
            form.shifty = region["shifty"]
            form.datum = region["datum"]
        except SystemExit:
            errors.append(f"invalid --region {args.region!r}")

    def _changed(name: str) -> bool:
        return getattr(args, name) != getattr(base, name)

    if _changed("map_type"):
        form.map_type = args.map_type
    if _changed("title"):
        form.title = args.title
    if _changed("output"):
        form.output = args.output
    if _changed("gpx"):
        try:
            path, trk, wpt = _split_gpx(args.gpx)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            form.gpx, form.label_trk, form.label_wpt = path, trk, wpt
    if _changed("keep_color"):
        form.keep_color = args.keep_color
    if _changed("grid_100m"):
        form.grid_100m = args.grid_100m
    if _changed("include_tracks"):
        form.include_tracks = args.include_tracks
    if _changed("a3"):
        form.a3 = args.a3
    if args.penghu == 1:
        form.penghu = True
    if _changed("dims") and args.dims:
        form.dims = list(args.dims)
    if _changed("font_path"):
        form.font_path = args.font_path or ""
    return form, errors


def _split_gpx(spec: str) -> tuple[str, int, int]:
    parts = spec.split(":")
    path = parts[0]
    trk = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    wpt = int(parts[2]) if len(parts) > 2 and parts[2] else 0
    if not path:
        raise ValueError("empty GPX path")
    return path, trk, wpt
