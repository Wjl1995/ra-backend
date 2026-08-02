"""URL 规范化与 SSRF 防护。

提供：
- canonicalize_url: URL 规范化（小写 scheme/host、去默认端口、去 fragment、排序 query）
- is_safe_host: 拦截私网 / 回环 / 链路本地 / 云元数据等受限地址
- validate_url_for_fetch: 综合校验入口，返回 (canonical_url, error)
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 允许的方案
_ALLOWED_SCHEMES = {"http", "https"}

# 云元数据地址（AWS/GCP/Aliyun 等都有 169.254.169.254）
_METADATA_IPS = {ipaddress.ip_address("169.254.169.254")}

# 受限网络段
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),    # 唯一本地地址 (ULA)
    ipaddress.ip_network("fe80::/10"),   # 链路本地
]


class UrlUnsafeError(ValueError):
    """URL 不安全或非法。"""


def canonicalize_url(url: str) -> str:
    """规范化 URL：小写 scheme/host、去默认端口、去尾斜杠、排序 query、丢弃 fragment。"""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    # 去除默认端口
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = f"{host}:{port}" if port else host
    # 规范化 path
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # 排序 query 参数（忽略空值，保证一致性便于去重）
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=False)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _resolve_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        raise UrlUnsafeError(f"无法解析主机名: {host}")
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        addr = info[4][0]
        try:
            ips.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    if not ips:
        raise UrlUnsafeError(f"主机未解析到任何 IP: {host}")
    return ips


def is_safe_host(host: str) -> tuple[bool, str]:
    """校验主机解析出的所有 IP 是否落在受限网段。返回 (安全, 原因)。"""
    try:
        ips = _resolve_ips(host)
    except UrlUnsafeError as e:
        return False, str(e)
    for ip in ips:
        if ip in _METADATA_IPS:
            return False, f"禁止访问云元数据地址: {ip}"
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False, f"禁止访问受限网络地址: {ip} (网段 {net})"
    return True, ""


def validate_url_for_fetch(url: str, *, allow_private: bool = False) -> tuple[str, str]:
    """校验并规范化 URL，供抓取前安全校验使用。

    Returns:
        (canonical_url, error): error 非空表示不安全或非法。
    """
    if not url or not url.strip():
        return "", "URL 为空"
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return "", f"仅支持 http/https，收到: {parts.scheme or '(无 scheme)'}"
    if not parts.hostname:
        return "", "缺少主机名"
    if not allow_private:
        safe, reason = is_safe_host(parts.hostname)
        if not safe:
            return "", reason
    try:
        canonical = canonicalize_url(url)
    except Exception as e:  # noqa: BLE001 - 规范化失败也视作不可抓取
        return "", f"URL 规范化失败: {e}"
    return canonical, ""
