"""Textual terminal UI (``mapgen-tui``).

A single-column form laid out like the PHP ``mapform`` page: title/map
source, Region (startx/starty in km, TWD97 toggle, 台灣/澎湖), Output &
Options (A3 + extra page dimensions, 100m grid / include tracks / keep
color, live outdir), then the generated command preview and Run/Quit.

- ``Run`` confirms the command, then opens a floating window that streams the
  subprocess output live until it finishes; an ``OK`` button then quits the
  app and prints the files produced in the output directory.
- ``Quit`` (button or ctrl+q) prints the previewed command line and exits.

Any ``mapgen make`` flag passed to ``mapgen-tui`` prefills the form; e.g.
``mapgen-tui -v 3 -t 合歡山 -p 1`` opens with those values already set.
``mapgen-tui --from-gpx track.gpx [--datum TWD97]`` derives the region from
the GPX file (Taiwan/Penghu auto-detected, centred on the track with >= 1 km
margin, aligned to A4 5x7 km pages), locks the region section, prefills the
title from the track/file name, and shows a 行跡資訊 section with
航跡標記/航點標記 toggles.
"""

from __future__ import annotations

import asyncio
import shlex
import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from .. import __version__
from ..config import list_sources
from ..gpx_region import region_from_gpx
from .core import (
    DEFAULT_TITLE,
    EXTRA_DIMS,
    MapForm,
    command_line,
    default_output_dir,
    hints,
    parse_cli_args,
    to_argv,
    validate,
)

SOURCE_LABELS = {k: f"{k} — {src.label}" for k, src in list_sources()}


def _cmd_text(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)


def _fmt_num(value: float | int) -> str:
    """Show whole numbers without a trailing ``.0`` (236.0 -> ``236``)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f.is_integer() else str(f)


def _gpx_info_text(reg) -> str:
    """Human-readable summary of the derived region for the GPX section."""
    area = "澎湖" if reg.penghu else "台灣"
    counts = f"{reg.tracks} 軌跡, {reg.routes} 路線, {reg.waypoints} 航點, 共 {reg.points} 點"
    wgs = (
        f"WGS84: {reg.lon_min:.3f},{reg.lat_min:.3f} — "
        f"{reg.lon_max:.3f},{reg.lat_max:.3f}"
    )
    spec = (
        f"{reg.datum}({area}): 左上 {reg.x0},{reg.y0}，{reg.shiftx}×{reg.shifty} km"
    )
    return (
        f"{Path(reg.path).name} | {counts}\n"
        f"{wgs}\n"
        f"{spec} [dim]— {reg.spec}[/dim]"
    )


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirm for the generated command."""

    BINDINGS = [
        ("enter", "confirm", "Run"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, argv: list[str]) -> None:
        super().__init__()
        self.argv = argv

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label("Run this command?", classes="title")
            yield Static(_cmd_text(self.argv), classes="cmd")
            yield Horizontal(
                Button("Run", id="run-yes", variant="primary"),
                Button("Cancel", id="run-no"),
                classes="actions",
            )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "run-yes")


