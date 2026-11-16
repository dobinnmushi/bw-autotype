#!/bin/sh
# bw-autotype を使える状態にする。何度実行してもよい（既にあるものは上書きせず、そろえるだけ）。
#   ./install.sh                 リンク・ランチャー・ショートカット・設定ファイルをそろえる
#   ./install.sh --build-dotool  上に加えて dotool をソースからビルドして ~/.local/bin に入れる
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

if [ "${1:-}" = "--build-dotool" ]; then
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

# ---- ショートカット（既存のカスタムショートカットは消さず、足すだけ。キーは設定ファイルの [hotkeys]）----
python3 -I - "$HOME" "$R/lib" <<'EOF'
import ast, subprocess, sys
home = sys.argv[1]
sys.path.insert(0, sys.argv[2])
import bwcommon as bw
K = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
hk = bw.CONFIG["hotkeys"]
keys = [("bw-autotype", bw.tr("Bitwarden 自動入力", "Bitwarden Autotype"), f"{home}/.local/bin/bw-autotype", hk["autotype"]),
        ("bw-new", bw.tr("Bitwarden 新規登録", "Bitwarden New Login"), f"{home}/.local/bin/bw-new", hk["new"])]
cur = ast.literal_eval(subprocess.run(["gsettings", "get", K, "custom-keybindings"],
                                      capture_output=True, text=True).stdout.strip().removeprefix("@as "))
for kid, name, cmd, binding in keys:
    path = f"{BASE}{kid}/"
    schema = f"{K}.custom-keybinding:{path}"
    for k, v in (("name", name), ("command", cmd), ("binding", binding)):
        subprocess.run(["gsettings", "set", schema, k, v], check=True)
    if path not in cur:
        cur.append(path)
    print(bw.tr("ショートカット: ", "Hotkey: ") + f"{binding} → {name}")
subprocess.run(["gsettings", "set", K, "custom-keybindings", str(cur)], check=True)
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
for c in rbw rbw-agent rofi-rbw rofi dotool notify-send busctl; do
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
