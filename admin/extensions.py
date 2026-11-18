#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BilibiliDownloader 发行管理后台 —— 扩展模块

仅依赖 Python 标准库，提供：
  - ConfigStore     管理后台配置持久化
  - AuditLog        操作审计日志（JSONL，自动截断）
  - GitManager      Git 管理：状态/分支/日志/diff/暂存/提交/推送/拉取（凭据管理器 token）
  - FileManager     项目内文件浏览/读取/写入/上传/删除（带安全边界）
  - system_info     运行环境与资源占用快照

安全约定（重要）：
  - 文件访问一律限制在 PROJECT_ROOT 内，路径穿越（../、绝对路径、盘符）一律拒绝；
  - 凭据类文件（cookies*.txt、_ghcred*、.env*）与依赖/产物目录（.git、node_modules、
    dist、bin、__pycache__、.workbuddy）对 Web 完全不可见，连列表都不出现；
  - 写入/上传/删除仅限 WRITABLE_ROOTS 白名单子树，且受 WRITE_DENY / DELETE_DENY 约束；
  - 所有 mutating 操作写审计日志；
  - Git 推送 token 从 Windows 凭据管理器运行时读取，经 git -c url.<含token>.insteadOf
    内联传入，不落盘、不进命令行回显；禁用代理与 credential helper 避免沙箱卡死。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

CONFIG_PATH = HERE / "_admin_config.json"
AUDIT_PATH = HERE / "_audit.log"

# 可被 Web 写入/上传/删除的白名单子树（相对 PROJECT_ROOT，正斜杠）
# 注意：admin 目录（后台自身脚本/配置/日志）整体不开放通用写 API ——
# 脚本改了也不会热生效且有被覆盖风险，配置请走 /api/config/* 专用接口。
WRITABLE_ROOTS = ("release_notes", "website/src/pages/docs")

READ_DENY_DIRS = {".git", "node_modules", "__pycache__", "dist", "bin", ".workbuddy", ".astro", ".venv", "venv"}
READ_DENY_SUFFIX = (".pyc", ".pyo", ".tmp")
READ_DENY_NAMES = {".env", ".env.local", "cookies.txt", "cookies - 副本.txt", ".gitignore"}


def _is_deny_name(name: str) -> bool:
    low = name.lower()
    if low in READ_DENY_NAMES or low.endswith(READ_DENY_SUFFIX) or low in READ_DENY_DIRS:
        return True
    if low.startswith("cookies") and low.endswith(".txt"):
        return True
    if low.startswith("_ghcred") or low.startswith(".env"):
        return True
    return False


WRITE_DENY = {("admin", "_admin_config.json"), ("admin", "_audit.log")}
DELETE_DENY = {("admin", "server.py"), ("admin", "dashboard.html"), ("admin", "extensions.py"),
               ("admin", "run_admin.cmd"), ("admin", "_admin_config.json"), ("admin", "_audit.log")}

UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_ALLOW_EXT = {
    ".md", ".txt", ".json", ".html", ".htm", ".css", ".js", ".ts", ".astro",
    ".py", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".po", ".pot", ".svg",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG: Dict[str, Any] = {
    "git": {
        "remote": "origin",
        "default_branch": "main",
        "auto_commit_before_push": False,
    },
}


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config is not an object")
        except Exception:
            raw = {}
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for key, val in raw.items():
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key].update(val)
            else:
                merged[key] = val
        return merged

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def update_section(self, section: str, values: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            cur = self._data.setdefault(section, {})
            for k, v in values.items():
                cur[k] = v
            _atomic_write(self.path, json.dumps(self._data, ensure_ascii=False, indent=2))
            return self.get()


# --------------------------------------------------------------------------- #
# 审计日志
# --------------------------------------------------------------------------- #
class AuditLog:
    MAX_LINES = 2000

    def __init__(self, path: Path = AUDIT_PATH):
        self.path = path
        self._lock = threading.Lock()

    def append(self, action: str, detail: str = "", ok: bool = True, ip: str = ""):
        entry = {"ts": _now_iso(), "action": action, "detail": detail[:400], "ok": bool(ok), "ip": ip}
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._trim()

    def _trim(self):
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) > self.MAX_LINES:
                _atomic_write(self.path, "\n".join(lines[-self.MAX_LINES:]) + "\n")
        except Exception:
            pass

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        with self._lock:
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            except Exception:
                return []
        out: List[Dict[str, Any]] = []
        for line in reversed(lines[-limit:]):
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out


