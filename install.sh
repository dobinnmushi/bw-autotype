#!/bin/sh
# bw-autotype を使える状態にする。何度実行してもよい（既にあるものは上書きせず、そろえるだけ）。
#   ./install.sh                 リンク・ランチャー・ショートカット・設定ファイルをそろえる
#   ./install.sh --build-dotool  上に加えて dotool をソースからビルドして ~/.local/bin に入れる
#   ./install.sh --chrome        上に加えて、アドレスバーを読めるようにした Chrome 系のランチャーを作る
#   ./install.sh --ssh           上に加えて、保管庫の SSH キーで署名する bw-ssh-agent を動かし、SSH_AUTH_SOCK をそこへ向ける
# オプションは並べて指定できる。
# 事前に必要なもの（sudo が要るものを含む）は README の「導入」（Installation）を参照。
set -eu
R=$(cd "$(dirname "$0")" && pwd)
today=$(date +%Y%m%d)
msg() { # msg <日本語> <English>（LANG が ja なら日本語）
    case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in ja*) echo "$1";; *) echo "$2";; esac
}

link() { # link <リポジトリ内のパス> <置き先>
    src=$R/$1 dst=$2
    mkdir -p "$(dirname "$dst")"
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        mv "$dst" "$dst.bak-$today"; msg "退避: $dst → $dst.bak-$today" "Backed up: $dst → $dst.bak-$today"
    fi
    ln -sfn "$src" "$dst"; msg "リンク: $dst → $src" "Linked: $dst → $src"
}

build_dotool=false chrome=false ssh=false
for a in "$@"; do
    case $a in
        --build-dotool) build_dotool=true;;
        --chrome) chrome=true;;
        --ssh) ssh=true;;
        *) msg "知らないオプション: $a" "Unknown option: $a"; exit 2;;
    esac
done

if $build_dotool; then
    # Go の作業場所はすべて一時ディレクトリに置き、ホームを汚さない
    tmp=$(mktemp -d); trap 'chmod -R u+w "$tmp"; rm -rf "$tmp"' EXIT
    git clone -q https://git.sr.ht/~geb/dotool "$tmp/dotool"
    (cd "$tmp/dotool" && GOPATH=$tmp/gopath GOMODCACHE=$tmp/gomod GOCACHE=$tmp/gocache \
        go build -ldflags "-X main.Version=$(git describe --long --abbrev=12 --tags)")
    install -m755 "$tmp/dotool/dotool" "$tmp/dotool/dotoolc" "$tmp/dotool/dotoold" "$HOME/.local/bin/"
    v=$("$HOME/.local/bin/dotool" --version)
    msg "dotool を ~/.local/bin に入れました: $v" "Installed dotool to ~/.local/bin: $v"
fi

# ---- スクリプトと設定（リンク）----
link bin/bw-autotype             "$HOME/.local/bin/bw-autotype"
link bin/bw-new                  "$HOME/.local/bin/bw-new"
link bin/pinentry-gnome3-nograb  "$HOME/.local/bin/pinentry-gnome3-nograb"
link bin/bw-ssh-agent            "$HOME/.local/bin/bw-ssh-agent"
link lib                         "$HOME/.local/lib/bw-autotype"
link config/rofi-rbw.rc          "${XDG_CONFIG_HOME:-$HOME/.config}/rofi-rbw.rc"
link config/bw-autotype.rasi     "${XDG_CONFIG_HOME:-$HOME/.config}/rofi/themes/bw-autotype.rasi"

# ---- 設定ファイル（なければ見本を写す。リンクにしないのは、利用者が書き換えるため）----
conf=${XDG_CONFIG_HOME:-$HOME/.config}/bw-autotype/config.toml
if [ ! -e "$conf" ]; then
    mkdir -p "$(dirname "$conf")"; cp "$R/config/config.example.toml" "$conf"; msg "設定ファイル: $conf" "Config file: $conf"
fi

# ---- ランチャー（ホームのパスを埋め込んで生成）----
for n in bw-autotype bw-new; do
    dst=$HOME/.local/share/applications/$n.desktop
    mkdir -p "$(dirname "$dst")"
    sed "s|@HOME@|$HOME|g" "$R/applications/$n.desktop.in" > "$dst"
    msg "ランチャー: $dst" "Launcher: $dst"
done

