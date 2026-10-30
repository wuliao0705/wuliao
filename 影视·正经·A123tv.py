#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A123TV (a123tv.com) TVBox Python Spider
增强: 主分类支持二级子分类筛选（通过 filters）
完成: 2026-08-31
"""

import re
import json
import urllib.parse
import urllib.request

HOST = "https://a123tv.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 主分类
MAIN_CATS = [
    (10, "电影"),
    (11, "连续剧"),
    (12, "综艺"),
    (13, "动漫"),
    (15, "福利"),
]

# 子分类映射（从 README 整理）
SUB_CATS = {
    10: [
        (1001, "动作片"), (1002, "喜剧片"), (1003, "爱情片"), (1004, "科幻片"),
        (1005, "恐怖片"), (1006, "剧情片"), (1007, "战争片"), (1008, "纪录片"),
        (1010, "动漫电影"), (1011, "奇幻片"), (1013, "动画片"), (1014, "犯罪片"),
        (1016, "悬疑片"), (1019, "邵氏电影"), (1022, "歌舞片"), (1024, "家庭片"),
        (1025, "古装片"), (1026, "历史片"), (1027, "4K电影")
    ],
    11: [
        (1101, "国产剧"), (1102, "香港剧"), (1103, "韩国剧"), (1104, "欧美剧"),
        (1105, "台湾剧"), (1106, "日本剧"), (1107, "海外剧"), (1108, "泰国剧"),
        (1110, "港台剧"), (1111, "日韩剧")
    ],
    12: [
        (1201, "内地综艺"), (1202, "港台综艺"), (1203, "日韩综艺"),
        (1204, "欧美综艺"), (1205, "国外综艺")
    ],
    13: [
        (1301, "国产动漫"), (1302, "日韩动漫"), (1303, "欧美动漫"),
        (1305, "海外动漫"), (1307, "里番")
    ],
    15: [
        (1551, "韩国情色片"), (1552, "日本情色片"), (1553, "香港情色片"),
        (1554, "台湾情色片"), (1555, "大陆情色片"), (1556, "美国情色片"),
        (1557, "欧洲情色片"), (1558, "印度情色片"), (1559, "东南亚情色片"),
        (1550, "其它情色片")
    ],
}

MAX_LINES_DEFAULT = 8
MAX_LINES_HARD = 30


class Spider:

    def __init__(self):
        self.max_lines = MAX_LINES_DEFAULT

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict) and "max_lines" in cfg:
                    self.max_lines = int(cfg["max_lines"])
                    if self.max_lines < 1:
                        self.max_lines = 1
                    if self.max_lines > MAX_LINES_HARD:
                        self.max_lines = MAX_LINES_HARD
            except Exception:
                pass
        return True

    def destroy(self):
        pass

    def getName(self):
        return "A123TV"

    # ---------- HTTP ----------
    def _fetch(self, url, timeout=25):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")

    @staticmethod
    def _abs(u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith(("http://", "https://")):
            return u
        if u.startswith("/"):
            return HOST + u
        return HOST + "/" + u

    # ---------- 解析 ----------
    def _parse_cards(self, html):
        items = []
        chunks = re.split(r'<div\s+class="w4-item-wrap">', html)
        for chunk in chunks[1:]:
            a = re.search(r'<a\s+class="w4-item"\s+href="([^"]+)"', chunk)
            if not a:
                continue
            href = a.group(1)
            t = re.search(r'<div\s+class="t"(?:\s+title="([^"]*)")?[^>]*>([^<]+)</div>', chunk)
            title = (t.group(1) or t.group(2)).strip() if t else ""
            img_m = re.search(r'<img[^>]*\bdata-src="([^"]*)"', chunk)
            if not img_m:
                img_m = re.search(r'<img[^>]*\bsrc="([^"]*?a123tv\.com[^"]*)"', chunk)
            img = img_m.group(1) if img_m else ""
            alt_m = re.search(r'<img[^>]*\balt="([^"]*)"', chunk)
            if alt_m and not title:
                title = alt_m.group(1)
            quality = ""
            fig = re.search(r'<figure[^>]*>(.*?)</figure>', chunk, re.S)
            if fig:
                q = re.search(r'<div\s+class="r"[^>]*>([^<]+)</div>', fig.group(1))
                if q:
                    quality = q.group(1).strip()
                s = re.search(r'<span>([^<]+)</span>', fig.group(1))
                lines_txt = s.group(1).strip() if s else ""
            info_m = re.search(r'<div\s+class="i"[^>]*>([^<]+)</div>', chunk)
            info = info_m.group(1).strip() if info_m else ""
            parts = info.split("/")
            vod_class = parts[0].strip() if parts else ""
            vod_year = parts[1].strip()[:-1] if len(parts) > 1 and parts[1].strip().endswith("年") else ""
            m2 = re.search(r'/v/([a-z0-9\-_]+)/?\.?html?$', href)
            if not m2:
                m2 = re.search(r'/v/([a-z0-9\-_]+)', href)
            vod_id = m2.group(1) if m2 else href
            remark = quality
            if lines_txt:
                remark = (remark + " " if remark else "") + lines_txt
            items.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._abs(img),
                "vod_class": vod_class,
                "vod_year": vod_year,
                "vod_area": "",
                "vod_remarks": remark,
                "vod_url": self._abs(href),
                "vod_play_from": "",
                "vod_play_url": "",
            })
        return items

    def _parse_pp_json(self, html):
        m = re.search(r'var\s+pp\s*=\s*(\{.*?\})\s*;\s*</script>', html, re.S)
        if not m:
            return None
        raw = m.group(1).replace("\\/", "/")
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        """返回主分类 + 每个主分类的筛选器（子分类）"""
        classes = []
        filters = {}
        for tid, name in MAIN_CATS:
            classes.append({"type_id": str(tid), "type_name": name})
            # 为该主分类添加子分类筛选器
            subs = SUB_CATS.get(tid, [])
            if subs:
                opts = [{"n": "全部", "v": ""}]
                for sub_id, sub_name in subs:
                    opts.append({"n": sub_name, "v": str(sub_id)})
                filters[str(tid)] = [
                    {"key": "sub", "name": "分类", "value": opts}
                ]
        return json.dumps({"class": classes, "filters": filters})

    def categoryContent(self, tid, pg, filter=False, extend=None):
        tid = str(tid).strip()
        pg = int(pg) if pg else 1

        # 检查是否有子分类筛选
        sub_tid = None
        if extend and isinstance(extend, dict):
            sub_tid = extend.get("sub")
        if not sub_tid and filter and isinstance(filter, dict):
            sub_tid = filter.get("sub")
        # 如果 sub_tid 存在且不为空，则使用子分类 ID
        if sub_tid:
            tid = sub_tid

        if not tid:
            html = self._fetch(HOST + "/")
        elif pg <= 1:
            html = self._fetch(f"{HOST}/t/{tid}.html")
        else:
            html = self._fetch(f"{HOST}/t/{tid}/p{pg}.html")

        items = self._parse_cards(html)
        pagecount = 1
        m = re.findall(r'href="/t/%s/p(\d+)\.html"' % re.escape(tid), html)
        if m:
            pagecount = max(int(x) for x in m)
        return json.dumps({
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        })

    def detailContent(self, ids):
        if not ids:
            return json.dumps({"list": []})
        vid = str(ids[0] if isinstance(ids, list) else ids).strip()
        vid = vid.replace("/v/", "").replace(".html", "").replace(".htm", "")
        vid = re.sub(r'/.*$', '', vid)
        html = self._fetch(f"{HOST}/v/{vid}.html")

        # 标题
        title = ""
        m = re.search(r'<title>《([^》]+)》', html)
        if m:
            title = m.group(1)
        if not title:
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if m:
                title = m.group(1).strip()

        # 描述
        desc = ""
        m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
        if m:
            desc = m.group(1).strip()

        # 图片
        pic = ""
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
        if m:
            pic = self._abs(m.group(1))
        if not pic:
            m = re.search(r'<meta\s+name="twitter:image"\s+content="([^"]*)"', html)
            if m:
                pic = self._abs(m.group(1))

        # 分类
        vod_class = ""
        bc = re.search(r'w4-bread.*?</ol>', html, re.S)
        if bc:
            parts = re.findall(r'href="/t/(\d+)\.html">([^<]+)<', bc.group(0))
            if parts:
                vod_class = parts[-1][1].strip()

        # 年份
        vod_year = ""
        m = re.search(r'<title>[^<]*?(\d{4})年', html)
        if m:
            vod_year = m.group(1)

        # 元数据
        vod_area = ""
        vod_actor = ""
        vod_director = ""
        vod_blurb = desc
        if desc:
            m = re.match(r'^(?:地区：([^。]*)。)?', desc)
            if m and m.group(1):
                vod_area = m.group(1).strip()
            m = re.search(r'演员：([^。]*)。', desc)
            if m:
                vod_actor = m.group(1).strip()
            m = re.search(r'导演：([^。]*)。', desc)
            if m:
                vod_director = m.group(1).strip()
            m = re.search(r'剧情：(.+)', desc, re.S)
            if m:
                vod_blurb = m.group(1).strip()

        # 线路信息
        lines = []
        pp = self._parse_pp_json(html)
        if pp:
            la = pp.get("la") or []
            for it in la:
                if not isinstance(it, list) or len(it) < 5:
                    continue
                lines.append({
                    "id": it[0],
                    "name": it[1],
                    "ep": int(it[2]) if it[2] else 0,
                    "flag": int(it[3]) if len(it) > 3 else 0,
                    "url": it[4],
                })

        # 当前线路剧集
        episodes = []
        ep_sec = re.search(r'<div class="w4-episode-list[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.S)
        if ep_sec:
            for em in re.finditer(r'href="(/v/[^"]+\.html)"\s+title="([^"]+)"', ep_sec.group(1)):
                episodes.append({"url": em.group(1), "name": em.group(2)})

        total_ep = len(episodes)
        if total_ep == 0:
            m = re.search(r'选集（共\s*(\d+)\s*集）', html)
            if m:
                total_ep = int(m.group(1))
        if total_ep == 0:
            for l in lines:
                if l["ep"] > total_ep:
                    total_ep = l["ep"]
        if total_ep == 0:
            total_ep = 1

        if not lines and pp:
            ld = pp.get("ld")
            if ld:
                for l in pp.get("la", []):
                    lines.append({
                        "id": l[0], "name": l[1],
                        "ep": int(l[2]) if l[2] else total_ep,
                        "flag": 0,
                        "url": l[4] if len(l) > 4 else "",
                    })

        if len(lines) > self.max_lines:
            lines = lines[:self.max_lines]

        if not lines:
            m = re.search(r'id="awp1"[^>]*data-src="([^"]+)"', html)
            if m:
                lines.append({
                    "id": "default",
                    "name": "默认线路",
                    "ep": total_ep,
                    "flag": 0,
                    "url": m.group(1),
                })

        play_from_parts = []
        play_url_parts = []
        for line in lines:
            play_from_parts.append(line["name"])
            ep_links = []
            for i in range(total_ep):
                ep_url = f"{HOST}/v/{vid}/{line['id']}z{i}.html"
                ep_name = f"第{i+1:02d}集" if total_ep > 1 else "正片"
                ep_links.append(f"{ep_name}${ep_url}")
            play_url_parts.append("#".join(ep_links))

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_class": vod_class,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_blurb": vod_blurb,
            "vod_remarks": f"共{total_ep}集" if total_ep > 1 else "电影",
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_from_parts),
            "vod_play_url": "$$$".join(play_url_parts),
        }
        return json.dumps({"list": [vod]})

    # ---------- 播放（parse=1 让 TVBox 处理 AES-128 加密） ----------
    def playerContent(self, flag, id, vipFlags=None):
        url = id or ""
        if url and not url.startswith("http"):
            url = self._abs(url)
        if not url:
            return json.dumps({"parse": 1, "url": "", "header": {}})

        try:
            html = self._fetch(url)
        except Exception as e:
            return json.dumps({"parse": 1, "url": "", "header": {}})

        m3u8 = ""
        # 1) awp1 data-src
        m = re.search(r'id="awp1"[^>]*\bdata-src="([^"]+)"', html)
        if m:
            m3u8 = m.group(1)
        # 2) index.m3u8
        if not m3u8:
            m = re.search(r'(https?://[^"\']+/index\.m3u8(?:\?[^\s"\']*)?)', html)
            if m:
                m3u8 = m.group(1)
        # 3) pp JSON
        if not m3u8:
            pp = self._parse_pp_json(html)
            if pp and pp.get("la"):
                first = pp["la"][0]
                if isinstance(first, list) and len(first) > 4 and first[4]:
                    m3u8 = first[4]

        if not m3u8:
            return json.dumps({"parse": 1, "url": "", "header": {}})

        headers = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Origin": HOST,
        }
        return json.dumps({
            "parse": 1,
            "playUrl": m3u8,
            "url": m3u8,
            "header": json.dumps(headers),
        })

    def searchContent(self, key, quick=False, pg="1"):
        page = int(pg) if pg else 1
        kw = urllib.parse.quote((key or "").strip())
        if page <= 1:
            url = f"{HOST}/s/{kw}.html"
        else:
            url = f"{HOST}/s/{kw}/p{page}.html"
        try:
            html = self._fetch(url)
        except Exception:
            html = ""
        items = self._parse_cards(html)
        pagecount = 1
        m = re.findall(r'href="/s/%s/p(\d+)\.html"' % re.escape(kw), html)
        if m:
            pagecount = max(int(x) for x in m)
        return json.dumps({
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        })

    # ---------- 兼容 ----------
    def homeVideoContent(self):
        return json.dumps({"list": []})

    def localProxy(self, param):
        return ""

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []


# ============================================================
# CLI 测试
# ============================================================
if __name__ == "__main__":
    import sys
    sp = Spider()
    sp.init("")
    if len(sys.argv) < 2:
        print("usage: a123tv_spider.py home|cat|detail|search|player [arg]")
        print("  home")
        print("  cat <tid> [page]    tid=10电影,11连续剧,12综艺,13动漫,15福利")
        print("  detail <vid>        vid=liwu5, zhifajiaochadian")
        print("  search <keyword> [page]")
        print("  player <url>        播放页URL")
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "home":
        print(sp.homeContent())
    elif cmd == "cat":
        tid = sys.argv[2] if len(sys.argv) > 2 else "10"
        pg = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        r = json.loads(sp.categoryContent(tid, pg))
        print(f"total={len(r['list'])} pagecount={r['pagecount']}")
        for it in r["list"][:5]:
            print(f"  {it['vod_id']:30s} | {it['vod_name'][:20]:20s} | {it['vod_class']:8s} | {it['vod_year']}")
    elif cmd == "detail":
        vid = sys.argv[2]
        r = json.loads(sp.detailContent(vid))
        v = r["list"][0]
        print("name:", v["vod_name"])
        print("pic:", v["vod_pic"])
        print("class:", v["vod_class"], "year:", v["vod_year"], "area:", v["vod_area"])
        print("actor:", v["vod_actor"][:80])
        print("director:", v["vod_director"])
        print("remarks:", v["vod_remarks"])
        print("play_from:", v["vod_play_from"][:200])
        urls = v["vod_play_url"].split("$$$")
        print(f"play_url groups: {len(urls)}")
        if urls:
            eps = urls[0].split("#")
            print(f"  group0 ep count: {len(eps)}")
            print(f"  group0 first 2 eps: {eps[:2]}")
    elif cmd == "search":
        kw = sys.argv[2]
        page = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        r = json.loads(sp.searchContent(kw, False, page))
        print(f"total={len(r['list'])}")
        for it in r["list"][:5]:
            print(f"  {it['vod_id']:30s} | {it['vod_name'][:20]}")
    elif cmd == "player":
        url = sys.argv[2]
        r = json.loads(sp.playerContent("a123tv", url))
        print("parse:", r["parse"], "playUrl:", r["playUrl"], "msg:", r.get("msg"))