class RunScreen(ModalScreen[str]):
    """Floating window streaming the running command's output.

    Dismisses with ``"ok"`` (the job finished and files may be listed) or
    ``"cancel"`` (quit without running / abort the subprocess).
    """

    BINDINGS = [
        ("enter", "press_ok", "OK"),
        ("ctrl+q", "cancel", "Leave"),
    ]

    def __init__(self, argv: list[str], outdir: str) -> None:
        super().__init__()
        self.argv = argv
        self.outdir = outdir
        self._mounted = False
        self._finished = False
        self._closed = False
        self._pending: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="runbox"):
            yield Label("執行中 | Running", classes="title")
            yield Static(f"> {_cmd_text(self.argv)}", classes="cmdline")
            yield Static(f"輸出目錄: {self.outdir}", classes="outdir")
            yield RichLog(id="runlog", wrap=True, max_lines=2000, auto_scroll=True)
            yield Horizontal(
                Button("取消離開", id="run-cancel"),
                Button("OK", id="run-ok", variant="primary", disabled=True),
                classes="actions",
            )

    def on_unmount(self) -> None:
        self._closed = True

    def on_mount(self) -> None:
        self._mounted = True
        log = self.query_one("#runlog", RichLog)
        for line in self._pending:
            log.write(line)
        self._pending.clear()

    def write_line(self, line: str) -> None:
        """Append one output line (call from any thread)."""
        if self._closed:
            return
        if self._mounted:
            self.query_one("#runlog", RichLog).write(line)
        else:
            self._pending.append(line)

    def finish(self, rc: int) -> None:
        """Stream finished: mark done and enable the OK button."""
        if self._closed:
            return
        self.write_line("")
        self.write_line(f"» finished (exit {rc})")
        self._finished = True
        if self._mounted:
            self.query_one("#run-ok", Button).disabled = False

    def action_press_ok(self) -> None:
        if not self._closed and self._finished:
            self.dismiss("ok")

    def action_cancel(self) -> None:
        self.dismiss("cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "run-ok":
            self.dismiss("ok")
        elif event.button.id == "run-cancel":
            self.dismiss("cancel")


HELP_TEXT = """\
[b]Taiwan Map Generator | 台灣山區地圖產生器[/b]

設定單一頁面：標題/地圖、範圍(左上x,y 與 shift，單位 km，TWD67 預設)、
輸出選項（A3 與額外尺寸、100m 格線、山友 track、彩圖），下方即時預覽指令。

[b]快捷鍵 | Keys[/b]
  [b]ctrl+r[/b]    執行 Run（確認框與結果視窗內，Enter 等同確認/OK）
  [b]ctrl+q[/b]    離開，印出預覽指令後結束
  [b]f1[/b]         本說明
  [b]esc[/b]        關閉對話框

Run 先顯示確認框，執行期間於浮動視窗即時顯示輸出；
結束後按 OK 離開並列出輸出目錄產出的檔案。

任何 [b]mapgen make[/b] 旗標都可預填表單，例：[b]mapgen-tui -t 合歡山 -v 3[/b]。
自訂字型用 [b]--font-path /path/to/font.ttf[/b]（預設使用內建的
wqy-microhei，輸出跨平台一致）。
以 [b]--from-gpx 檔案.gpx [--datum TWD67|TWD97][/b] 啟動時，範圍自動由
GPX 決定（台灣/澎湖自動），以軌跡為中心、至少 1km 邊距、對齊 A4 5x7 km
頁面；標題自動取軌跡名稱（否則檔名）。勾選 '航跡標記/航點標記' 即可
在輸出標示軌跡上的點與航點（反映在 [b]--gpx 路徑:trk:wpt[/b]）。"""


class HelpScreen(ModalScreen[None]):
    """Usage / keyboard help."""

    BINDINGS = [
        ("f1", "cancel", "Close"),
        ("escape", "cancel", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="helpbox"):
            yield Label("使用說明 | Help", classes="title")
            yield Static(HELP_TEXT, id="helptext")
            yield Horizontal(
                Button("OK", id="help-ok", variant="primary"),
                classes="actions",
            )

    def action_cancel(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss()


class MapGenApp(App[None]):
    """Interactive map generator."""

    TITLE = "Taiwan Map Generator"
    SUB_TITLE = "mapgen make — preview and run"
    CSS = """
    #page {
        width: 100%;
        height: 100%;
        padding: 0 1;
        overflow-y: auto;
    }
    #header {
        height: 1;
        text-style: bold;
        background: $boost;
        color: $text;
        margin-bottom: 1;
    }
    .section {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }
    .section:first-of-type {
        margin-top: 0;
    }
    .label {
        color: $text-muted;
    }
    .row {
        height: 3;
        margin-bottom: 0;
    }
    .cpair {
        height: auto;
        margin-right: 1;
        width: 1fr;
    }
    .cpair > Label {
        width: 8;
        color: $text-muted;
    }
    .cpair > Input {
        width: 1fr;
        min-width: 6;
    }
    #src-pair > Label {
        width: 16;
    }
    #map-type {
        width: 1fr;
        min-width: 22;
    }
    #twd97 {
        width: auto;
    }
    #area {
        width: 20;
    }
    .chkrow Checkbox {
        margin-right: 1;
    }
    #gpx-info {
        height: auto;
        color: $text-muted;
        margin: 0 0 1 0;
    }
    #gpxflags {
        height: auto;
        margin: 0 0 0 0;
    }
    #outdir {
        color: $text-muted;
        margin: 0 0 1 0;
    }
    #preview {
        width: 1fr;
        height: 6;
        border: round $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    #errors {
        color: $error;
        height: auto;
        max-height: 6;
        padding: 1 0 0 0;
        overflow-y: auto;
    }
    #hints {
        color: $text-muted;
        height: auto;
        max-height: 4;
        padding: 1 0 0 0;
        overflow-y: auto;
    }
    #runrow {
        height: auto;
    }
    #actions {
        width: 20;
        height: auto;
        align-horizontal: left;
    }
    #actions Button {
        width: 19;
        min-width: 19;
        height: 3;
        margin: 0 0 0 1;
    }
    ConfirmScreen {
        align: center middle;
    }
    ConfirmScreen #box {
        width: 92;
        max-width: 92%;
        border: heavy $primary;
        background: $panel;
        padding: 2 3;
    }
    ConfirmScreen .title {
        text-style: bold;
        margin-bottom: 1;
    }
    ConfirmScreen .cmd {
        border: round $warning;
        padding: 1;
        margin: 1 0;
        color: $text;
    }
    ConfirmScreen .actions {
        align-horizontal: right;
    }
    ConfirmScreen Button {
        margin-left: 1;
        width: 16;
    }
    RunScreen {
        align: center middle;
    }
    RunScreen #runbox {
        width: 90%;
        height: 85%;
        border: heavy $accent;
        background: $panel;
        padding: 1 2;
    }
    RunScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    RunScreen .cmdline {
        color: $text;
        margin-bottom: 1;
    }
    RunScreen .outdir {
        color: $text-muted;
        margin-bottom: 1;
    }
    RunScreen #runlog {
        height: 1fr;
        border: round $primary;
        margin-bottom: 1;
    }
    RunScreen .actions {
        height: 3;
        align-horizontal: right;
    }
    RunScreen Button {
        margin-left: 1;
        width: 18;
    }
    HelpScreen {
        align: center middle;
    }
    HelpScreen #helpbox {
        width: 92;
        max-width: 92%;
        height: auto;
        border: heavy $accent;
        background: $panel;
        padding: 2 3;
    }
    HelpScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    HelpScreen #helptext {
        margin-bottom: 1;
        height: auto;
    }
    HelpScreen .actions {
        align-horizontal: right;
    }
    HelpScreen Button {
        width: 16;
    }
    """
    BINDINGS = [
        Binding("ctrl+r", "run", "Run", priority=True),
        Binding("f1", "help", "說明", priority=True),
        ("ctrl+q", "quit", "離開"),
    ]

    def __init__(
        self,
        form: MapForm | None = None,
        region_locked: bool = False,
        gpx_reg=None,
    ) -> None:
        self._form = form if form is not None else MapForm()
        self._region_locked = region_locked
        self._gpx_reg = gpx_reg
        self._gpx_path = gpx_reg.path if gpx_reg is not None else ""
        self._proc: subprocess.Popen | None = None
        self._sys_args: list[str] = []
        self._outdir = ""
        self._exit_message: str | None = None
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="page"):
            yield Static(
                f"Taiwan Map Generator v{__version__} | "
                "歡迎使用台灣山區地圖產生器 — mapgen-tui",
                id="header",
            )
            with Horizontal(id="title-row", classes="row"):
                with Horizontal(classes="cpair"):
                    yield Label("標題描述", classes="label")
                    yield Input(self._form.title, id="title",
                                placeholder=DEFAULT_TITLE)
            with Horizontal(id="source-row", classes="row"):
                with Horizontal(classes="cpair", id="src-pair"):
                    yield Label("地圖選擇 | Map source", classes="label")
                    yield Select(
                        [(SOURCE_LABELS[k], k) for k in SOURCE_LABELS],
                        value=self._form.map_type,
                        allow_blank=False,
                        id="map-type",
                    )

            if self._region_locked:
                yield Label("行跡資訊 | Input GPX", classes="section")
                yield Static(_gpx_info_text(self._gpx_reg), id="gpx-info")
                with Horizontal(id="gpxflags", classes="row chkrow"):
                    yield Checkbox(
                        "航跡標記 label_trk",
                        value=self._form.label_trk > 0,
                        id="label-trk",
                    )
                    yield Checkbox(
                        "航點標記 label_wpt",
                        value=self._form.label_wpt > 0,
                        id="label-wpt",
                    )
            else:
                yield Label("輸入範圍 (km) | Region & Datum", classes="section")
                with Horizontal(id="coord1", classes="row"):
                    with Horizontal(classes="cpair"):
                        yield Label("左上x", classes="label")
                        yield Input(
                            _fmt_num(self._form.startx),
                            id="startx",
                            placeholder="149-351",
                        )
                    with Horizontal(classes="cpair"):
                        yield Label("左上y", classes="label")
                        yield Input(
                            _fmt_num(self._form.starty),
                            id="starty",
                            placeholder="2424-2800",
                        )
                    yield Checkbox(
                        "TWD97",
                        value=self._form.datum == "TWD97",
                        id="twd97",
                    )
                with Horizontal(id="coord2", classes="row"):
                    with Horizontal(classes="cpair"):
                        yield Label("shiftx", classes="label")
                        yield Input(
                            _fmt_num(self._form.shiftx), id="shiftx", placeholder="3"
                        )
                    with Horizontal(classes="cpair"):
                        yield Label("shifty", classes="label")
                        yield Input(
                            _fmt_num(self._form.shifty), id="shifty", placeholder="3"
                        )
                    yield Select(
                        [("台灣", "taiwan"), ("澎湖", "penghu")],
                        value="penghu" if self._form.penghu else "taiwan",
                        allow_blank=False,
                        id="area",
                    )

            yield Label("輸出選項 | Output Options", classes="section")
            with Horizontal(id="dims", classes="row chkrow"):
                for dim in ["A3", *EXTRA_DIMS]:
                    widget_id = "a3" if dim == "A3" else f"d{dim}"
                    yield Checkbox(
                        dim,
                        value=(
                            self._form.a3
                            if dim == "A3"
                            else dim in self._form.dims
                        ),
                        id=widget_id,
                    )
            #with Horizontal(id="flags", classes="row chkrow"):
                yield Checkbox(
                    "100m格線", value=self._form.grid_100m, id="grid-100m"
                )
                yield Checkbox(
                    "山友track",
                    value=self._form.include_tracks,
                    id="include-tracks",
                )
                yield Checkbox(
                    "彩圖",
                    value=self._form.keep_color,
                    id="keep-color",
                )
            yield Static(id="outdir")

            yield Label("產生指令 | Command preview", classes="section")
            with Horizontal(id="runrow"):
                yield Static(id="preview")
                with Vertical(id="actions"):
                    yield Button("Run", id="run", variant="primary")
                    yield Button("離開 [ctrl+q]", id="quit")
            yield Static(id="errors")
            yield Static(id="hints")

        yield Footer()

    # --- live preview ---

    def on_mount(self) -> None:
        self._refresh_preview()

    def _read_form(self) -> MapForm:
        def _num(q: str, fallback: float) -> float:
            try:
                return int(self.query_one(f"#{q}", Input).value)
            except ValueError:
                try:
                    return float(self.query_one(f"#{q}", Input).value)
                except ValueError:
                    return fallback

        if self._region_locked:
            startx = self._form.startx
            starty = self._form.starty
            shiftx = int(self._form.shiftx)
            shifty = int(self._form.shifty)
            datum = self._form.datum
            penghu = self._form.penghu
        else:
            startx = _num("startx", self._form.startx)
            starty = _num("starty", self._form.starty)
            shiftx = int(_num("shiftx", self._form.shiftx))
            shifty = int(_num("shifty", self._form.shifty))
            datum = "TWD97" if self.query_one("#twd97", Checkbox).value else "TWD67"
            penghu = self.query_one("#area", Select).value == "penghu"

        label_trk = self.query_one("#label-trk", Checkbox).value if (
            self._region_locked) else self._form.label_trk > 0
        label_wpt = self.query_one("#label-wpt", Checkbox).value if (
            self._region_locked) else self._form.label_wpt > 0

        dims = [d for d in EXTRA_DIMS
                if self.query_one(f"#d{d}", Checkbox).value]
        return MapForm(
            startx=startx,
            starty=starty,
            shiftx=shiftx,
            shifty=shifty,
            datum=datum,
            penghu=penghu,
            map_type=str(self.query_one("#map-type", Select).value),
            title=self.query_one("#title", Input).value,
            output=self._form.output,
            gpx=self._form.gpx,
            label_trk=1 if label_trk else 0,
            label_wpt=1 if label_wpt else 0,
            keep_color=self.query_one("#keep-color", Checkbox).value,
            grid_100m=self.query_one("#grid-100m", Checkbox).value,
            include_tracks=self.query_one("#include-tracks", Checkbox).value,
            a3=self.query_one("#a3", Checkbox).value,
            dims=dims,
        )

    def _resolve_output(self, form: MapForm) -> str:
        if form.output:
            return form.output
        return default_output_dir(form.title)

    def _refresh_preview(self) -> None:
        try:
            form = self._read_form()
        except Exception as exc:  # noqa: BLE001
            self.query_one("#preview", Static).update(f"[red]UI error: {exc}")
            return
        problems = validate(form)
        if problems:
            self.query_one("#preview", Static).update(
                "[dim]Fix the problems below to enable Run[/dim]"
            )
            self.query_one("#errors", Static).update(
                "\n".join(f"• {p}" for p in problems[:8])
            )
            self.query_one("#hints", Static).update("")
            self.query_one("#run", Button).disabled = True
            return
        notes = hints(form)
        self.query_one("#errors", Static).update("")
        self.query_one("#hints", Static).update(
            "\n".join(f"• {n}" for n in notes) if notes else ""
        )
        outdir = self._resolve_output(form)
        self.query_one("#outdir", Static).update(f"輸出目錄: {outdir}")
        self._sys_args = to_argv(form, output_dir=outdir)
        self._outdir = outdir
        self.query_one("#preview", Static).update(
            command_line(form, output_dir=outdir)
        )
        self.query_one("#run", Button).disabled = False

    # --- widget change plumbing ---

    def on_input_changed(self, _: Input.Changed) -> None:
        self._refresh_preview()

    def on_select_changed(self, _: Select.Changed) -> None:
        self._refresh_preview()

    def on_checkbox_changed(self, _: Checkbox.Changed) -> None:
        self._refresh_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        button_id = event.button.id
        if button_id == "run":
            self.action_run()
        elif button_id == "quit":
            self.action_quit()

    def action_run(self) -> None:
        """Run the previewed command (bound to the Run button and ctrl+r).

        On the confirm screen ctrl+r confirms; on the run screen it presses OK.
        """
        screen = self.screen
        if isinstance(screen, ConfirmScreen):
            screen.dismiss(True)
            return
        if isinstance(screen, RunScreen):
            screen.action_press_ok()
            return
        if type(screen) is not Screen:
            return  # unknown modal (e.g. help) — leave it alone
        if self._proc is not None:
            self.notify("A job is already running", severity="warning")
            return
        if not self._sys_args:
            self._refresh_preview()
            return
        self.push_screen(ConfirmScreen(self._sys_args), self._on_run_confirmed)

    def action_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.screen.dismiss()
            return
        self.push_screen(HelpScreen())

    # --- running the command ---

    def _on_run_confirmed(self, confirmed: bool) -> None:
        if not (confirmed and self._sys_args):
            return
        screen = RunScreen(self._sys_args, self._outdir)
        self.push_screen(screen, self._on_run_done)
        self.run_command(screen)

    def run_command(self, screen: RunScreen) -> None:
        self.query_one("#run", Button).disabled = True
        cmd = [sys.executable, "-m", "mapgen.cli", *self._sys_args[1:]]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.run_worker(self._stream_output(screen), thread=True, name="mapgen-run")

    async def _stream_output(self, screen: RunScreen) -> None:
        proc = self._proc
        assert proc is not None
        try:
            while True:
                line = await asyncio.to_thread(proc.stdout.readline)
                if not line:
                    break
                if not screen._closed:
                    self.call_from_thread(screen.write_line, line.rstrip())
        finally:
            rc = await asyncio.to_thread(proc.wait)
            self._proc = None
            if not screen._closed:
                try:
                    self.call_from_thread(screen.finish, rc)
                except RuntimeError:
                    pass

    def _on_run_done(self, choice: str) -> None:
        self._terminate()
        if choice == "ok":
            self._exit_message = self._outdir_listing()
            self.exit()
        elif choice == "cancel":
            self._exit_message = "執行已取消。"
            self.exit()

    def _outdir_listing(self) -> str:
        lines = [f"輸出完成，輸出目錄: {self._outdir or '(unknown)'}"]
        files = sorted(
            p.name for p in Path(self._outdir).rglob("*") if p.is_file()
        ) if self._outdir else []
        if files:
            lines.append("輸出檔案:")
            lines.extend(f"  - {f}" for f in files)
            lines.append(f"共 {len(files)} 個檔案")
        else:
            lines.append("(尚未產生檔案)")
        return "\n".join(lines)

    # --- quit ---

    def action_quit(self) -> None:
        self._terminate()
        cmd = _cmd_text(self._sys_args) if self._sys_args else ""
        self._exit_message = (f"尚未執行。預覽指令:\n{cmd}" if cmd
                              else "尚未執行。表單未完整無法產生指令。")
        self.exit()

    def _terminate(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _prefill_from_gpx(argv: list[str]) -> tuple[list[str], bool, object | None]:
    """Extract ``--from-gpx <file>`` / ``--datum`` and synthesize prefill args.

    Returns ``(remaining_args, region_locked, GpxRegion|None)``. When a GPX
    file is given, ``remaining_args`` contains the rest of the caller's flags
    plus ``--region <spec>`` and ``--title <suggested>`` (derived from the
    file) and, unless the caller already passed ``--gpx``, ``--gpx <path>``.
    Precedence (argparse keeps the last occurrence of a flag): the derived
    ``--region`` is placed last so it always wins over an explicit ``--region``
    and keeps the map matching the track; the derived ``--title``/``--gpx``/
    ``--penghu`` are placed first so an explicit caller flag still wins.
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=False, prog="mapgen-tui")
    parser.add_argument("--from-gpx", dest="gpx_path")
    parser.add_argument("--datum", default="TWD67", choices=("TWD67", "TWD97"))
    ns, rest = parser.parse_known_args(argv)
    rest = [
        a for a in rest
        if not a.startswith(("--from-gpx", "--datum"))
    ]
    if not ns.gpx_path:
        return rest, False, None
    reg = region_from_gpx(ns.gpx_path, datum=ns.datum)
    pre: list[str] = []
    if "--gpx" not in rest:
        pre += ["--gpx", str(ns.gpx_path)]
    if reg.penghu:
        pre += ["--penghu", "1"]
    if "--title" not in rest and "-t" not in rest:
        pre += ["--title", reg.title]
    return pre + rest + ["--region", reg.spec], True, reg


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(
            "mapgen-tui — interactive Taiwan map generator.\n"
            "Any 'mapgen make' flag may be passed to prefill the form; what you "
            "leave out keeps its default (e.g. -v 3 -t 合歡山 -p 1).\n"
            "--from-gpx <file.gpx> [--datum TWD67|TWD97] computes the region\n"
            "from a GPX file (Taiwan/Penghu auto), centres it on the track with\n"
            ">=1km margin on A4 5x7 km pages, and prefills the form/title.\n"
            "In the UI: ctrl+r runs, f1 shows help, ctrl+q quits and prints the "
            "previewed command; Run executes it in a live output window."
        )
        return 0
    try:
        args, region_locked, gpx_reg = _prefill_from_gpx(args)
    except ValueError as exc:
        print(f"mapgen-tui: {exc}", file=sys.stderr)
        return 2
    form, errors = parse_cli_args(args)
    if errors:
        for err in errors:
            print(f"mapgen-tui: {err}", file=sys.stderr)
        return 2
    app = MapGenApp(form=form, region_locked=region_locked, gpx_reg=gpx_reg)
    app.run()
    if app._exit_message:
        print(app._exit_message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
