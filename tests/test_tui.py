"""Tests for the interactive TUI form model and the Textual app."""

from __future__ import annotations

import pytest

from mapgen.cli import _parse_region, build_parser
from mapgen.tui.core import (
    MapForm,
    command_line,
    default_output_dir,
    hints,
    parse_cli_args,
    to_argv,
    validate,
)


def test_region_string_default_datum_twd67():
    form = MapForm()  # km + TWD67 by default (PHP-style)
    assert form.region == "236000,2578000,3,3,TWD67"


def test_region_string_twd97_omits_datum():
    form = MapForm(datum="TWD97")
    assert form.region == "236000,2578000,3,3"


def test_region_scales_km_to_metres():
    form = MapForm(startx=246, starty=2514, shiftx=6, shifty=4, datum="TWD67")
    assert form.region == "246000,2514000,6,4,TWD67"


def test_default_output_dir_uses_timestamp_and_slug():
    assert default_output_dir("隨便/一個 地圖", timestamp="260908141530") == (
        "out/260908141530_隨便_一個_地圖"
    )
    assert default_output_dir("", timestamp="260908141530") == "out/260908141530_map"


def test_to_argv_defaults_and_always_includes_5x7():
    form = MapForm(dims=["4x6", "3x4"])
    argv = to_argv(form, output_dir="out/260908141530_demo")
    assert "--region" in argv
    assert argv[argv.index("--region") + 1] == form.region
    assert argv[argv.index("--output") + 1] == "out/260908141530_demo"
    assert argv[argv.index("--map-type") + 1] == "2016"
    dims = [argv[i + 1] for i, a in enumerate(argv) if a == "--dims"]
    assert dims == ["5x7", "4x6", "3x4"]


def test_to_argv_uses_form_output_when_set():
    form = MapForm(output="out/custom/")
    assert to_argv(form)[to_argv(form).index("--output") + 1] == "out/custom/"


def test_to_argv_round_trips_through_cli_parser():
    form = MapForm(
        startx=236,
        starty=2578,
        shiftx=12,
        shifty=6,
        datum="TWD67",
        penghu=True,
        map_type="3",
        title="測試",
        output="./out/x/",
        grid_100m=True,
        a3=True,
        keep_color=True,
        dims=["4x6", "3x4"],
    )
    argv = to_argv(form, output_dir=form.output)
    assert argv[0] == "mapgen"
    assert "make" in argv

    parsed = build_parser().parse_args(argv[1:])
    region = _parse_region(parsed.region)
    assert region == {
        "x0": 236000.0,
        "y0": 2578000.0,
        "shiftx": 12,
        "shifty": 6,
        "datum": "TWD67",
    }
    assert parsed.map_type == "3"
    assert parsed.title == "測試"
    assert parsed.output == "./out/x/"
    assert parsed.penghu == 1
    assert parsed.grid_100m is True
    assert parsed.a3 is True
    assert parsed.keep_color is True
    assert parsed.dims == ["5x7", "4x6", "3x4"]


def test_command_line_is_shell_quoted():
    form = MapForm(title="我的地圖")
    line = command_line(form, output_dir="out/auto")
    assert "'我的地圖'" in line
    assert "mapgen make --region" in line


def test_validate_accepts_valid_form():
    form = MapForm(startx=236, starty=2578, shiftx=3, shifty=3)
    assert validate(form) == []


def test_validate_flags_shift_errors():
    form = MapForm(startx=236, starty=2578, shiftx=0, shifty=-2)
    problems = validate(form)
    assert any("shiftx" in p for p in problems)
    assert any("shifty" in p for p in problems)


def test_validate_flags_bad_source_and_datum():
    form = MapForm(map_type="nope", datum="WGS84")
    problems = validate(form)
    assert any("map source" in p for p in problems)
    assert any("datum" in p for p in problems)


def test_validate_bounds_are_nonblocking_hints():
    # Out-of-box coords stay runnable (edge tiles) — reported by hints(),
    # not by validate().
    form = MapForm(startx=5000, starty=0)
    assert validate(form) == []
    notes = hints(form)
    assert any("startx" in n for n in notes)
    assert any("starty" in n for n in notes)


