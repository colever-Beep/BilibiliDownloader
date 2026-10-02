import requests
from requests.cookies import create_cookie
import re
import json
import time
import hashlib
import hmac
import struct
import random
from datetime import datetime
from urllib.parse import urlencode
import concurrent.futures  # 确保导入
from utils.helpers import duration_to_seconds

class BiliAPI:
    def __init__(self, cookie_string=""):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "Windows"
        })
        self.session.verify = False
        self.uid = None
        self.nickname = None
        self.avatar = None
        self.SESSDATA = ""
        self.bili_jct = ""
        self.cookies = {}
        # WBI签名相关
        self.wbi_mixin_key = ""
        self.wbi_last_refresh = 0
        
        if cookie_string:
            self.set_cookie_string(cookie_string)

    def clear_all_cookies(self):
        self.session.cookies.clear()
        self.uid = None
        self.nickname = None
        self.avatar = None
        self.SESSDATA = ""
        self.bili_jct = ""
        self.cookies.clear()
        self.wbi_mixin_key = ""

    def set_cookie_string(self, cookie_string):
        """解析 Cookie 字符串并登录。支持三种格式：
        1) JSON 对象：{"SESSDATA": "...", "bili_jct": "..."}
        2) Netscape 多行（tab 或空格分隔的 7 字段；也兼容每行一个 key=value）
        3) 请求头 Cookie：SESSDATA=xxx; bili_jct=yyy
        """
        self.clear_all_cookies()
        raw = (cookie_string or "").strip()
        if not raw:
            print("[Cookie解析] 输入内容为空")
            return False

        # 1) JSON 格式
        if raw.lstrip().startswith("{"):
            try:
                obj = json.loads(raw)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                for name, value in obj.items():
                    self._add_cookie(name, str(value))
            else:
                print("[Cookie解析] JSON 解析失败")
                return False
        # 2) 多行（Netscape 或每行 key=value）
        elif "\n" in raw:
            any_ok = False
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Netscape 字段用 tab 或连续空格分隔，兼容空格版
                parts = re.split(r"\s+", line)
                if len(parts) >= 7:
                    # domain flag path secure expires name value
                    domain, _flag, path, secure, _expires, name, value = parts[:7]
                    self._add_cookie(name, value,
                                     domain=domain or ".bilibili.com",
                                     path=path or "/",
                                     secure=secure.lower() in ("true", "1"))
                elif "=" in line:
                    # 每行一个 key=value 的导出
                    name, _, value = line.partition("=")
                    self._add_cookie(name, value)
                else:
                    continue
                any_ok = True
            if not any_ok:
                print("[Cookie解析] Netscape 格式无法识别（需为 tab/空格分隔的 7 字段）")
                return False
        # 3) 单行请求头 Cookie
        elif "=" in raw:
            for seg in raw.split(";"):
                seg = seg.strip()
                if "=" not in seg:
                    continue
                name, _, value = seg.partition("=")
                self._add_cookie(name, value)
        else:
            print("[Cookie解析] 无法识别格式（支持 Netscape / 请求头 Cookie / JSON）")
            return False

        # 同步cookie到字典
        self.cookies.clear()
        for cookie in self.session.cookies:
            self.cookies[cookie.name] = cookie.value

        if not self.SESSDATA:
            print("[登录校验失败] 未解析SESSDATA，无法登录")
            return False
        login_ok = self._refresh_user_info()
        if login_ok:
            print(f"[登录成功] UID:{self.uid} 昵称:{self.nickname}")
        return login_ok

    def _add_cookie(self, name, value, domain=".bilibili.com", path="/", secure=True):
        """写入单个 cookie 并同步关键字段（SESSDATA / bili_jct）。"""
        name = (name or "").strip()
        value = (value or "").strip()
        if not name:
            return
        if name == "SESSDATA":
            self.SESSDATA = value
        if name == "bili_jct":
            self.bili_jct = value
        try:
            cookie = create_cookie(name, value, domain=domain, path=path, secure=secure)
            self.session.cookies.set_cookie(cookie)
        except Exception:
            pass

    def _refresh_user_info(self):
        try:
            resp = self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=15)
            res_json = resp.json()
            code = res_json.get("code", -1)
            if code != 0:
                print(f"[登录校验失败 code:{code} msg:{res_json.get('message')}")
                self.uid = None
                return False
            data = res_json.get("data", {})
            if not data.get("isLogin"):
                print("[登录校验失败] Cookie过期/风控拦截 isLogin=false")
                self.uid = None
                return False
            self.uid = data.get("mid")
            self.nickname = data.get("uname")
            self.avatar = data.get("face")
            
            # 获取WBI密钥并生成mixin_key
            self._refresh_wbi_keys(data)
            
            return True
        except Exception as e:
            print(f"[nav接口异常] {str(e)}")
            return False

    # ========== WBI 密钥生成 ==========
    def _refresh_wbi_keys(self, nav_data=None):
        """从nav接口数据提取wbi密钥，生成mixin_key"""
        try:
            if nav_data is None:
                resp = self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
                nav_data = resp.json().get("data", {})
            
            wbi_img = nav_data.get("wbi_img", {})
            img_url = wbi_img.get("img_url", "")
            sub_url = wbi_img.get("sub_url", "")
            
            # 安全提取文件名
            img_key = ""
            sub_key = ""
            if img_url:
                match = re.search(r"/([^/]+)\.png", img_url)
                if match:
                    img_key = match.group(1)
            if sub_url:
                match = re.search(r"/([^/]+)\.png", sub_url)
                if match:
                    sub_key = match.group(1)
            
            if not (img_key and sub_key):
                print("[WBI签名] 密钥获取失败：缺少 img_key 或 sub_key")
                return False
            
            raw = img_key + sub_key
            # 确保长度足够（至少64位）
            if len(raw) < 64:
                print(f"[WBI签名] raw长度不足64，实际为 {len(raw)}，无法生成mixin_key")
                return False
            
            # 生成32位mixin key（固定索引表，来自社区逆向）
            mixin_key_table = [
                46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
                27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
                37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 22,
                56, 25, 21, 6, 63, 57, 59, 20, 34, 54, 62, 11, 36, 52, 44
            ]
            self.wbi_mixin_key = "".join([raw[i] for i in mixin_key_table])[:32]
            self.wbi_last_refresh = time.time()
            print(f"[WBI签名] 密钥刷新成功，mixin_key长度:{len(self.wbi_mixin_key)}")
            return True
        except Exception as e:
            print(f"[WBI签名] 密钥刷新异常:{str(e)}")
            return False

    def wbi_sign(self, params):
        """对参数进行WBI签名，返回带wts和w_rid的新参数字典"""
        if not self.wbi_mixin_key or time.time() - self.wbi_last_refresh > 3600:
            if not self._refresh_wbi_keys():
                print("[WBI签名] 密钥刷新失败，本次请求将不携带签名")
                return params
        
        if not self.wbi_mixin_key:
            return params
            
        params = dict(params)
        wts = int(time.time())
        params["wts"] = wts
        
        def filt(v):
            return re.sub(r"[!'\(\)\*]", "", str(v))
        
        for k in list(params.keys()):
            params[k] = filt(params[k])
        
        query = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
        w_rid = hashlib.md5((query + self.wbi_mixin_key).encode("utf-8")).hexdigest()
        params["w_rid"] = w_rid
        return params

    def format_timestamp(self, ts, fmt="%Y-%m-%d %H:%M:%S"):
        if ts is None or ts == "":
            return ""
        try:
            if isinstance(ts, str) and ts.isdigit():
                ts = int(ts)
            if isinstance(ts, (int, float)):
                if ts > 1e11:
                    ts = int(ts / 1000)
                return datetime.fromtimestamp(int(ts)).strftime(fmt)
        except Exception:
            pass
        return str(ts)

    def _get_with_csrf(self, url, params=None):
        if params is None:
            params = {}
        if self.bili_jct:
            params["csrf"] = self.bili_jct
        return self.session.get(url, params=params, timeout=12)

    # ========== 收藏夹相关 ==========
    def get_favorite_folders(self):
        if not self.uid:
            if not self._refresh_user_info():
                print("[收藏夹] 未登录")
                return []
        url = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
        params = {"up_mid": self.uid}
        try:
            resp = self._get_with_csrf(url, params)
            try:
                data = resp.json() if resp is not None else None
            except Exception:
                data = None
            if not isinstance(data, dict):
                print(f"[获取收藏夹失败] 响应非 JSON（可能风控/未登录），params={params}")
                return []
            if data.get("code") != 0:
                print(f"[获取收藏夹失败 code:{data.get('code')} msg:{data.get('message')} resp:{getattr(resp, 'text', '')} params:{params}")
                return []
            return data.get("data", {}).get("list", [])
        except Exception as e:
            print(f"[获取收藏夹异常] {str(e)}")
            return []

    def get_favorite_list(self, media_id, pn=1, ps=20):
        """获取收藏夹某一页的视频（单次请求，不再递归拉取全部）。

        返回结构化 dict：
          - items:    本页原始 media 列表（已补全 pic/thumbnail/author/publish_time/favorite_time）
          - has_more: 是否还有下一页（来自 data.has_more）
          - total:    收藏夹总条数（来自 data.info.media_count）
          - page:     当前页码
        上层（分页 loader）据此驱动「上一页 / 下一页」按钮，做到一次只拉一页。
        """
        if not self.uid:
            return {"items": [], "has_more": False, "total": 0, "page": pn}
        url = "https://api.bilibili.com/x/v3/fav/resource/list"
        params = {
            "media_id": media_id,
            "pn": pn,
            "ps": ps,
            "keyword": "",
            "order": "mtime",
            "type": 0,
            "tid": 0,
            "platform": "web",
            "web_location": "333.1387",
        }
        try:
            resp = self._get_with_csrf(url, params)
            try:
                data = resp.json() if resp is not None else None
            except Exception:
                data = None
            if not isinstance(data, dict):
                print(f"[收藏内容 第{pn}页 响应非 JSON/为空（可能风控/未登录），media_id={media_id}]")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            if data.get("code") != 0:
                print(f"[收藏内容 第{pn}页 失败 code:{data.get('code')} msg:{data.get('message')}")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            d = data.get("data", {})
            medias = d.get("medias", []) or []
            for m in medias:
                pic = m.get("pic", "")
                if pic and pic.startswith("//"):
                    m["pic"] = "https:" + pic
                elif pic and pic.startswith("http://"):
                    m["pic"] = pic.replace("http://", "https://")
                pubdate = m.get("pubdate") or m.get("ctime") or m.get("pubdate_time")
                m["publish_time"] = self.format_timestamp(pubdate) if pubdate else ""
                fav_time = m.get("fav_time") or m.get("add_at") or m.get("favtime") or m.get("add_at_time")
                m["favorite_time"] = self.format_timestamp(fav_time) if fav_time else ""
                m["thumbnail"] = m.get("pic", "")
                m["author"] = (m.get("upper") or {}).get("name", "")  # 提取UP主名称（upper 可能为 None）
            has_more = d.get("has_more", False)
            total = (d.get("info") or {}).get("media_count", 0)
            print(f"[收藏夹] 第{pn}页 拉取 {len(medias)} 条，has_more={has_more}，total={total}")
            return {"items": medias, "has_more": has_more, "total": total, "page": pn}
        except Exception as e:
            print(f"[读取收藏内容异常 media_id={media_id}] {str(e)}")
            return {"items": [], "has_more": False, "total": 0, "page": pn}

    # ========== 稍后再看 ==========
    def get_toview(self, pn=1, ps=20):
        """获取稍后再看列表的某一页（单次请求，不再循环拉取全部）。

        返回结构化 dict：
          - items:    本页列表（need_split 时合并 unviewed/viewed 两段，已补全封面/时间）
          - has_more: 是否还有下一页（由 data.count 与当前页比对得出）
          - total:    总条数（来自 data.count）
          - page:     当前页码
        上层（分页 loader）据此驱动「上一页 / 下一页」按钮，做到一次只拉一页。
        """
        if not self.uid:
            if not self._refresh_user_info():
                print("[稍后再看] 未登录")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
        url = "https://api.bilibili.com/x/v2/history/toview/web"
        params = {
            "pn": pn,
            "ps": ps,
            "viewed": 0,
            "key": "",
            "asc": False,
            "need_split": True,
            "web_location": "333.881",
        }
        try:
            signed_params = self.wbi_sign(params)
            resp = self.session.get(url, params=signed_params, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[稍后再看] API错误 code:{data.get('code')} msg:{data.get('message')}")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            page_data = data.get("data", {})
            # need_split=True 时 data.list 可能是 dict（含 viewed/unviewed），合并两段
            items = page_data.get("list", [])
            if isinstance(items, dict):
                items = (items.get("unviewed") or []) + (items.get("viewed") or [])
            total = page_data.get("count", 0)
            for item in items:
                cover = item.get("cover") or item.get("pic") or ""
                if cover and cover.startswith("//"):
                    cover = "https:" + cover
                elif cover and cover.startswith("http://"):
                    cover = cover.replace("http://", "https://")
                item["cover"] = cover
                item["thumbnail"] = cover
                item["publish_time"] = self.format_timestamp(item.get("view_at") or item.get("pubdate") or item.get("ctime"))
                item["play"] = 0
                item["like"] = 0
                item["fav"] = 0
            has_more = bool(total) and (pn * ps < total)
            print(f"[稍后再看] 第{pn}页 拉取 {len(items)} 条，has_more={has_more}，total={total}")
            return {"items": items, "has_more": has_more, "total": total, "page": pn}
        except Exception as e:
            print(f"[稍后再看] 请求异常: {str(e)}")
            return {"items": [], "has_more": False, "total": 0, "page": pn}

    # ========== 视频信息 ==========
    def _uploader_from_data(self, data):
        """从 view 接口 data 提取上传者展示名。

        联合投稿（多UP主创作）视频的 data.staff 含全部创作者，而 owner.name 仅为
        发布账号。若只取 owner.name 会丢失共创者，对『多个UP主创作』的视频表现为
        『视频信息不全』。故存在 staff 时返回『主UP 等N位UP主』，补全创作者信息。
        """
        owner = (data.get("owner") or {}).get("name", "") or ""
        staff = data.get("staff") or []
        names = [s.get("name") for s in staff if s.get("name")]
        if not names:
            return owner
        if owner:
            return f"{owner} 等{len(names)}位UP主"
        return "、".join(names[:3]) + (f" 等{len(names)}人" if len(names) > 3 else "")

    def get_video_info(self, bvid, get_info_data=False):
        url = "https://api.bilibili.com/x/web-interface/wbi/view"
        params = {"bvid": bvid}
        try:
            signed = self.wbi_sign(params)
            resp = self.session.get(url, params=signed, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[视频信息] 获取失败 code:{data.get('code')} msg:{data.get('message')} resp:{getattr(resp, 'text', '')} params:{signed}")
                return None
            if get_info_data:
                return data
            return data
        except Exception as e:
            print(f"[视频信息] 请求异常: {str(e)}")
            return None

    # ========== 历史记录 ==========
    def get_history(self, max_id=0, view_at=0, ps=20, business="archive",
                    max_pages=100, max_items=500):
        """获取浏览历史记录（cursor 游标分页，拉取全部）。

        与 history/search 不同，该接口用 max/view_at 游标翻页：响应 data.cursor 中的
        max / view_at 即为下一页入参，cursor.max == 0 表示已到末尾。循环翻页直到：
          - 游标耗尽（cursor.max == 0）
          - 某一页返回空列表
          - 达到 max_pages / max_items 安全上限
        返回 {"list": [...], "cursor": {...}}。
        """
        if not self.uid:
            if not self._refresh_user_info():
                print("[历史记录] 未登录")
                return None
        url = "https://api.bilibili.com/x/web-interface/history/cursor"
        all_items = []
        next_max = max_id
        next_view_at = view_at
        pages_fetched = 0
        last_cursor = {}
        for _ in range(max_pages):
            params = {
                "max": next_max,
                "view_at": next_view_at,
                "ps": ps,
                "business": business,
            }
            try:
                signed_params = self.wbi_sign(params)
                resp = self.session.get(url, params=signed_params, timeout=12)
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[历史记录] API错误 code:{data.get('code')} msg:{data.get('message')} resp:{getattr(resp, 'text', '')} params:{signed_params}")
                    if data.get("code") in (-400, -412):
                        print("[历史记录] 签名可能失效，刷新WBI密钥重试")
                        self._refresh_wbi_keys()
                        signed_params = self.wbi_sign(params)
                        resp = self.session.get(url, params=signed_params, timeout=12)
                        data = resp.json()
                        if data.get("code") != 0:
                            print(f"[历史记录] 重试仍失败 code:{data.get('code')} msg:{data.get('message')} params:{signed_params}")
                            break
                    else:
                        break
                result = data.get("data", {})
                items = result.get("list", [])
                for item in items:
                    cover = item.get("cover", "")
                    if cover and cover.startswith("//"):
                        item["cover"] = "https:" + cover
                    elif cover and cover.startswith("http://"):
                        item["cover"] = cover.replace("http://", "https://")
                all_items.extend(items)
                pages_fetched += 1
                last_cursor = result.get("cursor", {})
                # 终止条件
                if not items:
                    break
                if len(all_items) >= max_items:
                    print(f"[历史记录] 已达到安全上限 max_items={max_items}，停止翻页")
                    break
                next_max = last_cursor.get("max", 0)
                next_view_at = last_cursor.get("view_at", 0)
                if not next_max and not next_view_at:
                    # 游标归零，已无更多历史
                    break
            except Exception as e:
                print(f"[历史记录] 请求异常: {str(e)}")
                break
        print(f"[历史记录] 共拉取 {len(all_items)} 条（{pages_fetched} 页）")
        return {"list": all_items, "cursor": last_cursor}

    def get_history_search(self, pn=1, keyword="", business="archive", ps=20):
        """获取浏览历史记录某一页（单次请求，不再循环拉取全部）。

        返回结构化 dict：
          - items:    本页历史条目（已补全封面）
          - has_more: 是否还有下一页（由 data.page.total 与当前页比对得出）
          - total:    总条数（来自 data.page.total）
          - page:     当前页码
        上层（分页 loader）据此驱动「上一页 / 下一页」按钮，做到一次只拉一页。
        """
        if not self.uid:
            print("[历史记录] 未登录")
            return {"items": [], "has_more": False, "total": 0, "page": pn}
        base_params = {
            "keyword": keyword,
            "business": business,
            "add_time_start": 0,
            "add_time_end": 0,
            "arc_max_duration": 0,
            "arc_min_duration": 0,
            "device_type": 0,
            "web_location": "333.1391"
        }
        params = dict(base_params)
        params["pn"] = pn
        params["ps"] = ps
        url = f"https://api.bilibili.com/x/web-interface/history/search?{urlencode(params)}"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200:
                print(f"[历史记录] HTTP错误 {resp.status_code}")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            data = resp.json()
            if data.get("code") != 0:
                print(f"[历史记录] API错误 code:{data.get('code')} msg:{data.get('message')}")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            page_data = data.get("data", {})
            items = page_data.get("list", [])
            for item in items:
                cover = item.get("cover", "")
                if cover and cover.startswith("//"):
                    item["cover"] = "https:" + cover
                elif cover and cover.startswith("http://"):
                    item["cover"] = cover.replace("http://", "https://")
            total = page_data.get("page", {}).get("total", 0)
            has_more = bool(total) and (pn * ps < total)
            print(f"[历史记录] 第{pn}页 拉取 {len(items)} 条，has_more={has_more}，total={total}")
            return {"items": items, "has_more": has_more, "total": total, "page": pn}
        except Exception as e:
            print(f"[历史记录] 异常: {str(e)}")
            return {"items": [], "has_more": False, "total": 0, "page": pn}

    # ========== 新增：视频信息补全 ==========
    def enrich_videos(self, video_list, max_workers=5):
        """
        并发请求 get_video_info，补全视频列表中的缺失字段。
        直接修改原列表中的每个 dict。
        """
        def extract_bvid(url):
            match = re.search(r'/video/(BV\w+)', url)
            return match.group(1) if match else None

        def process_one(item):
            # 优先从 url 提取，其次直接用 item 自带的 bvid（番剧分集 url 不带 /video/）
            bvid = item.get('bvid') or extract_bvid(item.get('url', ''))
            if not bvid:
                return
            try:
                info = self.get_video_info(bvid)
                if not info or 'data' not in info:
                    return
                data = info['data']
                if 'duration' in data:
                    item['duration'] = data['duration']
                stat = data.get('stat', {})
                if 'view' in stat:
                    item['view_count'] = stat['view']
                if 'like' in stat:
                    item['like_count'] = stat['like']
                if 'favorite' in stat:
                    item['favorite_count'] = stat['favorite']
                if not item.get('thumbnail') or item['thumbnail'] == '':
                    pic = data.get('pic', '')
                    if pic and pic.startswith('//'):
                        pic = 'https:' + pic
                    elif pic and pic.startswith('http://'):
                        pic = pic.replace('http://', 'https://')
                    item['thumbnail'] = pic
                if not item.get('publish_time') or item['publish_time'] == '':
                    pubdate = data.get('pubdate')
                    if pubdate:
                        item['publish_time'] = self.format_timestamp(pubdate)
                if not item.get('uploader'):
                    item['uploader'] = self._uploader_from_data(data)
            except Exception as e:
                print(f"补全视频 {bvid} 失败: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_one, item) for item in video_list]
            for future in concurrent.futures.as_completed(futures):
                pass

    def get_following_list(self, pn=1, ps=50):
        """获取当前用户关注的UP主列表（递归获取全部）"""
        if not self.uid:
            if not self._refresh_user_info():
                print("[关注列表] 未登录")
                return []
        url = "https://api.bilibili.com/x/relation/followings"
        params = {"vmid": self.uid, "pn": pn, "ps": ps, "order": "desc"}
        try:
            signed = self.wbi_sign(params)
            resp = self.session.get(url, params=signed, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[关注列表] API错误: {data.get('message')}")
                return []
            items = data.get("data", {}).get("list", [])
            formatted = []
            for item in items:
                mid = item.get("mid")
                if not mid:
                    continue
                formatted.append({
                    "mid": mid,
                    "uname": item.get("uname", "未知UP主"),
                    "face": item.get("face", ""),
                    "sign": item.get("sign", ""),
                })
            total = data.get("data", {}).get("total", 0)
            if total > pn * ps:
                next_items = self.get_following_list(pn+1, ps)
                formatted.extend(next_items)
            return formatted
        except Exception as e:
            print(f"[关注列表] 异常: {e}")
            return []

    # ========== UP主空间视频 ==========
    def get_uploader_videos(self, mid, pn=1, ps=30):
        """获取UP主空间视频的某一页（单次请求，不再循环拉取全部）。

        返回结构化 dict：
          - items:    本页已格式化的视频列表（含 url/bvid/title/duration/thumbnail 等）
          - has_more: 是否还有下一页（由 data.page.count 与当前页比对得出）
          - total:    总条数（来自 data.page.count）
          - page:     当前页码
        上层（分页 loader）据此驱动「上一页 / 下一页」按钮，做到一次只拉一页。
        """
        if not mid:
            return {"items": [], "has_more": False, "total": 0, "page": pn}
        url = "https://api.bilibili.com/x/space/wbi/arc/search"
        params = {"mid": mid, "pn": pn, "ps": ps, "order": "pubdate"}
        try:
            signed = self.wbi_sign(params)
            resp = self.session.get(url, params=signed, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"获取UP主视频失败: {data.get('message')}")
                return {"items": [], "has_more": False, "total": 0, "page": pn}
            page_data = data.get("data", {})
            vlist = page_data.get("list", {}).get("vlist", [])
            total = page_data.get("page", {}).get("count", 0)
            items = []
            for v in vlist:
                bvid = v.get("bvid")
                if not bvid:
                    continue
                items.append({
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "bvid": bvid,
                    "title": v.get("title", "未知标题"),
                    "duration": duration_to_seconds(v.get("length", 0)),
                    "thumbnail": v.get("pic", ""),
                    "view_count": v.get("play", 0),
                    "like_count": 0,
                    "favorite_count": 0,
                    "publish_time": self.format_timestamp(v.get("created")),
                    "uploader": v.get("author", "未知UP主"),
                })
            has_more = bool(total) and (pn * ps < total)
            print(f"[UP主视频] 第{pn}页 拉取 {len(items)} 条，has_more={has_more}，total={total}")
            return {"items": items, "has_more": has_more, "total": total, "page": pn}
        except Exception as e:
            print(f"获取UP主视频异常: {e}")
            return {"items": [], "has_more": False, "total": 0, "page": pn}

    # ========== 新增：追番列表 ==========
    def get_season_list(self):
        """获取追番列表（番剧）"""
        if not self.uid:
            return []
        url = "https://api.bilibili.com/x/space/bangumi/follow/list"
        params = {"vmid": self.uid, "type": 1}
        try:
            resp = self._get_with_csrf(url, params)
            data = resp.json()
            if data.get("code") != 0:
                print(f"获取追番失败: {data.get('message')}")
                return []
            items = data.get("data", {}).get("list", [])
            formatted = []
            for item in items:
                season_id = item.get("season_id")
                if not season_id:
                    continue
                formatted.append({
                    "url": f"https://www.bilibili.com/bangumi/play/ss{season_id}",
                    "season_id": season_id,
                    "title": item.get("title", "未知番剧"),
                    "thumbnail": item.get("cover", ""),
                    "publish_time": "",
                    "duration": 0,
                    "view_count": 0,
                    "like_count": 0,
                    "favorite_count": 0,
                    "uploader": "",
                })
            return formatted
        except Exception as e:
            print(f"获取追番异常: {e}")
            return []

    # ========== 番剧/影视分集（原生，仿 bili23 BangumiParser） ==========
    def get_season_episodes(self, ssid=None, epid=None, mdid=None):
        """获取番剧/影视单季的全部分集（原生 pgc/view/web/season）。

        仿 bili23_example 的 BangumiParser：一次请求返回整季所有集，无需分页。
        - ss 号 → season_id= ；ep 号 → ep_id= ；md 号 → 先用 pgc/review/user 换 season_id
        过滤「预告」类 badge（避免预告片混进正片导致集数错乱），返回统一 video_list 结构
        （含 bvid/cid/封面/时长），供 VideoSelectDialog 直接展示与勾选。
        """
        try:
            params = None
            if ssid:
                params = {"season_id": ssid}
            elif epid:
                params = {"ep_id": epid}
            elif mdid:
                # md → ss 转换（仿 bili23）
                resp = self.session.get(
                    "https://api.bilibili.com/pgc/review/user",
                    params={"media_id": mdid}, timeout=12)
                j = resp.json()
                # 该接口返回 result 字段（部分旧响应用 data），season_id 可能在 result 或 result.media 下
                _res = j.get("result") or j.get("data") or {}
                sid = None
                if isinstance(_res, dict):
                    sid = _res.get("season_id") or _res.get("media", {}).get("season_id")
                if j.get("code") != 0 or not sid:
                    print(f"[番剧] md{mdid} 转换失败: {j.get('message')}")
                    return []
                params = {"season_id": sid}
            if not params:
                return []
            resp = self.session.get(
                "https://api.bilibili.com/pgc/view/web/season",
                params=params, timeout=12)
            j = resp.json()
            if j.get("code") != 0:
                print(f"[番剧] 获取失败 code:{j.get('code')} msg:{j.get('message')}")
                return []
            # 关键：番剧接口返回的是 result 字段（非 data），此前读 data 导致永远取不到分集
            d = j.get("result", {}) or {}
            episodes = d.get("episodes", [])
            ss_title = d.get("title", "番剧")
            if not episodes:
                return []
            result = []
            for ep in episodes:
                if (ep.get("badge") or "") == "预告":
                    continue
                bvid = ep.get("bvid")
                cid = ep.get("cid")
                if not bvid or not cid:
                    continue
                cover = ep.get("cover", "")
                if cover and cover.startswith("//"):
                    cover = "https:" + cover
                # PGC season durations are milliseconds; the app stores seconds.
                duration_ms = ep.get("duration") or 0
                result.append({
                    "url": f"https://www.bilibili.com/bangumi/play/ep{ep.get('ep_id')}",
                    # 番剧 ep.title 多为集号字符串（如 "1"），long_title 才是真正的集名，优先用 long_title
                    "title": ep.get("long_title") or ep.get("title") or f"第{ep.get('index', '')}集",
                    "bvid": bvid,
                    "cid": cid,
                    "duration": int(duration_ms) // 1000,
                    "thumbnail": cover,
                    "view_count": 0,
                    "like_count": 0,
                    "favorite_count": 0,
                    "publish_time": self.format_timestamp(ep.get("pub_time") or ep.get("release_date")),
                    "uploader": ss_title,
                })
            print(f"[番剧] ss{ssid or epid or mdid} 共 {len(result)} 集")
            return result
        except Exception as e:
            print(f"[番剧] 异常: {e}")
            return []

    # ========== 视频详情 / 合集(ugc_season) / 分P（原生，仿 bili23 video episode parser） ==========
    def get_video_pages(self, bvid):
        """获取单个视频的详情，并识别其是否属于合集(ugc_season)或多分P。

        返回 dict：
          - single:     该视频自身信息（始终有，前提是接口成功）
          - collection: 若属于合集(ugc_season)，返回合集全部分集（含自身）；否则 []
          - pages:      若多分P，返回每个分P 信息；否则 []
          - is_collection: 是否命中合集
        优先用原生 wbi/view 解析，避免对合集/分P 依赖 yt_dlp 导致顺序或字段不准。
        """
        info = self.get_video_info(bvid)
        if not info or "data" not in info:
            return {"single": None, "collection": [], "pages": [], "is_collection": False}
        data = info["data"]
        pic = data.get("pic", "")
        if pic and pic.startswith("//"):
            pic = "https:" + pic
        elif pic and pic.startswith("http://"):
            pic = pic.replace("http://", "https://")
        owner = self._uploader_from_data(data)
        single = {
            "url": f"https://www.bilibili.com/video/{bvid}",
            "bvid": bvid,
            "title": data.get("title", "未知标题"),
            "duration": data.get("duration", 0) or 0,
            "thumbnail": pic,
            "view_count": data.get("stat", {}).get("view", 0) or 0,
            "like_count": data.get("stat", {}).get("like", 0) or 0,
            "favorite_count": data.get("stat", {}).get("favorite", 0) or 0,
            "publish_time": self.format_timestamp(data.get("pubdate") or data.get("ctime")),
            "uploader": owner,
        }
        # 合集（视频页内嵌 ugc_season），仿 bili23 video episode parser
        collection = []
        ugc = data.get("ugc_season")
        if ugc:
            for section in ugc.get("sections", []):
                for ep in section.get("episodes", []):
                    arc = ep.get("arc", {})
                    ep_bvid = arc.get("bvid") or ep.get("bvid")
                    ep_cid = arc.get("cid") or ep.get("cid")
                    if not ep_bvid:
                        continue
                    ep_pic = arc.get("pic", "")
                    if ep_pic and ep_pic.startswith("//"):
                        ep_pic = "https:" + ep_pic
                    elif ep_pic and ep_pic.startswith("http://"):
                        ep_pic = ep_pic.replace("http://", "https://")
                    collection.append({
                        "url": f"https://www.bilibili.com/video/{ep_bvid}",
                        "bvid": ep_bvid,
                        "cid": ep_cid,
                        "title": arc.get("title") or ep.get("title") or "未知标题",
                        "duration": arc.get("duration", 0) or 0,
                        "thumbnail": ep_pic,
                        "view_count": arc.get("stat", {}).get("view", 0) or 0,
                        "like_count": arc.get("stat", {}).get("like", 0) or 0,
                        "favorite_count": arc.get("stat", {}).get("favorite", 0) or 0,
                        "publish_time": self.format_timestamp(arc.get("pubdate")),
                        "uploader": owner,
                    })
        # 多分P
        pages = []
        for p in data.get("pages", []):
            pages.append({
                "url": f"https://www.bilibili.com/video/{bvid}?p={p.get('page')}",
                "bvid": bvid,
                "cid": p.get("cid"),
                "title": p.get("part") or f"P{p.get('page')} {single['title']}",
                "duration": p.get("duration", 0) or 0,
                "thumbnail": pic,
                "view_count": 0,
                "like_count": 0,
                "favorite_count": 0,
                "publish_time": single["publish_time"],
                "uploader": owner,
            })
        return {
            "single": single,
            "collection": collection,
            "pages": pages,
            "is_collection": bool(collection),
        }

    # ========== 空间合集 / 系列（原生，仿 bili23 ListParser） ==========
    def get_space_season_videos(self, mid, season_id, ps=30, max_pages=20, max_items=600):
        """空间合集(列表)视频，仿 bili23 ListParser.get_seasons_archives_list。
        端点 x/polymer/web-space/seasons_archives_list，总数字段 data.page.total。"""
        if not mid or not season_id:
            return []
        url = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
        all_items = []
        total = None
        cur = 1
        while cur < 1 + max_pages:
            params = {"mid": mid, "season_id": season_id, "sort_reverse": False,
                      "page_size": ps, "page_num": cur, "web_location": "333.1387"}
            try:
                resp = self.session.get(url, params=params, timeout=12)
                d = resp.json()
                if d.get("code") != 0:
                    print(f"[空间合集] 失败 code:{d.get('code')} msg:{d.get('message')}")
                    if cur == 1:
                        return []
                    break
                dd = d.get("data", {})
                archives = dd.get("archives", [])
                if total is None:
                    total = dd.get("page", {}).get("total", 0)
                for a in archives:
                    bvid = a.get("bvid")
                    if not bvid:
                        continue
                    pic = a.get("pic", "")
                    if pic and pic.startswith("//"):
                        pic = "https:" + pic
                    all_items.append({
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "bvid": bvid,
                        "title": a.get("title", "未知标题"),
                        "duration": a.get("duration", 0) or 0,
                        "thumbnail": pic,
                        "view_count": a.get("play", 0) or 0,
                        "like_count": 0,
                        "favorite_count": 0,
                        "publish_time": self.format_timestamp(a.get("pubdate")),
                        "uploader": a.get("author", ""),
                    })
                if not archives:
                    break
                if total and len(all_items) >= total:
                    break
                if len(all_items) >= max_items:
                    print(f"[空间合集] 达安全上限 max_items={max_items}")
                    break
                cur += 1
            except Exception as e:
                print(f"[空间合集] 异常: {e}")
                if cur == 1:
                    return []
                break
        print(f"[空间合集] 共 {len(all_items)} 条")
        return all_items

    def get_space_series_videos(self, mid, series_id, ps=30, max_pages=20, max_items=600):
        """空间系列视频，仿 bili23 ListParser.get_series_archives_list。
        端点 x/series/archives（WBI 签名），需 current_mid/mid/series_id。"""
        if not mid or not series_id:
            return []
        url = "https://api.bilibili.com/x/series/archives"
        all_items = []
        cur = 1
        while cur < 1 + max_pages:
            params = {"mid": mid, "current_mid": 0, "series_id": series_id,
                      "only_normal": True, "sort": "desc", "ps": ps, "pn": cur}
            try:
                resp = self.session.get(url, params=self.wbi_sign(params), timeout=12)
                d = resp.json()
                if d.get("code") != 0:
                    print(f"[空间系列] 失败 code:{d.get('code')} msg:{d.get('message')}")
                    if cur == 1:
                        return []
                    break
                archives = d.get("data", {}).get("archives", [])
                for a in archives:
                    bvid = a.get("bvid")
                    if not bvid:
                        continue
                    pic = a.get("pic", "")
                    if pic and pic.startswith("//"):
                        pic = "https:" + pic
                    all_items.append({
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "bvid": bvid,
                        "title": a.get("title", "未知标题"),
                        "duration": a.get("duration", 0) or 0,
                        "thumbnail": pic,
                        "view_count": a.get("play", 0) or 0,
                        "like_count": 0,
                        "favorite_count": 0,
                        "publish_time": self.format_timestamp(a.get("pubdate")),
                        "uploader": a.get("author", ""),
                    })
                if not archives:
                    break
                if len(all_items) >= max_items:
                    print(f"[空间系列] 达安全上限 max_items={max_items}")
                    break
                cur += 1
            except Exception as e:
                print(f"[空间系列] 异常: {e}")
                if cur == 1:
                    return []
                break
        print(f"[空间系列] 共 {len(all_items)} 条")
        return all_items

    # ========== 课程（cheese）原生，仿 bili23 CheeseParser ==========
    def get_cheese_episodes(self, epid=None, ssid=None):
        """获取课程（课堂）全部分集。端点 pugv/view/web/season/v2。
        ep 号 / ss 号 均可；返回统一 video_list（含 cid/封面/时长）。"""
        if not (epid or ssid):
            return []
        url = "https://api.bilibili.com/pugv/view/web/season/v2"
        params = {}
        if epid:
            params["ep_id"] = epid
        else:
            params["season_id"] = ssid
        try:
            resp = self.session.get(url, params=params, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[课程] 获取失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            d = data.get("data", {})
            sections = d.get("sections", [])
            if not sections:
                return []
            up_name = (d.get("up_info") or {}).get("uname", "")
            result = []
            for section in sections:
                for ep in section.get("episodes", []):
                    ep_id = ep.get("id")
                    if not ep_id:
                        continue
                    cover = ep.get("cover", "")
                    if cover and cover.startswith("//"):
                        cover = "https:" + cover
                    result.append({
                        "url": f"https://www.bilibili.com/cheese/play/{ep_id}",
                        "title": ep.get("title", "未知章节"),
                        "duration": ep.get("duration", 0) or 0,
                        "thumbnail": cover,
                        "view_count": 0,
                        "like_count": 0,
                        "favorite_count": 0,
                        "publish_time": self.format_timestamp(ep.get("release_date")),
                        "uploader": up_name,
                        "category": "课程",
                    })
            print(f"[课程] 共 {len(result)} 个章节")
            return result
        except Exception as e:
            print(f"[课程] 异常: {e}")
            return []

    # ========== 音频 / 歌单（audio）原生，仿 bili23 AudioParser ==========
    def get_audio_list(self, auid=None, amid=None):
        """获取音频（单曲 au）或歌单（am）。端点 music-service-c/web。
        返回统一 video_list。"""
        if auid:
            try:
                resp = self.session.get(
                    "https://www.bilibili.com/audio/music-service-c/web/song/info",
                    params={"sid": auid}, timeout=12)
                d = resp.json()
                if d.get("code") != 0:
                    print(f"[音频] 获取失败: {d.get('message')}")
                    return []
                song = d.get("data", {})
                item = self._audio_to_item(song)
                if item:
                    item["category"] = "音频"
                return [item] if item else []
            except Exception as e:
                print(f"[音频] 异常: {e}")
                return []
        if amid:
            try:
                menu = self.session.get(
                    "https://www.bilibili.com/audio/music-service-c/web/menu/info",
                    params={"sid": amid}, timeout=12).json()
                menu_title = (menu.get("data") or {}).get("title", "歌单")
                resp = self.session.get(
                    "https://www.bilibili.com/audio/music-service-c/web/song/of-menu",
                    params={"sid": amid, "pn": 1, "ps": 100}, timeout=12)
                d = resp.json()
                if d.get("code") != 0:
                    print(f"[歌单] 获取失败: {d.get('message')}")
                    return []
                songs = d.get("data", []) or []
                items = []
                for s in songs:
                    it = self._audio_to_item(s)
                    if it:
                        it["category"] = f"歌单·{menu_title}"
                        items.append(it)
                print(f"[歌单] {menu_title} 共 {len(items)} 首")
                return items
            except Exception as e:
                print(f"[歌单] 异常: {e}")
                return []
        return []

    def _audio_to_item(self, s):
        if not s:
            return None
        cover = s.get("cover", "")
        if cover and cover.startswith("//"):
            cover = "https:" + cover
        stat = s.get("statistic") or {}
        sid = stat.get("sid") or s.get("id") or s.get("sid")
        if not sid:
            return None
        return {
            "url": f"https://www.bilibili.com/audio/au{sid}",
            "title": s.get("title", "未知音频"),
            "duration": s.get("duration", 0) or 0,
            "thumbnail": cover,
            "view_count": stat.get("play", 0) or 0,
            "like_count": 0,
            "favorite_count": 0,
            "publish_time": self.format_timestamp(s.get("passtime")),
            "uploader": s.get("author", ""),
            "category": "音频",
        }

    # ========== 每周必看（popular）原生，仿 bili23 PopularParser ==========
    def get_popular_weekly(self, number=None):
        """获取「每周必看」某一期（默认最新一期）的全部视频。端点 popular/series/one。"""
        if number is None:
            try:
                lst = self.session.get(
                    "https://api.bilibili.com/x/web-interface/popular/series/list",
                    timeout=12).json()
                if lst.get("code") == 0:
                    items = lst.get("data", {}).get("list", [])
                    if items:
                        number = items[0].get("number")
            except Exception:
                pass
        params = {"web_location": "333.934"}
        if number:
            params["number"] = number
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/popular/series/one",
                params=self.wbi_sign(params), timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[每周必看] 获取失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            d = data.get("data", {})
            videos = d.get("list", [])
            if not videos:
                return []
            label = (d.get("config") or {}).get("label", "每周必看")
            result = []
            for v in videos:
                bvid = v.get("bvid")
                if not bvid:
                    continue
                pic = v.get("pic", "")
                if pic and pic.startswith("//"):
                    pic = "https:" + pic
                result.append({
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "title": v.get("title", "未知"),
                    "duration": v.get("duration", 0) or 0,
                    "thumbnail": pic,
                    "view_count": v.get("play", 0) or 0,
                    "like_count": v.get("like", 0) or 0,
                    "favorite_count": 0,
                    "publish_time": self.format_timestamp(v.get("pubdate")),
                    "uploader": "",
                    "category": label,
                })
            print(f"[每周必看] {label} 共 {len(result)} 个")
            return result
        except Exception as e:
            print(f"[每周必看] 异常: {e}")
            return []

    # ========== 排行榜（ranking）原生，仿 bili23 列表解析 ==========
    def get_ranking(self, rid=0):
        """获取排行榜视频（rid=0 为全站，其它为分区）。端点 ranking/v2。"""
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/ranking/v2",
                params={"rid": rid}, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[排行榜] 获取失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            items = (data.get("data") or {}).get("list", [])
            if not items:
                return []
            result = []
            for v in items:
                bvid = v.get("bvid")
                if not bvid:
                    continue
                pic = v.get("pic", "")
                if pic and pic.startswith("//"):
                    pic = "https:" + pic
                owner = v.get("owner") or {}
                result.append({
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "title": v.get("title", "未知"),
                    "duration": v.get("duration", 0) or 0,
                    "thumbnail": pic,
                    "view_count": v.get("play", 0) or 0,
                    "like_count": v.get("like", 0) or 0,
                    "favorite_count": 0,
                    "publish_time": "",
                    "uploader": v.get("author") or owner.get("name", ""),
                    "category": "排行榜",
                })
            print(f"[排行榜] 全站共 {len(result)} 个")
            return result
        except Exception as e:
            print(f"[排行榜] 异常: {e}")
            return []

    # ========== 活动页（festival）原生，仿 bili23 FestivalParser ==========
    def get_festival_bvid(self, url):
        """解析活动页（bilibili.com/festival/...）内嵌的视频 bvid。
        返回 bvid 字符串，上层再按视频解析。"""
        import json
        try:
            resp = self.session.get(url, timeout=12)
            html = resp.text
            m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
            if not m:
                print("[活动] 未找到 __INITIAL_STATE__")
                return None
            info = json.loads(m.group(1))
            bvid = (info.get("videoInfo") or {}).get("bvid")
            if not bvid:
                print("[活动] 未提取到 bvid")
                return None
            print(f"[活动] 提取到视频 bvid={bvid}")
            return bvid
        except Exception as e:
            print(f"[活动] 解析失败: {e}")
            return None

    # ========== 动态（dynamic）原生，仿 bili23 DynamicParser ==========
    def get_dynamic_videos(self, mid, max_pages=3):
        """获取某 UP 主动态流中的视频（最佳努力）。端点 web-dynamic/v1/feed/space。"""
        if not mid:
            return []
        all_items = []
        offset = 0
        for _ in range(max_pages):
            try:
                resp = self.session.get(
                    "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
                    params={"host_mid": mid, "offset": offset, "timezone_offset": -480},
                    timeout=12)
                data = resp.json()
                if data.get("code") != 0:
                    break
                d = data.get("data", {})
                items = d.get("items", []) or []
                if not items:
                    break
                for it in items:
                    major = (it.get("modules") or {}).get("module_dynamic", {}).get("major")
                    if not major:
                        continue
                    arc = major.get("archive") or major.get("ugc") or {}
                    bvid = arc.get("bvid")
                    if not bvid and major.get("type") == "PGC":
                        bvid = (major.get("pgc") or {}).get("bvid")
                    if not bvid:
                        continue
                    all_items.append({
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "title": arc.get("title", "动态视频"),
                        "duration": 0,
                        "thumbnail": "",
                        "view_count": 0,
                        "like_count": 0,
                        "favorite_count": 0,
                        "publish_time": "",
                        "uploader": "",
                        "category": "动态",
                    })
                offset = d.get("offset")
                if not offset:
                    break
            except Exception as e:
                print(f"[动态] 异常: {e}")
                break
        print(f"[动态] 共 {len(all_items)} 个视频")
        return all_items

    # ========== 综合搜索（search）原生，仿 bili23 搜索入口 ==========
    def get_search_results(self, keyword, page=1):
        """B 站综合搜索：返回结构化结果列表（视频 / 番剧 / UP主）。
        结果项字段：type('video'|'bangumi'|'user')、bvid/season_id/mid、
        title、uploader、thumbnail、duration、view_count、url、category。"""
        if not keyword:
            return []
        params = {
            "keyword": keyword,
            "page": page,
            "web_location": "333.1007",
        }
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/all/v2",
                params=self.wbi_sign(params), timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[搜索] 失败 code:{data.get('code')} msg:{data.get('message')}")
                return [], False
            groups = (data.get("data") or {}).get("result", []) or []
            results = []
            # 不再人为限制每页条数：单页条数由 B 站接口决定（视频约 20 条），
            # 翻页通过 page 参数获取后续内容。记录 count 仅用于推算 has_more。
            video_count, user_count = 0, 0
            for grp in groups:
                rtype = grp.get("result_type")
                items = grp.get("data", []) or []
                if rtype == "video":
                    for it in items:
                        video_count += 1
                        title = re.sub(r"<[^>]+>", "", it.get("title", ""))
                        author = it.get("author", "")
                        cover = it.get("pic", "") or it.get("cover", "")
                        if cover and cover.startswith("//"):
                            cover = "https:" + cover
                        results.append({
                            "type": "video",
                            "bvid": it.get("bvid"),
                            "title": title,
                            "uploader": author,
                            "thumbnail": cover,
                            "duration": it.get("duration", 0) or 0,
                            "view_count": it.get("play", 0) or 0,
                            "url": f"https://www.bilibili.com/video/{it.get('bvid')}",
                            "category": "搜索·视频",
                        })
                elif rtype == "media_bangumi":
                    for it in items:
                        title = re.sub(r"<[^>]+>", "", it.get("title", ""))
                        cover = it.get("cover", "") or it.get("pic", "")
                        if cover and cover.startswith("//"):
                            cover = "https:" + cover
                        results.append({
                            "type": "bangumi",
                            "season_id": it.get("season_id"),
                            "title": title,
                            "uploader": "",
                            "thumbnail": cover,
                            "duration": 0,
                            "view_count": 0,
                            "url": f"https://www.bilibili.com/bangumi/play/ss{it.get('season_id')}",
                            "category": "搜索·番剧",
                        })
                elif rtype == "bili_user":
                    for it in items:
                        user_count += 1
                        name = re.sub(r"<[^>]+>", "", it.get("uname", ""))
                        face = it.get("upic", "") or it.get("face", "")
                        if face and face.startswith("//"):
                            face = "https:" + face
                        results.append({
                            "type": "user",
                            "mid": it.get("mid"),
                            "title": name,
                            "uploader": name,
                            "thumbnail": face,
                            "duration": 0,
                            "view_count": 0,
                            "url": f"https://space.bilibili.com/{it.get('mid')}",
                            "category": "搜索·UP主",
                        })
            video_results = [item for item in results if item.get("type") == "video"]
            if video_results:
                self.enrich_videos(video_results)
            # 综合搜索每页视频约 20 条；满页视为还有下一页（设软上限 50 页防失控）。
            has_more = (video_count >= 20 or user_count >= 20) and page < 50
            print(f"[搜索] {keyword!r} 第{page}页 共 {len(results)} 条，has_more={has_more}")
            return results, has_more
        except Exception as e:
            print(f"[搜索] 异常: {e}")
            return [], False

    def get_music_search_results(self, keyword, page=1):
        """bilibili 音乐搜索：返回音乐 / MV 视频结果。

        B 站的音乐与 MV 本质上都是视频（av/BV），因此复用 WBI 签名的综合搜索接口，
        仅取 result_type == 'video' 的条目并标记为「音乐」分类。下载流程与普通视频完全一致。
        结果项字段同 get_search_results 的 video 分支（含 bvid / title / uploader /
        thumbnail / duration / view_count / url / category）。
        """
        if not keyword:
            return []
        params = {
            "keyword": keyword,
            "page": page,
            "web_location": "333.1007",
        }
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/all/v2",
                params=self.wbi_sign(params), timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[音乐搜索] 失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            groups = (data.get("data") or {}).get("result", []) or []
            results = []
            video_count = 0
            for grp in groups:
                rtype = grp.get("result_type")
                # 仅取视频类（MV / 音乐视频都属于视频），其余类型不参与音乐搜索
                if rtype != "video":
                    continue
                items = grp.get("data", []) or []
                for it in items:
                    video_count += 1
                    title = re.sub(r"<[^>]+>", "", it.get("title", ""))
                    author = it.get("author", "")
                    cover = it.get("pic", "") or it.get("cover", "")
                    if cover and cover.startswith("//"):
                        cover = "https:" + cover
                    results.append({
                        "type": "video",
                        "bvid": it.get("bvid"),
                        "title": title,
                        "uploader": author,
                        "thumbnail": cover,
                        "duration": it.get("duration", 0) or 0,
                        "view_count": it.get("play", 0) or 0,
                        "url": f"https://www.bilibili.com/video/{it.get('bvid')}",
                        "category": "音乐",
                    })
            if results:
                self.enrich_videos(results)
            # 音乐搜索每页视频约 20 条；满页视为还有下一页（设软上限 50 页防失控）。
            has_more = (video_count >= 20) and page < 50
            print(f"[音乐搜索] {keyword!r} 第{page}页 共 {len(results)} 条，has_more={has_more}")
            return results, has_more
        except Exception as e:
            print(f"[音乐搜索] 异常: {e}")
            return []

    # ========== 直播中心（发现较火直播 / 分区 / 搜索）==========
    def _ensure_buvid(self, force=False):
        """直播列表 / 流地址接口的风控需要一整套设备指纹 Cookie；缺失会被风控拦截，
        表现为 playUrl 返回 -352（buvid 校验失败）或 -400（请求被拦 / 参数缺失）。

        本方法在原 buvid3/buvid4 基础上补齐：b_nut、_uuid、b_lsid、buvid_fp（设备指纹）、
        bili_ticket（gaia-gateway 票务），并主动发起 ExClimbWuzhi 握手以「激活」buvid3。
        这套组合与上游 bili23 的 init_cookie_info 一致，是绕过直播流 -400/-352 风控的关键。
        各子步骤均 best-effort，单个失败不影响其余 Cookie 写入。
        """
        import uuid as _uuid_mod
        ck = self.session.cookies

        # 1) buvid3 / buvid4（缺失才重新获取；force 强制刷新）
        if force or "buvid3" not in ck or "buvid4" not in ck:
            self._fetch_buvid34()
            # 兜底：仍无 buvid3 则生成随机值（仿 yt-dlp），避免必现 -352
            if "buvid3" not in ck:
                try:
                    ck.set("buvid3", f"{_uuid_mod.uuid4()}infoc", domain=".bilibili.com")
                except Exception:
                    pass

        # 2) b_nut（时间戳，风控需要）
        if "b_nut" not in ck:
            try:
                ck.set("b_nut", str(int(time.time())), domain=".bilibili.com")
            except Exception:
                pass

        # 3) _uuid / b_lsid（风控指纹 + ExClimbWuzhi payload 需要）
        if "b_lsid" not in ck:
            try:
                ck.set("b_lsid", self._gen_b_lsid(), domain=".bilibili.com")
            except Exception:
                pass
        if "_uuid" not in ck:
            try:
                ck.set("_uuid", self._gen_uuid(), domain=".bilibili.com")
            except Exception:
                pass

        # 4) buvid_fp（murmur3 设备指纹，风控强校验字段）
        if "buvid_fp" not in ck:
            try:
                ua = self.session.headers.get("User-Agent", "")
                ck.set("buvid_fp", self._gen_buvid_fp(ua, 31), domain=".bilibili.com")
            except Exception:
                pass

        # 5) bili_ticket（gaia-gateway 票务，直播流风控核心）
        if force or "bili_ticket" not in ck:
            self._ensure_bili_ticket()

        # 6) ExClimbWuzhi 握手（激活 buvid3），每个会话仅一次
        if force or not getattr(self, "_exclimbwuzhi_done", False):
            try:
                self._exclimbwuzhi()
            except Exception:
                pass
            self._exclimbwuzhi_done = True

        # 7) 透传上游同款常量 Cookie（无害，且对齐 bili23 请求头）
        for k, v in (("CURRENT_FNVAL", "4048"), ("CURRENT_QUALITY", "0")):
            if k not in ck:
                try:
                    ck.set(k, v, domain=".bilibili.com")
                except Exception:
                    pass

    def _fetch_buvid34(self):
        """从 finger/spi 获取 buvid3/buvid4；无 buvid3 时先访问主页捕获 Set-Cookie。"""
        try:
            headers = {
                "User-Agent": self.session.headers.get("User-Agent", ""),
                "Referer": "https://www.bilibili.com/",
            }
            # 无 buvid3 时先访问主页，捕获服务端下发的 buvid3（Set-Cookie）
            if "buvid3" not in self.session.cookies:
                try:
                    self.session.get("https://www.bilibili.com/", headers=headers, timeout=10)
                except Exception:
                    pass
            # 用 buvid3 调 finger/spi 取 b_3/b_4（补齐 buvid4）
            r = self.session.get("https://api.bilibili.com/x/frontend/finger/spi",
                                 headers=headers, timeout=10)
            d = r.json().get("data", {}) if r.status_code == 200 else {}
            if d.get("b_3"):
                self.session.cookies.set("buvid3", d["b_3"], domain=".bilibili.com")
            if d.get("b_4"):
                self.session.cookies.set("buvid4", d["b_4"], domain=".bilibili.com")
        except Exception:
            pass

    @staticmethod
    def _gen_uuid():
        """仿 bili23：生成 _uuid（带 infoc 后缀的设备标识）。"""
        t = int(time.time()) % 100000
        mp = list("123456789ABCDEF") + ["10"]
        pck = [8, 4, 4, 4, 12]
        gen_part = lambda x: "".join([random.choice(mp) for _ in range(x)])
        return "-".join([gen_part(l) for l in pck]) + str(t).ljust(5, "0") + "infoc"

    @staticmethod
    def _gen_b_lsid():
        ret = "".join([hex(random.randint(0, 15))[2:].upper() for _ in range(8)])
        return f"{ret}_{hex(int(time.time()))[2:].upper()}"

    @staticmethod
    def _hmac_sha256(key, message):
        return hmac.new(key.encode("utf-8"), message.encode("utf-8"),
                        hashlib.sha256).digest().hex()

    @staticmethod
    def _gen_buvid_fp(ua, seed=31):
        """murmur3_x64_128 设备指纹（仿 bili23 get_buvid_fp）。"""
        def rotate_left(x, k):
            bin_str = bin(x)[2:].rjust(64, "0")
            return int(bin_str[k:] + bin_str[:k], 2)

        MOD = 1 << 64

        def fmix64(k):
            C1 = 0xFF51AFD7ED558CCD
            C2 = 0xC4CEB9FE1A85EC53
            R = 33
            tmp = k
            tmp ^= tmp >> R
            tmp = tmp * C1 % MOD
            tmp ^= tmp >> R
            tmp = tmp * C2 % MOD
            tmp ^= tmp >> R
            return tmp

        C1 = 0x87C37B91114253D5
        C2 = 0x4CF5AD432745937F
        C3 = 0x52DCE729
        C4 = 0x38495AB5
        R1, R2, R3, M = 27, 31, 33, 5
        h1, h2 = seed, seed
        data = bytes(ua, "ascii")
        n = len(data)
        i = 0
        processed = 0
        while i + 16 <= n:
            k1 = struct.unpack("<q", data[i:i + 8])[0]
            k2 = struct.unpack("<q", data[i + 8:i + 16])[0]
            h1 ^= (rotate_left(k1 * C1 % MOD, R2) * C2 % MOD)
            h1 = ((rotate_left(h1, R1) + h2) * M + C3) % MOD
            h2 ^= rotate_left(k2 * C2 % MOD, R3) * C1 % MOD
            h2 = ((rotate_left(h2, R2) + h1) * M + C4) % MOD
            i += 16
            processed += 16
        # 尾部不足 16 字节
        if i < n:
            rem = data[i:]
            k1 = 0
            k2 = 0
            if len(rem) >= 15:
                k2 ^= rem[14] << 48
            if len(rem) >= 14:
                k2 ^= rem[13] << 40
            if len(rem) >= 13:
                k2 ^= rem[12] << 32
            if len(rem) >= 12:
                k2 ^= rem[11] << 24
            if len(rem) >= 11:
                k2 ^= rem[10] << 16
            if len(rem) >= 10:
                k2 ^= rem[9] << 8
            if len(rem) >= 9:
                k2 ^= rem[8]
                k2 = rotate_left(k2 * C2 % MOD, R3) * C1 % MOD
                h2 ^= k2
            if len(rem) >= 8:
                k1 ^= rem[7] << 56
            if len(rem) >= 7:
                k1 ^= rem[6] << 48
            if len(rem) >= 6:
                k1 ^= rem[5] << 40
            if len(rem) >= 5:
                k1 ^= rem[4] << 32
            if len(rem) >= 4:
                k1 ^= rem[3] << 24
            if len(rem) >= 3:
                k1 ^= rem[2] << 16
            if len(rem) >= 2:
                k1 ^= rem[1] << 8
            if len(rem) >= 1:
                k1 ^= rem[0]
            if len(rem) > 0:
                k1 = rotate_left(k1 * C1 % MOD, R2) * C2 % MOD
                h1 ^= k1
            processed += len(rem)
        h1 ^= processed
        h2 ^= processed
        h1 = (h1 + h2) % MOD
        h2 = (h2 + h1) % MOD
        h1 = fmix64(h1)
        h2 = fmix64(h2)
        h1 = (h1 + h2) % MOD
        h2 = (h2 + h1) % MOD
        m = (h2 << 64) | h1
        return "{}{}".format(hex(m & (MOD - 1))[2:], hex(m >> 64)[2:])

    def _ensure_bili_ticket(self):
        """获取 bili_ticket（gaia-gateway GenWebTicket），直播流风控核心 Cookie。

        该接口是 gRPC-gateway，参数必须走查询字符串（params），放 form body 会返回
        -400 empty `ts` field。未登录也能签发 ticket，登录态追加 csrf。best-effort。
        """
        try:
            ts = int(time.time())
            params = {
                "key_id": "ec02",
                "hexsign": self._hmac_sha256("XgwSnGZ1p", f"ts{ts}"),
                "ts": f"{ts}",
                "context[ts]": f"{ts}",
            }
            if self.bili_jct:
                params["csrf"] = self.bili_jct
            resp = self.session.post(
                "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
                params=params, timeout=10)
            d = resp.json()
            if d.get("code") == 0:
                ticket = (d.get("data") or {}).get("ticket")
                if ticket:
                    self.session.cookies.set("bili_ticket", ticket, domain=".bilibili.com")
                    try:
                        self.session.cookies.set(
                            "bili_ticket_expires", str(ts + 3 * 24 * 3600),
                            domain=".bilibili.com")
                    except Exception:
                        pass
        except Exception:
            pass

    def _exclimbwuzhi(self):
        """ExClimbWuzhi 握手（gaia-gateway），用于「激活」buvid3，配合风控。"""
        try:
            uuid_val = self.session.cookies.get("_uuid") or self._gen_uuid()
            payload = self._build_exclimbwuzhi_payload(
                self.session.headers.get("User-Agent", ""), uuid_val)
            self.session.post(
                "https://api.bilibili.com/x/internal/gaia-gateway/ExClimbWuzhi",
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=10)
        except Exception:
            pass

    @staticmethod
    def _build_exclimbwuzhi_payload(user_agent, uuid_val):
        """构造 ExClimbWuzhi 风控上报 payload（仿 bili23 exclimbwuzhi.py）。"""
        payload = {
            "3064": 1,
            "5062": str(int(time.time() * 1000)),
            "03bf": "https%3A%2F%2Fwww.bilibili.com%2F",
            "39c8": "333.1007.fp.risk",
            "34f1": "",
            "d402": "",
            "654a": "",
            "6e7c": "1699x794",
            "3c43": {
                "2673": 0, "5766": 32, "6527": 0, "7003": 1, "807e": 1,
                "b8ce": user_agent, "641c": 0, "07a4": "zh-CN", "1c57": 32, "0bd0": 20,
                "748e": [960, 1707], "d61f": [912, 1707], "fc9d": -480, "6aa9": "Asia/Shanghai",
                "75b8": 1, "3b21": 1, "8a1c": 0, "d52f": "not available", "adca": "Win32",
                "80c9": [
                    ["PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
                    ["Chrome PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
                    ["Chromium PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
                    ["Microsoft Edge PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
                    ["WebKit built-in PDF", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
                ],
                "13ab": "EPQAAAAASUVORK5CYII=",
                "bfe9": "//TgNIfAAAAAZJREFUAwBde+3wgcxEHQAAAABJRU5ErkJggg==",
                "a3c1": [
                    "extensions:ANGLE_instanced_arrays;EXT_blend_minmax;EXT_clip_control;EXT_color_buffer_half_float;EXT_depth_clamp;EXT_disjoint_timer_query;EXT_float_blend;EXT_frag_depth;EXT_polygon_offset_clamp;EXT_shader_texture_lod;EXT_texture_compression_bptc;EXT_texture_compression_rgtc;EXT_texture_filter_anisotropic;EXT_texture_mirror_clamp_to_edge;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_blend_func_extended;WEBGL_color_buffer_float;WEBGL_compressed_texture_s3tc;WEBGL_compressed_texture_s3tc_srgb;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw;WEBGL_polygon_mode",
                    "webgl aliased line width range:[1, 1]",
                    "webgl aliased point size range:[1, 1024]",
                    "webgl alpha bits:8",
                    "webgl antialiasing:yes",
                    "webgl blue bits:8",
                    "webgl depth bits:24",
                    "webgl green bits:8",
                    "webgl max anisotropy:16",
                    "webgl max combined texture image units:32",
                    "webgl max cube map texture size:16384",
                    "webgl max fragment uniform vectors:1024",
                    "webgl max render buffer size:16384",
                    "webgl max texture image units:16",
                    "webgl max texture size:16384",
                    "webgl max varying vectors:30",
                    "webgl max vertex attribs:16",
                    "webgl max vertex texture image units:16",
                    "webgl max vertex uniform vectors:4095",
                    "webgl max viewport dims:[32767, 32767]",
                    "webgl red bits:8",
                    "webgl renderer:WebKit WebGL",
                    "webgl shading language version:WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)",
                    "webgl stencil bits:0",
                    "webgl vendor:WebKit",
                    "webgl version:WebGL 1.0 (OpenGL ES 2.0 Chromium)",
                    "webgl unmasked vendor:Google Inc. (NVIDIA)",
                    "webgl unmasked renderer:ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Laptop GPU (0x000028E0) Direct3D11 vs_5_0 ps_5_0, D3D11)",
                    "webgl vertex shader high float precision:23",
                    "webgl vertex shader high float precision rangeMin:127",
                    "webgl vertex shader high float precision rangeMax:127",
                    "webgl vertex shader medium float precision:23",
                    "webgl vertex shader medium float precision rangeMin:127",
                    "webgl vertex shader medium float precision rangeMax:127",
                    "webgl vertex shader low float precision:23",
                    "webgl vertex shader low float precision rangeMin:127",
                    "webgl vertex shader low float precision rangeMax:127",
                    "webgl fragment shader high float precision:23",
                    "webgl fragment shader high float precision rangeMin:127",
                    "webgl fragment shader high float precision rangeMax:127",
                    "webgl fragment shader medium float precision:23",
                    "webgl fragment shader medium float precision rangeMin:127",
                    "webgl fragment shader medium float precision rangeMax:127",
                    "webgl fragment shader low float precision:23",
                    "webgl fragment shader low float precision rangeMin:127",
                    "webgl fragment shader low float precision rangeMax:127",
                    "webgl vertex shader high int precision:0",
                    "webgl vertex shader high int precision rangeMin:31",
                    "webgl vertex shader high int precision rangeMax:30",
                    "webgl vertex shader medium int precision:0",
                    "webgl vertex shader medium int precision rangeMin:31",
                    "webgl vertex shader medium int precision rangeMax:30",
                    "webgl vertex shader low int precision:0",
                    "webgl vertex shader low int precision rangeMin:31",
                    "webgl vertex shader low int precision rangeMax:30",
                    "webgl fragment shader high int precision:0",
                    "webgl fragment shader high int precision rangeMin:31",
                    "webgl fragment shader high int precision rangeMax:30",
                    "webgl fragment shader medium int precision:0",
                    "webgl fragment shader medium int precision rangeMin:31",
                    "webgl fragment shader medium int precision rangeMax:30",
                    "webgl fragment shader low int precision:0",
                    "webgl fragment shader low int precision rangeMin:31",
                    "webgl fragment shader low int precision rangeMax:30"
                ],
                "6bc5": "Google Inc. (NVIDIA)~ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Laptop GPU (0x000028E0) Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ed31": 0, "72bd": 0, "097b": 0, "52cd": [0, 0, 0],
                "a658": [
                    "Arial", "Arial Black", "Arial Narrow", "Book Antiqua", "Bookman Old Style",
                    "Calibri", "Cambria", "Cambria Math", "Century", "Century Gothic",
                    "Century Schoolbook", "Comic Sans MS", "Consolas", "Courier", "Courier New",
                    "Georgia", "Helvetica", "Impact", "Lucida Bright", "Lucida Calligraphy",
                    "Lucida Console", "Lucida Fax", "Lucida Handwriting", "Lucida Sans",
                    "Lucida Sans Typewriter", "Lucida Sans Unicode", "Microsoft Sans Serif",
                    "Monotype Corsiva", "MS Gothic", "MS PGothic", "MS Reference Sans Serif",
                    "MS Sans Serif", "MS Serif", "Palatino Linotype", "Segoe Print",
                    "Segoe Script", "Segoe UI", "Segoe UI Light", "Segoe UI Semibold",
                    "Segoe UI Symbol", "Tahoma", "Times", "Times New Roman", "Trebuchet MS",
                    "Verdana", "Wingdings", "Wingdings 2", "Wingdings 3"
                ],
                "d02f": "124.04347527516074"
            },
            "54ef": "{\"b_ut\":\"\",\"home_version\":\"V8\",\"in_new_ab\":true,\"ab_version\":{\"for_ai_home_version\":\"V8\",\"in_theme_version\":\"OPEN\",\"enable_web_push\":\"DISABLE\",\"enable_ai_floor_api\":\"ENABLE\",\"enable_shortcut_key\":\"DISABLE\",\"rcmd_timeout_config\":\"550\",\"home_performance_opt\":\"ssr_fetch_opt\",\"infra_projection\":\"OFF\"},\"ab_split_num\":{\"for_ai_home_version\":54,\"in_theme_version\":30,\"enable_web_push\":10,\"enable_ai_floor_api\":137,\"enable_shortcut_key\":54,\"rcmd_timeout_config\":49,\"home_performance_opt\":49,\"infra_projection\":49},\"uniq_page_id\":\"1671272756362\",\"is_modern\":true}",
            "8b94": "",
            "df35": uuid_val,
            "07a4": "zh-CN",
            "5f45": None,
            "db46": 0
        }
        return json.dumps({"payload": json.dumps(payload)})

    @staticmethod
    def _live_watched_text(watched):
        """watched_show 可能是 dict（含 text_large/text_small/num）或空，统一成展示字符串。"""
        if not watched:
            return ""
        if isinstance(watched, dict):
            return watched.get("text_large") or watched.get("text_small") or str(watched.get("num", ""))
        return str(watched)

    @staticmethod
    def _norm_live_room(r, is_search=False):
        """把 getListByArea / search 的房间项归一化为统一字段，供直播中心卡片直接消费。"""
        cover = (r.get("system_cover") or r.get("user_cover") or r.get("cover") or "")
        if cover.startswith("//"):
            cover = "https:" + cover
        face = (r.get("face") or r.get("uface") or "")
        if face.startswith("//"):
            face = "https:" + face
        # 搜索结果标题/主播名带 <em class="keyword"> 高亮，需去标签
        title = r.get("title", "") or ""
        title = re.sub(r"<[^>]+>", "", title) or "未知直播"
        uname = r.get("uname", "") or ""
        uname = re.sub(r"<[^>]+>", "", uname)
        area = (r.get("area_name") or r.get("area_v2_name")
                or r.get("cate_name") or r.get("area") or "")
        parent = (r.get("parent_name") or r.get("area_v2_parent_name") or "")
        return {
            "roomid": r.get("roomid"),
            "title": title,
            "uname": uname,
            "cover": cover,
            "face": face,
            "online": r.get("online") or 0,
            "watched_show": BiliAPI._live_watched_text(r.get("watched_show")),
            "area_name": area,
            "parent_name": parent,
            "uid": r.get("uid") or 0,
            "live_status": r.get("live_status", 1),
        }

    def get_live_areas(self):
        """返回直播分区树：[{id, name, list:[{id, name, parent_name, hot_status, pic}]}]。"""
        try:
            self._ensure_buvid()
            headers = {"Referer": "https://live.bilibili.com/",
                       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            resp = self.session.get(
                "https://api.live.bilibili.com/room/v1/Area/getList",
                headers=headers, timeout=12)
            data = resp.json().get("data") or []
            if not isinstance(data, list):
                return []
            return data
        except Exception as e:
            print(f"[直播分区] 异常: {e}")
            return []

    def get_live_hot(self, page=1, area_id=0, sort="online", ps=30):
        """较火/分区直播间列表。area_id=0 为全站热门；返回归一化房间字典列表。"""
        try:
            self._ensure_buvid()
            headers = {"Referer": "https://live.bilibili.com/",
                       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            params = self.wbi_sign({"platform": "web", "sort": sort,
                                     "page_size": ps, "page": page})
            if area_id:
                params["area_id"] = area_id
            resp = self.session.get(
                "https://api.live.bilibili.com/xlive/web-interface/v1/second/getListByArea",
                params=params, headers=headers, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[直播热门] 获取失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            rooms = (data.get("data") or {}).get("list") or []
            return [self._norm_live_room(r) for r in rooms]
        except Exception as e:
            print(f"[直播热门] 异常: {e}")
            return []

    def search_live_rooms(self, keyword, page=1):
        """直播搜索：复用主站 search/type?search_type=live（WBI 签名）。返回归一化房间列表。"""
        if not keyword:
            return []
        try:
            self._ensure_buvid()
            headers = {"Referer": "https://live.bilibili.com/",
                       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            params = self.wbi_sign({"search_type": "live", "keyword": keyword, "page": page})
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params=params, headers=headers, timeout=12)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[直播搜索] 失败 code:{data.get('code')} msg:{data.get('message')}")
                return []
            res = (data.get("data") or {}).get("result") or {}
            rooms = res.get("live_room") or [] if isinstance(res, dict) else (res or [])
            return [self._norm_live_room(r, is_search=True) for r in rooms]
        except Exception as e:
            print(f"[直播搜索] 异常: {e}")
            return []

    def get_live_playurl(self, room_id, qn=10000):
        """获取直播间 FLV/HLS 流地址，供 LiveRecorder 录制使用。

        关键坑（本次 -400 的根因）：该接口的必填参数名是 ``cid``（真实直播间号），
        不是 ``room_id``；传错名称会导致服务端收不到必填项，恒返回 -400（请求错误）。
        因此这里统一用 ``cid``。

        直播流接口另有风控：缺失/失效的设备指纹 Cookie（buvid3/4、buvid_fp、
        bili_ticket 等）会返回 -352（buvid 校验失败）。先 _ensure_buvid 补齐整套
        风控 Cookie；若仍命中 -352/-400，则强制刷新风控 Cookie 并重签名重试一次
        （应对过期/限频）。返回首个可用流地址字符串；失败返回 None。
        """
        try:
            cid = int(room_id)
        except Exception:
            return None
        headers = {
            "Referer": f"https://live.bilibili.com/{cid}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        params = {
            "cid": cid,
            "qn": qn,
            "platform": "web",
            "ptype": 16,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1",
            "web_location": "444.8",  # 对齐 web 客户端，WBI 签名需要
        }
        last_code = None
        last_msg = ""
        # 第一次正常补全；失败（风控）时强制刷新再试一次
        for attempt in (0, 1):
            try:
                if attempt == 0:
                    self._ensure_buvid()
                else:
                    self._ensure_buvid(force=True)
                # WBI 签名（密钥缺失/过期时自动刷新），对齐 web 客户端以规避风控
                signed = self.wbi_sign(dict(params))
                resp = self.session.get(
                    "https://api.live.bilibili.com/xlive/web-room/v1/playUrl/playUrl",
                    params=signed, headers=headers, timeout=12)
                data = resp.json()
                if data.get("code") == 0:
                    durl = (data.get("data") or {}).get("durl") or []
                    for d in durl:
                        u = d.get("url")
                        if u:
                            return u
                    return None
                last_code, last_msg = data.get("code"), data.get("message")
                # 仅对风控类错误重试
                if last_code not in (-352, -400):
                    break
            except Exception as e:
                if attempt == 0:
                    continue
                print(f"[直播流] 异常: {e}")
                return None
        hint = ""
        if last_code == -352:
            hint = "（风控拦截：buvid 校验失败，请确认已登录或重试）"
        elif last_code == -400:
            hint = "（请求被 B 站直播流风控拦截：已尝试刷新风控 Cookie 仍失败，多为 IP 限频/未开播/房间无效，请稍后重试或重新登录）"
        elif last_code == -404:
            hint = "（房间未开播或不存在）"
        print(f"[直播流] 获取失败 code:{last_code} msg:{last_msg} {hint}")
        return None
