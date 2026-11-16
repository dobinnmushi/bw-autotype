"""rofi の代わりに出す一覧（GTK4）。lib/rofi から呼ばれ、rofi -dmenu と同じ約束で答える。

rofi-rbw との約束（rofi-rbw の selector/rofi.py が使う分だけ）:
- 標準入力の1行が1項目（-markup-rows の pango マークアップ）。
- -format i なら選んだ行の番号、なければ選んだ行そのものを標準出力へ。
- 終了コード: 選んだら 0、閉じたら 1、-kb-custom-N のキーなら 9+N。
- -p は入力欄の見出し、-mesg は下に出す説明。

項目の一覧（-format i のとき）は、行からフォルダ・名前・ユーザー名を取り出し、`rbw list` と突き合わせて
種類を知る。種類とフォルダのプルダウンで絞り、入力欄の語でさらに絞る。
bw-autotype が環境変数で渡すもの:
  BW_AUTOTYPE_SITE    前面のページに合う項目 [[フォルダ, 名前, ユーザー名], …]（上に並べて印を付ける）
  BW_AUTOTYPE_RECENT  "1" なら最初の行（直前に使った項目）を一番上に置く
"""
import html
import json
import os
import re
import subprocess
import sys
import time

import bwcommon as bw

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

tr = bw.tr
TITLE = "Bitwarden — bw-autotype"
TYPE_NAMES = {"Login": tr("ログイン", "Login"), "Card": tr("カード", "Card"),
              "Identity": tr("個人情報", "Identity"), "Note": tr("メモ", "Note")}
ALL = tr("すべて", "All")
NO_FOLDER = tr("（フォルダなし）", "(no folder)")

CSS = b"""
.bw-badge { font-size: 0.8em; padding: 1px 6px; border-radius: 6px; background: alpha(@accent_bg_color, 0.35); }
.bw-dim { opacity: 0.65; }
.bw-help { font-size: 0.85em; }
"""


# ---- 引数 ----
def parse_args(argv):
    opts = {"format_index": False, "prompt": "", "mesg": "", "keys": {}}
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else ""
        if a == "-format":
            opts["format_index"] = nxt == "i"
            i += 1
        elif a == "-p":
            opts["prompt"] = nxt
            i += 1
        elif a == "-mesg":
            opts["mesg"] = nxt
            i += 1
        elif a.startswith("-kb-custom-"):
            opts["keys"][int(a.removeprefix("-kb-custom-"))] = nxt
            i += 1
        elif a in ("-theme", "-theme-str", "-dpi", "-filter", "-selected-row", "-matching", "-sorting-method"):
            i += 1
        i += 1
    return opts


MODS = {"alt": Gdk.ModifierType.ALT_MASK, "control": Gdk.ModifierType.CONTROL_MASK,
        "ctrl": Gdk.ModifierType.CONTROL_MASK, "shift": Gdk.ModifierType.SHIFT_MASK,
        "super": Gdk.ModifierType.SUPER_MASK}
MOD_MASK = Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SUPER_MASK


def parse_key(spec):
    """rofi のキー書式（Alt+1 など。カンマ区切りで複数可）を [(修飾, keyval)] にする。"""
    out = []
    for one in spec.split(","):
        parts = one.strip().split("+")
        mods = Gdk.ModifierType(0)
        for m in parts[:-1]:
            mods |= MODS.get(m.lower(), Gdk.ModifierType(0))
        keyval = Gdk.keyval_from_name(parts[-1])
        if keyval in (0, 0xFFFFFF) and len(parts[-1]) == 1:
            keyval = Gdk.unicode_to_keyval(ord(parts[-1]))
        if keyval not in (0, 0xFFFFFF):
            out.append((mods, Gdk.keyval_to_lower(keyval)))
    return out


# ---- 行 ----
ENTRY_RE = re.compile(r"^(?:(?P<folder>.*?)/)?<b>(?P<name>.*?)</b>\s*(?P<user>.*)$")


def parse_line(line):
    """rofi-rbw の行（フォルダ/<b>名前</b>  ユーザー名）を [フォルダ, 名前, ユーザー名] にする。"""
    m = ENTRY_RE.match(line)
    if not m:
        return ["", html.unescape(re.sub(r"<[^>]+>", "", line)).strip(), ""]
    return [html.unescape(m.group(k) or "").strip() for k in ("folder", "name", "user")]


def plain(line):
    return html.unescape(re.sub(r"<[^>]+>", "", line)).strip()


class Row:
    def __init__(self, index, line, key, kind, site):
        self.index, self.line, self.key, self.kind, self.site = index, line, key, kind, site
        self.text = " ".join([*key, TYPE_NAMES.get(kind, "")]).lower() if key else plain(line).lower()


