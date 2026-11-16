"""bw-autotype と bw-new の共通部分。

- 設定ファイル（~/.config/bw-autotype/config.toml）と表示の言語
- PATH の用意（rofi の中継スクリプト・rbw・dotool・rofi-rbw）
- 通知、本人確認（指紋 → だめならマスターパスワード）
- 前面ウィンドウの取得（Window Calls 拡張）
- キーボード配列の判別と、入力中だけ IBus を素の配列にすること
- rofi-rbw の使用回数ファイルと「直前に使った項目」の記録
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import tomllib

HOME = os.path.expanduser("~")
CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config"
CACHE_HOME = os.environ.get("XDG_CACHE_HOME") or f"{HOME}/.cache"
CONFIG_FILE = f"{CONFIG_HOME}/bw-autotype/config.toml"
RC_FILE = f"{CONFIG_HOME}/rofi-rbw.rc"
RUNCACHE = f"{CACHE_HOME}/rofi-rbw.runcache"          # rofi-rbw が書く「回数 項目のハッシュ」
STATE_DIR = f"{os.environ.get('XDG_RUNTIME_DIR') or '/run/user/%d' % os.getuid()}/bw-autotype"
LAST_FILE = f"{STATE_DIR}/last"                        # 直前に使った項目のハッシュと時刻（ログアウトで消える）
LIB_DIR = os.path.dirname(os.path.abspath(__file__))

def run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not found")


def log(text):
    """journal に記録する（`journalctl -t bw-autotype` で見られる）。認証情報は渡さないこと。"""
    run(["logger", "-t", "bw-autotype", text])


# ---- 設定 ----
# 既定値。config.toml に書いたものだけが上書きされる（書式は config/config.example.toml）
DEFAULTS = {
    "language": "auto",                 # auto（LANG を見る）| ja | en
    "keyboard": {
        "layout": "auto",               # dotool に渡す XKB 配列。auto は IBus・GNOME の入力ソースから判別
        "variant": "",
        "plain_ibus_engine": "auto",    # 入力中に切り替える IBus エンジン。"" なら切り替えない
    },
    "hotkeys": {"autotype": "<Super><Alt>p", "new": "<Super><Alt>n"},
    "auth": {
        "method": "auto",               # fingerprint | none | auto（指紋が登録されていれば fingerprint）
        "fingerprint_tries": 3,
        "fingerprint_timeout": 15,      # 1回の指紋照合を待つ秒数
    },
    "autotype": {
        "recent_seconds": 300,          # この秒数以内に使った項目を一覧の先頭に置く
        "settle_seconds": 0.1,          # 元のウィンドウが前面に戻ってから打ち始めるまでの待ち（一覧が閉じた直後の1回だけ）
        "clear_clipboard_seconds": 30,  # コピーしてからクリップボードを消すまでの秒数（0 なら消さない）
        "help": "full",                 # 一覧の下のキー説明: full（列に並べる）| line（1行）| none
        "selector": "gtk",              # 一覧の画面: gtk（種類・フォルダで絞れる自作の一覧）| rofi
    },
    "ssh": {
        "confirm_seconds": 30,          # SSH の署名で一度確認したら、この秒数は確認なしで署名する（0 なら毎回）
    },
    "new": {
        "keys": "standard",             # standard | vim
        "kind": "symbols",              # symbols | alnum | passphrase | pin | ssh
        "password_length": 20,
        "passphrase_words": 6,
        "pin_digits": 6,
        "finish": "once",               # once | twice | none
    },
}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


def load_config():
    try:
        with open(CONFIG_FILE, "rb") as f:
            return _merge(DEFAULTS, tomllib.load(f))
    except FileNotFoundError:
        return DEFAULTS
    except (OSError, tomllib.TOMLDecodeError) as e:
        log(f"config: {e}")
        return DEFAULTS


CONFIG = load_config()
SETTLE_SECONDS = float(CONFIG["autotype"]["settle_seconds"])


def _japanese():
    lang = CONFIG["language"]
    if lang in ("ja", "en"):
        return lang == "ja"
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return loc.startswith("ja")


JA = _japanese()


def tr(ja, en):
    """表示の言語に合わせて ja か en を返す。"""
    return ja if JA else en


def hotkey_label(binding):
    """GNOME の書式（<Super><Alt>p）を表示用（Super+Alt+P）にする。"""
    mods = re.findall(r"<(\w+)>", binding)
    key = re.sub(r"<\w+>", "", binding)
    return "+".join([*mods, key.upper() if len(key) == 1 else key])


APP_NAME = tr("Bitwarden 自動入力", "Bitwarden Autotype")

# ショートカットやドックから起動したときも rbw・dotool・rofi-rbw が見つかるように。
# 先頭のこのディレクトリには rofi・dotool の中継スクリプトがある。
os.environ["PATH"] = ":".join([LIB_DIR, f"{HOME}/.local/bin", os.environ.get("PATH", "")])


def which_real(cmd):
    """中継スクリプト（このディレクトリ）を除いた PATH から cmd を探す。"""
    path = ":".join(p for p in os.environ["PATH"].split(":") if os.path.abspath(p) != LIB_DIR)
    return shutil.which(cmd, path=path)


# ---- 通知 ----
def notify(text, replace=None, urgent=False):
    cmd = ["notify-send", "-p", "-a", APP_NAME, "-i", "dialog-password", "-t", "20000"]
    if urgent:
        cmd += ["-u", "critical"]
    if replace:
        cmd += ["-r", str(replace)]
    r = run(cmd + [APP_NAME, text])
    return r.stdout.strip() or replace


def close_notification(nid):
    if nid:
        run(["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
             "--object-path", "/org/freedesktop/Notifications",
             "--method", "org.freedesktop.Notifications.CloseNotification", str(nid)])


# ---- 本人確認 ----
def fingerprint_enrolled():
    r = run(["fprintd-list", os.environ.get("USER") or str(os.getuid())])
    return r.returncode == 0 and re.search(r"^\s*-\s*#\d+:", r.stdout, re.M) is not None


def verify_fingerprint(reason=None):
    """指紋が一致すれば True。センサーが使えない・一致しない・時間切れなら False。reason は通知の1行目に添える。"""
    tries = int(CONFIG["auth"]["fingerprint_tries"])
    touch = tr("指紋センサーに触れてください", "Touch the fingerprint sensor")
    nid = notify(f"{reason}\n{touch}" if reason else touch)
    try:
        for left in range(tries - 1, -1, -1):
            try:
                r = run(["fprintd-verify"], timeout=float(CONFIG["auth"]["fingerprint_timeout"]))
            except subprocess.TimeoutExpired:
                log("fingerprint: timeout")
                return False
            out = r.stdout + r.stderr
            results = [line.strip() for line in out.splitlines() if "result" in line.lower() or "error" in line.lower()]
            log(f"fingerprint: exit={r.returncode} {' / '.join(results)[-300:]}")
            if "verify-match" in out:
                return True
            if "verify-no-match" in out and left:
                nid = notify(tr(f"指紋が一致しません。もう一度触れてください（残り {left} 回）",
                                f"No match. Touch the sensor again ({left} left)"), replace=nid)
                continue
            return False
        return False
    finally:
        close_notification(nid)


def auth_method():
    m = CONFIG["auth"]["method"]
    if m == "auto":
        return "fingerprint" if fingerprint_enrolled() else "none"
    return m


def authorize(reason=None):
    """先へ進んでよければ True。reason（何のための確認か）は通知に添える。"""
    if run(["rbw", "unlocked"]).returncode != 0:
        # ロック中：マスターパスワードで解除（pinentry のダイアログ）。それ自体が本人確認になる
        log("auth: vault locked, unlocking with the master password")
        nid = notify(reason) if reason else None
        ok = subprocess.run(["rbw", "unlock"]).returncode == 0
        close_notification(nid)
        return ok
    if auth_method() != "fingerprint":
        log("auth: vault unlocked, no fingerprint check (auth.method)")
        return True
    if verify_fingerprint(reason):
        log("auth: fingerprint ok")
        return True
    log("auth: fingerprint failed, falling back to the master password")
    # 指紋が使えないときは、マスターパスワードより弱い経路にしないよう、ロックし直して聞く
    nid = notify(tr("指紋を確認できなかったため、マスターパスワードで確認します",
                    "Fingerprint not verified. Asking for the master password instead"))
    run(["rbw", "lock"])
    ok = subprocess.run(["rbw", "unlock"]).returncode == 0
    close_notification(nid)
    return ok


# ---- 前面ウィンドウ ----
def windows():
    r = run(["busctl", "--user", "--json=short", "call", "org.gnome.Shell",
             "/org/gnome/Shell/Extensions/Windows",
             "org.gnome.Shell.Extensions.Windows", "List"])
    if r.returncode != 0:
        return []
    try:
        return json.loads(json.loads(r.stdout)["data"][0])
    except (ValueError, KeyError, IndexError):
        return []


def focused_window():
    """前面ウィンドウの {id, wm_class, title}。取れなければ空の dict。"""
    for w in windows():
        if w.get("focus"):
            return {"id": w.get("id"), "wm_class": w.get("wm_class") or "", "title": w.get("title") or ""}
    return {}


def wait_focus(win_id, seconds=3.0):
    """win_id のウィンドウが前面に戻るまで待つ。戻れば True。"""
    end = time.time() + seconds
    while time.time() < end:
        if focused_window().get("id") == win_id:
            return True
        time.sleep(0.1)
    return False


# ---- ブラウザの表示中のページ ----
# wm_class の先頭 → AT-SPI でのアプリ名
BROWSERS = {"firefox": "Firefox", "google-chrome": "Google Chrome", "chromium": "Chromium",
            "brave-browser": "Brave Browser"}
BROWSER_SUFFIX = re.compile(r"\s+[—-]\s+(Mozilla Firefox|Google Chrome|Chromium|Brave)$")


def browser_app(win):
    """前面のウィンドウがアドレスバーを読めるブラウザなら、その AT-SPI でのアプリ名。違えば None。"""
    cls = win.get("wm_class", "").lower()
    return next((app for prefix, app in BROWSERS.items() if cls.startswith(prefix)), None)


def page_title(win):
    """ウィンドウの題名から「 — Mozilla Firefox」などのブラウザ名を除いたもの。"""
    return BROWSER_SUFFIX.sub("", win.get("title", "")).strip()


def browser_host(win):
    """前面のブラウザのウィンドウのアドレスバーからホスト名を取る。

    アクセシビリティ（AT-SPI）で読む。Firefox は GNOME の toolkit-accessibility が有効な状態で、
    Chrome 系は --force-renderer-accessibility を付けて起動している必要がある（install.sh --chrome）。
    取れなければ None。ページ本文の中には入らない。
    """
    import urllib.parse
    app_name = browser_app(win)
    if not app_name:
        return None
    title = win.get("title", "")
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        return None
    try:
        desk = Atspi.get_desktop(0)
        apps = [desk.get_child_at_index(i) for i in range(desk.get_child_count())]
        wins = []
        for app in apps:
            if app and (app.get_name() or "") == app_name:
                wins += [app.get_child_at_index(w) for w in range(app.get_child_count())]
        wins = [w for w in wins if w and (w.get_name() or "") == title] or \
               [w for w in wins if w and w.get_state_set().contains(Atspi.StateType.ACTIVE)]
        for win in wins[:1]:
            stack = [(win, 0)]
            while stack:
                node, depth = stack.pop()
                role = node.get_role_name()
                if role in ("document web", "document frame"):
                    continue
                if role in ("combo box", "entry"):
                    t = node.get_text_iface()
                    s = Atspi.Text.get_text(t, 0, Atspi.Text.get_character_count(t)) if t else ""
                    s = s.strip()
                    if s and " " not in s and "." in s:
                        # 表示上は https:// を省くことがある（途中の ?continue=https://… は先頭ではないので見ない）
                        has_scheme = re.match(r"[a-z][a-z0-9+.-]*://", s, re.I)
                        host = urllib.parse.urlsplit(s if has_scheme else "https://" + s).hostname
                        if host:
                            return host
                if depth < 8:
                    stack += [(node.get_child_at_index(k), depth + 1) for k in range(node.get_child_count())]
    except Exception:  # noqa: BLE001  アクセシビリティ側の不具合で本体を止めない
        return None
    return None


PSL_FILE = "/usr/share/publicsuffix/public_suffix_list.dat"   # Debian/Ubuntu の publicsuffix パッケージ
_psl = None


def _public_suffixes():
    global _psl
    if _psl is None:
        _psl = set()
        try:
            with open(PSL_FILE, encoding="utf-8") as f:
                _psl = {line.strip() for line in f if line.strip() and not line.startswith("//")}
        except OSError:
            pass
    return _psl


def base_domain(host):
    """ホスト名から登録ドメインを取る（例: accounts.google.com → google.com、www.example.co.uk → example.co.uk）。

    Public Suffix List があればそれで判定し、なければ「2文字の国コードの前の短い語」を接尾辞とみなす。
    """
    parts = host.lower().removeprefix("www.").split(".")
    psl = _public_suffixes()
    if psl:
        for i in range(len(parts)):
            suffix = ".".join(parts[i:])
            wild = ".".join(["*", *parts[i + 1:]])
            if f"!{suffix}" in psl:
                return ".".join(parts[i:])
            if suffix in psl or (i + 1 < len(parts) and wild in psl):
                return ".".join(parts[max(0, i - 1):])
        return ".".join(parts[-2:])
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"ac", "co", "ne", "or", "go", "ed", "lg", "gr", "com", "net", "org"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ---- キーボード配列と IME ----
def _ibus():
    try:
        import gi
        gi.require_version("IBus", "1.0")
        from gi.repository import IBus
        bus = IBus.Bus()
        return (IBus, bus) if bus.is_connected() else (None, None)
    except (ImportError, ValueError):
        return None, None


def current_ibus_engine():
    r = run(["ibus", "engine"])
    return r.stdout.strip() if r.returncode == 0 else ""


def _gnome_xkb():
    """GNOME の入力ソースのうち最初の xkb のもの（"jp"、"us+dvorak" など）。なければ ""。"""
    r = run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"])
    m = re.search(r"\('xkb', '([^']+)'\)", r.stdout)
    return m.group(1) if m else ""


def detect_layout():
    """(配列, variant)。今の IBus エンジンの配列 → GNOME の入力ソース → us の順に見る。"""
    kb = CONFIG["keyboard"]
    if kb["layout"] != "auto":
        return kb["layout"], kb["variant"]
    _, bus = _ibus()
    engine = current_ibus_engine()
    if bus and engine:
        descs = bus.get_engines_by_names([engine])
        if descs and descs[0].get_layout() not in ("", "default"):
            return descs[0].get_layout(), descs[0].get_layout_variant() or ""
    layout, _, variant = _gnome_xkb().partition("+")
    return (layout, variant) if layout else ("us", "")


def plain_engine(layout, variant):
    """入力中に使う IBus エンジン（配列そのままのもの）。見つからなければ ""。"""
    want = CONFIG["keyboard"]["plain_ibus_engine"]
    if want != "auto":
        return want
    _, bus = _ibus()
    if not bus:
        return ""
    names = [e.get_name() for e in bus.list_engines()]
    prefix = f"xkb:{layout}:{variant}:"
    return next((n for n in names if n.startswith(prefix)), "")


@contextlib.contextmanager
def plain_ime(layout, variant):
    """この中にいる間だけ IBus を素の配列にし、出るときに元へ戻す（IBus がなければ何もしない）。"""
    engine = current_ibus_engine()
    plain = plain_engine(layout, variant) if engine and not engine.startswith("xkb:") else ""
    switch = bool(plain) and engine != plain
    if switch:
        run(["ibus", "engine", plain])
    try:
        yield
    finally:
        if switch:
            run(["ibus", "engine", engine])


def dotool_env(layout, variant):
    env = dict(os.environ, DOTOOL_XKB_LAYOUT=layout)
    if variant:
        env["DOTOOL_XKB_VARIANT"] = variant
    return env


# ---- rofi-rbw の使用回数と直前の項目 ----
def entry_hash(name, folder, username):
    """rofi-rbw の Entry.hashed と同じ計算（名前 + フォルダ + ユーザー名の SHA-1）。"""
    m = hashlib.sha1()
    m.update(name.encode())
    if folder:
        m.update(folder.encode())
    if username:
        m.update(username.encode())
    return m.hexdigest()


def read_runcache():
    """[(行, ハッシュ, 回数)]。ファイルがなければ空。"""
    try:
        with open(RUNCACHE, encoding="utf-8") as f:
            rows = []
            for line in f:
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    rows.append((line if line.endswith("\n") else line + "\n", parts[1].strip(), int(parts[0])))
            return rows
    except OSError:
        return []


def write_runcache(rows):
    os.makedirs(os.path.dirname(RUNCACHE), exist_ok=True)
    with open(RUNCACHE, "w", encoding="utf-8") as f:
        f.writelines(r[0] for r in rows)


def recent_hash():
    try:
        with open(LAST_FILE, encoding="utf-8") as f:
            h, t = f.read().split()
        return h if time.time() - float(t) <= float(CONFIG["autotype"]["recent_seconds"]) else None
    except (OSError, ValueError):
        return None


def remember(h):
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        f.write(f"{h} {time.time()}\n")


def put_first(h, rows):
    """rofi-rbw はこのファイルの行の順に一覧を並べるので、h の行を先頭へ移す。行がなければ False。"""
    first = [r for r in rows if r[1] == h]
    if not first:
        return False
    write_runcache([first[0]] + [r for r in rows if r[1] != h])
    return True