# ---- Chrome 系（--chrome）----
# アドレスバーを AT-SPI で読むには --force-renderer-accessibility が要る。システムのランチャーを
# ~/.local/share/applications に写して、起動の指定にそれを足す（同じ名前のものがあればそちらが使われる）。
# 目印の X-BwAutotype 行があるものだけを作り直し・削除の対象にする。
if $chrome; then
    found=false
    for src in /usr/share/applications/google-chrome.desktop /usr/share/applications/chromium.desktop \
               /var/lib/snapd/desktop/applications/chromium_chromium.desktop \
               /usr/share/applications/brave-browser.desktop; do
        [ -r "$src" ] || continue
        found=true
        dst=$HOME/.local/share/applications/$(basename "$src")
        if [ -e "$dst" ] && ! grep -q '^X-BwAutotype=' "$dst"; then
            msg "そのまま: $dst（自分で置いたランチャーがあるため。起動の指定に --force-renderer-accessibility を足してください）" \
                "Skipped: $dst (you have your own launcher; add --force-renderer-accessibility to its Exec lines)"
            continue
        fi
        mkdir -p "$(dirname "$dst")"
        sed -E -e '/^Exec=/{/--force-renderer-accessibility/!s|^(Exec=[^ ]+)|\1 --force-renderer-accessibility|}' \
            -e '/^\[Desktop Entry\]$/a X-BwAutotype=true' "$src" > "$dst"
        msg "ランチャー: $dst（ブラウザを終了して開き直すと効きます）" "Launcher: $dst (quit and reopen the browser to apply)"
    done
    $found || msg "Chrome 系のブラウザが見つかりませんでした" "No Chrome-based browser found"
fi

# ---- SSH エージェント（--ssh）----
# 他の SSH エージェントのソケットと同じく、systemd のソケットが起動したときに SSH_AUTH_SOCK を設定する。
# GNOME のアプリはログインのときの値を受け継ぐので、効くのは次にログインし直してから。
if $ssh; then
    units=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
    mkdir -p "$units"
    cp "$R/systemd/bw-ssh-agent.socket" "$R/systemd/bw-ssh-agent.service" "$units/"
    systemctl --user daemon-reload
    systemctl --user enable --now bw-ssh-agent.socket >/dev/null 2>&1
    systemctl --user restart bw-ssh-agent.socket
    msg "SSH エージェント: SSH_AUTH_SOCK=\$XDG_RUNTIME_DIR/bw-ssh-agent/socket（ログインし直すと、すべてのアプリで効く）" \
        "SSH agent: SSH_AUTH_SOCK=\$XDG_RUNTIME_DIR/bw-ssh-agent/socket (log in again for all apps to use it)"
fi

# ---- ショートカット（既存のショートカットは消さず、足すだけ。キーは設定ファイルの [hotkeys]）----
# GNOME: gsettings のカスタムショートカット。KDE: ランチャーの X-KDE-Shortcuts と kglobalaccel への登録。
# どちらの環境も入っていれば両方に登録する（もう一方に切り替えたときも使えるように）。
python3 -I - "$HOME" "$R/lib" <<'EOF'
import ast, os, re, subprocess, sys
home = sys.argv[1]
sys.path.insert(0, sys.argv[2])
import bwcommon as bw
hk = bw.CONFIG["hotkeys"]
keys = [("bw-autotype", bw.tr("Bitwarden 自動入力", "Bitwarden Autotype"), f"{home}/.local/bin/bw-autotype", hk["autotype"]),
        ("bw-new", bw.tr("Bitwarden 新規登録", "Bitwarden New Login"), f"{home}/.local/bin/bw-new", hk["new"])]

K = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
if K in bw.run(["gsettings", "list-schemas"]).stdout.split():
    cur = ast.literal_eval(bw.run(["gsettings", "get", K, "custom-keybindings"]).stdout.strip().removeprefix("@as "))
    for kid, name, cmd, binding in keys:
        path = f"{BASE}{kid}/"
        schema = f"{K}.custom-keybinding:{path}"
        for k, v in (("name", name), ("command", cmd), ("binding", binding)):
            subprocess.run(["gsettings", "set", schema, k, v], check=True)
        if path not in cur:
            cur.append(path)
        print(bw.tr("ショートカット（GNOME）: ", "Hotkey (GNOME): ") + f"{binding} → {name}")
    subprocess.run(["gsettings", "set", K, "custom-keybindings", str(cur)], check=True)