def test_hints_penghu():
    notes = hints(MapForm(startx=150, starty=2680, penghu=True))
    assert any("startx" in n for n in notes)
    assert any("starty" in n for n in notes)


def test_hints_empty_in_bounds():
    assert hints(MapForm(startx=236, starty=2578)) == []


def test_validate_missing_gpx():
    form = MapForm(gpx="/definitely/not/a/file.gpx")
    assert any("GPX" in p for p in validate(form))


# --- parse_cli_args (prefill from the command line) ---


def test_parse_cli_args_no_args_gives_defaults():
    form, errors = parse_cli_args([])
    assert errors == []
    assert form == MapForm()


def test_parse_cli_args_region_legacy_km():
    form, errors = parse_cli_args(["--region", "236:2578:6:4:TWD67"])
    assert errors == []
    assert form.startx == 236
    assert form.starty == 2578
    assert form.shiftx == 6
    assert form.shifty == 4
    assert form.datum == "TWD67"


def test_parse_cli_args_region_modern_metres():
    form, errors = parse_cli_args(["-r", "236000,2578000,6,4,TWD97"])
    assert errors == []
    assert form.startx == 236
    assert form.starty == 2578
    assert form.datum == "TWD97"


def test_parse_cli_args_region_invalid():
    form, errors = parse_cli_args(["--region", "oops"])
    # Tolerates the fallback parse; the app refuses to start on errors.
    assert errors  # non-empty -> refuses to start


def test_parse_cli_args_tolerates_make_subcommand():
    form, errors = parse_cli_args(["make", "-v", "3"])
    assert errors == []
    assert form.map_type == "3"


def test_parse_cli_args_flags():
    form, errors = parse_cli_args(
        ["-v", "1904", "-t", "合歡山", "-O", "out/demo/", "-c", "-e", "-G", "-3", "-p", "1"]
    )
    assert errors == []
    assert form.map_type == "1904"
    assert form.title == "合歡山"
    assert form.output == "out/demo/"
    assert form.keep_color is True
    assert form.grid_100m is True
    assert form.include_tracks is True
    assert form.a3 is True
    assert form.penghu is True


def test_parse_cli_args_dims_not_passed_stay_empty():
    form, errors = parse_cli_args(["-D", "4x6", "-D", "3x4"])
    assert errors == []
    assert form.dims == ["4x6", "3x4"]


def test_parse_cli_args_unknown_flag():
    form, errors = parse_cli_args(["--bogus"])
    assert errors
    assert "--bogus" in errors[0]


def test_parse_cli_args_font_path_accepted():
    form, errors = parse_cli_args(["--font-path", "/custom/wqy.ttc"])
    assert not errors
    assert form.font_path == "/custom/wqy.ttc"


# --- Textual app behavior ---


@pytest.mark.asyncio
async def test_app_preview_tracks_inputs():
    from textual.widgets import Button, Checkbox, Input, Select, Static

    from mapgen.tui.app import MapGenApp

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        await pilot.pause()
        app = pilot.app
        preview = app.query_one("#preview", Static)
        assert "mapgen make" in str(preview.content)
        # Default region is km 236,2578 -> metres with TWD67
        assert "236000,2578000,3,3,TWD67" in str(preview.content)

        app.query_one("#startx", Input).value = "200"
        await pilot.pause()
        assert "200000" in str(app.query_one("#preview", Static).content)

        # Out-of-bounds coords are a hint, not a blocker: Run stays enabled
        # and the note appears in #hints.
        app.query_one("#area", Select).value = "penghu"
        await pilot.pause()
        assert not app.query_one("#run", Button).disabled
        assert "startx" in str(app.query_one("#hints", Static).content)

        # Invalid shiftx disables Run and shows an error.
        app.query_one("#area", Select).value = "taiwan"
        app.query_one("#shiftx", Input).value = "0"
        await pilot.pause()
        assert app.query_one("#run", Button).disabled
        assert "shiftx" in str(app.query_one("#errors", Static).content)

        # Fix it; TWD97 toggle + area select change the command.
        app.query_one("#shiftx", Input).value = "3"
        app.query_one("#twd97", Checkbox).value = True
        app.query_one("#area", Select).value = "penghu"
        await pilot.pause()
        text = str(app.query_one("#preview", Static).content)
        assert "--penghu 1" in text
        assert "200000,2578000,3,3" in text  # TWD97 datum omitted
        assert app.query_one("#outdir", Static).content


