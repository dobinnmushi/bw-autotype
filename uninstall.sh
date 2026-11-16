#!/bin/sh
# install.sh で入れたもの（リンク・ランチャー・ショートカット）を外す。
# 設定ファイル・rbw の設定・アクセシビリティ・apt で入れたもの・udev 規則・GNOME 拡張は自動では戻さない（最後に戻し方を表示）。
set -eu
R=$(cd "$(dirname "$0")" && pwd)
msg() { # msg <日本語> <English>（LANG が ja なら日本語）
    case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in ja*) echo "$1";; *) echo "$2";; esac
}

unlink_if_ours() { # リポジトリを指すリンクのときだけ消す
    dst=$1
    if [ -L "$dst" ] && case "$(readlink "$dst")" in "$R"/*) true;; *) false;; esac; then
        rm "$dst"; msg "削除: $dst" "Removed: $dst"
    fi
}
unlink_if_ours "$HOME/.local/bin/bw-autotype"
unlink_if_ours "$HOME/.local/bin/bw-new"
unlink_if_ours "$HOME/.local/bin/pinentry-gnome3-nograb"
unlink_if_ours "$HOME/.local/bin/bw-ssh-agent"
unlink_if_ours "$HOME/.local/lib/bw-autotype"
unlink_if_ours "${XDG_CONFIG_HOME:-$HOME/.config}/rofi-rbw.rc"
unlink_if_ours "${XDG_CONFIG_HOME:-$HOME/.config}/rofi/themes/bw-autotype.rasi"
# install.sh --ssh で入れた SSH エージェント（止めると SSH_AUTH_SOCK の設定も外れる）
units=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
if [ -e "$units/bw-ssh-agent.socket" ]; then
    systemctl --user disable --now bw-ssh-agent.socket bw-ssh-agent.service 2>/dev/null || true
    rm -fv "$units/bw-ssh-agent.socket" "$units/bw-ssh-agent.service"
    systemctl --user daemon-reload
fi
rm -fv "$HOME/.local/share/applications/bw-autotype.desktop" "$HOME/.local/share/applications/bw-new.desktop"
# install.sh --chrome で作った Chrome 系のランチャー（目印の行があるものだけ）
for f in "$HOME"/.local/share/applications/*.desktop; do
    [ -f "$f" ] && grep -q '^X-BwAutotype=' "$f" && { rm "$f"; msg "削除: $f" "Removed: $f"; }
done

# ショートカット: 自分の2つだけをリストから外し、中身を消す（他のカスタムショートカットはそのまま）
python3 -I - <<'PY'
import ast, os, subprocess
K = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
mine = [f"{BASE}bw-autotype/", f"{BASE}bw-new/"]
cur = ast.literal_eval(subprocess.run(["gsettings", "get", K, "custom-keybindings"],
                                      capture_output=True, text=True).stdout.strip().removeprefix("@as "))
subprocess.run(["gsettings", "set", K, "custom-keybindings", str([p for p in cur if p not in mine])], check=True)
for p in mine:
    for k in ("name", "command", "binding"):
        subprocess.run(["gsettings", "reset", f"{K}.custom-keybinding:{p}", k])
ja = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "").startswith("ja")
print("ショートカットを外しました" if ja else "Removed the hotkeys")
PY

msg "自動では戻していないもの（必要なら手で）:" "Not reverted automatically (undo by hand if you want):"
cat <<'EOF2'
  config              rm -r ~/.config/bw-autotype
  rbw config          rbw config unset pinentry ; rbw config set lock_timeout 3600
  accessibility       gsettings set org.gnome.desktop.interface toolkit-accessibility false
  rbw data            rbw purge ; rbw stop-agent ; rm -r ~/.config/rbw ~/.cache/rbw ~/.local/share/rbw
  rofi-rbw            pipx uninstall rofi-rbw
  rbw, dotool         rm ~/.local/bin/{rbw,rbw-agent,dotool,dotoolc,dotoold}
  GNOME extension     gnome-extensions uninstall window-calls@domandoman.xyz
  apt                 sudo apt remove rofi golang-go libxkbcommon-dev pipx
  udev rule           sudo rm /etc/udev/rules.d/70-uinput-uaccess.rules && sudo udevadm control --reload
EOF2
