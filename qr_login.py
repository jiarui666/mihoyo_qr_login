# -*- coding: utf-8 -*-
"""
miHoYo QRCode Login Tool v1.0
==============================
通过米游社 APP 扫码登录，获取所有凭证并自动写入 config.yaml。

无需短信、无需 Geetest 验证，最稳定的登录方式。

流程:
  1. 脚本生成二维码并在终端显示
  2. 用米游社 APP 扫码（APP -> 我的 -> 右上角扫一扫）
  3. APP 上确认登录
  4. 脚本自动获取 stoken/ltoken/cookie_token 并写入同级目录 config.yaml
"""

import hashlib
import json
import os
import random
import string
import sys
import time
import uuid
from typing import Any, Optional

import httpx
import yaml

try:
    import qrcode
except ImportError:
    print("[FATAL] 需要安装 qrcode 库:")
    print("  pip install qrcode")
    sys.exit(1)


# ============================================================
# 常量
# ============================================================

# config.yaml 默认生成在脚本同级目录下，可通过环境变量覆盖
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(SCRIPT_DIR, "config.yaml"))

# 二维码登录 API（hk4e_cn 是固定的，不影响其他游戏）
QRCODE_FETCH_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
QRCODE_QUERY_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"

# game_token 换 stoken 的 API
GET_TOKEN_BY_GAMETOKEN_URL = (
    "https://api-takumi.mihoyo.com/account/ma-cn-session/app/getTokenByGameToken"
)

# stoken 换其他 token
GET_LTOKEN_URL = (
    "https://passport-api.mihoyo.com/account/auth/api/getLTokenBySToken"
)
GET_COOKIE_TOKEN_URL = (
    "https://passport-api.mihoyo.com/account/auth/api/getCookieAccountInfoBySToken"
)

# 应用 ID
APP_ID_QRCODE = "7"  # 二维码登录用的 app_id（原神）
APP_ID_PASSPORT = "bll8iq97cem8"  # passport API 用

# DS 签名 salt
DS_SALT_X4 = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
DS_SALT_K2 = "OvOIsZRXrUbXoUlpQuhEx4tgAwNVUMmp"

# BBS 版本
BBS_VERSION = "2.102.1"
BBS_UA = f"Mozilla/5.0 (Linux; Android 12) Mobile miHoYoBBS/{BBS_VERSION}"


# ============================================================
# 工具函数
# ============================================================


def generate_device_id() -> str:
    return str(uuid.uuid4()).upper()


def generate_device_fp() -> str:
    return "".join(random.choices("0123456789abcdef", k=13))


def generate_ds_x4(query: str = "", body: str = "") -> str:
    """X4 DS 签名（用于 stoken 换 token）"""
    t = str(int(time.time()))
    r = str(random.randint(100000, 200000))
    h = hashlib.md5(
        f"salt={DS_SALT_X4}&t={t}&r={r}&b={body}&q={query}".encode()
    ).hexdigest()
    return f"{t},{r},{h}"


def generate_ds_k2(body: dict[str, Any]) -> str:
    """K2 DS 签名（用于 game_token 换 stoken）"""
    t = str(int(time.time()))
    r = "".join(random.choices(string.ascii_letters, k=6))
    b = json.dumps(body)
    h = hashlib.md5(
        f"salt={DS_SALT_K2}&t={t}&r={r}&b={b}&q=".encode()
    ).hexdigest()
    return f"{t},{r},{h}"


def print_qrcode_terminal(text: str) -> None:
    """在终端打印二维码（ASCII 字符）"""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(text)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def save_qrcode_image(text: str, filename: str = "qrcode.png") -> None:
    """保存二维码为图片文件"""
    img = qrcode.make(text)
    img.save(filename)
    print(f"[INFO] 二维码已保存为图片: {os.path.abspath(filename)}")


# ============================================================
# 扫码登录类
# ============================================================