@pytest.mark.asyncio
async def test_app_confirm_screen_and_quit():
    from mapgen.tui.app import ConfirmScreen, MapGenApp

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        await pilot.click("#run")
        await pilot.pause()
        assert any(  # noqa: SIM118
            isinstance(w, ConfirmScreen) for w in app.screen_stack
        )
        await pilot.press("escape")
        await pilot.pause()
        assert not any(
            isinstance(w, ConfirmScreen) for w in app.screen_stack
        )


class _FakeProc:
    """Fake Popen: emit scripted lines, optionally blocking until cancelled."""

    def __init__(self, lines, block_after=None, release=None):
        self._lines = list(lines)
        self._pos = 0
        self._block_after = block_after
        self._release = release or _NeverSetEvent()
        self.stdout = self

    def readline(self):
        if self._pos < len(self._lines):
            line = self._lines[self._pos]
            self._pos += 1
            if self._block_after is not None and self._pos >= self._block_after:
                self._release.wait()
            return line
        return ""

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return None if not self._release.is_set() else 0

    def terminate(self):
        self._release.set()


class _NeverSetEvent:
    def set(self):
        pass

    def wait(self, timeout=None):
        return True


@pytest.mark.asyncio
async def test_app_quit_prints_command_line():
    from textual.widgets import Static

    from mapgen.tui.app import MapGenApp

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        cmd = str(app.query_one("#preview", Static).content)
        assert "mapgen make" in cmd
        await pilot.press("ctrl+q")
        await pilot.pause()
    assert app._exit_message is not None
    assert "mapgen make" in app._exit_message
    assert "236000,2578000,3,3,TWD67" in app._exit_message


@pytest.mark.asyncio
async def test_app_run_window_lists_files_on_ok(monkeypatch, tmp_path):
    from textual.widgets import Button

    from mapgen.tui import app as tui_app
    from mapgen.tui.app import MapGenApp, RunScreen

    (tmp_path / "out.png").write_bytes(b"x")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "deep.png").write_bytes(b"x")

    proc = _FakeProc(["line one", "line two"])
    monkeypatch.setattr(tui_app.subprocess, "Popen", lambda *a, **k: proc)

    async with MapGenApp(form=MapForm(output=str(tmp_path))).run_test(
        size=(160, 48)
    ) as pilot:
        app = pilot.app
        await pilot.pause()
        await pilot.click("#run")
        await pilot.pause()
        await pilot.click("#run-yes")
        await pilot.pause()

        run_screen = next(
            w for w in app.screen_stack if isinstance(w, RunScreen)
        )
        ok = run_screen.query_one("#run-ok", Button)
        for _ in range(100):
            await pilot.pause()
            if not ok.disabled:
                break
        assert not ok.disabled
        assert run_screen._finished

        await pilot.click("#run-ok")
        await pilot.pause()

    assert app._exit_message is not None
    assert "輸出完成" in app._exit_message
    assert "out.png" in app._exit_message
    assert "deep.png" in app._exit_message
    assert "共 2 個檔案" in app._exit_message


@pytest.mark.asyncio
async def test_app_run_window_cancel_aborts(monkeypatch):
    import threading

    from textual.widgets import Button

    from mapgen.tui import app as tui_app
    from mapgen.tui.app import MapGenApp, RunScreen

    release = threading.Event()
    proc = _FakeProc(
        ["started"], block_after=1, release=release
    )
    monkeypatch.setattr(tui_app.subprocess, "Popen", lambda *a, **k: proc)

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        await pilot.click("#run")
        await pilot.pause()
        await pilot.click("#run-yes")
        await pilot.pause()

        run_screen = next(
            w for w in app.screen_stack if isinstance(w, RunScreen)
        )
        assert run_screen.query_one("#run-ok", Button).disabled
        assert release.is_set() is False

        await pilot.press("ctrl+q")
        await pilot.pause()

    assert release.is_set()
    assert app._exit_message == "執行已取消。"


