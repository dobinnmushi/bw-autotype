# bw-autotype

[English](README.md)

GNOME / Wayland で、Bitwarden のユーザー名・パスワードを**どのアプリにでも**ホットキーで入力し、
新しいパスワードを生成・保存するための道具一式。
Firefox の about:config・端末・普通のアプリなど、ブラウザ拡張が届かない場所でも使える。

中身は既存の道具の組み合わせと、その間をつなぐ薄いスクリプト。

| 役割 | 使うもの |
|---|---|
| 保管庫（Bitwarden 互換の非公式クライアント） | [rbw](https://github.com/doy/rbw) |
| 項目一覧と入力・コピー | [rofi-rbw](https://github.com/fdw/rofi-rbw)。一覧の画面は自作の GTK4 のウィンドウ（rofi にもできる） |
| キー入力の送信 | [dotool](https://git.sr.ht/~geb/dotool)（uinput。キーボード配列に合わせるので、US 以外の配列でも記号がずれない） |
| 前面ウィンドウの取得 | GNOME 拡張 [Window Calls](https://extensions.gnome.org/extension/4724/window-calls/) |
| 表示中のページの URL（Firefox・Chrome・Chromium・Brave） | AT-SPI（アクセシビリティ）でアドレスバーを読む |
| 本人確認 | fprintd（指紋）→ だめなら rbw のマスターパスワード |

Ubuntu 26.04（GNOME 50 / Wayland、jp 配列 + IBus Mozc）で作って試している。
ほかの GNOME / Wayland の環境でも動くはずだが、あまり試していない。

## 既存の道具との違い
2026年の時点で、GNOME/Wayland のデスクトップで Bitwarden を使うと、ブラウザの外が手薄になる。

| 道具 | GNOME/Wayland で、ブラウザの外に入力できるか | 備考 |
|---|---|---|
| Bitwarden のブラウザ拡張 | ×（ブラウザの中だけ） | Web ページにしか入れられない。 |
| Bitwarden のデスクトップ版アプリ | × | 自動入力は[要望があり開発中](https://community.bitwarden.com/t/desktop-app-auto-type-windows-macos-linux/158)だが、ロードマップにあるのは Windows と macOS だけ。署名の前に確認できる [SSH エージェント](https://bitwarden.com/help/ssh-agent/)はある（Flatpak 版にはない）。 |
| [Goldwarden](https://github.com/quexten/goldwarden) | ○（RemoteDesktop ポータル経由） | **2025年8月に開発が無期限に停止**した。作者は SSH キーの項目・SSH エージェント・メモリの保護・Linux の指紋での解除を公式のクライアントに取り込ませたが、自動入力は取り込まれていない。今後の Bitwarden の認証・暗号の変更で動かなくなる見込み（[作者のコメント](https://github.com/quexten/goldwarden/issues/331#issuecomment-3221660132)）。 |
| [rbw](https://github.com/doy/rbw) + [rofi-rbw](https://github.com/fdw/rofi-rbw) | そのままでは × | X11 や wlroots 系（Sway、Hyprland）では動く。GNOME/Wayland では rofi・wofi・fuzzel が layer-shell を必要とし、wtype は使えず、ydotool は US 配列が前提。rbw の SSH エージェントは確認なしで署名する。 |

bw-autotype は rbw と rofi-rbw の上に、足りないものを足している: 実際のキーボード配列と IME に合わせた dotool での入力
（jp 配列と Mozc で確認）、種類・フォルダで絞れて合うサイトが先頭に来る GTK の一覧、アクセシビリティ経由のアドレスバーの読み取り、
ホットキーごとの指紋の確認、パスワードと SSH キーの作成、署名のたびに指紋を求める SSH エージェント。
パスキーは [bw-passkey](https://github.com/dobinnmushi/bw-passkey) を使う。

## 使い方

### Super+Alt+P — 入力（`bin/bw-autotype`）
入力したい欄をクリックしてから押す →（指紋 →）一覧から選ぶ。
前面のウィンドウに合う項目（ブラウザならアドレスバーのドメイン、それ以外は題名・アプリ名）が「このサイト」の印付きで上に並び、
最初から選ばれた状態で出る。ほかの項目もその下に残る。
5分以内に使った項目があれば、それがさらに先頭に来る（ユーザー名 → 次のページでパスワード、が Alt+3 だけで済む）。
検索欄の上の2つのプルダウンで、種類（ログイン・カード・個人情報・メモ）とフォルダを、それぞれ独立に、検索の文字とも
組み合わせて絞れる（Alt+k / Alt+f で開く）。各行にはフォルダと種類が出る。

| キー | 動作 |
|---|---|
| Enter / Alt+1 | ユーザー名 → Tab → パスワード |
| Alt+2 / Alt+3 / Alt+4 | ユーザー名だけ / パスワードだけ / ワンタイムコードだけ |
| Alt+m | 項目を選んでから、入れる中身を選ぶ |
| Alt+s | 保管庫をサーバーと同期 |
| Alt+u / Alt+t / Alt+h | ユーザー名 / ワンタイムコード / カード名義をコピー（30秒後に消える） |

カード: Enter で「番号 → Tab → 有効期限（YYYY-MM）→ Tab → セキュリティコード」。Alt+m で1項目ずつ選べる。
有効期限の欄はサイトによって形がばらばら（1つか2つか、年が2桁か4桁か、打ち込みかプルダウンか）なので、
ブラウザでの支払いには、各欄が何かを見られるブラウザ拡張のカードの自動入力のほうが合うことが多い。
個人情報: Enter で、入れる中身（名前・メール・電話・住所など）を選ぶメニューが開く。

キーの割り当ては `config/rofi-rbw.rc` の `keybindings`。一覧の下の説明はそこから自動で作る。
パスワードとカード番号はコピーせず、入力だけにしている。クリップボードの履歴を取る道具の多く
（GNOME 拡張の Clipboard Indicator など）は「秘密の情報」の印を無視して履歴に残すため。
なお、パスワードを入力すると、rofi-rbw はその項目のワンタイムコード（あれば）をコピーする。

### Super+Alt+N — 新規登録（`bin/bw-new`）
新規登録の画面でパスワード欄をクリックしてから押す →（指紋 →）フォームで確認して Enter。
パスワードを生成して保管庫に保存し、前面の欄に入力する。名前と URI はブラウザのアドレスバーから最初に入る。
存在しないフォルダ名を入れると新しく作られる。

フォームは先に種類（パスワード・パスフレーズ・SSH キー）を選び、それより下の欄だけが種類に合わせて変わる。
パスワードなら、すぐ下の「文字」で記号あり・英数字のみ・数字のみ（PIN）を選ぶ。

**SSH キー**: 種類で「SSH キー（Ed25519）」を選ぶ。種類より下の欄が切り替わり（ユーザー名・URI・長さはなくなる）、
保存するときに鍵を作って（`$XDG_RUNTIME_DIR` の中で `ssh-keygen`。すぐ消す）保管庫の「SSH キー」の項目にし、公開鍵を
前面の欄に入力する（GitHub の「New SSH key」の欄など）か、コピーするか、保存だけにする。秘密鍵は保管庫にだけ入る。

フォームはマウスでもすべて操作できる。キーは既定では普通の操作（Tab で移動、Enter で保存、Esc でやめる）。
`new.keys = "vim"` にすると Vim ふうのモード操作になる:

| モード | キー | 動作 |
|---|---|---|
| ノーマル | J / K | 項目を移動 |
| | j / k | 選択肢・候補を切替（長さは k で +1、j で −1） |
| | i | 文字入力 |
| | p | クリップボードの1行目をカーソル位置に貼り付け |
| | v / r | パスワードの表示切替 / 作り直し |
| | Enter / q | 保存して実行 / やめる |
| 入力 | Esc か Enter | ノーマルモードへ |

どちらもアクティビティ画面の「Bitwarden 自動入力」「Bitwarden 新規登録」から起動できる。

## 設定
`~/.config/bw-autotype/config.toml`（`install.sh` が [`config/config.example.toml`](config/config.example.toml) から作る）。どれも省略できる。

| 項目 | 変えられること |
|---|---|
| `language` | 表示の言語。`auto`（LANG を見る）・`ja`・`en` |
| `[keyboard]` | dotool に渡す配列と、入力中に切り替える IBus エンジン（どちらも自動で判別） |
| `[hotkeys]` | 2つのホットキー（変えたら `./install.sh` を実行し直す） |
| `[auth]` | 本人確認。`fingerprint`・`none`・`auto`（指紋が登録されていれば fingerprint）。[bw-vault](#bw-vault-と一緒に使う任意) と使うときは `none` |
| `[autotype]` | 手元の保管庫が `sync_minutes`（10分）より古ければ一覧の前に同期、直前の項目を先頭に置く秒数、入力を始めるまでの待ち、コピーを消すまでの秒数、キー説明（`full`/`line`/`none`）、一覧の画面（`gtk`/`rofi`） |
| `[ssh]` | SSH の署名で、一度の確認を使い回す秒数 |
| `[new]` | フォームの操作（`standard` / `vim`）、パスワードの種類と長さの既定、保存後の動作 |

rofi-rbw 自体の設定は `config/rofi-rbw.rc`。`autotype.selector = "rofi"` にすると一覧を rofi で出す
（見た目は `config/bw-autotype.rasi`。プルダウンはなく、合う語を絞り込み欄に入れる）。

## 安全のための決まり
- `auth.method = "fingerprint"` なら、ホットキーのたびに指紋を求める。指紋が使えない・一致しないときは、
  保管庫をロックし直してマスターパスワードを聞く（それより弱い経路にはしない）。
- 保管庫は rbw の `lock_timeout` まで rbw-agent のメモリ上で開いたまま。指紋で守れるのはホットキーの入口だけで、
  ログイン中の自分の権限のプログラムは `rbw get` で読める。席を立つときは画面ロック
  （この穴をふさぐのが [bw-vault](#bw-vault-と一緒に使う任意)）。
- パスワードはファイル・ログ・通知に出さない。dotool と `rbw add` には標準入力で渡す。
- 入力は、元のウィンドウが前面に戻ったことを確かめ、最初の欄の前だけさらに `autotype.settle_seconds` 待ってから行う。
  キーは常駐の dotoold（必要なときに起動。命令の口は `$XDG_RUNTIME_DIR/bw-autotype/`）に送るので、欄ごとに dotool の起動（約 0.7 秒）を待たない。
- 記録: `journalctl -t bw-autotype`（本人確認の経路と保存の有無だけ。認証情報は書かない）。

## bw-vault と一緒に使う（任意）
[bw-vault](https://github.com/dobinnmushi/bw-vault)（姉妹品。公開予定）は、保管庫の鍵を別のユーザー（`bwvault`）に置き、
秘密を出す前に polkit（指紋、だめなら `sudo` と同じパスワード）で本人確認をする。bw-autotype は、あっても無くても動き、
自動で切り替わる。こちらの書き換えは要らない。

- **切り替わり方：** 入力と一覧は `rbw` を呼ぶだけで、bw-vault がその `rbw` をラッパーに差し替えるので、変更は要らない。
  SSH キーの保存（`lib/bwvault.py`）だけが bw-vault のソケット（`/run/bwvault-gate/gate.sock`。`BWVAULT_GATE_SOCKET` で変えられる）を探し、
  あれば rbw のトークンを直接使わずに、鍵を bw-vault に渡す。
- **`[auth] method = "none"` にする。** 確認は bw-vault がする。一覧を出すとき（20 秒の窓）と、選んだ項目のとき（画面に項目名が出る）の2回。
  ここでも指紋を求めると3回になる。bw-vault なしなら、既定のままにする。
- **上の「安全のための決まり」への影響：** 保管庫の鍵が、あなたのユーザーのメモリから無くなるので、
  「ログイン中の自分の権限のプログラムは `rbw get` で読める」は当てはまらない。秘密は、すべて確認を通す。
- **SSH：** 下の `./install.sh --ssh` の代わりに、bw-vault の SSH エージェント（署名のたびに、鍵と親プロセスに結び付けて確認する）を使う。
- **違い：** Steam Guard のコード（`steam://`）は未対応。`rbw search`・`edit`・`remove` は、bw-vault のラッパー経由では使えない（この道具は、どれも呼ばない）。

## パスキー
パスキーには、姉妹品の **[bw-passkey](https://github.com/dobinnmushi/bw-passkey)** を使う。Bitwarden の保管庫にある
パスキーでログインし、新しいパスキーもそこへ保存する仮想の FIDO2 セキュリティキーで、本人確認は指紋。
ブラウザからは USB のセキュリティキーに見えるので、Bitwarden の拡張なしで使える。

この道具自体はパスキーを扱わない（rbw 1.15 がパスキーを読まないため）。
- パスキーを持つ項目も、普通のログイン項目として一覧に出る（パスキーは使えない）。
- `bw-new` が作るのはパスワードの項目だけ。パスキーは bw-passkey かブラウザ拡張で作る。
- この道具も rofi-rbw も `rbw edit` は呼ばない。自分で `rbw edit` を使うときは、パスキーを持つ項目に注意。
  rbw はパスキーの欄を持たない形で項目を送り直すので、パスキーが消える恐れがある（確かめてはいない）。

## SSH キー（任意）
（[bw-vault](#bw-vault-と一緒に使う任意) を使うときは、ここで説明するものの代わりに、その SSH エージェントを使う。）

rbw-agent は保管庫の SSH キーで SSH のログインに署名できるが、署名の前に確認はしない。
`./install.sh --ssh` で、その手前に **bw-ssh-agent** を置く。ssh や git は bw-ssh-agent に話しかけ、
鍵の一覧はそのまま rbw に渡し、署名の前には指紋（だめならマスターパスワード。入力のときと同じ）を求める。
1回の git の操作で何度も接続することがあるので、一度確認したら `ssh.confirm_seconds` 秒（既定 30）は確認しない。
通知には鍵と接続先でのユーザー名を出す（SSH エージェントの約束では、接続先のホストは分からない）。

systemd のソケットとして、OpenSSH・gcr・gpg のエージェントのソケットのあとに起動し、それらと同じ方式で
`SSH_AUTH_SOCK` を設定するので、次にログインし直したときから使われる。記録は `journalctl -t bw-autotype`。

## 構成
```
bin/bw-autotype              入力のホットキーの本体（rofi-rbw を呼ぶ）
bin/bw-new                   新規登録のホットキーの本体（GTK4 のフォーム）
bin/pinentry-gnome3-nograb   画面を暗転させない pinentry（任意。rbw の設定で使う）
bin/bw-ssh-agent             rbw の SSH エージェントの前に置き、署名の前に確認する（install.sh --ssh）
lib/bwcommon.py              共通部分（設定・本人確認・前面ウィンドウ・ブラウザの URL・配列と IME・直前の項目）
lib/bwselect.py              一覧の画面（GTK4。rofi -dmenu と同じ約束で答え、種類・フォルダのプルダウンを足す）
lib/rofi                     rofi-rbw が `rofi` として呼ぶもの。上の一覧か、本物の rofi（XWayland・テーマ）を出す
lib/dotool                   dotool の中継（元のウィンドウが前面に戻るのを待ち、常駐の dotoold にキーを送る）
lib/wl-copy                  wl-copy の中継（古い wl-clipboard では --sensitive を外す。コピーをしばらくして消す）
config/config.example.toml   設定ファイルの見本
config/rofi-rbw.rc           rofi-rbw の設定
config/bw-autotype.rasi      rofi のテーマ（selector = "rofi" のときだけ）
applications/*.desktop.in    ランチャーの雛形（@HOME@ を install.sh が埋める）
systemd/bw-ssh-agent.*       bw-ssh-agent の systemd のユーザー用ソケットとサービス
```

## 導入
1. apt と uinput の権限（sudo）
   ```
   sudo apt install golang-go libxkbcommon-dev pipx publicsuffix   # selector = "rofi" にするなら rofi も
   echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/70-uinput-uaccess.rules && sudo udevadm control --reload
   ```
   指紋を使うなら、GNOME の設定で指紋を登録しておく（fprintd）。
2. rbw: [GitHub のリリース](https://github.com/doy/rbw/releases)の `rbw_*_linux_amd64.tar.gz` から `rbw` と `rbw-agent` を `~/.local/bin` へ。
3. rofi-rbw。個人情報と、古い wl-clipboard に対応した版（本家へ提案中。それまではフォーク）:
   ```
   pipx install "rofi-rbw @ git+https://github.com/dobinnmushi/rofi-rbw@identity"
   ```
   普通の `pipx install rofi-rbw` でも動く（個人情報が使えないだけ。古い wl-clipboard には bw-autotype 側で対応している）。
4. GNOME 拡張 Window Calls を入れて有効にする。
5. `./install.sh --build-dotool`（dotool のビルドを含む。2回目以降は `./install.sh` だけ）。
   Chrome・Chromium・Brave を使うなら `--chrome` も付ける。アドレスバーを読むのに要る `--force-renderer-accessibility` を
   付けて起動するランチャーを作る（ブラウザが少し重くなるかもしれない）。
   スクリプトと設定を `~/.local/bin`・`~/.local/lib/bw-autotype`・`~/.config` にシンボリックリンクで置くので、
   リポジトリで編集すればそのまま反映される。既存の `~/.config/rofi-rbw.rc` は `*.bak-YYYYMMDD` に退避する。
6. rbw の初回設定（公式サーバーは、最初に個人用 API キーでの端末登録が要る）
   ```
   rbw config set email <メールアドレス>
   rbw config set pinentry ~/.local/bin/pinentry-gnome3-nograb   # 任意: 画面を暗転させない
   rbw register    # client_id と client_secret（Web 保管庫 → 設定 → セキュリティ → キー）
   rbw login
   ```
7. ブラウザを再起動する（アドレスバーを読めるようにするため）。

外すときは `./uninstall.sh`（自動で戻さないものは、最後に戻し方を表示する）。

## 分かっている制約
- GNOME は layer-shell に対応しないので、wofi・fuzzel・Wayland 版の rofi は動かない（selector = "rofi" のときは XWayland で動かす）。
- Mozc が「あ」のとき、Shift を含むショートカットは GNOME に届かない（そのためホットキーは Super+Alt+…）。
- Chrome 系のブラウザは `--force-renderer-accessibility` を付けて起動したときだけアドレスバーを読める（`install.sh --chrome`）。付けなければ題名だけで絞り込む。
- できないこと: パスキー（bw-passkey を使う）、項目の編集、GNOME 以外のデスクトップ。
- 「直前の項目」は rofi-rbw の `~/.cache/rofi-rbw.runcache` の並び順を使う。rofi-rbw の更新で形式が変わると効かなくなりうる。

## ライセンス
MIT