if bw.run(["busctl", "--user", "status", "org.kde.kglobalaccel"]).returncode == 0:
    for kid, name, cmd, binding in keys:
        conv = bw.kde_shortcut(binding)
        if not conv:
            print(bw.tr(f"ショートカット（KDE）: {binding} は変換できないので、システム設定で割り当ててください",
                        f"Hotkey (KDE): cannot convert {binding}; assign it in System Settings"))
            continue
        label, code = conv
        desktop = f"{home}/.local/share/applications/{kid}.desktop"
        with open(desktop, encoding="utf-8") as f:
            text = re.sub(r"^X-KDE-Shortcuts=.*\n?", "", f.read(), flags=re.M).rstrip("\n")
        with open(desktop, "w", encoding="utf-8") as f:
            f.write(f"{text}\nX-KDE-Shortcuts={label}\n")
        bw.run(["kbuildsycoca6"])
        # KDE のショートカット設定と同じ DBus の呼び出し（フラグ 6 = SetPresent | NoAutoloading。後者は、前に
        # 失敗したときにデーモンが覚えた「割り当てなし」を読み戻させないため）。戻り値が 0 なら、そのキーは他の操作が使っている
        r = bw.run(["busctl", "--user", "call", "org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel",
                    "setShortcut", "asaiu", "4", f"{kid}.desktop", "_launch", name, name, "1", str(code), "6"])
        if r.stdout.split()[-1:] == [str(code)]:
            print(bw.tr("ショートカット（KDE）: ", "Hotkey (KDE): ") + f"{label} → {name}")
        else:
            print(bw.tr(f"ショートカット（KDE）: {label} は他の操作が使っているため、{name} には割り当てていません。"
                        "システム設定 → キーボード → ショートカットで、使っている側を外すか、別のキーを割り当ててください",
                        f"Hotkey (KDE): {label} is used by another action, so {name} was not bound. "
                        "In System Settings → Keyboard → Shortcuts, free that key or pick another"))
EOF

# ---- 設定 ----
# Firefox のアドレスバーを AT-SPI で読むため（反映には Firefox の再起動が要る）
gsettings set org.gnome.desktop.interface toolkit-accessibility true
msg "設定: toolkit-accessibility = true" "Set: toolkit-accessibility = true"
# rbw の設定は書き換えない（rbw config set は rbw-agent を止めて保管庫をロックするうえ、好みが分かれるため）。
# 勧める値と違うときだけ、変え方を表示する。
if command -v rbw >/dev/null 2>&1; then
    cfg=$(rbw config show 2>/dev/null || echo '{}')
    want_pin=$HOME/.local/bin/pinentry-gnome3-nograb
    echo "$cfg" | grep -q "\"pinentry\": \"$want_pin\"" || \
        msg "おすすめ: rbw config set pinentry $want_pin   # 画面を暗転させない pinentry" \
            "Recommended: rbw config set pinentry $want_pin   # pinentry that does not dim the screen"
    echo "$cfg" | grep -q '"lock_timeout": 3600\b' && \
        msg "おすすめ（任意）: rbw config set lock_timeout 28800   # 自動ロックまでの秒数（既定は 1時間）" \
            "Optional: rbw config set lock_timeout 28800   # seconds until auto-lock (default 1 hour)"
fi

# ---- 足りないものの確認 ----
missing=""
for c in rbw rbw-agent rofi-rbw dotool notify-send busctl; do
    command -v "$c" >/dev/null 2>&1 || missing="$missing $c"
done
gnome-extensions info window-calls@domandoman.xyz 2>/dev/null | grep -q 'ACTIVE' || missing="$missing window-calls(GNOME-extension)"
python3 -I -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("Atspi","2.0")' 2>/dev/null \
    || missing="$missing GTK4/Adw/Atspi(PyGObject)"
[ -r /usr/share/publicsuffix/public_suffix_list.dat ] || \
    msg "任意: publicsuffix（apt）があると、URL からの項目の絞り込みが正確になります" \
        "Optional: install publicsuffix (apt) for more accurate filtering by URL"
[ -w /dev/uinput ] || missing="$missing /dev/uinput(write-permission)"
if [ -n "$missing" ]; then
    msg "足りないもの:$missing（README の「導入」を参照）" "Missing:$missing (see Installation in the README)"
else
    msg "必要なものはそろっています" "All requirements are present"
fi
