#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BilibiliDownloader 发行管理后台（后端服务）

职责：
  - 定时（默认 60 秒）从 GitHub Releases API 拉取各版本资产包下载量并缓存；
  - 发行说明在线管理（release_notes/*.md 的读取/新建/保存/删除）；
  - 项目文件管理（白名单目录内浏览/编辑/上传/删除，带安全边界）；
  - Git 管理（状态/分支/日志/diff/暂存/提交/推送/拉取，token 免交互、不落盘）；
  - 操作审计日志与环境/资源状态；
  - 提供 JSON API 与静态管理面板（/）。

设计：
  - 仅依赖 Python 标准库，Python 3.9+ 均可运行，无需 pip install；
  - GitHub Token 解析顺序：--token > GITHUB_TOKEN/GH_TOKEN 环境变量 >
    Windows 凭据管理器(git:https://github.com) > 匿名（匿名 60 次/小时，建议提供 token）；
  - 刷新失败时保留上一次成功快照，并在 status.error 中暴露错误；
  - 管理类 API 的安全边界与审计由 extensions.py 统一负责。

用法：
  python admin/server.py
  python admin/server.py --port 8080 --interval 60
  python admin/server.py --repo owner/name --token ghp_xxx --host 127.0.0.1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import extensions
from extensions import AuditLog, ConfigStore, FileManager, GitManager, system_info

DEFAULT_REPO = "colever-Beep/BilibiliDownloader"
DEFAULT_PORT = 8765
DEFAULT_INTERVAL = 60
API_ROOT = "https://api.github.com"
HERE = Path(__file__).resolve().parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Token 解析
# --------------------------------------------------------------------------- #
def resolve_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit.strip()
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env and env.strip():
        return env.strip()
    return GitManager._wincred_token()


# --------------------------------------------------------------------------- #
# 资产包平台/架构标注
# --------------------------------------------------------------------------- #
def classify_asset(name: str) -> Dict[str, str]:
    n = name.lower()
    platform, arch, kind = "其他", "-", "资产包"
    if ".appimage" in n:
        platform = "Linux"
        arch = "aarch64" if "aarch64" in n or "arm64" in n else "x86_64"
        kind = "AppImage"
    elif "macos" in n or n.endswith(".dmg") or ".app.zip" in n:
        platform = "macOS"
        arch = "arm64" if "arm64" in n else ("x86_64" if "x86_64" in n else "-")
        kind = ".app.zip" if ".app.zip" in n else ".dmg"
    elif n.endswith(".exe") or "portable" in n or "setup" in n:
        platform = "Windows"
        arch = "x86_64"
        kind = "便携版" if "portable" in n else "安装版"
    return {"platform": platform, "arch": arch, "kind": kind}


# --------------------------------------------------------------------------- #
# GitHub 客户端
# --------------------------------------------------------------------------- #
class GitHubClient:
    def __init__(self, repo: str, token: Optional[str], timeout: int = 20):
        self.repo = repo
        self.token = token
        self.timeout = timeout
        self.last_rate: Dict[str, Any] = {}

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bili-release-admin",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for key, out in (
                ("X-RateLimit-Limit", "limit"),
                ("X-RateLimit-Remaining", "remaining"),
                ("X-RateLimit-Reset", "reset"),
            ):
                val = resp.headers.get(key)
                if val is not None:
                    self.last_rate[out] = val
            return json.loads(resp.read().decode("utf-8"))

    def list_releases(self, per_page: int = 100, max_pages: int = 10) -> List[Dict[str, Any]]:
        all_releases: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            url = f"{API_ROOT}/repos/{self.repo}/releases?per_page={per_page}&page={page}"
            chunk = self._get(url)
            if not isinstance(chunk, list):
                raise RuntimeError("GitHub 返回了意外的响应格式（非列表）")
            all_releases.extend(chunk)
            if len(chunk) < per_page:
                break
        return all_releases


# --------------------------------------------------------------------------- #
# 聚合 + 缓存
# --------------------------------------------------------------------------- #
def summarize(raw_releases: List[Dict[str, Any]], repo: str) -> Dict[str, Any]:
    releases: List[Dict[str, Any]] = []
    total_downloads = 0
    total_assets = 0

    for rel in raw_releases:
        if rel.get("draft"):
            continue
        assets: List[Dict[str, Any]] = []
        for a in rel.get("assets", []):
            downloads = int(a.get("download_count", 0) or 0)
            meta = classify_asset(a.get("name", ""))
            assets.append({
                "name": a.get("name", ""),
                "downloads": downloads,
                "size": int(a.get("size", 0) or 0),
                "download_url": a.get("browser_download_url", ""),
                "platform": meta["platform"],
                "arch": meta["arch"],
                "kind": meta["kind"],
            })
            total_downloads += downloads
            total_assets += 1
        assets.sort(key=lambda x: x["downloads"], reverse=True)
        releases.append({
            "tag": rel.get("tag_name", ""),
            "name": rel.get("name", ""),
            "published_at": rel.get("published_at", ""),
            "prerelease": bool(rel.get("prerelease")),
            "total_downloads": sum(a["downloads"] for a in assets),
            "asset_count": len(assets),
            "assets": assets,
        })

    def version_key(item: Dict[str, Any]):
        parts = [int(p) for p in "".join(c if c.isdigit() else " " for c in item["tag"]).split()]
        return parts or [0]

    releases.sort(key=version_key, reverse=True)
    top = max(releases, key=lambda r: r["total_downloads"]) if releases else None
    return {
        "repo": repo,
        "summary": {
            "release_count": len(releases),
            "asset_count": total_assets,
            "total_downloads": total_downloads,
            "top_release": top["tag"] if top else None,
            "top_release_downloads": top["total_downloads"] if top else 0,
        },
        "releases": releases,
    }


class StatsCache:
    def __init__(self, client: GitHubClient, interval: int):
        self.client = client
        self.interval = interval
        self._lock = threading.Lock()
        self._snapshot: Dict[str, Any] = {"repo": client.repo, "summary": {}, "releases": []}
        self._status: Dict[str, Any] = {
            "last_success": None, "last_attempt": None, "error": None, "refreshing": False,
        }
        self._stop = threading.Event()

    def refresh(self) -> bool:
        with self._lock:
            if self._status["refreshing"]:
                return False
            self._status["refreshing"] = True
            self._status["last_attempt"] = _now_iso()
        ok = False
        try:
            raw = self.client.list_releases()
            data = summarize(raw, self.client.repo)
            data["rate_limit"] = dict(self.client.last_rate)
            with self._lock:
                self._snapshot = data
                self._status["last_success"] = _now_iso()
                self._status["error"] = None
            ok = True
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            with self._lock:
                self._status["error"] = msg
            print(f"[refresh] FAILED: {msg}", file=sys.stderr)
        finally:
            with self._lock:
                self._status["refreshing"] = False
        return ok

    def start(self):
        self.refresh()
        threading.Thread(target=self._loop, name="refresh-loop", daemon=True).start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.refresh()

    def get_payload(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = json.loads(json.dumps(self._snapshot))
            status = dict(self._status)
        payload = dict(snapshot)
        payload["status"] = status
        payload["status"]["interval"] = self.interval
        payload["status"]["next_refresh_seconds"] = self._next_refresh_seconds(status)
        payload["generated_at"] = _now_iso()
        return payload

    def _next_refresh_seconds(self, status: Dict[str, Any]) -> Optional[int]:
        if not status.get("last_success"):
            return None
        try:
            last = datetime.fromisoformat(status["last_success"]).timestamp()
            return max(0, int(self.interval - (time.time() - last)))
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# 管理对象容器
# --------------------------------------------------------------------------- #
class Services:
    cache: StatsCache
    config: ConfigStore
    audit: AuditLog
    git: GitManager
    files: FileManager
    started_at: float
    auth_source: str
    repo: str
    interval: int


# --------------------------------------------------------------------------- #
# HTTP Handler
# --------------------------------------------------------------------------- #
class AdminHandler(BaseHTTPRequestHandler):
    svc: Services  # 由 main() 注入

    # ---------- 基础响应 ----------
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: Any):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _query(self) -> Dict[str, str]:
        if "?" not in self.path:
            return {}
        return {k: v[0] for k, v in parse_qs(self.path.split("?", 1)[1], keep_blank_values=True).items()}

    def _body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _client_ip(self) -> str:
        return self.client_address[0] if self.client_address else ""

    # ---------- GET ----------
    def do_GET(self):
        path, q = self.path.split("?", 1)[0], self._query()
        svc = self.svc

        if path in ("/", "/index.html"):
            html = HERE / "dashboard.html"
            self._send(200, html.read_bytes(), "text/html; charset=utf-8") if html.exists() \
                else self._send(200, b"dashboard.html not found", "text/plain; charset=utf-8")
        elif path == "/api/stats":
            self._json(200, svc.cache.get_payload())
        elif path == "/api/health":
            self._json(200, {"ok": True, "generated_at": _now_iso()})
        elif path == "/api/system":
            self._json(200, system_info(svc.started_at, svc.repo, svc.interval, svc.auth_source,
                                        svc.cache.client.last_rate))
        elif path == "/api/config":
            self._json(200, svc.config.get())
        elif path == "/api/audit":
            self._json(200, {"ok": True, "items": svc.audit.list(int(q.get("limit", "100")))})

        # ---- 发行说明 ----
        elif path == "/api/notes":
            r = svc.files.list_dir("release_notes")
            if r.get("ok"):
                r["items"] = [x for x in r["items"] if x["type"] == "file" and x["name"].endswith(".md")]
            self._json(200, r)
        elif path == "/api/notes/read":
            rel = q.get("path", "")
            if not rel.startswith("release_notes/") or not rel.endswith(".md"):
                self._json(400, {"ok": False, "error": "只允许读取 release_notes 下的 .md"})
            else:
                self._json(200, svc.files.read(rel))

        # ---- 文件管理 ----
        elif path == "/api/files":
            self._json(200, svc.files.list_dir(q.get("path", "")))
        elif path == "/api/file/read":
            self._json(200, svc.files.read(q.get("path", "")))

        # ---- Git ----
        elif path == "/api/git/status":
            self._json(200, svc.git.status())
        elif path == "/api/git/branches":
            self._json(200, svc.git.branches())
        elif path == "/api/git/remotes":
            self._json(200, svc.git.remote_branches())
        elif path == "/api/git/log":
            self._json(200, svc.git.log(int(q.get("limit", "20"))))
        elif path == "/api/git/diff":
            self._json(200, svc.git.diff(q.get("path", ""), q.get("staged", "").lower() == "true"))
        else:
            self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain; charset=utf-8")

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        svc = self.svc
        body = self._body()
        ip = self._client_ip()

        if path == "/api/refresh":
            ok = svc.cache.refresh()
            payload = svc.cache.get_payload()
            payload["refresh_result"] = "ok" if ok else "failed"
            self._json(200, payload)

        # ---- 发行说明 ----
        elif path == "/api/notes/save":
            rel = str(body.get("path", ""))
            if not rel.startswith("release_notes/") or not rel.endswith(".md"):
                self._json(400, {"ok": False, "error": "只允许保存 release_notes 下的 .md"})
            else:
                self._json(200, svc.files.write(rel, str(body.get("content", "")), ip))

        # ---- 文件管理 ----
        elif path == "/api/file/save":
            self._json(200, svc.files.write(str(body.get("path", "")), str(body.get("content", "")), ip))
        elif path == "/api/file/upload":
            self._json(200, svc.files.upload(str(body.get("dir", "")), str(body.get("filename", "")),
                                             str(body.get("data", "")), ip))
        elif path == "/api/file/delete":
            self._json(200, svc.files.delete(str(body.get("path", "")), ip))

        # ---- Git ----
        elif path == "/api/git/add":
            self._json(200, svc.git.add(body.get("paths", []) if isinstance(body.get("paths"), list) else [], ip))
        elif path == "/api/git/commit":
            self._json(200, svc.git.commit(str(body.get("message", "")), ip))
        elif path == "/api/git/push":
            self._json(200, svc.git.push(str(body.get("branch", "")), str(body.get("remote", "")), ip))
        elif path == "/api/git/pull":
            self._json(200, svc.git.pull(str(body.get("branch", "")), str(body.get("remote", "")), ip))

        # ---- 配置 ----
        elif path == "/api/config/git":
            values = {k: body[k] for k in ("remote", "default_branch", "auto_commit_before_push") if k in body}
            result = svc.config.update_section("git", values)
            svc.audit.append("config.update", f"git: {values}", True, ip)
            self._json(200, {"ok": True, "config": result})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args):
        print("[http] " + (fmt % args), file=sys.stderr)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="BilibiliDownloader 发行管理后台")
    p.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1，仅本机可访问）")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub 仓库 owner/name（默认 {DEFAULT_REPO}）")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help=f"刷新间隔秒数（默认 {DEFAULT_INTERVAL}）")
    p.add_argument("--token", default=None, help="GitHub token（缺省时自动从环境变量/凭据管理器读取）")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    token = resolve_token(args.token)
    auth_source = "explicit" if args.token else (
        "env" if (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")) else ("wincred" if token else "anonymous")
    )

    svc = Services()
    svc.repo = args.repo
    svc.interval = args.interval
    svc.auth_source = auth_source
    svc.started_at = time.time()
    svc.config = ConfigStore()
    svc.audit = AuditLog()
    svc.git = GitManager(svc.audit, svc.config)
    svc.files = FileManager(svc.audit)
    svc.cache = StatsCache(GitHubClient(args.repo, token), args.interval)
    AdminHandler.svc = svc
    svc.cache.start()
    svc.audit.append("server.start", f"port={args.port} repo={args.repo} auth={auth_source}", True)

    server = ThreadingHTTPServer((args.host, args.port), AdminHandler)
    url = f"http://{args.host}:{args.port}/"
    print("=" * 64)
    print("  BilibiliDownloader 发行管理后台 已启动")
    print(f"  面板地址 : {url}")
    print(f"  仓库     : {args.repo}")
    print(f"  刷新间隔 : {args.interval} 秒")
    print(f"  GitHub   : {'已认证 (' + auth_source + ')' if token else '匿名（限流 60 次/小时，建议提供 token）'}")
    print(f"  API      : {url}api/stats")
    print("  按 Ctrl+C 停止")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止...")
        svc.audit.append("server.stop", "", True)
        svc.cache._stop.set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
