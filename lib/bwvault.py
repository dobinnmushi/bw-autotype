"""rbw にない書き込み（SSH キーの項目の作成）のための、保管庫への直接の保存。

rbw の `rbw add` はログインの項目しか作れないので、SSH キーの項目は Bitwarden の API に直接送る:
- 各欄は rbw-agent に暗号化させる（UNIX ソケットに1行の JSON。rbw の src/protocol.rs）。
  項目ごとの鍵は付けず、個人の保管庫の鍵で暗号化する（rbw-agent が項目ごとの鍵での暗号化に対応しないため）。
- API には rbw の DB にあるアクセストークンで送る。古ければ（401）rbw sync でトークンを更新させて読み直す。
- 送ったあとに rbw sync を走らせ、rbw からも新しい項目が見えるようにする。
形式は Bitwarden 公式クライアント（libs/common/src/vault/models/request/cipher.request.ts）に合わせる。
"""
import base64
import json
import os
import shutil
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import bwcommon as bw

CLIENT_VERSION = "2024.12.0"      # rbw と同じ値（rbw の src/api.rs）
TYPE_SSH_KEY = 5
_ENV_VARS = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS")


def _profile():
    return f"rbw-{os.environ['RBW_PROFILE']}" if os.environ.get("RBW_PROFILE") else "rbw"


def _agent(action):
    env_vars = [[base64.b64encode(k.encode()).decode(), base64.b64encode(os.environ[k].encode()).decode()]
                for k in _ENV_VARS if k in os.environ]
    msg = {"tty": None, "environment": {"tty": None, "env_vars": env_vars}, "action": action}
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(os.path.join(runtime, _profile(), "socket"))
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    res = json.loads(buf)
    if res.get("type") == "Error":
        raise RuntimeError(res.get("error") or "rbw-agent error")
    return res


def encrypt(plaintext):
    return _agent({"type": "Encrypt", "plaintext": plaintext, "org_id": None})["cipherstring"]


def decrypt(cipherstring):
    return _agent({"type": "Decrypt", "cipherstring": cipherstring, "entry_key": None, "org_id": None})["plaintext"]


def _config():
    with open(os.path.join(bw.CONFIG_HOME, _profile(), "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _api_url(config):
    url = (config.get("base_url") or "").rstrip("/")
    if not url:
        return "https://api.bitwarden.com"
    return url if url == "https://api.bitwarden.eu" else f"{url}/api"


def _access_token(config):
    d = os.path.join(bw.CACHE_HOME, _profile())
    for name in os.listdir(d):
        if name.endswith(f":{config.get('email')}.json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                token = json.load(f).get("access_token")
            if token:
                return token
    raise RuntimeError(bw.tr("rbw にログインしていません", "rbw is not logged in"))


def _api(method, path, body=None):
    config = _config()
    url = _api_url(config) + path

    def call():
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {_access_token(config)}",
                                              "Bitwarden-Client-Version": CLIENT_VERSION,
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")

    try:
        return call()
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise RuntimeError(f"{method} {path}: {e.code} {e.read()[:200].decode(errors='replace')}") from None
        if bw.run(["rbw", "sync"]).returncode != 0:
            raise RuntimeError(bw.tr("rbw sync に失敗しました", "rbw sync failed")) from None
        return call()


def _folder_id(name):
    """フォルダ名からその ID を返す。なければ作る。名前が空なら None"""
    if not name:
        return None
    res = _api("GET", "/folders")
    for f in res.get("data") or res.get("Data") or []:
        enc = f.get("name") or f.get("Name")
        if enc and decrypt(enc) == name:
            return f.get("id") or f.get("Id")
    created = _api("POST", "/folders", {"name": encrypt(name)})
    return created.get("id") or created.get("Id")


def _gate_socket():
    """bw-vault（保管庫の鍵を別ユーザーに置く門）が入っていれば、そのソケットのパス"""
    path = os.environ.get("BWVAULT_GATE_SOCKET", "/run/bwvault-gate/gate.sock")
    return path if os.path.exists(path) else None


def totp_supported():
    """フォームに TOTP のシークレット欄を出してよいか。保存できるのは bw-vault の門だけ（標準の rbw add には、その指定がない）"""
    return bool(_gate_socket()) and bool(shutil.which("bwv"))


_BASE32 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def totp_clean(text):
    """フォームの TOTP 欄の文字を整える。base32 なら、全角を半角に、空白を除いて大文字にする（日本語入力のまま貼った・打った場合）。
    otpauth:// の URI は、前後の空白だけを除く"""
    s = text.strip()
    if s.lower().startswith("otpauth://"):
        return s
    return "".join(unicodedata.normalize("NFKC", s).split()).upper().rstrip("=")


def totp_problem(text):
    """TOTP 欄の文字の、貼り間違いを知らせる文面（問題がない・空なら None）。最終的な検証は、保存のときに門が行う"""
    s = totp_clean(text)
    if not s:
        return None
    if s.lower().startswith("otpauth://"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(s).query)
        return None if q.get("secret", [""])[0] else bw.tr("otpauth の URI に secret がありません", "The otpauth URI has no secret")
    bad = sorted({c for c in s if c not in _BASE32})
    if bad:
        return bw.tr(f"使えない文字があります（{' '.join(bad[:5])}）。A–Z と 2–7 だけです",
                     f"Invalid characters ({' '.join(bad[:5])}); only A–Z and 2–7 are allowed")
    return None


def save_login_with_totp(name, user, uri, folder, password, totp):
    """TOTP のシークレットつきのログイン項目を、門に作らせる。パスワードと種は標準入力で渡す（引数にも記録にも出さない）。
    結果は subprocess.CompletedProcess（失敗は returncode と stderr）"""
    cmd = ["bwv", "add", "--json", *(["--uri", uri] if uri else []), *(["--folder", folder] if folder else []),
           name, *([user] if user else [])]
    return bw.run(cmd, input=json.dumps({"password": password, "totp": totp}))


def save_ssh_key(name, folder, private_key, public_key, fingerprint):
    """SSH キーの項目を保管庫に作る"""
    if _gate_socket():
        # 門が暗号化・送信・本人確認をする（この側は保管庫の鍵もトークンも持たない）。秘密は標準入力で渡す
        r = bw.run(["bwv", "add", "--ssh", *(["--folder", folder] if folder else []), name],
                   input=json.dumps({"private_key": private_key, "public_key": public_key, "fingerprint": fingerprint}))
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "bwv add failed")
        return 0
    cipher = {
        "type": TYPE_SSH_KEY,
        "folderId": _folder_id(folder),
        "name": encrypt(name),
        "notes": None,
        "sshKey": {
            "privateKey": encrypt(private_key),
            "publicKey": encrypt(public_key),
            "keyFingerprint": encrypt(fingerprint),
        },
    }
    _api("POST", "/ciphers", cipher)
    bw.run(["rbw", "sync"])
