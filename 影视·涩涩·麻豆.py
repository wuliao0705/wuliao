# -*- coding: utf-8 -*-
"""
madouai.xyz (麻豆传媒AI) - TVBox Python 爬虫
站点: https://www.madouai.xyz/media/  (Vue 3 SPA + REST API /api/v1)

修复：
- 移除抽象类继承，避免 Can't instantiate abstract class 错误
- 所有方法返回字典（而非 JSON 字符串）
- 兼容 TVBox 标准接口
"""

import re
import json
import sys
import base64
from urllib import request, parse, error as _url_err

BASE = "https://www.madouai.xyz"
API = BASE + "/api/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _url_join(base, path):
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/"):
        return base + path
    return base + "/" + path


def _b64(s, safe=False):
    if safe:
        return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


# ============================================================
# 主爬虫类（不继承任何基类，避免抽象方法检查）
# ============================================================
class Spider:

    # ---------------- 初始化 ----------------
    def init(self, extend=""):
        """兼容 TVBox 调用"""
        self.extend = {}
        if extend:
            if isinstance(extend, dict):
                self.extend = extend
            else:
                try:
                    self.extend = json.loads(extend) if extend else {}
                except Exception:
                    self.extend = {}
        # 支持自定义域名
        if self.extend.get('host'):
            global BASE, API
            BASE = self.extend['host'].rstrip('/')
            API = BASE + "/api/v1"
        return True

    def getName(self):
        return "麻豆AI"

    def destroy(self):
        pass

    # ---------------- HTTP ----------------
    def _headers(self):
        return {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": BASE + "/media/",
            "Origin": BASE,
        }

    def _get_json(self, path, params=None, timeout=15):
        url = API + path
        if params:
            url = url + "?" + parse.urlencode(params)
        req = request.Request(url, headers=self._headers())
        try:
            with request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
        except Exception as e:
            return {"_error": "GET %s failed: %s" % (url, e)}
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return {"_error": "json decode failed: %s; head=%r" % (e, raw[:200])}
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    def _get_text(self, path, params=None, timeout=30):
        url = path if path.startswith("http") else API + path
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + parse.urlencode(params)
        req = request.Request(url, headers=self._headers())
        try:
            with request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            return ""

    # ---------------- 解析 ----------------
    @staticmethod
    def _cover_full(v):
        cover = v.get("coverUrl") or ""
        if not cover:
            return ""
        if cover.startswith("http"):
            return cover
        return BASE + cover

    def _vod_item(self, v):
        vid = v.get("id")
        title = v.get("title") or "无标题"
        cat = v.get("categoryName") or "其它"
        dur = v.get("durationSec") or 0
        views = v.get("viewCount") or 0
        author = v.get("authorName") or ""
        pub = (v.get("publishedAt") or "").split("T")[0] or ""
        tags = v.get("tags") or []
        if isinstance(tags, (list, tuple)):
            tags_str = ",".join([str(t) for t in tags if t])
        else:
            tags_str = str(tags)

        mm, ss = divmod(int(dur), 60)
        hh, mm = divmod(mm, 60)
        if hh:
            dur_str = "%d:%02d:%02d" % (hh, mm, ss)
        else:
            dur_str = "%d:%02d" % (mm, ss)

        remark = []
        if cat and cat != "其它":
            remark.append(cat)
        if author:
            remark.append(author)
        if views:
            remark.append("观看%d" % views)
        if pub:
            remark.append(pub)
        if tags_str:
            remark.append(tags_str)

        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_sub": "",
            "vod_remarks": " | ".join(remark),
            "vod_pic": self._cover_full(v),
            "vod_class": cat,
            "vod_score": "",
            "vod_play_from": "madouai",
            "vod_play_url": "",
        }

    def _vod_detail(self, v):
        vid = v.get("id")
        title = v.get("title") or "无标题"
        cat = v.get("categoryName") or "其它"
        desc = v.get("description") or ""
        tags = v.get("tags") or []
        if isinstance(tags, (list, tuple)):
            tags = [str(t) for t in tags if t]
        author = v.get("authorName") or ""
        pub = (v.get("publishedAt") or "").split("T")[0] or ""
        views = v.get("viewCount") or 0
        dur = v.get("durationSec") or 0

        cls_parts = [cat]
        if author:
            cls_parts.append(author)
        if pub:
            cls_parts.append(pub)

        mm, ss = divmod(int(dur), 60)
        hh, mm = divmod(mm, 60)
        dur_str = "%d:%02d:%02d" % (hh, mm, ss) if hh else "%d:%02d" % (mm, ss)

        vod_id = str(vid)

        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_sub": "时长 %s · 观看 %d" % (dur_str, views),
            "vod_remarks": dur_str,
            "vod_pic": self._cover_full(v),
            "vod_class": ",".join(cls_parts),
            "vod_area": "AI生成" if v.get("sourcePlatform") in ("cg51", "gossip", "ai") else "国产",
            "vod_year": pub or "",
            "vod_lang": "国语",
            "vod_actor": author,
            "vod_director": "",
            "vod_score": "",
            "vod_blurb": desc or "AI 生成视频，来自 %s 平台" % (v.get("sourcePlatform") or "麻豆"),
            "vod_content": desc or "",
            "vod_play_from": "madouai",
            "vod_play_url": f"{title}${vod_id}",
        }

    # ---------------- TVBox 接口（返回字典） ----------------
    def homeContent(self, filter=False):
        cats = self._get_json("/categories", {"type": "video"})
        if not isinstance(cats, list):
            return {"class": [], "list": []}

        seen = set()
        classes = []
        for c in cats:
            cid = c.get("id")
            name = c.get("name") or ""
            if not cid or not name or cid in seen:
                continue
            seen.add(cid)
            classes.append({
                "type_id": "%s_%s" % (c.get("menuId", 1), cid),
                "type_name": name,
            })

        # 首页推荐 = 最近 30 条
        first = self._get_json("/videos", {"page": 1, "size": 30})
        items = first.get("items", []) if isinstance(first, dict) else []
        videos = [self._vod_item(v) for v in items]

        return {"class": classes, "list": videos}

    def homeVideoContent(self):
        return self.categoryContent()

    def categoryContent(self, tid="", pg=1, filter=False, extend=None):
        try:
            page = int(pg)
        except:
            page = 1
        params = {"page": page, "size": 60}

        if tid:
            s = str(tid)
            if "_" in s:
                _, cid = s.split("_", 1)
            else:
                cid = s
            if cid.isdigit():
                params["categoryId"] = int(cid)

        data = self._get_json("/videos", params)
        if not isinstance(data, dict):
            return {"list": [], "page": page, "pagecount": 1}

        items = data.get("items") or []
        videos = [self._vod_item(v) for v in items]
        total = data.get("totalCount", 0) or data.get("total", 0)
        pagecount = (total + 59) // 60 if total else 1

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 60,
            "total": total,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0] if isinstance(ids, list) else ids).strip()
        if not vid.isdigit():
            return {"list": []}
        v = self._get_json("/videos/%s" % vid)
        if not isinstance(v, dict) or not v.get("id"):
            return {"list": []}
        return {"list": [self._vod_detail(v)]}

    def playerContent(self, flag="", id="", vipFlags=None):
        vod_id = str(id or "").strip()
        if not vod_id.isdigit():
            return {"parse": 1, "url": "", "header": {}}

        v = self._get_json("/videos/%s" % vod_id)
        if not isinstance(v, dict) or not v.get("videoUrl"):
            return {"parse": 1, "url": "", "header": {}}

        vid_path = v["videoUrl"]
        enc = parse.quote(vid_path, safe="")
        proxy_url = "%s/api/v1/m3u8/proxy?path=%s" % (BASE, enc)

        return {
            "parse": 1,
            "playUrl": proxy_url,
            "url": proxy_url,
            "header": {
                "Referer": BASE + "/",
                "User-Agent": UA,
            }
        }

    def searchContent(self, key, quick=False, pg="1"):
        if not key:
            return {"list": [], "page": 1, "pagecount": 1}
        try:
            page = int(pg)
        except:
            page = 1
        data = self._get_json("/videos/search", {
            "q": key, "page": page, "size": 60
        })
        if not isinstance(data, dict):
            return {"list": [], "page": page, "pagecount": 1}
        items = data.get("items") or []
        videos = [self._vod_item(v) for v in items]
        total = data.get("totalCount", 0) or data.get("total", 0)
        pagecount = (total + 59) // 60 if total else 1
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 60,
            "total": total,
        }

    # ---------------- 兼容方法 ----------------
    def localProxy(self, param):
        return ""

    def isVideoFormat(self, url):
        return url and any(url.endswith(ext) for ext in ('.m3u8', '.mp4', '.flv', '.mkv', '.ts'))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    # 以下为兼容旧版 TVBox 调用
    def getAll(self, **kwargs):
        return self.homeContent()

    def getVodDetail(self, vodId, **kwargs):
        return self.detailContent(vodId)

    def getCategory(self, tuid, page=1, **kwargs):
        return self.categoryContent(str(tuid), page)

    def getSearch(self, keys, page=1, **kwargs):
        return self.searchContent(keys, False, str(page))

    def getPlayer(self, vodId, **kwargs):
        return self.playerContent(None, str(vodId))