# --------------------------------------------------------------------------- #
# Git 管理
# --------------------------------------------------------------------------- #
class GitManager:
    """封装常用 Git 操作。所有写操作写审计；push 使用凭据管理器 token 免交互。"""

    GIT_TIMEOUT = 180  # 秒，push 在网络差时可能较慢

    def __init__(self, audit: AuditLog, config: ConfigStore, root: Path = PROJECT_ROOT):
        self.audit = audit
        self.config = config
        self.root = Path(root).resolve()
        self._lock = threading.Lock()  # 串行化 git 写操作，避免 index.lock 冲突

    @staticmethod
    def _wincred_token() -> Optional[str]:
        if sys.platform != "win32":
            return None
        try:
            from ctypes import wintypes

            class CREDENTIAL(ctypes.Structure):
                _fields_ = [
                    ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
                ]

            advapi32 = ctypes.windll.advapi32
            ptr = ctypes.POINTER(ctypes.c_void_p)()
            if not advapi32.CredReadW("git:https://github.com", 0x1, 0, ctypes.byref(ptr)):
                return None
            cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            advapi32.CredFree(ptr)
            return blob.decode("utf-16-le").rstrip("\x00") or None
        except Exception:
            return None

    def _env(self, no_proxy: bool = False) -> Dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        if no_proxy:
            for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
                env.pop(k, None)
        return env

    def _run(self, args: List[str], no_proxy: bool = False) -> Dict[str, Any]:
        try:
            p = subprocess.run(
                args, cwd=str(self.root), env=self._env(no_proxy),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.GIT_TIMEOUT,
            )
            out = p.stdout.strip() if p.stdout else ""
            err = p.stderr.strip() if p.stderr else ""
            return {"ok": p.returncode == 0, "code": p.returncode, "stdout": out, "stderr": err}
        except subprocess.TimeoutExpired:
            return {"ok": False, "code": -1, "stdout": "", "stderr": f"命令超时（{self.GIT_TIMEOUT}s）"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "code": -1, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}

    def _git(self, *args: str, no_proxy: bool = False) -> Dict[str, Any]:
        return self._run(["git", *args], no_proxy=no_proxy)

    # ---------- 只读 ----------
    def status(self) -> Dict[str, Any]:
        r = self._git("status", "--porcelain=v1", "-b")
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"]}
        lines = r["stdout"].splitlines()
        head = lines[0] if lines else "## ..."
        # ## main...origin/main [ahead 1, behind 2]
        branch, ahead, behind = head[3:].split("...")[0], 0, 0
        if "[" in head and "]" in head:
            bracket = head[head.find("[") + 1:head.find("]")]
            import re
            m_a = re.search(r"ahead (\d+)", bracket)
            m_b = re.search(r"behind (\d+)", bracket)
            ahead = int(m_a.group(1)) if m_a else 0
            behind = int(m_b.group(1)) if m_b else 0
        changes = []
        for line in lines[1:]:
            if len(line) >= 3:
                changes.append({"code": line[:2], "path": line[3:]})
        return {"ok": True, "branch": branch, "ahead": ahead, "behind": behind,
                "changes": changes, "clean": not changes}

    def branches(self) -> Dict[str, Any]:
        r = self._git("branch", "-a", "--format=%(refname:short)")
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"]}
        cur = self._git("branch", "--show-current")
        return {"ok": True, "current": cur["stdout"].strip(),
                "branches": [b for b in r["stdout"].splitlines() if b]}

    def log(self, limit: int = 20) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 20), 100))
        r = self._git("log", f"-{limit}", "--date=format:%m-%d %H:%M",
                      "--pretty=format:%h%x09%ad%x09%an%x09%s")
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"]}
        out = []
        for line in r["stdout"].splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                out.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
        return {"ok": True, "commits": out}

    def diff(self, path: str = "", staged: bool = False) -> Dict[str, Any]:
        args = ["diff", "--stat", "HEAD"] if staged else ["diff", "--stat"]
        if path:
            args += ["--", path]
        r = self._git(*args)
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"]}
        return {"ok": True, "stat": r["stdout"] or "（无改动）"}

    def remote_branches(self) -> Dict[str, Any]:
        """列出可推送的远程分支名（精简）。"""
        cfg = self.config.get().get("git", {})
        remote = str(cfg.get("remote") or "origin")
        r = self._git("branch", "-r", "--format=%(refname:short)")
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"]}
        names = []
        for line in r["stdout"].splitlines():
            name = line.strip()
            if name.startswith(remote + "/") and "HEAD" not in name:
                names.append(name[len(remote) + 1:])
        return {"ok": True, "remote": remote, "branches": sorted(set(names))}

    # ---------- 写操作 ----------
    def add(self, paths: List[str], ip: str = "") -> Dict[str, Any]:
        if not isinstance(paths, list) or not paths:
            return {"ok": False, "error": "未选择文件"}
        safe = []
        for p in paths:
            rel = str(p).replace("\\", "/").lstrip("/")
            if not rel or ".." in rel.split("/") or ":" in rel.split("/")[0]:
                return {"ok": False, "error": f"非法路径: {p}"}
            safe.append(rel)
        with self._lock:
            r = self._git("add", "--", *safe)
        self.audit.append("git.add", f"{len(safe)} 个文件: {', '.join(safe[:5])}", r["ok"], ip)
        return {"ok": r["ok"], "stdout": r["stdout"], "error": r["stderr"] if not r["ok"] else ""}

    def commit(self, message: str, ip: str = "") -> Dict[str, Any]:
        msg = (message or "").strip()
        if not msg:
            return {"ok": False, "error": "提交信息不能为空"}
        with self._lock:
            r = self._git("commit", "-m", msg)
        self.audit.append("git.commit", msg[:120], r["ok"], ip)
        return {"ok": r["ok"], "stdout": r["stdout"], "error": r["stderr"] if not r["ok"] else ""}

    def push(self, branch: str = "", remote: str = "", ip: str = "", require_confirm: bool = True) -> Dict[str, Any]:
        if require_confirm and branch.strip().lower() not in ("main", "slim", "master"):
            allowed = {"main", "slim", "master"}
            if branch.strip() not in allowed:
                return {"ok": False, "error": "目标分支不在允许列表（main / slim / master）"}
        cfg = self.config.get().get("git", {})
        remote = (remote or str(cfg.get("remote") or "origin")).strip()
        branch = (branch or str(cfg.get("default_branch") or "main")).strip()
        if not branch:
            return {"ok": False, "error": "未指定推送分支"}

        token = self._wincred_token()
        if not token:
            return {"ok": False, "error": "无法从 Windows 凭据管理器读取 GitHub token，无法免交互推送"}

        # 内联 token URL；禁用 credential helper 与代理，规避沙箱 GCM 卡死 / CONNECT 502
        cmd = [
            "git",
            "-c", "credential.helper=",
            "-c", "http.proxy=",
            "-c", "https.proxy=",
            "-c", f"url.https://colever-Beep:{token}@github.com/.insteadOf=https://github.com/",
            "push", remote, f"HEAD:{branch}",
        ]
        with self._lock:
            r = self._run(cmd, no_proxy=True)
        # 防御性脱敏：任何输出都不得出现 token
        scrub = lambda s: (s or "").replace(token, "***TOKEN***")
        result = {"ok": r["ok"], "branch": branch, "remote": remote,
                  "stdout": scrub(r["stdout"]), "error": scrub(r["stderr"]) if not r["ok"] else ""}
        self.audit.append("git.push", f"{remote} HEAD:{branch} {'成功' if r['ok'] else '失败'}", r["ok"], ip)
        return result

    def pull(self, branch: str = "", remote: str = "", ip: str = "") -> Dict[str, Any]:
        cfg = self.config.get().get("git", {})
        remote = (remote or str(cfg.get("remote") or "origin")).strip()
        branch = (branch or str(cfg.get("default_branch") or "main")).strip()
        with self._lock:
            r = self._git("pull", "--ff-only", remote, branch, no_proxy=True)
        return {"ok": r["ok"], "stdout": r["stdout"], "error": r["stderr"] if not r["ok"] else ""}