def load_types():
    """(フォルダ, 名前, ユーザー名) → 種類。bw-autotype が BW_AUTOTYPE_ITEMS のファイルで渡していればそれを、
    なければ rbw list を読む"""
    try:
        with open(os.environ["BW_AUTOTYPE_ITEMS"], encoding="utf-8") as f:
            return {(folder, name, user): kind for folder, name, user, kind in json.load(f)}
    except (KeyError, OSError, ValueError):
        pass
    try:
        r = subprocess.run(["rbw", "list", "--raw"], capture_output=True, text=True)
        return {(i.get("folder") or "", i.get("name") or "", i.get("user") or ""): i.get("type")
                for i in (json.loads(r.stdout) if r.returncode == 0 else [])}
    except ValueError:
        return {}


def load_rows(lines, entries):
    types = load_types()
    try:
        site = {tuple(k) for k in json.loads(os.environ.get("BW_AUTOTYPE_SITE") or "[]")}
    except ValueError:
        site = set()
    rows = []
    for n, line in enumerate(lines):
        key = parse_line(line) if entries else None
        rows.append(Row(n, line, key, types.get(tuple(key)) if key else None, bool(key) and tuple(key) in site))
    if entries:
        # 直前の項目 → 前面のページに合う項目 → 残り（それぞれ rofi-rbw の並びのまま）
        recent = rows[:1] if os.environ.get("BW_AUTOTYPE_RECENT") == "1" else []
        rest = rows[len(recent):]
        rows = recent + [r for r in rest if r.site] + [r for r in rest if not r.site]
    return rows