class QRLogin:
    def __init__(self) -> None:
        self.device_id = generate_device_id()
        self.device_fp = generate_device_fp()
        self.client = httpx.Client(timeout=30.0)

    def fetch_qrcode(self) -> Optional[dict[str, str]]:
        """生成二维码 URL 和 ticket。

        返回: { "url": "...", "ticket": "..." }
        """
        body = {
            "app_id": APP_ID_QRCODE,
            "device": self.device_id,
        }
        resp = self.client.post(QRCODE_FETCH_URL, json=body)
        data = resp.json()

        if data.get("retcode") != 0:
            print(f"[ERROR] 生成二维码失败: {data}")
            return None

        url = data["data"]["url"]
        # 从 URL 中提取 ticket
        # url 格式: https://...?ticket=xxx
        ticket = ""
        if "ticket=" in url:
            ticket = url.split("ticket=")[1].split("&")[0]

        return {"url": url, "ticket": ticket}

    def query_qrcode(self, ticket: str) -> dict[str, Any]:
        """查询二维码扫描状态。

        stat 取值:
          - "Init":      未扫码
          - "Scanned":   已扫码，等待用户确认
          - "Confirmed": 已确认，可获取 token
        """
        body = {
            "app_id": APP_ID_QRCODE,
            "device": self.device_id,
            "ticket": ticket,
        }
        resp = self.client.post(QRCODE_QUERY_URL, json=body)
        return resp.json()

    def wait_for_scan(self, ticket: str, timeout: int = 120) -> Optional[dict[str, str]]:
        """轮询等待用户扫码 + 确认。

        返回: { "uid": "...", "game_token": "..." } 或 None
        """
        print()
        print("[INFO] 等待扫码... (超时 {}s)".format(timeout))
        print("[INFO] 请用米游社 APP 扫描上方二维码")
        print("       APP -> 我的 -> 右上角扫一扫")
        print()

        last_stat = ""
        start = time.time()

        while time.time() - start < timeout:
            result = self.query_qrcode(ticket)
            retcode = result.get("retcode")

            if retcode != 0:
                print(f"[ERROR] 查询失败: {result}")
                return None

            stat = result["data"].get("stat", "")

            if stat != last_stat:
                if stat == "Init":
                    print("[STAT] 等待扫码...")
                elif stat == "Scanned":
                    print("[STAT] 已扫码！请在 APP 上确认登录")
                elif stat == "Confirmed":
                    print("[STAT] 已确认！正在获取 token...")
                last_stat = stat

            if stat == "Confirmed":
                # payload.raw 是 JSON 字符串
                raw = result["data"].get("payload", {}).get("raw", "{}")
                try:
                    payload = json.loads(raw)
                    return {
                        "uid": payload.get("uid", ""),
                        "game_token": payload.get("token", ""),
                    }
                except json.JSONDecodeError:
                    print(f"[ERROR] payload 解析失败: {raw}")
                    return None

            time.sleep(2)

        print("[ERROR] 扫码超时")
        return None

    def get_stoken_by_game_token(self, uid: str, game_token: str) -> Optional[dict[str, str]]:
        """用 game_token 换取 stoken_v2 + mid。

        返回: { "stoken": "...", "mid": "...", "aid": "..." }
        """
        body = {
            "account_id": int(uid),
            "game_token": game_token,
        }

        headers = {
            "x-rpc-app_id": APP_ID_PASSPORT,
            "x-rpc-client_type": "2",
            "x-rpc-game_biz": "bbs_cn",
            "x-rpc-device_id": self.device_id,
            "x-rpc-device_fp": self.device_fp,
            "ds": generate_ds_k2(body),
            "user-agent": BBS_UA,
            "content-type": "application/json",
        }

        resp = self.client.post(GET_TOKEN_BY_GAMETOKEN_URL, json=body, headers=headers)
        data = resp.json()

        print(
            f"[TOKEN] getTokenByGameToken: retcode={data.get('retcode')}, "
            f"message={data.get('message')}"
        )

        if data.get("retcode") != 0:
            print(f"[ERROR] 换取 stoken 失败: {data}")
            return None

        login_data = data.get("data", {})
        token_info = login_data.get("token", {})
        user_info = login_data.get("user_info", {})

        return {
            "stoken": token_info.get("token", ""),
            "mid": user_info.get("mid", ""),
            "aid": user_info.get("aid", "") or uid,
        }

    def _get_token_exchange_headers(
        self, stoken: str, mid: str, query_str: str
    ) -> dict[str, str]:
        cookie_str = f"mid={mid};stoken={stoken}"
        return {
            "user-agent": BBS_UA,
            "x-rpc-app_version": BBS_VERSION,
            "x-rpc-client_type": "5",
            "x-requested-with": "com.mihoyo.hyperion",
            "referer": "https://webstatic.mihoyo.com",
            "x-rpc-device_id": self.device_id,
            "x-rpc-device_fp": self.device_fp,
            "ds": generate_ds_x4(query=query_str),
            "cookie": cookie_str,
        }

    def get_ltoken(self, stoken: str, mid: str) -> Optional[str]:
        params = {"stoken": stoken}
        query_str = f"stoken={stoken}"
        headers = self._get_token_exchange_headers(stoken, mid, query_str)

        resp = self.client.get(GET_LTOKEN_URL, headers=headers, params=params)
        data = resp.json()
        print(
            f"[TOKEN] getLToken: retcode={data.get('retcode')}, "
            f"message={data.get('message')}"
        )

        if data.get("retcode") == 0:
            return data.get("data", {}).get("ltoken", "")
        return None

    def get_cookie_token(self, stoken: str, mid: str) -> Optional[str]:
        params = {"stoken": stoken}
        query_str = f"stoken={stoken}"
        headers = self._get_token_exchange_headers(stoken, mid, query_str)

        resp = self.client.get(GET_COOKIE_TOKEN_URL, headers=headers, params=params)
        data = resp.json()
        print(
            f"[TOKEN] getCookieToken: retcode={data.get('retcode')}, "
            f"message={data.get('message')}"
        )

        if data.get("retcode") == 0:
            return data.get("data", {}).get("cookie_token", "")
        return None

    def close(self) -> None:
        self.client.close()


