#!/usr/bin/env python3
# scripts/i18n_tools.py
"""i18n 工具链：抽取 -> .pot/.po -> 烘焙回 utils/locales_*.py。

设计目标
--------
* 零第三方依赖（仅用标准库 ast / importlib），可直接用系统 Python 运行。
* 翻译存储交给标准 gettext 格式（.pot 模板 + 各语言 .po），Weblate 原生支持。
* 运行时 i18n.py（tr/register/retranslate_all）完全不改：烘焙脚本把 .po 重新
  生成成 utils/locales_weblate.py，其 FRAGMENT 结构与现有 locales_*.py 完全一致。

用法
----
    python scripts/i18n_tools.py extract [--seed]   # 生成 messages.pot 并同步各语言 .po
    python scripts/i18n_tools.py bake               # .po -> utils/locales_weblate.py
    python scripts/i18n_tools.py stats              # 打印各语言翻译覆盖率

--seed：首次迁移用，把现有 utils/locales_*.py 的译文回填进新 .po（仅填补缺失项）。
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UTILS = ROOT / "utils"
TRANS = ROOT / "translations"
POT = TRANS / "messages.pot"
DOMAIN = "messages"

# 源语言是简体中文（msgid 即中文原文），以下为待翻译目标语言。
SOURCE_LANG = "zh_CN"
LANGS = ["zh_TW", "en", "ja"]

EXCLUDE_DIRS = {
    "bili23_example", "__pycache__", "dist", "build", "bin", "scripts",
    ".build_tmp", ".git", "node_modules", "env", "venv", ".venv",
}
SKIP_PREFIXES = ("test_", "smoke_", "verify_")

PLURAL_FORMS = {
    "en": "nplurals=2; plural=(n != 1);",
    "ja": "nplurals=1; plural=0;",
    "zh_TW": "nplurals=1; plural=0;",
}


def _discover_langs() -> list[str]:
    """从 translations/<lang>/LC_MESSAGES/messages.po 自动发现仓库中已有语言。

    这样译者在 Weblate 上新增一种语言（自动生成对应 .po）后，无需改代码即可
    被 bake / stats 识别并合并进运行时字典。源语言 zh_CN 没有独立 .po，被排除。
    """
    found = []
    for po in sorted(TRANS.glob("*/LC_MESSAGES/messages.po")):
        lang = po.relative_to(TRANS).parts[0]
        if lang and lang != SOURCE_LANG:
            found.append(lang)
    return found


def active_langs() -> list[str]:
    """硬编码目标语言 + 仓库中已存在的语言（去重并排序）。

    LANGS 保证即便仓库尚未生成任何 .po 也能正确初始化；已存在的 .po 语言（可能
    由 Weblate 新增）也会被纳入，二者合并即为 bake / extract / stats 实际处理的集合。
    """
    return sorted(set(LANGS) | set(_discover_langs()))


# --------------------------------------------------------------------------- #
# .po 读写（极简但足够覆盖本项目：无复数 / 无 msgctxt）
# --------------------------------------------------------------------------- #
def _unquote(s: str) -> str:
    """把 .po 引号串（可能跨多行拼接）还原为真实字符串。"""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _quote(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return '"' + s + '"'


def _seg(s: str) -> str:
    """从一行中抽取首个被引号包裹的串并还原转义（跨行续接由调用方拼接）。"""
    s = s.strip()
    i = s.find('"')
    if i == -1:
        return ""
    j = s.find('"', i + 1)
    if j == -1:
        return ""
    return _unquote(s[i + 1:j])


def read_po(path: Path):
    """返回 [(msgid, msgstr), ...]，跳过空 msgid（文件头）。"""
    entries = []
    state = None
    id_parts = []   # 已还原转义的片段
    str_parts = []

    def finalize():
        if id_parts:
            mid = "".join(id_parts)
            if mid != "":
                entries.append((mid, "".join(str_parts)))

    with open(path, encoding="utf-8") as f:
        for raw in f:
            st = raw.strip()
            if st == "":
                finalize()
                id_parts, str_parts, state = [], [], None
                continue
            if st.startswith("#"):
                continue
            if st.startswith("msgid"):
                finalize()
                id_parts, str_parts, state = [], [], "id"
                id_parts.append(_seg(st[len("msgid"):]))
                continue
            if st.startswith("msgid_plural"):
                id_parts.append(_seg(st[len("msgid_plural"):]))
                continue
            if st.startswith("msgstr"):
                state = "str"
                str_parts.append(_seg(st[st.find("msgstr") + len("msgstr"):]))
                continue
            if st.startswith('"'):
                if state == "id":
                    id_parts.append(_seg(st))
                elif state == "str":
                    str_parts.append(_seg(st))
                continue
    finalize()
    return entries


def _po_header(lang: str | None) -> str:
    date = _dt.datetime.now().strftime("%Y-%m-%d %H:%M%z")
    plural = PLURAL_FORMS.get(lang, "nplurals=1; plural=0;") if lang else "nplurals=1; plural=0;"
    lang_line = f'"Language: {lang}\\n"' if lang else '"Language: \\n"'
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: bili23 1.0\\n"',
        '"Report-Msgid-Bugs-To: \\n"',
        f'"POT-Creation-Date: {date}\\n"',
        f'"PO-Revision-Date: {date}\\n"',
        '"Last-Translator: \\n"',
        lang_line,
        '"Language-Team: \\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Plural-Forms: {plural}\\n"',
        "",
    ]
    return "\n".join(lines)


def write_po(path: Path, entries, lang: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [_po_header(lang)]
    for msgid, msgstr in entries:
        out.append("")
        out.append("msgid " + _quote(msgid))
        out.append("msgstr " + (_quote(msgstr) if msgstr else '""'))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# 抽取（ast，无依赖）
# --------------------------------------------------------------------------- #
def iter_py(root: Path):
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if set(rel.parts) & EXCLUDE_DIRS:
            continue
        if p.name.startswith(SKIP_PREFIXES):
            continue
        yield p


def extract_strings(root: Path) -> list[str]:
    found = set()
    for py in iter_py(root):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
            if name == "tr" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)
            if name == "register" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                found.add(node.args[1].value)
    return sorted(found)


def load_legacy_locales() -> dict:
    """读取现有 utils/locales_*.py 的 FRAGMENT，合并为 {源文: {lang: 译文}}。"""
    merged: dict = {}
    for p in sorted(UTILS.glob("locales_*.py")):
        if p.name == "locales_weblate.py":
            continue
        spec = importlib.util.spec_from_file_location("legacy_" + p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        frag = getattr(mod, "FRAGMENT", None)
        if not isinstance(frag, dict):
            continue
        for zh, trans in frag.items():
            if not isinstance(trans, dict):
                continue
            merged.setdefault(zh, {})
            for lang, text in trans.items():
                if isinstance(text, str):
                    merged[zh][lang] = text
    return merged


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def cmd_extract(seed: bool) -> None:
    strings = extract_strings(ROOT)
    POT.parent.mkdir(parents=True, exist_ok=True)
    write_po(POT, [(s, "") for s in strings], None)
    print(f"[extract] messages.pot: {len(strings)} 条源字符串")

    legacy = load_legacy_locales() if seed else {}
    for lang in active_langs():
        po = TRANS / lang / "LC_MESSAGES" / (DOMAIN + ".po")
        existing = {k: v for k, v in read_po(po)} if po.exists() else {}
        if seed:
            for s in strings:
                if s not in existing and s in legacy and lang in legacy[s]:
                    existing[s] = legacy[s][lang]
        out = [(s, existing.get(s, "")) for s in strings]
        write_po(po, out, lang)
        filled = sum(1 for _, v in out if v)
        print(f"[extract] {lang}: {filled}/{len(strings)} 已填")


def cmd_bake() -> None:
    frag: dict = {}
    for lang in active_langs():
        po = TRANS / lang / "LC_MESSAGES" / (DOMAIN + ".po")
        if not po.exists():
            print(f"[bake] 跳过缺失: {po}")
            continue
        for msgid, msgstr in read_po(po):
            if msgstr:
                frag.setdefault(msgid, {})[lang] = msgstr
    # 生成 utils/locales_weblate.py（结构与现有 locales_*.py 一致）
    lines = [
        "# 本文件由 scripts/i18n_tools.py bake 自动生成，请勿手改。",
        "# 译文请通过 Weblate 平台或直接编辑 translations/<lang>/LC_MESSAGES/messages.po，",
        "# 然后运行 python scripts/i18n_tools.py bake 重新生成。",
        "",
        "FRAGMENT = {",
    ]
    for zh in sorted(frag):
        inner = ", ".join(f"{repr(lg)}: {repr(txt)}" for lg, txt in frag[zh].items())
        lines.append(f"    {repr(zh)}: {{{inner}}},",)
    lines.append("}")
    (UTILS / "locales_weblate.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = len(frag)
    print(f"[bake] 已生成 utils/locales_weblate.py（{total} 条源字符串有译文）")


def cmd_stats() -> None:
    strings = set(extract_strings(ROOT))
    print(f"源字符串总数: {len(strings)}")
    for lang in active_langs():
        po = TRANS / lang / "LC_MESSAGES" / (DOMAIN + ".po")
        if not po.exists():
            print(f"  {lang}: 无 .po 文件")
            continue
        entries = read_po(po)
        filled = sum(1 for m, v in entries if m and v)
        pct = (filled / len(strings) * 100) if strings else 0
        print(f"  {lang}: {filled}/{len(strings)} 已译 ({pct:.1f}%)")


def main() -> int:
    ap = argparse.ArgumentParser(description="i18n 工具链（抽取 / 烘焙 / 统计）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract", help="生成 .pot 并同步各语言 .po")
    ex.add_argument("--seed", action="store_true", help="从现有 locales_*.py 回填译文")
    sub.add_parser("bake", help=".po -> utils/locales_weblate.py")
    sub.add_parser("stats", help="打印翻译覆盖率")
    args = ap.parse_args()

    if args.cmd == "extract":
        cmd_extract(args.seed)
    elif args.cmd == "bake":
        cmd_bake()
    elif args.cmd == "stats":
        cmd_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
