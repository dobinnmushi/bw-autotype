# bw-autotype

[English](README.md)

GNOME / Wayland で、Bitwarden のユーザー名・パスワードを**どのアプリにでも**ホットキーで入力し、
新しいパスワードを生成・保存するための道具一式。
Firefox の about:config・端末・普通のアプリなど、ブラウザ拡張が届かない場所でも使える。

中身は既存の道具の組み合わせと、その間をつなぐ薄いスクリプト。

| 役割 | 使うもの |
|---|---|
| 保管庫（Bitwarden 互換の非公式クライアント） | [rbw](https://github.com/doy/rbw) |
| 項目一覧と入力・コピー | [rofi-rbw](https://github.com/fdw/rofi-rbw) + rofi（XWayland の普通のウィンドウとして開く） |
| キー入力の送信 | [dotool](https://git.sr.ht/~geb/dotool)（uinput。キーボード配列に合わせるので、US 以外の配列でも記号がずれない） |
| 前面ウィンドウの取得 | GNOME 拡張 [Window Calls](https://extensions.gnome.org/extension/4724/window-calls/) |
| 表示中のページの URL（Firefox・Chrome・Chromium・Brave） | AT-SPI（アクセシビリティ）でアドレスバーを読む |
| 本人確認 | fprintd（指紋）→ だめなら rbw のマスターパスワード |

Ubuntu 26.04（GNOME 50 / Wayland、jp 配列 + IBus Mozc）で作って試している。
ほかの GNOME / Wayland の環境でも動くはずだが、あまり試していない。

## 使い方

### Super+Alt+P — 入力（`bin/bw-autotype`）
入力したい欄をクリックしてから押す →（指紋 →）一覧から選ぶ。
一覧は、前面のアプリ名・題名（ブラウザならアドレスバーのドメイン）で最初から絞り込まれる。
5分以内に使った項目があれば、それが先頭に選ばれた状態で出る（ユーザー名 → 次のページでパスワード、が Alt+3 だけで済む）。

| キー | 動作 |
|---|---|
| Enter / Alt+1 | ユーザー名 → Tab → パスワード |
| Alt+2 / Alt+3 / Alt+4 | ユーザー名だけ / パスワードだけ / ワンタイムコードだけ |
| Alt+m | 項目を選んでから、入れる中身を選ぶ |
| Alt+s | 保管庫をサーバーと同期 |
| Alt+u / Alt+t / Alt+h | ユーザー名 / ワンタイムコード / カード名義をコピー（30秒後に消える） |

カード: Enter で「番号 → Tab → 有効期限（YYYY-MM）→ Tab → セキュリティコード」。月と年が別の欄のフォームでは、
Alt+m で「Expiry month」「Expiry year」を選ぶか、項目にカスタムフィールド `_autotype`
（例: `number:tab:expiry month:tab:expiry year:tab:code`）を足す。
個人情報: Enter で、入れる中身（名前・メール・電話・住所など）を選ぶメニューが開く。

キーの割り当ては `config/rofi-rbw.rc` の `keybindings`。一覧の下の説明はそこから自動で作る。
パスワードとカード番号はコピーせず、入力だけにしている。クリップボードの履歴を取る道具の多く
（GNOME 拡張の Clipboard Indicator など）は「秘密の情報」の印を無視して履歴に残すため。
なお、パスワードを入力すると、rofi-rbw はその項目のワンタイムコード（あれば）をコピーする。

### Super+Alt+N — 新規登録（`bin/bw-new`）
新規登録の画面でパスワード欄をクリックしてから押す →（指紋 →）フォームで確認して Enter。
パスワードを生成して保管庫に保存し、前面の欄に入力する。名前と URI はブラウザのアドレスバーから最初に入る。
存在しないフォルダ名を入れると新しく作られる。

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
| `[auth]` | 本人確認。`fingerprint`・`none`・`auto`（指紋が登録されていれば fingerprint） |
| `[autotype]` | 直前の項目を先頭に置く秒数、入力を始めるまでの待ち、コピーを消すまでの秒数 |
| `[new]` | フォームの操作（`standard` / `vim`）、パスワードの種類と長さの既定、保存後の動作 |

一覧の見た目は `config/bw-autotype.rasi`、rofi-rbw 自体の設定は `config/rofi-rbw.rc`。

## 安全のための決まり
- `auth.method = "fingerprint"` なら、ホットキーのたびに指紋を求める。指紋が使えない・一致しないときは、
  保管庫をロックし直してマスターパスワードを聞く（それより弱い経路にはしない）。
- 保管庫は rbw の `lock_timeout` まで rbw-agent のメモリ上で開いたまま。指紋で守れるのはホットキーの入口だけで、
  ログイン中の自分の権限のプログラムは `rbw get` で読める。席を立つときは画面ロック。
- パスワードはファイル・ログ・通知に出さない。dotool と `rbw add` には標準入力で渡す。
- 入力は、元のウィンドウが前面に戻ったことを確かめ、さらに `autotype.settle_seconds` 待ってから行う。
- 記録: `journalctl -t bw-autotype`（本人確認の経路と保存の有無だけ。認証情報は書かない）。

## パスキー
rbw（1.15）はパスキー（FIDO2 の認証情報）にまったく対応していないので、この道具からは見えず、使えない。
- パスキーを持つ項目も、普通のログイン項目として一覧に出る（パスキーは使えない）。
- `bw-new` が作るのはパスワードの項目だけ。パスキーはブラウザ拡張で作る。
- この道具も rofi-rbw も `rbw edit` は呼ばない。自分で `rbw edit` を使うときは、パスキーを持つ項目に注意。
  rbw はパスキーの欄を持たない形で項目を送り直すので、パスキーが消える恐れがある（確かめてはいない）。

## 構成
```
bin/bw-autotype              入力のホットキーの本体（rofi-rbw を呼ぶ）
bin/bw-new                   新規登録のホットキーの本体（GTK4 のフォーム）
bin/pinentry-gnome3-nograb   画面を暗転させない pinentry（任意。rbw の設定で使う）
lib/bwcommon.py              共通部分（設定・本人確認・前面ウィンドウ・ブラウザの URL・配列と IME・直前の項目）
lib/rofi                     rofi の中継（XWayland・テーマ・-dpi 1、最初の一覧にだけ絞り込み語とキー説明を付ける）
lib/dotool                   dotool の中継（rofi が閉じて前面が落ち着くまで待つ）
lib/wl-copy                  wl-copy の中継（古い wl-clipboard では --sensitive を外す。コピーをしばらくして消す）
config/config.example.toml   設定ファイルの見本
config/rofi-rbw.rc           rofi-rbw の設定
config/bw-autotype.rasi      rofi のテーマ
applications/*.desktop.in    ランチャーの雛形（@HOME@ を install.sh が埋める）
```

## 導入
1. apt と uinput の権限（sudo）
   ```
   sudo apt install rofi golang-go libxkbcommon-dev pipx publicsuffix
   echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/70-uinput-uaccess.rules && sudo udevadm control --reload
   ```
   指紋を使うなら、GNOME の設定で指紋を登録しておく（fprintd）。
2. rbw: [GitHub のリリース](https://github.com/doy/rbw/releases)の `rbw_*_linux_amd64.tar.gz` から `rbw` と `rbw-agent` を `~/.local/bin` へ。
3. rofi-rbw。個人情報と、カードの有効期限の月・年別入力に対応した版（本家へ提案予定。それまではフォーク）:
   ```
   pipx install "rofi-rbw @ git+https://github.com/dobinnmushi/rofi-rbw@identity"
   ```
   普通の `pipx install rofi-rbw` でも動く（その2つが使えないだけ）。
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
- GNOME は layer-shell に対応しないので、wofi・fuzzel・Wayland 版の rofi は動かない（rofi は XWayland で動かす）。
- Mozc が「あ」のとき、Shift を含むショートカットは GNOME に届かない（そのためホットキーは Super+Alt+…）。
- Chrome 系のブラウザは `--force-renderer-accessibility` を付けて起動したときだけアドレスバーを読める（`install.sh --chrome`）。付けなければ題名だけで絞り込む。
- できないこと: パスキー（上を参照）、項目の編集、GNOME 以外のデスクトップ。
- 「直前の項目」は rofi-rbw の `~/.cache/rofi-rbw.runcache` の並び順を使う。rofi-rbw の更新で形式が変わると効かなくなりうる。

## ライセンス
MIT
