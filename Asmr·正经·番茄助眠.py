# -*- coding: utf-8 -*-
# Author: 无聊
# 网站: https://www.qqasmr.com/zh-cn
# 源站: https://www.asmr.red  (Yii2)
# CMS: Next.js 前端 + /api/v1 REST
# 日期: 2026-09-16
# 说明: 内置 VIP 账号自动登录，详情下发带 timestamp+sign 的 OSS 直链
#
# Site.ext 可选 JSON:
#   {"email":"...","password":"...","token":"...","redeem":"A2QA"}
# token 优先；否则用 email/password 登录；都空则用内置 VIP 账号。

import re
import json
import time
import warnings
import requests

warnings.filterwarnings("ignore")
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass
try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass


try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass

        def destroy(self):
            pass

        def getName(self):
            return ""

        def homeContent(self, filter=False):
            return {"class": []}

        def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
            return {"list": []}

        def categoryContent(self, tid, pg="1", filter=False, extend=None):
            return {"list": []}

        def detailContent(self, ids):
            return {"list": []}

        def searchContent(self, key, quick=False, pg="1"):
            return {"list": []}

        def playerContent(self, flag, id, vipFlags=None):
            return {"parse": 1, "url": "", "header": {}, "content": ""}

        def localProxy(self, params):
            return []


