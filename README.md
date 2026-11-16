# bw-autotype

[日本語](README.ja.md)

Type Bitwarden usernames and passwords into **any application** with a hotkey on GNOME / Wayland,
and generate and save new passwords — including places browser extensions cannot reach,
such as Firefox's `about:config`, terminals or native apps.

It is mostly a combination of existing tools glued together with thin scripts.

| Role | Tool |
|---|---|
| Vault (unofficial Bitwarden client) | [rbw](https://github.com/doy/rbw) |
| Item list, typing and copying | [rofi-rbw](https://github.com/fdw/rofi-rbw), with its list shown in a built-in GTK4 window (or rofi) |
| Sending keystrokes | [dotool](https://git.sr.ht/~geb/dotool) (uinput; follows your XKB layout, so symbols are typed correctly on non-US layouts) |
| Focused window | GNOME extension [Window Calls](https://extensions.gnome.org/extension/4724/window-calls/) |
| URL of the current page (Firefox, Chrome, Chromium, Brave) | AT-SPI (accessibility) reads the address bar |
| Identity check | fprintd (fingerprint), falling back to rbw's master password |

Developed and tested on Ubuntu 26.04 (GNOME 50 / Wayland) with a Japanese keyboard and IBus Mozc.
Other GNOME / Wayland setups should work but are less tested; reports are welcome.

## How it compares
As of 2026, Bitwarden on a GNOME/Wayland desktop leaves a gap outside the browser:

| Tool | Typing outside the browser on GNOME/Wayland | Notes |
|---|---|---|
| Bitwarden browser extension | – (browser only) | Fills web pages only. |
| Bitwarden desktop app | – | Auto-type is [requested and in progress](https://community.bitwarden.com/t/desktop-app-auto-type-windows-macos-linux/158), but the roadmap mentions only Windows and macOS. It has an [SSH agent](https://bitwarden.com/help/ssh-agent/) that can ask before signing (not in the Flatpak build). |
| [Goldwarden](https://github.com/quexten/goldwarden) | Yes (via the RemoteDesktop portal) | Its development was **paused indefinitely in August 2025**. Its author upstreamed SSH items, the SSH agent, memory protection and Linux biometric unlock into the official clients, but not auto-type; upcoming changes to Bitwarden's auth and crypto are expected to break it ([author's note](https://github.com/quexten/goldwarden/issues/331#issuecomment-3221660132)). |
| [rbw](https://github.com/doy/rbw) + [rofi-rbw](https://github.com/fdw/rofi-rbw) | Not out of the box | Works on X11 and wlroots compositors (Sway, Hyprland). On GNOME/Wayland, rofi/wofi/fuzzel need layer-shell, wtype is unsupported and ydotool assumes a US layout. rbw's built-in SSH agent signs without asking. |

bw-autotype builds on rbw and rofi-rbw and adds what is missing there: typing through dotool with your real
keyboard layout and input method (tested with a Japanese layout and Mozc), its own GTK list with type/folder
filters and the matching site first, the browser's address bar read via accessibility, a fingerprint check per
hotkey, password and SSH-key creation, and an SSH agent that asks for your fingerprint before each signature.
For passkeys see [bw-passkey](https://github.com/dobinnmushi/bw-passkey).

## Usage

### Super+Alt+P — type (`bin/bw-autotype`)
Click the field you want to fill, press the hotkey, (touch the fingerprint sensor,) pick an item.
Items that match the focused window (for browsers, the domain in the address bar; otherwise the window title
and app name) are listed first, marked "this site", and the first one is preselected; all other items stay below.
An item used within the last 5 minutes comes first of all, so "username on one page,
password on the next" is just Alt+3 the second time.
Above the filter box, two dropdowns narrow the list by type (login, card, identity, note) and by folder,
independently of each other and of the text you type (Alt+k / Alt+f open them). Each row shows its folder and type.

| Key | Action |
|---|---|
| Enter / Alt+1 | username → Tab → password |
| Alt+2 / Alt+3 / Alt+4 | username only / password only / one-time code only |
| Alt+m | pick an item, then choose what to type |
| Alt+s | sync the vault with the server |
| Alt+u / Alt+t / Alt+h | copy username / one-time code / cardholder name (cleared after 30 seconds) |

Cards: Enter types number → Tab → expiry (YYYY-MM) → Tab → code. For forms with separate month and year fields,
use Alt+m and pick "Expiry month" / "Expiry year", or give the item a custom field `_autotype` such as
`number:tab:expiry month:tab:expiry year:tab:code`.
Identities: Enter opens the menu to choose a field (name, email, phone, address, …).

The keys are the `keybindings` line in `config/rofi-rbw.rc`; the help shown below the list is built from it.
Passwords and card numbers are never copied, only typed: many clipboard history managers (for example the GNOME
extension Clipboard Indicator) ignore the "sensitive" hint and would keep them. After typing a password, rofi-rbw
copies the item's one-time code, if it has one.

### Super+Alt+N — new login (`bin/bw-new`)
On a sign-up page, click the password field, press the hotkey, (touch the sensor,) review the form and press Enter.
A password is generated, saved to the vault and typed into the field. Name and URI are prefilled from the browser's
address bar. Typing a folder name that does not exist creates it.

The form asks for the type first (password, passphrase or SSH key); only the fields below it change. For a
password, the next field chooses the characters (with symbols, letters and digits only, or digits only for PINs).

**SSH keys:** choose "SSH key (Ed25519)" as the type. The fields below the type change: username, URI and
length disappear, and the key is created when you save (`ssh-keygen` in `$XDG_RUNTIME_DIR`, removed right away),
saved to the vault as an SSH key item, and its public key is typed into the focused field (for example GitHub's
"New SSH key" box), copied, or only saved. The private key goes only to the vault.

The form works with the mouse, with standard keys (Tab / Enter / Esc), or — with `new.keys = "vim"` — modal
Vim-like keys (J/K field, j/k option, i edit, p paste, v show, r regenerate, Enter save, q cancel).

Both are also in the Activities overview as "Bitwarden Autotype" and "Bitwarden New Login".

## Settings
`~/.config/bw-autotype/config.toml` (created from [`config/config.example.toml`](config/config.example.toml) by
`install.sh`). Everything is optional:

| Section | What you can change |
|---|---|
| `language` | `auto` (from `LANG`), `ja` or `en` |
| `[keyboard]` | XKB layout for dotool and the IBus engine used while typing (both detected automatically) |
| `[hotkeys]` | the two hotkeys (run `./install.sh` again after changing) |
| `[auth]` | `fingerprint`, `none` or `auto` (fingerprint if one is enrolled) |
| `[autotype]` | how long the last item stays preselected; delay before typing; when copies are cleared; key help (`full`/`line`/`none`); list window (`gtk`/`rofi`) |
| `[ssh]` | how long one confirmation covers SSH signatures |
| `[new]` | form keys (`standard` / `vim`), default password type and lengths, what to do after saving |

rofi-rbw's own options are in `config/rofi-rbw.rc`. With `autotype.selector = "rofi"` the list is shown by rofi instead
(styled by `config/bw-autotype.rasi`, without the dropdowns; the matching word is put into the filter box).

## Security notes
- With `auth.method = "fingerprint"`, every hotkey press asks for a fingerprint. If the sensor is unavailable or
  does not match, the vault is locked again and the master password is asked — never a weaker path.
- The vault stays unlocked in rbw-agent's memory until rbw's `lock_timeout`. The fingerprint only guards the
  hotkeys: any program running as you can still run `rbw get`. Lock your screen when you leave.
- Passwords are never written to files, logs or notifications. They are passed to dotool and `rbw add` on stdin.
- Typing waits until the original window has focus again, plus `autotype.settle_seconds` before the first field.
  Keys go through a resident dotoold (started on demand, its pipe in `$XDG_RUNTIME_DIR/bw-autotype/`), which
  avoids dotool's ~0.7 s start-up for every field.
- Logs: `journalctl -t bw-autotype` (which identity check was used and whether something was saved; no secrets).

## Passkeys
For passkeys, use the companion **[bw-passkey](https://github.com/dobinnmushi/bw-passkey)**: a virtual FIDO2
security key that signs in with the passkeys in your Bitwarden vault and saves new ones there, verified with your
fingerprint. Browsers see it as a USB security key, so it works without the Bitwarden extension.

This tool itself does not handle passkeys (rbw 1.15 does not read them):
- Items that have a passkey still appear in the list as ordinary logins; there is just no passkey to use.
- `bw-new` creates password logins only. Create passkeys with bw-passkey or the browser extension.
- Neither this tool nor rofi-rbw ever calls `rbw edit`. Be careful with `rbw edit` yourself on items that have a
  passkey: rbw re-sends the item without its passkey data, which may remove the passkey (not verified).

## SSH keys (optional)
rbw-agent can sign SSH logins with the SSH keys in your vault, but it never asks before signing.
`./install.sh --ssh` puts **bw-ssh-agent** in front of it: ssh and git talk to bw-ssh-agent, which passes key
listings straight through and asks for your fingerprint (or the master password, as for typing) before each
signature. After one confirmation it signs without asking for `ssh.confirm_seconds` (30 by default), since
one git command may connect several times. The notification names the key and the remote user name (the
agent protocol does not tell which host).

It is a systemd socket that sets `SSH_AUTH_SOCK` after the OpenSSH, gcr and gpg agent sockets, the same way
they do, so it wins from the next login on. Logs: `journalctl -t bw-autotype`.

## Files
```
bin/bw-autotype              the type hotkey (calls rofi-rbw)
bin/bw-new                   the new-login hotkey (GTK4 form)
bin/pinentry-gnome3-nograb   pinentry that does not dim the screen (optional, for rbw)
bin/bw-ssh-agent             SSH agent in front of rbw's, asks before signing (install.sh --ssh)
lib/bwcommon.py              shared code (settings, identity check, focused window, browser URL, layout/IME, last item)
lib/bwselect.py              the list window (GTK4; answers like rofi -dmenu, adds type/folder dropdowns)
lib/rofi                     what rofi-rbw calls as `rofi`: the list window above, or real rofi (XWayland, theme)
lib/dotool                   dotool wrapper (waits for the window you started from; sends keys to a resident dotoold)
lib/wl-copy                  wl-copy wrapper (drops --sensitive on old wl-clipboard; clears copies after a while)
config/config.example.toml   settings template
config/rofi-rbw.rc           rofi-rbw settings
config/bw-autotype.rasi      rofi theme (only with selector = "rofi")
applications/*.desktop.in    launcher templates (install.sh fills in @HOME@)
systemd/bw-ssh-agent.*       systemd user socket and service for bw-ssh-agent
```

## Installation
1. Packages and uinput permission (sudo)
   ```
   sudo apt install golang-go libxkbcommon-dev pipx publicsuffix   # add rofi if you want selector = "rofi"
   echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/70-uinput-uaccess.rules && sudo udevadm control --reload
   ```
   For fingerprints, enroll one in GNOME Settings (fprintd).
2. rbw: put `rbw` and `rbw-agent` from `rbw_*_linux_amd64.tar.gz` on the [releases page](https://github.com/doy/rbw/releases) into `~/.local/bin`.
3. rofi-rbw, with support for identities and separate card expiry month/year (proposed upstream; until then a fork):
   ```
   pipx install "rofi-rbw @ git+https://github.com/dobinnmushi/rofi-rbw@identity"
   ```
   Plain `pipx install rofi-rbw` also works, without those two features.
4. Install and enable the GNOME extension Window Calls.
5. `./install.sh --build-dotool` (builds dotool; afterwards plain `./install.sh` is enough).
   Add `--chrome` if you use Chrome, Chromium or Brave: it adds a launcher that starts the browser with
   `--force-renderer-accessibility`, which is needed to read its address bar (this may make the browser a bit slower).
   It links the scripts into `~/.local/bin`, `~/.local/lib/bw-autotype` and `~/.config`, so edits in the
   repository take effect immediately. An existing `~/.config/rofi-rbw.rc` is moved to `*.bak-YYYYMMDD`.
6. First-time rbw setup (the official server requires registering the device with your personal API key first)
   ```
   rbw config set email <your email>
   rbw config set pinentry ~/.local/bin/pinentry-gnome3-nograb   # optional: does not dim the screen
   rbw register    # client_id and client_secret (web vault → Settings → Security → Keys)
   rbw login
   ```
7. Restart your browser (so that its address bar can be read).

`./uninstall.sh` removes what `install.sh` added and prints how to undo the rest.

## Known limitations
- GNOME does not support layer-shell, so wofi, fuzzel and the Wayland build of rofi do not work; with selector = "rofi", rofi runs under XWayland.
- With Mozc in hiragana mode, shortcuts containing Shift do not reach GNOME (hence Super+Alt+…).
- Chrome-based browsers expose their address bar only when started with `--force-renderer-accessibility` (`install.sh --chrome`); otherwise the list is filtered by the window title only.
- Not supported: passkeys (use bw-passkey), editing items, other desktops than GNOME.
- "Last used item" relies on the order of rofi-rbw's `~/.cache/rofi-rbw.runcache`; a format change in rofi-rbw could break it.

## License
MIT