# ---- 画面 ----
class Selector:
    def __init__(self, app, opts, rows, entries):
        self.app, self.opts, self.rows, self.entries = app, opts, rows, entries
        self.result = (1, "")
        self.keys = [(n, k) for n, spec in sorted(opts["keys"].items()) for k in parse_key(spec)]
        # 同期のキー（bw-autotype が BW_AUTOTYPE_SYNC_KEY で渡す）が何番目の -kb-custom か
        sync_spec = os.environ.get("BW_AUTOTYPE_SYNC_KEY", "")
        self.sync_n = next((n for n, spec in opts["keys"].items() if spec == sync_spec), None) if entries else None

        self.win = Gtk.ApplicationWindow(application=app, title=TITLE)
        self.win.set_default_size(960, 600)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                        margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.win.set_child(outer)

        # 種類・フォルダのプルダウン（項目の一覧のときだけ）
        self.kind_dd = self.folder_dd = None
        if entries:
            bar = Gtk.Box(spacing=8)
            kinds = [k for k in TYPE_NAMES if any(r.kind == k for r in rows)]
            folders = sorted({r.key[0] for r in rows if r.key[0]}, key=str.lower)
            self.kind_values = [None, *kinds]
            # 「フォルダなし」は、フォルダが1つでもあれば常に出す（該当する項目がなければ空の一覧になるだけ）
            self.folder_values = [None, *folders] + ([""] if folders else [])
            self.kind_dd = self._dropdown(bar, tr("種類", "Type") + " (Alt+k)",
                                          [ALL] + [TYPE_NAMES[k] for k in kinds])
            self.folder_dd = self._dropdown(bar, tr("フォルダ", "Folder") + " (Alt+f)",
                                            [ALL] + folders + ([NO_FOLDER] if self.folder_values[-1] == "" else []))
            outer.append(bar)

        search = Gtk.Box(spacing=8)
        if opts["prompt"]:
            search.append(Gtk.Label(label=opts["prompt"], css_classes=["dim-label"]))
        self.entry = Gtk.Entry(hexpand=True, placeholder_text=tr("名前・ユーザー名で絞り込み", "Filter by name or username")
                               if entries else tr("絞り込み", "Filter"))
        self.entry.connect("changed", lambda *_: self.refilter())
        self.entry.connect("activate", lambda *_: self.choose(0))
        search.append(self.entry)
        self.count = Gtk.Label(css_classes=["dim-label"])
        search.append(self.count)
        outer.append(search)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self.listbox.connect("row-activated", lambda *_: self.choose(0))
        for r in rows:
            self.listbox.append(self._row_widget(r))
        self.listbox.set_filter_func(self._visible)
        if entries:
            self.listbox.set_placeholder(self._not_found())
        scroll = Gtk.ScrolledWindow(child=self.listbox, vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.append(scroll)

        help_box = self._help() if entries else None
        if help_box is not None:
            outer.append(help_box)
        elif opts["mesg"]:
            outer.append(Gtk.Label(xalign=0, use_markup=True, label=opts["mesg"], css_classes=["bw-help"],
                                   wrap=True))

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self.on_key)
        self.win.add_controller(key)
        self.win.connect("close-request", lambda *_: (self.finish(1, ""), True)[1])
        self.restore_state()
        self.refilter()
        self.win.present()
        self.entry.grab_focus_without_selecting()

    def _help(self):
        """bw-autotype が BW_AUTOTYPE_HELP で渡したキー説明を表にする。なければ None。"""
        try:
            data = json.loads(os.environ.get("BW_AUTOTYPE_HELP") or "null")
        except ValueError:
            data = None
        if not data:
            return None
        if data["mode"] == "line":
            text = "  ".join(f"<b>{html.escape(k)}</b> {html.escape(label)}"
                             for _, rows in data["groups"] for k, label in rows if k and k != "Esc")
            return Gtk.Label(xalign=0, use_markup=True, label=text, wrap=True, css_classes=["bw-help"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        grid = Gtk.Grid(column_spacing=8, row_spacing=1, css_classes=["bw-help"])
        for g, (head, rows) in enumerate(data["groups"]):
            col = g * 4
            if g:
                grid.attach(Gtk.Label(label="", width_chars=2), col - 1, 0, 1, 1)
            grid.attach(Gtk.Label(label=head, xalign=0, css_classes=["dim-label"]), col, 0, 1, 1)
            for r, (k, label) in enumerate(rows):
                key = Gtk.Label(xalign=0)
                key.set_markup(f"<b>{html.escape(k)}</b>")
                grid.attach(key, col + 1, r, 1, 1)
                grid.attach(Gtk.Label(label=label, xalign=0), col + 2, r, 1, 1)
        box.append(grid)
        box.append(Gtk.Label(label=data["last"], xalign=0, css_classes=["bw-help", "dim-label"], wrap=True))
        return box

    def _not_found(self):
        """1件も合わないときに一覧の場所に出すもの（同期のキーがあれば、同期して探し直すボタンも）"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=24, margin_bottom=24,
                      halign=Gtk.Align.CENTER)
        box.append(Gtk.Label(label=tr("見つかりません", "Nothing found"), css_classes=["dim-label"]))
        if self.sync_n is not None:
            key = os.environ.get("BW_AUTOTYPE_SYNC_KEY", "")
            button = Gtk.Button(label=tr(f"保管庫を同期して探し直す（{key}）", f"Sync the vault and search again ({key})"))
            button.connect("clicked", lambda *_: self.sync())
            box.append(button)
        return box

    # ---- 同期のあとに、絞り込みの状態を引き継ぐ ----
    STATE_SECONDS = 30

    def _state_path(self):
        return os.path.join(bw.STATE_DIR, "list-state.json")

    def save_state(self):
        state = {"time": time.time(), "text": self.entry.get_text(),
                 "kind": self.kind_values[self.kind_dd.get_selected()] if self.kind_dd else None,
                 "folder": self.folder_values[self.folder_dd.get_selected()] if self.folder_dd else None}
        os.makedirs(bw.STATE_DIR, mode=0o700, exist_ok=True)
        with open(os.open(self._state_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(state, f)

    def restore_state(self):
        if not self.entries:
            return
        try:
            with open(self._state_path(), encoding="utf-8") as f:
                state = json.load(f)
            os.unlink(self._state_path())
        except (OSError, ValueError):
            return
        if time.time() - state.get("time", 0) > self.STATE_SECONDS:
            return
        self.entry.set_text(state.get("text") or "")
        self.entry.set_position(-1)
        for dd, values, value in ((self.kind_dd, self.kind_values, state.get("kind")),
                                  (self.folder_dd, self.folder_values, state.get("folder"))):
            if dd is not None and value in values:
                dd.set_selected(values.index(value))

    def sync(self):
        """同期のキーで終わる。rofi-rbw が rbw sync をしてから一覧を開き直す。絞り込みの状態は引き継ぎ、
        項目の種類のファイルは古くなるので消す（開き直した一覧は rbw list を読み直す）"""
        self.save_state()
        try:
            os.unlink(os.environ["BW_AUTOTYPE_ITEMS"])
        except (KeyError, OSError):
            pass
        # rofi-rbw はキーで終わったときも行の番号を読むので、空の一覧でも 0 を返す
        self.finish(9 + self.sync_n, "0")

    def _dropdown(self, bar, label, options):
        bar.append(Gtk.Label(label=label, css_classes=["dim-label"]))
        dd = Gtk.DropDown.new_from_strings(options)
        dd.connect("notify::selected", lambda *_: (self.refilter(), self.entry.grab_focus_without_selecting()))
        bar.append(dd)
        return dd

    def _row_widget(self, r):
        box = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4, margin_start=6, margin_end=6)
        if not self.entries:
            box.append(Gtk.Label(label=r.line, use_markup=True, xalign=0, hexpand=True,
                                 ellipsize=3))
            return box
        folder, name, user = r.key
        name_l = Gtk.Label(xalign=0, ellipsize=3, width_chars=24, max_width_chars=40)
        name_l.set_markup(f"<b>{html.escape(name)}</b>")
        box.append(name_l)
        box.append(Gtk.Label(label=user, xalign=0, hexpand=True, ellipsize=3))
        if r.site:
            box.append(Gtk.Label(label=tr("このサイト", "this site"), css_classes=["bw-badge"]))
        box.append(Gtk.Label(label=folder, xalign=1, css_classes=["bw-dim"], ellipsize=3, max_width_chars=20))
        box.append(Gtk.Label(label=TYPE_NAMES.get(r.kind, ""), xalign=1, width_chars=8, css_classes=["bw-dim"]))
        return box

    # ---- 絞り込み ----
    def _visible(self, lrow):
        r = self.rows[lrow.get_index()]
        if self.kind_dd is not None:
            kind = self.kind_values[self.kind_dd.get_selected()]
            folder = self.folder_values[self.folder_dd.get_selected()]
            if kind is not None and r.kind != kind:
                return False
            if folder is not None and r.key[0] != folder:
                return False
        return all(w in r.text for w in self.entry.get_text().lower().split())

    def visible_rows(self):
        out, i = [], 0
        while (lrow := self.listbox.get_row_at_index(i)) is not None:
            if lrow.get_child_visible() and self._visible(lrow):
                out.append(lrow)
            i += 1
        return out

    def refilter(self):
        self.listbox.invalidate_filter()
        vis = self.visible_rows()
        self.count.set_label(f"{len(vis)}")
        cur = self.listbox.get_selected_row()
        if vis and (cur is None or cur not in vis):
            self.listbox.select_row(vis[0])

    def move(self, d):
        vis = self.visible_rows()
        if not vis:
            return
        cur = self.listbox.get_selected_row()
        i = vis.index(cur) if cur in vis else 0
        nxt = vis[max(0, min(len(vis) - 1, i + d))]
        self.listbox.select_row(nxt)
        nxt.grab_focus()
        self.entry.grab_focus_without_selecting()

    # ---- キー ----
    def on_key(self, _ctrl, keyval, _code, state):
        name = Gdk.keyval_name(keyval) or ""
        mods = state & MOD_MASK
        low = Gdk.keyval_to_lower(keyval)
        for n, (kmods, kval) in self.keys:
            if mods == (kmods & MOD_MASK) and low == kval:
                if n == self.sync_n:
                    self.sync()          # 同期は、行が選ばれていなくても（一覧が空でも）できる
                else:
                    self.choose(9 + n)
                return True
        if mods == Gdk.ModifierType.ALT_MASK and self.kind_dd is not None and low in (Gdk.KEY_k, Gdk.KEY_f):
            (self.kind_dd if low == Gdk.KEY_k else self.folder_dd).activate()
            return True
        if mods:
            return False
        if name == "Escape":
            self.finish(1, "")
            return True
        if name in ("Down", "Up", "Page_Down", "Page_Up"):
            self.move({"Down": 1, "Up": -1, "Page_Down": 10, "Page_Up": -10}[name])
            return True
        return False

    # ---- 終了 ----
    def choose(self, code):
        lrow = self.listbox.get_selected_row()
        if lrow is None or lrow not in self.visible_rows():
            return
        r = self.rows[lrow.get_index()]
        self.finish(code, str(r.index) if self.opts["format_index"] else r.line)

    def finish(self, code, out):
        self.result = (code, out)
        self.win.set_visible(False)
        self.app.quit()


APP_ID = "local.bwautotype.list"


def activate_own_window():
    # 題名ではなく wm_class で探す（Bitwarden のデスクトップアプリも題名が「Bitwarden」のため）
    for w in bw.windows():
        if w.get("wm_class") == APP_ID and not w.get("focus"):
            bw.run(["busctl", "--user", "call", "org.gnome.Shell", "/org/gnome/Shell/Extensions/Windows",
                    "org.gnome.Shell.Extensions.Windows", "Activate", "u", str(w["id"])])


def main(argv):
    opts = parse_args(argv)
    lines = [line for line in sys.stdin.read().split("\n") if line.strip()]
    entries = opts["format_index"]
    rows = load_rows(lines, entries)
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    holder = {}

    def activate(a):
        holder["sel"] = Selector(a, opts, rows, entries)
        # ショートカットから起動したとき前面に来ないことがあるので、念のため Window Calls で前面にする
        GLib.timeout_add(250, lambda: (activate_own_window(), False)[1])

    app.connect("activate", activate)
    app.run([])
    code, out = holder["sel"].result if "sel" in holder else (1, "")
    if code != 1:
        print(out)
    return code