class Spider(BaseSpider):
    HOST = "https://www.qqasmr.com"
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # 默认内置账号（备用）
    DEFAULT_EMAIL = "8f64qmw7yl@uberip.com"
    DEFAULT_PASSWORD = "Passw0rd!123"
    DEFAULT_TOKEN = "N5ZM5cjtA95y1NNrxoZfUjOuU1RHKHYD_1789568104"

    TRIGGERS = [
        ("t:1:mix-asmr", "🎧 混合ASMR"),
        ("t:2:role-play", "🎭 角色扮演"),
        ("t:3:mouth-sounds", "👄 口腔音"),
        ("t:4:ear-cleaning", "👂 耳朵清洁"),
        ("t:6:scratching", "🖐️ 物体刮擦"),
        ("t:7:eating-sounds", "🍽️ 咀嚼音"),
        ("t:8:massage", "💆 按摩推拿"),
        ("t:9:liquid-sounds", "💧 水的声音"),
        ("t:10:heartbeat", "❤️ 心跳音"),
        ("t:11:whisper", "🤫 耳边轻语"),
        ("t:12:tapping", "🔔 物体敲击"),
        ("t:13:slime", "🫧 史莱姆"),
        ("t:14:trigger-words", "💬 触发词"),
        ("t:15:white-noise", "🌙 白噪音"),
    ]

    def getName(self):
        return "番茄助眠"

    def init(self, extend=""):
        self.host = self.HOST
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/zh-cn",
            "Origin": self.host,
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        self.session.verify = False
        self.token = ""
        self.email = self.DEFAULT_EMAIL
        self.password = self.DEFAULT_PASSWORD
        self.token = self.DEFAULT_TOKEN  # 直接使用内置token
        self._parse_ext(extend)
        self._ensure_vip()

    def destroy(self):
        try:
            if getattr(self, "session", None):
                self.session.close()
                self.session = None
        except Exception:
            pass

    def _parse_ext(self, extend):
        if not extend:
            return
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        else:
            s = str(extend).strip()
            if not s:
                return
            try:
                cfg = json.loads(s)
            except Exception:
                if s.startswith("http"):
                    self.host = s.rstrip("/")
                    return
        if isinstance(cfg, dict):
            self.host = (cfg.get("host") or self.host).rstrip("/")
            if cfg.get("token"):
                self.token = str(cfg.get("token")).strip()
            if cfg.get("email"):
                self.email = str(cfg.get("email")).strip()
            if cfg.get("password"):
                self.password = str(cfg.get("password"))
            if cfg.get("redeem"):
                self.redeem = str(cfg.get("redeem")).strip()

    def _auth_headers(self):
        h = dict(self.headers)
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _get(self, path, params=None, timeout=15):
        url = path if str(path).startswith("http") else (self.host + path)
        try:
            r = self.session.get(url, params=params, headers=self._auth_headers(), timeout=timeout)
            return r
        except Exception:
            return None

    def _post(self, path, payload=None, timeout=15):
        url = path if str(path).startswith("http") else (self.host + path)
        try:
            r = self.session.post(
                url, json=payload or {}, headers=self._auth_headers(), timeout=timeout
            )
            return r
        except Exception:
            return None

    def _jget(self, path, params=None):
        r = self._get(path, params=params)
        if r is None or not r.content:
            return {}
        try:
            return r.json() or {}
        except Exception:
            return {}

    def _ensure_vip(self):
        """确保VIP状态，尝试轮换账号"""
        import json as _json
        from pathlib import Path as _Path
        
        # 先检查当前token是否有效
        if self.token:
            info = self._jget("/api/v1/user/info")
            data = info.get("data") or {}
            if data.get("is_vip"):
                return True
        
        # 尝试加载账号池
        pool_file = _Path("/var/minis/workspace/qqasmr_accounts.json")
        if pool_file.exists():
            try:
                pool = _json.loads(pool_file.read_text(encoding="utf-8"))
                accounts = pool.get("accounts", [])
                if accounts:
                    # 遍历账号池找到有效的
                    for acc in accounts:
                        tok = acc.get("token", "")
                        if tok:
                            self.token = tok
                            info = self._jget("/api/v1/user/info")
                            data = info.get("data") or {}
                            if data.get("is_vip"):
                                self.email = acc.get("email", "")
                                self.password = acc.get("password", "")
                                return True
                    # 重置回默认
                    self.token = self.DEFAULT_TOKEN
            except Exception:
                pass
        
        # 尝试登录默认账号
        if self.email and self.password:
            r = self._post("/api/v1/login-new", {"username": self.email, "password": self.password})
            try:
                js = r.json() if r is not None else {}
            except Exception:
                js = {}
            tok = ((js.get("data") or {}).get("token")) or ""
            if tok:
                self.token = tok
        
        # 最终检查
        if self.token:
            info = self._jget("/api/v1/user/info")
            data = info.get("data") or {}
            return bool(data.get("is_vip"))
        return False

    def _empty_page(self, pg=1):
        return {"list": [], "page": int(pg) or 1, "pagecount": 1, "limit": 20, "total": 0}

    def _card(self, it, folder=False):
        if not isinstance(it, dict):
            return None
        vid = it.get("id")
        if vid is None:
            return None
        title = it.get("title") or it.get("nickname") or it.get("username") or str(vid)
        pic = it.get("thumb") or it.get("cover_path") or it.get("cover") or it.get("avatar") or ""
        remarks = it.get("duration") or it.get("nickname") or ""
        if it.get("nickname") and it.get("duration"):
            remarks = "{} · {}".format(it.get("nickname"), it.get("duration"))
        item = {
            "vod_id": str(vid) if not folder else it.get("vod_id", str(vid)),
            "vod_name": str(title).strip(),
            "vod_pic": pic,
            "vod_remarks": str(remarks).strip(),
        }
        if folder:
            item["vod_tag"] = "folder"
        return item

    def _parse_pages(self, data, pg, nlist):
        pages = (data or {}).get("pages") or {}
        page = int(pages.get("page") or pg or 1)
        pagecount = int(pages.get("pageCount") or 0)
        total = int(pages.get("totalCount") or 0)
        limit = int(pages.get("pageSize") or 20)
        if pagecount <= 0:
            pagecount = page + 1 if nlist >= limit else page
        if pagecount < page:
            pagecount = page
        if total <= 0:
            total = pagecount * limit
        return page, pagecount, limit, total

    def _list_from_api(self, params, pg=1):
        js = self._jget("/api/v1/video", params=params)
        data = js.get("data") or {}
        lst = data.get("list") or []
        videos = []
        for it in lst:
            c = self._card(it)
            if c:
                videos.append(c)
        page, pagecount, limit, total = self._parse_pages(data, pg, len(videos))
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
        }

    def _list_from_html(self, path, pg=1):
        pg = int(pg) or 1
        url = self.host + path
        if pg > 1:
            url += ("&" if "?" in url else "?") + "page=" + str(pg)
        r = self._get(url, timeout=20)
        html = r.text if r is not None else ""
        ids = list(dict.fromkeys(re.findall(r"/zh-cn/video/(\d+)", html)))
        videos = []
        for vid in ids:
            title = ""
            m = re.search(
                r'href="/zh-cn/video/%s"[^>]*>.*?alt="([^"]+)"' % re.escape(vid),
                html,
                re.S,
            )
            if m:
                title = m.group(1)
            if not title:
                m = re.search(
                    r'href="/zh-cn/video/%s"[^>]*>\s*<img[^>]+alt="([^"]+)"' % re.escape(vid),
                    html,
                    re.S,
                )
                title = m.group(1) if m else ("视频 " + vid)
            pic = ""
            m = re.search(
                r'href="/zh-cn/video/%s"[^>]*>.*?src="(https://x\.asmr\.red/[^"]+)"' % re.escape(vid),
                html,
                re.S,
            )
            if m:
                pic = m.group(1)
            videos.append(
                {
                    "vod_id": vid,
                    "vod_name": title.strip(),
                    "vod_pic": pic,
                    "vod_remarks": "",
                }
            )
        n = len(videos)
        pagecount = pg + 1 if n >= 20 else max(pg, 1)
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "newest", "type_name": "🆕 最新"},
            {"type_id": "recommend", "type_name": "🔥 推荐"},
            {"type_id": "artist", "type_name": "🎤 主播", "vod_tag": "folder"},
            {"type_id": "collection", "type_name": "📂 播单", "vod_tag": "folder"},
        ]
        for tid, name in self.TRIGGERS:
            classes.append({"type_id": tid, "type_name": name})
        js = self._jget("/api/v1/home")
        data = js.get("data") or {}
        rec = data.get("newest") or data.get("recommend") or []
        videos = []
        for it in rec[:20]:
            c = self._card(it)
            if c:
                videos.append(c)
        return {"class": classes, "list": videos}

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        js = self._jget("/api/v1/home")
        data = js.get("data") or {}
        rec = data.get("recommend") or data.get("newest") or []
        videos = []
        for it in rec:
            c = self._card(it)
            if c:
                videos.append(c)
        return {
            "list": videos,
            "page": 1,
            "pagecount": 1,
            "limit": 20,
            "total": len(videos),
        }

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid or "").strip()
        extend = extend or {}
        if not isinstance(extend, dict):
            try:
                extend = json.loads(str(extend))
            except Exception:
                extend = {}

        if tid == "newest":
            return self._list_from_api({"page": pg, "type": 1, "per-page": 20}, pg)

        if tid == "recommend":
            js = self._jget("/api/v1/home")
            rec = (js.get("data") or {}).get("recommend") or []
            videos = []
            for it in rec:
                c = self._card(it)
                if c:
                    videos.append(c)
            return {
                "list": videos,
                "page": 1,
                "pagecount": 1,
                "limit": 20,
                "total": len(videos),
            }

        if tid == "artist":
            js = self._jget("/api/v1/artist", {"page": pg, "per-page": 40})
            data = js.get("data") or []
            if isinstance(data, dict):
                data = data.get("list") or []
            videos = []
            for it in data:
                uid = it.get("id")
                if uid is None:
                    continue
                videos.append(
                    {
                        "vod_id": "u:" + str(uid),
                        "vod_name": it.get("nickname") or it.get("username") or str(uid),
                        "vod_pic": it.get("avatar") or "",
                        "vod_remarks": "{} 作品".format(it.get("video_count") or ""),
                        "vod_tag": "folder",
                    }
                )
            n = len(videos)
            pagecount = pg + 1 if n >= 40 else pg
            return {
                "list": videos,
                "page": pg,
                "pagecount": max(pagecount, 1),
                "limit": 40,
                "total": pagecount * 40,
            }

        if tid.startswith("u:"):
            uid = tid.split(":", 1)[-1]
            return self._list_from_api({"page": pg, "user_id": uid, "per-page": 20}, pg)

        if tid == "collection":
            js = self._jget("/api/v1/collection", {"page": pg})
            data = js.get("data") or {}
            lst = data.get("list") or data.get("recommend") or []
            if isinstance(data, list):
                lst = data
            videos = []
            for it in lst:
                cid = it.get("id")
                if cid is None:
                    continue
                videos.append(
                    {
                        "vod_id": "c:" + str(cid),
                        "vod_name": it.get("title") or str(cid),
                        "vod_pic": it.get("cover") or "",
                        "vod_remarks": "{} · {}首".format(it.get("nickname") or "", it.get("count") or 0),
                        "vod_tag": "folder",
                    }
                )
            return {
                "list": videos,
                "page": 1,
                "pagecount": 1,
                "limit": 20,
                "total": len(videos),
            }

        if tid.startswith("c:"):
            cid = tid.split(":", 1)[-1]
            return self._list_from_api({"page": pg, "collection_id": cid, "per-page": 20}, pg)

        if tid.startswith("t:"):
            parts = tid.split(":")
            slug = parts[2] if len(parts) > 2 else parts[-1]
            return self._list_from_html("/zh-cn/trigger/" + slug, pg)

        return self._list_from_api({"page": pg, "type": 1, "per-page": 20}, pg)

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        key = str(key or "").strip()
        if not key:
            return self._empty_page(pg)
        js = self._jget("/api/v1/search", {"keyword": key})
        data = js.get("data") or {}
        videos = []
        seen = set()
        for it in data.get("videos") or []:
            c = self._card(it)
            if c and c["vod_id"] not in seen:
                seen.add(c["vod_id"])
                videos.append(c)
        for it in data.get("artist") or []:
            uid = it.get("id")
            if uid is None:
                continue
            vid = "u:" + str(uid)
            if vid in seen:
                continue
            seen.add(vid)
            videos.append(
                {
                    "vod_id": vid,
                    "vod_name": "🎤 " + (it.get("nickname") or it.get("username") or str(uid)),
                    "vod_pic": it.get("avatar") or "",
                    "vod_remarks": "{} 作品".format(it.get("video_count") or ""),
                    "vod_tag": "folder",
                }
            )
        # 搜索接口不分页，额外用 video?keyword= 拿完整列表
        extra = self._jget("/api/v1/video", {"page": pg, "keyword": key, "per-page": 20})
        ed = extra.get("data") or {}
        for it in ed.get("list") or []:
            c = self._card(it)
            if c and c["vod_id"] not in seen:
                seen.add(c["vod_id"])
                videos.append(c)
        page, pagecount, limit, total = self._parse_pages(ed, pg, len(ed.get("list") or []))
        if not videos:
            pagecount = 1
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total or len(videos),
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        raw = str(ids[0]).strip()
        if raw.startswith("u:"):
            return self._artist_detail(raw.split(":", 1)[-1])
        if raw.startswith("c:"):
            return self._collection_detail(raw.split(":", 1)[-1])
        return self._video_detail(raw)

    def _artist_detail(self, uid):
        info = (self._jget("/api/v1/artist/" + str(uid)).get("data") or {})
        lst = self._jget("/api/v1/video", {"page": 1, "user_id": uid, "per-page": 50}).get("data") or {}
        items = lst.get("list") or []
        play = []
        for it in items:
            title = (it.get("title") or str(it.get("id"))).replace("$", "＄").replace("#", "＃")
            play.append("{} ${}".format(title, it.get("id")))
        name = info.get("nickname") or info.get("username") or ("主播 " + str(uid))
        return {
            "list": [
                {
                    "vod_id": "u:" + str(uid),
                    "vod_name": name,
                    "vod_pic": info.get("avatar") or "",
                    "vod_actor": name,
                    "vod_remarks": "{} 作品".format(info.get("video_count") or len(items)),
                    "vod_content": (info.get("bio") or "").strip(),
                    "vod_play_from": "作品列表",
                    "vod_play_url": "#".join(play) if play else "暂无$0",
                }
            ]
        }

    def _collection_detail(self, cid):
        js = self._jget("/api/v1/collection/" + str(cid))
        data = js.get("data") or {}
        info = data.get("info") or data
        items = data.get("list") or []
        if not items:
            items = (self._jget("/api/v1/video", {"page": 1, "collection_id": cid, "per-page": 50}).get("data") or {}).get("list") or []
        play = []
        for it in items:
            title = (it.get("title") or str(it.get("id"))).replace("$", "＄").replace("#", "＃")
            play.append("{} ${}".format(title, it.get("id")))
        return {
            "list": [
                {
                    "vod_id": "c:" + str(cid),
                    "vod_name": info.get("title") or ("播单 " + str(cid)),
                    "vod_pic": info.get("cover") or "",
                    "vod_actor": info.get("nickname") or "",
                    "vod_remarks": "{}首".format(info.get("count") or len(items)),
                    "vod_content": (info.get("content") or "").strip(),
                    "vod_play_from": "播单",
                    "vod_play_url": "#".join(play) if play else "暂无$0",
                }
            ]
        }

    def _video_detail(self, vid):
        self._ensure_vip()
        js = self._jget("/api/v1/video/" + str(vid))
        it = js.get("data") or {}
        if not it:
            return {"list": []}
        title = it.get("title") or ("视频 " + str(vid))
        pic = it.get("cover_path") or it.get("thumb") or ""
        actor = it.get("nickname") or it.get("username") or ""
        content = (it.get("content") or "").strip()
        duration = it.get("duration") or ""
        vurl = it.get("video_path") or ""
        aurl = it.get("audio_path") or ""
        froms = []
        urls = []
        if vurl and "vip.mp4" not in vurl:
            froms.append("🎬 视频")
            urls.append("正片$" + vurl)
        if aurl and "vip.mp3" not in aurl:
            froms.append("🎧 音频")
            urls.append("正片$" + aurl)
        if not froms:
            froms = ["🎬 视频"]
            urls = ["正片$" + str(vid)]
        return {
            "list": [
                {
                    "vod_id": str(vid),
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_actor": actor,
                    "vod_remarks": duration,
                    "type_name": "ASMR",
                    "vod_content": content,
                    "vod_play_from": "$$$".join(froms),
                    "vod_play_url": "$$$".join(urls),
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id or "").strip()
        header = {
            "User-Agent": self.UA,
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        if url.startswith("http"):
            return {"parse": 0, "url": url, "header": header}
        if url.isdigit():
            self._ensure_vip()
            it = (self._jget("/api/v1/video/" + url).get("data") or {})
            vurl = it.get("video_path") or ""
            aurl = it.get("audio_path") or ""
            if "视频" in str(flag) and vurl and "vip.mp4" not in vurl:
                url = vurl
            elif aurl and "vip.mp3" not in aurl:
                url = aurl
            elif vurl and "vip.mp4" not in vurl:
                url = vurl
            else:
                url = ""
            if url:
                return {"parse": 0, "url": url, "header": header}
        return {"parse": 1, "url": url, "header": header}

    def isVideoFormat(self, url):
        url = str(url or "").lower()
        return any(x in url for x in (".mp4", ".m4a", ".mp3", ".m3u8", ".flv"))

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return []


if __name__ == "__main__":
    sp = Spider()
    sp.init()
    home = sp.homeContent(False)
    print("class", len(home.get("class") or []), "list", len(home.get("list") or []))
    if home.get("list"):
        print("first", home["list"][0])
    cat = sp.categoryContent("newest", "1")
    print("newest", len(cat.get("list") or []), "pagecount", cat.get("pagecount"))
    trig = sp.categoryContent("t:3:mouth-sounds", "1")
    print("mouth", len(trig.get("list") or []), [x["vod_id"] for x in (trig.get("list") or [])[:5]])
    se = sp.searchContent("benio", pg="1")
    print("search", len(se.get("list") or []))
    did = (cat.get("list") or [{}])[0].get("vod_id") or "3136"
    det = sp.detailContent([did])
    item = (det.get("list") or [{}])[0]
    print("detail", item.get("vod_name"), item.get("vod_play_from"))
    print("play_url", str(item.get("vod_play_url"))[:180])
    play = item.get("vod_play_url") or ""
    first = play.split("$$$")[0].split("#")[0]
    pid = first.split("$")[-1] if "$" in first else first
    pc = sp.playerContent("视频", pid, None)
    print("player parse", pc.get("parse"), "url", str(pc.get("url"))[:160])
    sp.destroy()