# ============================================================
# CLI 测试
# ============================================================
if __name__ == "__main__":
    s = Spider()
    s.init("")
    if len(sys.argv) < 2:
        print("用法: python madouai_spider.py home|cat <tid> [page]|search <kw> [page]|detail <vid>|player <vid>")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "home":
        r = s.homeContent()
        print("分类数:", len(r.get("class", [])))
        for c in r["class"][:15]:
            print("  ", c["type_id"], c["type_name"])
        print("推荐数:", len(r.get("list", [])))
        for v in r["list"][:5]:
            print("  ", v["vod_id"], v["vod_name"][:40], v["vod_class"])
    elif cmd == "cat":
        tid = sys.argv[2] if len(sys.argv) > 2 else ""
        pg = sys.argv[3] if len(sys.argv) > 3 else "1"
        r = s.categoryContent(tid, pg)
        print("返回:", len(r.get("list", [])))
        for v in r.get("list", [])[:10]:
            print("  ", v["vod_id"], v["vod_name"][:40], v["vod_class"])
    elif cmd == "search":
        kw = sys.argv[2] if len(sys.argv) > 2 else ""
        pg = sys.argv[3] if len(sys.argv) > 3 else "1"
        r = s.searchContent(kw, False, pg)
        print("搜索 %r ->" % kw, len(r.get("list", [])))
        for v in r.get("list", [])[:10]:
            print("  ", v["vod_id"], v["vod_name"][:40])
    elif cmd == "detail":
        vid = sys.argv[2] if len(sys.argv) > 2 else ""
        r = s.detailContent(vid)
        if r.get("list"):
            print(json.dumps(r["list"][0], ensure_ascii=False, indent=2))
    elif cmd == "player":
        vid = sys.argv[2] if len(sys.argv) > 2 else ""
        r = s.playerContent(None, vid)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("未知命令")