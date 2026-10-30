# -*- coding: utf-8 -*-
"""
av3698.cc 影视爬虫源 (TVBox/影视仓 T4 Python)
- 分类/搜索: /?source=external&category={id}&page={n}
- 详情: /xwatch/{vid}.html  → <video data-stream="/proxy-m3u8?url=...">
- 播放: 站点自身代理 https://av3698.cc/proxy-m3u8?url=<CDN编码>  (最可靠, 同源无跨域/防盗链问题)
        兜底 CDN 直链 https://2608.xbv2608.com/...
v3 修复: ids 兼容 list/str/int; 双播放源; 分类去重; 图片走站点代理
"""
import re
import time

try:
    from base.spider import BaseSpider
except Exception:
    class BaseSpider:
        pass

class Spider(BaseSpider):

    def init(self, extend=""):
        self.siteUrl = "https://av3698.cc"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.siteUrl + "/",
        }
        self.CATEGORIES = [
            ("54", "日韩无码"), ("55", "国产主播"), ("57", "日韩精品"), ("58", "欧美劲爆"),
            ("59", "成人动漫"), ("60", "自拍偷拍"), ("61", "伦理影片"), ("69", "视频二区"),
            ("70", "巨乳尤物"), ("71", "颜射系列"), ("72", "口交视频"), ("73", "自慰系列"),
            ("74", "教师学生"), ("75", "群P换妻"), ("76", "AI换脸"), ("56", "视频三区"),
            ("62", "中文字幕"), ("63", "人妻系列"), ("64", "制服诱惑"), ("65", "强奸乱伦"),
            ("66", "AV明星"), ("68", "SM重味"), ("78", "AV解说"), ("79", "视频四区"),
            ("80", "吃瓜黑料"), ("81", "酒店探花"), ("82", "直播裸聊"), ("83", "反差母狗"),
            ("84", "颜值正义"), ("85", "熟女少妇"), ("89", "国产传媒"), ("90", "视频五区"),
            ("91", "野战车震"), ("92", "SM调教"), ("93", "家庭乱伦"), ("94", "百合女同"),
            ("95", "学生空姐"), ("96", "撸管必看"), ("97", "偷情少妇"),
        ]

    def _fetch(self, url, timeout=12, retry=2):
        html = ""
        for i in range(retry + 1):
            try:
                import requests
                resp = requests.get(url, headers=self.headers, timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = "utf-8"
                    html = resp.text
                    if html and len(html) > 500 and "xwatch" in url or "data-stream" in html or len(html) > 3000:
                        return html
            except Exception:
                pass
            try:
                import curl_cffi.requests as crequests
                resp = crequests.get(url, impersonate="chrome120", timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = "utf-8"
                    html = resp.text
                    if html:
                        return html
            except Exception:
                pass
            time.sleep(0.6)
        return html

    def getName(self):
        return "av3698"

    def homeContent(self, filter=""):
        return {
            "class": [{"type_id": i, "type_name": n} for i, n in self.CATEGORIES],
            "filters": {}, "list": [],
        }

    def homeVideoContent(self):
        return self.categoryContent("54", 1, "", "")

    # ---------- 列表解析(首页/分类/搜索共用) ----------
    def _parse_list(self, html):
        videos, seen = [], set()
        # 每张卡片只取一次: card-cover 链接 + 标题(可能带span)
        pat = re.compile(
            r'<a class="card-cover"[^>]*href="(/xwatch/\d+)"[^>]*>.*?'
            r'<img[^>]*src="([^"]+)"[^>]*>.*?'
            r'<span class="duration">([^<]*)</span>.*?'
            r'<a class="card-title"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for m in pat.finditer(html):
            href, img, dur, title = m.groups()
            vid = re.search(r'/xwatch/(\d+)', href)
            if not vid:
                continue
            vid_id = vid.group(1)
            if vid_id in seen:
                continue
            seen.add(vid_id)
            title = re.sub(r'<[^>]+>', '', title).strip()
            # 图片统一走站点代理(同源可靠)
            if not img.startswith("http"):
                img = self.siteUrl + img
            elif "cached-thumb" not in img and "2608" not in img:
                img = self.siteUrl + img
            videos.append({
                "vod_id": vid_id,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": dur.strip() or "",
            })
        return videos

    def categoryContent(self, tid, page, filter="", extend=""):
        page = int(page or 1)
        url = f"{self.siteUrl}/?source=external&category={tid}"
        if page > 1:
            url += f"&page={page}"
        html = self._fetch(url)
        videos = self._parse_list(html)
        return {"list": videos, "page": page, "pagecount": 9999,
                "limit": len(videos) or 20, "total": 99999}

    def searchContent(self, key, quick=False, page="1"):
        from urllib.parse import quote
        page = int(page or 1)
        url = f"{self.siteUrl}/?source=external&q={quote(key)}"
        if page > 1:
            url += f"&page={page}"
        html = self._fetch(url)
        videos = self._parse_list(html)
        return {"list": videos}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        # T4/影视仓兼容: ids 可能是 ['142065'] / '142065' / 142065 / 'xwatch/142065'
        vid = ""
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        elif isinstance(ids, int):
            vid = str(ids)
        else:
            vid = str(ids).split(",")[0].strip()
        m = re.search(r'(\d{4,})', vid)
        vid_id = m.group(1) if m else vid
        print(f"[av3698] detailContent raw={vid!r} -> vid_id={vid_id!r}")

        url = f"{self.siteUrl}/xwatch/{vid_id}"
        html = self._fetch(url, retry=3)
        vod = {
            "vod_id": vid_id,
            "vod_name": "", "vod_pic": "", "vod_remarks": "",
            "vod_content": "", "type_name": "",
            "vod_play_from": "", "vod_play_url": "",
        }
        if not html:
            print(f"[av3698] detail fetch FAILED empty html: {url}")
            return {"list": [vod]}

        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if h1:
            vod["vod_name"] = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
        eb = re.search(r'<span class="eyebrow"[^>]*>(.*?)</span>', html, re.DOTALL)
        if eb:
            vod["type_name"] = eb.group(1).strip()
        cap = re.search(r'<p class="caption"[^>]*>(.*?)</p>', html, re.DOTALL)
        if cap:
            vod["vod_content"] = re.sub(r'<[^>]+>', '', cap.group(1)).strip()
        meta = re.search(r'<div class="watch-meta"[^>]*>(.*?)</div>', html, re.DOTALL)
        if meta:
            spans = re.findall(r'<span>([^<]+)</span>', meta.group(1))
            if spans:
                vod["vod_remarks"] = spans[0].strip()

        # 播放源1: 站点代理(最可靠, 同域无跨域/防盗链)
        proxy_url = ""
        m = re.search(r'<video[^>]*data-stream="([^"]+)"', html)
        if m:
            raw = m.group(1).strip()
            if raw.startswith("/"):
                proxy_url = self.siteUrl + raw
            elif raw.startswith("http"):
                proxy_url = raw
        # 播放源2: CDN 直链(从代理参数中解出)
        direct_url = ""
        if proxy_url and "url=" in proxy_url:
            from urllib.parse import unquote, urlparse, parse_qs
            try:
                qs = parse_qs(urlparse(proxy_url).query)
                if qs.get("url"):
                    direct_url = unquote(qs["url"][0])
            except Exception:
                pass

        srcs = []
        names = []
        if proxy_url:
            srcs.append(proxy_url); names.append("站点代理")
        if direct_url and direct_url != proxy_url:
            srcs.append(direct_url); names.append("CDN直链")
        if srcs:
            vod["vod_play_from"] = "$$$".join(names)
            vod["vod_play_url"] = "$$$".join("播放$" + u for u in srcs)
            print(f"[av3698] play sources: {vod['vod_play_from']} / {vod['vod_play_url']}")
        else:
            print(f"[av3698] NO play source found in html len={len(html)}")

        # 详情图(可选, 站点代理)
        post = re.search(r'<video[^>]*poster="([^"]+)"', html)
        if post:
            p = post.group(1)
            vod["vod_pic"] = p if p.startswith("http") else self.siteUrl + p
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        if "$" in id:
            url = id.split("$", 1)[1].strip()
        else:
            url = id.strip()
        # 若给的是详情页URL则直接返回由播放器嗅探
        headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.siteUrl + "/",
        }
        return {"parse": 0, "url": url, "playUrl": url, "header": headers}

    def localProxy(self, params):
        # 保留空实现防止旧版调用报错; 本源播放无需本地代理
        return (404, "text/plain", "not needed", {})
