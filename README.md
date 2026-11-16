# bw-autotype

[日本語](README.ja.md)

Type Bitwarden usernames and passwords into **any application** with a hotkey on GNOME / Wayland,
and generate and save new passwords — including places browser extensions cannot reach,
such as Firefox's `about:config`, terminals or native apps.

It is mostly a combination of existing tools glued together with thin scripts.

| Role | Tool |
|---|---|
| Vault (unofficial Bitwarden client) | [rbw](https://github.com/doy/rbw) |
| Item list, typing and copying | [rofi-rbw](https://github.com/fdw/rofi-rbw) + rofi (opened as a normal XWayland window) |
| Sending keystrokes | [dotool](https://git.sr.ht/~geb/dotool) (uinput; follows your XKB layout, so symbols are typed correctly on non-US layouts) |
| Focused window | GNOME extension [Window Calls](https://extensions.gnome.org/extension/4724/window-calls/) |
| URL of the current page (Firefox, Chrome, Chromium, Brave) | AT-SPI (accessibility) reads the address bar |
| Identity check | fprintd (fingerprint), falling back to rbw's master password |

Developed and tested on Ubuntu 26.04 (GNOME 50 / Wayland) with a Japanese keyboard and IBus Mozc.
Other GNOME / Wayland setups should work but are less tested; reports are welcome.

## Usage

### Super+Alt+P — type (`bin/bw-autotype`)
Click the field you want to fill, press the hotkey, (touch the fingerprint sensor,) pick an item.
The list is pre-filtered by the focused app and window title (for browsers, by the domain in the address bar).
An item used within the last 5 minutes is preselected at the top, so "username on one page,
password on the next" is just Alt+3 the second time.

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
| `[autotype]` | how long the last item stays preselected; delay before typing; when copies are cleared |
| `[new]` | form keys (`standard` / `vim`), default password type and lengths, what to do after saving |

The list's look is `config/bw-autotype.rasi`; rofi-rbw's own options are in `config/rofi-rbw.rc`.

## Security notes
- With `auth.method = "fingerprint"`, every hotkey press asks for a fingerprint. If the sensor is unavailable or
  does not match, the vault is locked again and the master password is asked — never a weaker path.
- The vault stays unlocked in rbw-agent's memory until rbw's `lock_timeout`. The fingerprint only guards the
  hotkeys: any program running as you can still run `rbw get`. Lock your screen when you leave.
- Passwords are never written to files, logs or notifications. They are passed to dotool and `rbw add` on stdin.
- Typing waits until the original window has focus again, plus `autotype.settle_seconds`.
- Logs: `journalctl -t bw-autotype` (which identity check was used and whether something was saved; no secrets).

## Passkeys
rbw (1.15) does not support passkeys (FIDO2 credentials) at all, so this tool neither shows nor uses them:
- Items that have a passkey still appear in the list as ordinary logins; there is just no passkey to use.
- `bw-new` creates password logins only. Create passkeys with the browser extension.
- Neither this tool nor rofi-rbw ever calls `rbw edit`. Be careful with `rbw edit` yourself on items that have a
  passkey: rbw re-sends the item without its passkey data, which may remove the passkey (not verified).

## Files
```
bin/bw-autotype              the type hotkey (calls rofi-rbw)
bin/bw-new                   the new-login hotkey (GTK4 form)
bin/pinentry-gnome3-nograb   pinentry that does not dim the screen (optional, for rbw)
lib/bwcommon.py              shared code (settings, identity check, focused window, browser URL, layout/IME, last item)
lib/rofi                     rofi wrapper (XWayland, theme, -dpi 1; filter and key help on the first list only)
lib/dotool                   dotool wrapper (waits until rofi has closed and focus has settled)
lib/wl-copy                  wl-copy wrapper (drops --sensitive on old wl-clipboard; clears copies after a while)
config/config.example.toml   settings template
config/rofi-rbw.rc           rofi-rbw settings
config/bw-autotype.rasi      rofi theme
applications/*.desktop.in    launcher templates (install.sh fills in @HOME@)
```

## Installation
1. Packages and uinput permission (sudo)
   ```
   sudo apt install rofi golang-go libxkbcommon-dev pipx publicsuffix
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
- GNOME does not support layer-shell, so wofi, fuzzel and the Wayland build of rofi do not work; rofi runs under XWayland.
- With Mozc in hiragana mode, shortcuts containing Shift do not reach GNOME (hence Super+Alt+…).
- Chrome-based browsers expose their address bar only when started with `--force-renderer-accessibility` (`install.sh --chrome`); otherwise the list is filtered by the window title only.
- Not supported: passkeys (see above), editing items, other desktops than GNOME.
- "Last used item" relies on the order of rofi-rbw's `~/.cache/rofi-rbw.runcache`; a format change in rofi-rbw could break it.

## License
MIT