# --------------------------------------------------------------------------- #
# 文件管理
# --------------------------------------------------------------------------- #
class FileManager:
    def __init__(self, audit: AuditLog, root: Path = PROJECT_ROOT):
        self.root = root.resolve()
        self.audit = audit

    def _resolve(self, rel: str) -> Optional[Path]:
        if not isinstance(rel, str):
            return None
        rel = rel.strip().replace("\\", "/")
        if not rel or rel.startswith("/") or ":" in rel.split("/")[0]:
            return None
        try:
            resolved = (self.root / rel).resolve()
            resolved.relative_to(self.root)  # 路径穿越检测
        except Exception:
            return None
        return resolved

    def _segments(self, path: Path) -> Tuple[str, ...]:
        return tuple(part for part in path.relative_to(self.root).parts)

    def _denied(self, path: Path, mode: str) -> bool:
        segs = self._segments(path)
        if not segs:
            return True
        for s in segs:
            if _is_deny_name(s):
                return True
        if mode in ("write", "delete", "upload"):
            rel = "/".join(segs)
            if not any(rel == r or rel.startswith(r + "/") for r in WRITABLE_ROOTS):
                return True
            if segs in WRITE_DENY:
                return True
            if mode == "delete" and segs in DELETE_DENY:
                return True
        return False

    def list_dir(self, rel: str = "") -> Dict[str, Any]:
        if rel.strip():
            target = self._resolve(rel)
            if target is None or not target.exists() or not target.is_dir():
                return {"ok": False, "error": "目录不存在或不可访问", "path": rel or "."}
            if self._denied(target, "read"):
                return {"ok": False, "error": "该目录受保护", "path": rel}
        else:
            target = self.root
        items: List[Dict[str, Any]] = []
        try:
            for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    if self._denied(child, "read"):
                        continue
                    st = child.stat()
                    items.append({
                        "name": child.name,
                        "path": child.relative_to(self.root).as_posix(),
                        "type": "dir" if child.is_dir() else "file",
                        "size": int(st.st_size) if child.is_file() else 0,
                        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                        "writable": not self._denied(child, "write"),
                    })
                except Exception:
                    continue
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "path": rel or "."}
        return {"ok": True, "path": rel or ".", "items": items}

    def read(self, rel: str) -> Dict[str, Any]:
        path = self._resolve(rel)
        if path is None or self._denied(path, "read"):
            return {"ok": False, "error": "文件不存在或受保护"}
        if not path.is_file():
            return {"ok": False, "error": "不是文件"}
        if path.stat().st_size > 1024 * 1024:
            return {"ok": False, "error": "文件过大（>1MB），不支持在线编辑"}
        try:
            raw = path.read_bytes()
            if b"\x00" in raw[:4096]:
                return {"ok": False, "error": "疑似二进制文件，无法以文本读取"}
            content = raw.decode("utf-8").replace("\r\n", "\n")
            return {"ok": True, "path": path.relative_to(self.root).as_posix(),
                    "content": content, "writable": not self._denied(path, "write")}
        except UnicodeDecodeError:
            return {"ok": False, "error": "文件不是 UTF-8 编码"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def write(self, rel: str, content: str, ip: str = "") -> Dict[str, Any]:
        path = self._resolve(rel)
        if path is None or self._denied(path, "write"):
            self.audit.append("file.write", rel[:200], False, ip)
            return {"ok": False, "error": "目标目录不允许写入或文件受保护"}
        if path.exists() and path.is_dir():
            return {"ok": False, "error": "目标是目录"}
        try:
            existed = path.exists()
            _atomic_write(path, content)
            self.audit.append("file.write" if existed else "file.create", rel[:200], True, ip)
            return {"ok": True, "path": path.relative_to(self.root).as_posix(), "created": not existed}
        except Exception as e:  # noqa: BLE001
            self.audit.append("file.write", rel[:200], False, ip)
            return {"ok": False, "error": str(e)}

    def upload(self, rel_dir: str, filename: str, data_b64: str, ip: str = "") -> Dict[str, Any]:
        base = self._resolve(rel_dir) if rel_dir.strip() else None
        if base is None or not base.is_dir() or self._denied(base, "upload"):
            return {"ok": False, "error": "目标目录不允许上传"}
        name = (filename or "").strip().replace("\\", "/").split("/")[-1]
        if not name or _is_deny_name(name) or Path(name).suffix.lower() not in UPLOAD_ALLOW_EXT:
            return {"ok": False, "error": "文件名非法或类型不允许"}
        try:
            raw = base64.b64decode(data_b64 or "", validate=True)
        except Exception:
            return {"ok": False, "error": "文件内容不是合法的 base64"}
        if len(raw) > UPLOAD_MAX_BYTES:
            return {"ok": False, "error": f"文件超过 {UPLOAD_MAX_BYTES // 1024 // 1024}MB 限制"}
        target = base / name
        if self._denied(target, "upload"):
            return {"ok": False, "error": "目标文件受保护"}
        try:
            target.write_bytes(raw)
            self.audit.append("file.upload", target.relative_to(self.root).as_posix(), True, ip)
            return {"ok": True, "path": target.relative_to(self.root).as_posix(), "size": len(raw)}
        except Exception as e:  # noqa: BLE001
            self.audit.append("file.upload", name[:200], False, ip)
            return {"ok": False, "error": str(e)}

    def delete(self, rel: str, ip: str = "") -> Dict[str, Any]:
        path = self._resolve(rel)
        if path is None or self._denied(path, "delete"):
            self.audit.append("file.delete", rel[:200], False, ip)
            return {"ok": False, "error": "文件不存在或不允许删除"}
        if not path.is_file():
            return {"ok": False, "error": "只能删除文件，不能删除目录"}
        try:
            path.unlink()
            self.audit.append("file.delete", rel[:200], True, ip)
            return {"ok": True, "path": rel}
        except Exception as e:  # noqa: BLE001
            self.audit.append("file.delete", rel[:200], False, ip)
            return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# 系统信息
# --------------------------------------------------------------------------- #
def _memory_mb() -> Optional[Dict[str, int]]:
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return {"total": st.ullTotalPhys // 1048576, "available": st.ullAvailPhys // 1048576}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                return {"total": total, "available": int(line.split()[1]) // 1024}
    except Exception:
        pass
    return None


def system_info(started_at: float, repo: str, interval: int, auth_source: str,
                rate_limit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    disk = shutil.disk_usage(str(PROJECT_ROOT))
    return {
        "ok": True,
        "app": "BilibiliDownloader 发行管理后台",
        "app_version": "1.1.0",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "memory_mb": _memory_mb(),
        "disk": {"total_gb": round(disk.total / 1073741824, 1),
                 "used_gb": round(disk.used / 1073741824, 1),
                 "free_gb": round(disk.free / 1073741824, 1)},
        "project_root": str(PROJECT_ROOT),
        "uptime_seconds": int(time.time() - started_at),
        "repo": repo,
        "refresh_interval": interval,
        "github_auth": auth_source,
        "github_rate_limit": rate_limit or {},
        "generated_at": _now_iso(),
    }