@pytest.mark.asyncio
async def test_app_prefill_region_formats_whole_kms():
    from textual.widgets import Input

    from mapgen.tui.app import MapGenApp

    form, errors = parse_cli_args(["--region", "236:2567:2:3:TWD67"])
    assert errors == []
    assert form.startx == 236.0 and form.starty == 2567.0  # float after parse

    async with MapGenApp(form=form).run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        assert app.query_one("#startx", Input).value == "236"
        assert app.query_one("#starty", Input).value == "2567"
        assert app.query_one("#shiftx", Input).value == "2"
        assert app.query_one("#shifty", Input).value == "3"


@pytest.mark.asyncio
async def test_app_fractional_kms_keep_decimal():
    from textual.widgets import Input, Static

    from mapgen.tui.app import MapGenApp

    form, _ = parse_cli_args(["--region", "236250,2567200,2,3"])
    assert form.startx == 236.25

    async with MapGenApp(form=form).run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        assert app.query_one("#startx", Input).value == "236.25"
        assert app.query_one("#starty", Input).value == "2567.2"
        # metres round-trip in the preview
        assert "236250,2567200,2,3" in str(
            app.query_one("#preview", Static).content
        )


@pytest.mark.asyncio
async def test_app_ctrl_r_runs_and_confirms(monkeypatch):
    from textual.widgets import Button

    from mapgen.tui import app as tui_app
    from mapgen.tui.app import ConfirmScreen, MapGenApp, RunScreen

    proc = _FakeProc(["hello"])
    monkeypatch.setattr(tui_app.subprocess, "Popen", lambda *a, **k: proc)

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()

        # Enter keeps its normal meaning on the form — it must NOT trigger Run.
        await pilot.press("enter")
        await pilot.pause()
        assert not any(isinstance(w, ConfirmScreen) for w in app.screen_stack)

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert any(isinstance(w, ConfirmScreen) for w in app.screen_stack)

        await pilot.press("ctrl+r")
        await pilot.pause()
        run_screen = next(
            w for w in app.screen_stack if isinstance(w, RunScreen)
        )
        ok = run_screen.query_one("#run-ok", Button)
        for _ in range(100):
            await pilot.pause()
            if not ok.disabled:
                break
        assert not ok.disabled

        await pilot.press("ctrl+r")
        await pilot.pause()

    assert app._exit_message is not None
    assert "輸出完成" in app._exit_message
    assert "尚未產生檔案" in app._exit_message


@pytest.mark.asyncio
async def test_app_header_shows_program_info_and_help():
    from textual.widgets import Static

    from mapgen import __version__
    from mapgen.tui.app import HelpScreen, MapGenApp

    async with MapGenApp().run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        assert __version__ in str(app.query_one("#header", Static).content)

        # f1 shows help even while an input box is focused.
        assert app.focused is not None
        await pilot.press("f1")
        await pilot.pause()
        assert any(isinstance(w, HelpScreen) for w in app.screen_stack)

        await pilot.press("escape")
        await pilot.pause()
        assert not any(isinstance(w, HelpScreen) for w in app.screen_stack)


def _write_gpx(tmp_path, name="track.gpx") -> str:
    path = tmp_path / name
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest">
  <metadata><name>test</name></metadata>
  <wpt lat="24.08" lon="121.16"><name>start</name></wpt>
  <trk><trkseg>
    <trkpt lat="24.13" lon="121.19"><ele>3000</ele></trkpt>
    <trkpt lat="24.10" lon="121.18"></trkpt>
  </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )
    return str(path)


def test_prefill_from_gpx_synthesizes_region_and_gpx(tmp_path):
    from mapgen.tui.app import _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    args, locked, reg = _prefill_from_gpx(["--from-gpx", gpx, "-t", "合歡山"])
    assert locked is True
    assert reg is not None
    assert "--from-gpx" not in args
    assert "--gpx" in args and args[args.index("--gpx") + 1] == gpx
    assert "--region" in args
    region = args[args.index("--region") + 1]
    assert region == reg.spec
    assert "-t" in args and args[args.index("-t") + 1] == "合歡山"

    form, errors = parse_cli_args(args)
    assert errors == []
    assert form.gpx == gpx
    assert int(form.startx) == reg.x0 // 1000