# ============================================================
# Config 写入
# ============================================================


def update_config(
    stoken: str,
    mid: str,
    stuid: str,
    ltoken: Optional[str] = None,
    cookie_token: Optional[str] = None,
) -> None:
    """将凭证写入 config.yaml（自动创建或更新）"""
    print()
    print("=" * 60)
    print("  凭证汇总")
    print("=" * 60)
    print(f"  stuid:        {stuid}")
    print(f"  stoken:       {stoken}")
    print(f"  mid:          {mid}")
    if ltoken:
        print(f"  ltoken:       {ltoken}")
    if cookie_token:
        print(f"  cookie_token: {cookie_token}")
    print("=" * 60)
    print()

    cookie_str = ""
    if ltoken and cookie_token:
        cookie_str = (
            f"account_id={stuid}; "
            f"account_id_v2={stuid}; "
            f"account_mid_v2={mid}; "
            f"cookie_token={cookie_token}; "
            f"ltmid_v2={mid}; "
            f"ltoken={ltoken}; "
            f"ltuid={stuid}; "
            f"ltuid_v2={stuid}"
        )
        print("[Cookie 字符串 (可直接粘贴到浏览器)]")
        print(f"  {cookie_str}")
        print()

    # 读取已有 config 或创建新的
    config: dict[str, Any] = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        print(f"[INFO] 已读取现有配置: {CONFIG_PATH}")

    def _set_fields(target: dict[str, Any]) -> None:
        target["stuid"] = stuid
        target["stoken"] = stoken
        target["mid"] = mid
        if ltoken and cookie_token:
            target["cookie"] = cookie_str

    if (
        "account" in config
        and isinstance(config["account"], list)
        and len(config["account"]) > 0
    ):
        _set_fields(config["account"][0])
    else:
        _set_fields(config)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    print(f"[OK] 凭证已写入: {CONFIG_PATH}")


# ============================================================
# 主流程
# ============================================================


def main() -> None:
    print("=" * 60)
    print("  miHoYo QRCode Login Tool v1.0")
    print("=" * 60)
    print()

    login = QRLogin()
    try:
        # 步骤 1：生成二维码
        print("[步骤 1] 正在生成二维码...")
        qr_info = login.fetch_qrcode()
        if not qr_info:
            return

        url = qr_info["url"]
        ticket = qr_info["ticket"]

        print(f"[INFO] 二维码 URL: {url}")
        print()

        # 在终端显示二维码
        print_qrcode_terminal(url)

        # 同时保存为图片，方便扫码不便时使用
        try:
            save_qrcode_image(url, "qrcode.png")
        except Exception as e:
            print(f"[WARN] 保存图片失败: {e}")

        # 步骤 2：等待扫码
        print("[步骤 2] 等待扫码 + 确认...")
        scan_result = login.wait_for_scan(ticket, timeout=120)
        if not scan_result:
            return

        uid = scan_result["uid"]
        game_token = scan_result["game_token"]
        print(f"[OK] 获取 game_token 成功: uid={uid}")
        print()

        # 步骤 3：换 stoken
        print("[步骤 3] 用 game_token 换 stoken_v2...")
        token_result = login.get_stoken_by_game_token(uid, game_token)
        if not token_result:
            return

        stoken = token_result["stoken"]
        mid = token_result["mid"]
        aid = token_result["aid"]
        print(f"[OK] stoken 获取成功! mid={mid}")
        print()

        # 步骤 4：换 ltoken + cookie_token
        print("[步骤 4] 换取 ltoken 和 cookie_token...")
        ltoken = login.get_ltoken(stoken, mid)
        cookie_token = login.get_cookie_token(stoken, mid)
        print()

        # 步骤 5：写入 config
        print("[步骤 5] 写入 config.yaml...")
        update_config(stoken, mid, aid, ltoken=ltoken, cookie_token=cookie_token)

        # 清理图片
        if os.path.exists("qrcode.png"):
            try:
                os.remove("qrcode.png")
            except Exception:
                pass

        print()
        print("=" * 60)
        print("  全部完成!")
        print("=" * 60)

    finally:
        login.close()


if __name__ == "__main__":
    main()
