#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简幻欢(simpfun.cn) 自动签到脚本

流程：登录获取 token -> 调用签到接口领取积分 -> 查询用户信息输出当前积分。
配置优先级：环境变量 > config.json。
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

# 接口常量
BASE_URL = "https://api.simpfun.cn"
LOGIN_PATH = "/api/auth/login"
POINT_PATH = "/api/user/point"
INFO_PATH = "/api/auth/info"

REQUEST_TIMEOUT = 15
RETRY_TIMES = 3
RETRY_INTERVAL = 5

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"

# 出现这些关键字时，认为今日已签到（视为成功，避免重复打卡报错导致任务失败）
ALREADY_CLAIMED_KEYWORDS = ("已领取", "已签到", "已经领取", "已经签到", "重复", "already")

logger = logging.getLogger("simpfun-checkin")


class LoginError(Exception):
    """登录失败异常"""


class ApiError(Exception):
    """接口返回异常"""


def setup_logging() -> None:
    """初始化日志：默认输出到标准输出，级别由 SIMPFUN_LOG_LEVEL 控制"""
    level_name = os.environ.get("SIMPFUN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def mask(text: str, keep: int = 2) -> str:
    """对账号等信息做脱敏处理"""
    if not text:
        return "<空>"
    if len(text) <= keep * 2:
        return text[0] + "*" * (len(text) - 1) if len(text) > 1 else "*"
    return f"{text[:keep]}{'*' * (len(text) - keep * 2)}{text[-keep:]}"


def load_config() -> tuple:
    """读取配置：环境变量优先，其次 config.json，缺失字段互相补全"""
    config_path = Path(os.environ.get("SIMPFUN_CONFIG", DEFAULT_CONFIG_PATH))
    file_config = {}
    if config_path.is_file():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                file_config = json.load(f)
            logger.info("已加载配置文件: %s", config_path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("配置文件解析失败(%s): %s", config_path, exc)
    else:
        logger.info("未找到配置文件 %s，仅使用环境变量", config_path)

    username = os.environ.get("SIMPFUN_USERNAME") or file_config.get("username", "")
    password = os.environ.get("SIMPFUN_PASSWORD") or file_config.get("password", "")
    return str(username).strip(), str(password).strip()


class SimpfunClient:
    """简幻欢接口客户端"""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self.token = ""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "simpfun-checkin/1.0",
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """发起请求并解析 JSON，统一处理网络与解析异常"""
        url = f"{BASE_URL}{path}"
        try:
            resp = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"请求 {path} 网络异常: {exc}") from exc
        if resp.status_code >= 500:
            raise ApiError(f"请求 {path} 服务端错误: HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError(f"请求 {path} 返回非 JSON 内容: HTTP {resp.status_code}") from exc
        if not isinstance(data, dict):
            raise ApiError(f"请求 {path} 返回格式异常: {data!r}")
        return data

    def login(self) -> None:
        """登录并保存 token"""
        data = self._request(
            "POST",
            LOGIN_PATH,
            data={"username": self.username, "passwd": self.password},
        )
        if data.get("code") != 200:
            raise LoginError(data.get("msg") or data.get("message") or f"返回值 {data!r}")
        token = (data.get("data") or {}).get("token")
        if not token:
            raise LoginError("登录响应中缺少 token")
        self.token = token
        self.session.headers["Authorization"] = token
        logger.info("登录成功，账号: %s", mask(self.username))

    def claim_point(self) -> tuple:
        """调用签到接口，返回 (是否成功, 原始响应)"""
        data = self._request("POST", POINT_PATH)
        code = data.get("code")
        msg = str(data.get("msg") or data.get("message") or "")
        info = str(data.get("data") or "")

        if code == 200:
            return True, data

        # 今日已领取，视为成功
        merged = f"{msg}{info}"
        if any(word in merged.lower() for word in ALREADY_CLAIMED_KEYWORDS):
            logger.info("今日已签到，无需重复领取: %s", msg or info)
            return True, data

        logger.error("签到失败: code=%s, msg=%s", code, msg or info or "未知错误")
        return False, data

    def checkin(self) -> bool:
        """签到，失败时最多重试 RETRY_TIMES 次，每次间隔 RETRY_INTERVAL 秒"""
        for attempt in range(1, RETRY_TIMES + 1):
            logger.info("开始签到（第 %d/%d 次）", attempt, RETRY_TIMES)
            try:
                ok, data = self.claim_point()
            except ApiError as exc:
                logger.error("签到请求异常: %s", exc)
                ok, data = False, {}
            if ok:
                logger.info("签到成功: %s", json.dumps(data, ensure_ascii=False))
                return True
            if attempt < RETRY_TIMES:
                logger.warning("%d 秒后重试...", RETRY_INTERVAL)
                time.sleep(RETRY_INTERVAL)

        logger.error("签到失败，已重试 %d 次", RETRY_TIMES)
        return False

    def show_user_info(self) -> None:
        """查询并输出用户信息与当前积分（失败不影响签到结果）"""
        try:
            data = self._request("GET", INFO_PATH)
        except ApiError as exc:
            logger.warning("获取用户信息失败: %s", exc)
            return
        if data.get("code") != 200:
            logger.warning("获取用户信息失败: code=%s, msg=%s", data.get("code"), data.get("msg"))
            return
        user = data.get("data") or {}
        if not isinstance(user, dict):
            logger.info("用户信息: %s", user)
            return
        logger.info(
            "用户信息: 用户名=%s, 积分=%s",
            user.get("username") or mask(self.username),
            user.get("point", user.get("points", "未知")),
        )


def main() -> int:
    setup_logging()
    username, password = load_config()
    if not username or not password:
        logger.error(
            "缺少账号或密码，请设置环境变量 SIMPFUN_USERNAME/SIMPFUN_PASSWORD 或配置 config.json"
        )
        return 1

    client = SimpfunClient(username, password)
    try:
        client.login()
    except LoginError as exc:
        logger.error("登录失败: %s", exc)
        return 1
    except ApiError as exc:
        logger.error("登录请求异常: %s", exc)
        return 1

    success = client.checkin()
    client.show_user_info()

    if success:
        logger.info("任务完成")
        return 0
    logger.error("任务失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