def test_prefill_from_gpx_respects_existing_gpx_flag(tmp_path):
    from mapgen.tui.app import _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    args, locked, _ = _prefill_from_gpx(
        ["--from-gpx", gpx, "--gpx", f"{gpx}:3:4"]
    )
    assert locked is True
    gpx_flags = [args[i + 1] for i, a in enumerate(args) if a == "--gpx"]
    assert gpx_flags.count(f"{gpx}:3:4") == 1
    form, _ = parse_cli_args(args)
    assert form.label_trk == 3 and form.label_wpt == 4


def test_prefill_from_gpx_region_beats_explicit_region(tmp_path):
    from mapgen.tui.app import _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    args, locked, reg = _prefill_from_gpx(["--region", "100:100:2:2", "--from-gpx", gpx])
    assert locked is True
    form, errors = parse_cli_args(args)
    assert errors == []
    assert int(form.startx) == reg.x0 // 1000
    assert int(form.starty) == reg.y0 // 1000


def test_prefill_from_gpx_title_from_filename_stem(tmp_path):
    from mapgen.tui.app import _prefill_from_gpx

    gpx = _write_gpx(tmp_path)  # track has no name
    args, locked, _ = _prefill_from_gpx(["--from-gpx", gpx])
    assert locked is True
    form, errors = parse_cli_args(args)
    assert errors == []
    assert form.title == "track"


def test_prefill_from_gpx_title_respects_explicit_title(tmp_path):
    from mapgen.tui.app import _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    args, locked, _ = _prefill_from_gpx(["--from-gpx", gpx, "-t", "自訂標題"])
    assert locked is True
    form, errors = parse_cli_args(args)
    assert errors == []
    assert form.title == "自訂標題"


@pytest.mark.asyncio
async def test_app_from_gpx_locks_region_and_updates_gpx_labels(tmp_path):
    from textual.app import NoMatches
    from textual.widgets import Checkbox, Static

    from mapgen.tui.app import MapGenApp, _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    args, _, reg = _prefill_from_gpx(["--from-gpx", gpx])
    form, errors = parse_cli_args(args)
    assert errors == []

    async with MapGenApp(
        form=form, region_locked=True, gpx_reg=reg
    ).run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()

        # region section is hidden, GPX section is shown
        with pytest.raises(NoMatches):
            app.query_one("#coord1")
        with pytest.raises(NoMatches):
            app.query_one("#startx")
        assert "track.gpx" in str(app.query_one("#gpx-info", Static).content)

        # toggling 航跡標記/航點標記 reflects into the previewed --gpx spec
        assert app.query_one("#label-trk", Checkbox).value is False
        assert app.query_one("#label-wpt", Checkbox).value is False
        await pilot.click("#label-trk")
        await pilot.pause()
        assert not app.query_one("#run").disabled
        assert f"{gpx}:1:0" in str(app.query_one("#preview", Static).content)
        await pilot.click("#label-wpt")
        await pilot.pause()
        assert f"{gpx}:1:1" in str(app.query_one("#preview", Static).content)


@pytest.mark.asyncio
async def test_app_from_gpx_shows_gpx_section_with_filename(tmp_path):
    from textual.widgets import Static

    from mapgen.gpx_region import region_from_gpx
    from mapgen.tui.app import MapGenApp, _prefill_from_gpx

    gpx = _write_gpx(tmp_path)
    reg = region_from_gpx(gpx, datum="TWD67")
    args, _, _ = _prefill_from_gpx(["--from-gpx", gpx, "--datum", "TWD67"])
    form, errors = parse_cli_args(args)
    assert errors == []

    async with MapGenApp(
        form=form, region_locked=True, gpx_reg=reg
    ).run_test(size=(160, 48)) as pilot:
        app = pilot.app
        await pilot.pause()
        info = str(app.query_one("#gpx-info", Static).content)
        assert "track.gpx" in info
        assert "1 軌跡" in info
        assert "WGS84" in info
        assert reg.spec in str(app.query_one("#preview", Static).content)
        assert "--gpx" in str(app.query_one("#preview", Static).content)
