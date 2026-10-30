# -*- coding: utf-8 -*-
"""
wpg_spider.py — 玩偶盘搜 8.0 逆向版 (TVBox / 本地双环境, 完整版)
修复：移除抽象类继承 + 方法签名适配 TVBox 标准
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ============================================================
# 常量（保持不变）
# ============================================================
PAN_DEFAULT_API = "http://panso.xxmu.top"
PAN_OLD_DEFAULT_API = "https://so.252035.xyz"

PAN_ALL_TYPES = ["quark", "aliyun", "baidu", "uc", "tianyi", "xunlei",
                 "123", "115", "mobile", "guangya", "magnet", "ed2k"]
PAN_TYPE_LABEL = {"quark": "夸克", "aliyun": "阿里", "baidu": "百度", "uc": "UC",
                  "tianyi": "天翼", "xunlei": "迅雷", "123": "123", "115": "115",
                  "mobile": "移动", "guangya": "光鸭", "magnet": "磁力", "ed2k": "电驴"}
PAN_DEFAULT_TYPES = ["aliyun", "quark", "uc", "baidu", "tianyi", "123", "xunlei", "115", "mobile"]
PAN_TYPE_ORDER = ["quark", "baidu", "123", "uc", "115", "aliyun", "tianyi", "xunlei"]

PAN_QUALITY_KEYWORDS = [
    (["dolby vision", "dovi", "杜比视界", "dv"], 100),
    (["hdr10+", "hdr10plus"], 90),
    (["hdr10", "hdr", "hlg"], 80),
    (["4k", "2160p", "uhd", "8k"], 70),
    (["remux", "蓝光原盘", "原盘", "bluray", "blu-ray"], 65),
    (["高码率", "高码", "x265", "h265", "hevc"], 55),
    (["杜比全景声", "dolby atmos", "atmos"], 50),
    (["1080p", "1080i", "fhd"], 40),
    (["60fps", "60帧"], 30),
    (["720p"], 20),
    (["web-dl", "webdl", "bdrip"], 15),
    (["国语", "粤语", "国粤", "中字", "双语"], 5),
]

MACCMS_SITES = [
    {"id": "wanou", "name": "玩偶",
     "domains": ["https://wogg.xxooo.cf", "https://www.wogg.net"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": ".module-item", "cats": [
         ("44", "臻彩"), ("1", "电影"), ("2", "电视剧"), ("3", "动漫"),
         ("4", "综艺"), ("5", "音乐"), ("6", "短剧"), ("46", "纪录片")]},
    {"id": "muou", "name": "木偶",
     "domains": ["https://www.muou.site", "https://www.muou.asia", "https://666.666291.xyz"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("25", "臻选"), ("1", "电影"), ("2", "电视剧"), ("3", "动漫"),
         ("4", "纪录片"), ("29", "综艺"), ("30", "原盘")]},
    {"id": "labi", "name": "蜡笔",
     "domains": ["http://feimo.fun", "http://xiaocgege.shop"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("29", "臻彩"), ("1", "电影"), ("2", "电视剧"), ("3", "动漫"),
         ("4", "综艺"), ("5", "短剧"), ("24", "蜡笔4K")]},
    {"id": "zhizhen", "name": "至臻",
     "domains": ["https://zhizhen1.top", "https://www.mihdr.top",
                 "https://mihdr.top", "https://zhizhen.top"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("26", "臻彩"), ("1", "电影"), ("2", "电视剧"), ("3", "动漫"),
         ("4", "综艺"), ("5", "短剧"), ("24", "老剧")]},
    {"id": "erxiao", "name": "二小",
     "domains": ["https://www.2xiaopan.top", "https://2xiaopan.top",
                 "https://www.2xiaopan.com"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("4", "臻彩"), ("1", "电影"), ("2", "电视剧"), ("3", "动漫"), ("21", "综艺")]},
    {"id": "huban", "name": "虎斑",
     "domains": ["http://121.205.88.174:16969"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("6", "臻彩"), ("1", "电影"), ("2", "电视剧"), ("3", "综艺"),
         ("4", "动漫"), ("5", "短剧"), ("30", "115网盘")]},
    {"id": "shandian", "name": "闪电",
     "domains": ["http://shandian.blog", "http://sd.sduc.site"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("1", "电影"), ("2", "电视剧"), ("3", "综艺"), ("4", "动漫"), ("30", "短剧")]},
    {"id": "ouge", "name": "欧哥",
     "domains": ["https://woog.nxog.eu.org"],
     "search_path": "/vodsearch/index.html", "search_kw_param": "wd",
     "list_selector": "#main .module-item", "cats": [
         ("1", "电影"), ("2", "电视剧"), ("3", "动漫"), ("4", "综艺"),
         ("5", "短剧"), ("21", "综合")]},
]
SITE_BY_ID = {s["id"]: s for s in MACCMS_SITES}

DOMAIN_TO_SITE = {}
for _s in MACCMS_SITES:
    for _d in _s["domains"]:
        try:
            netloc = urllib.parse.urlsplit(_d).netloc.lower()
            DOMAIN_TO_SITE[netloc] = _s["id"]
        except Exception:
            pass
    for _d in _s["domains"]:
        _host = _d.lower().replace("https://", "").replace("http://", "").split("/")[0]
        DOMAIN_TO_SITE.setdefault(_host, _s["id"])

HEADERS_UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
HEADERS_PAN = {
    "User-Agent": HEADERS_UA, "Content-Type": "application/json",
    "Origin": PAN_DEFAULT_API, "Referer": PAN_DEFAULT_API + "/",
    "Accept": "application/json, text/plain, */*",
}

# ============================================================
# 工具函数（保持不变）
# ============================================================
def _strip_html(s):
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()

def _clean_title(t):
    t = re.sub(r"[《》\[\]【】]", "", str(t or ""))
    t = re.sub(r"[(（].*?[)）]", "", t)
    return re.sub(r"\s+", " ", t).strip()

def _quality_score(title):
    t = str(title or "").lower()
    return sum(w for keys, w in PAN_QUALITY_KEYWORDS if any(k in t for k in keys))

def _quality_tags(title):
    t = str(title or "").lower()
    rules = [(r"dolby.?vision|dovi|杜比视界|\bdv\b", "杜比视界"),
             (r"hdr10\+|hdr10plus", "HDR10+"),
             (r"hdr", "HDR"),
             (r"4k|2160p|uhd|8k", "4K"),
             (r"remux|蓝光原盘|bluray|blu-ray|原盘", "蓝光"),
             (r"高码率|高码|h265|hevc|x265", "高码"),
             (r"1080p|1080i", "1080P"),
             (r"60fps|60帧", "60帧")]
    return [label for pat, label in rules if re.search(pat, t)][:3]

def _type_rank(t):
    if t in PAN_TYPE_ORDER:
        return PAN_TYPE_ORDER.index(t)
    return 100 + (PAN_ALL_TYPES.index(t) if t in PAN_ALL_TYPES else 99)

def _abs_url(base, href):
    if not href:
        return ""
    href = href.strip()
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return "https:" + href
    try:
        p = urllib.parse.urlsplit(base)
        origin = f"{p.scheme}://{p.netloc}"
    except Exception:
        origin = base.rstrip("/").rsplit("/", 1)[0]
    if href.startswith("/"):
        return origin + href
    if href.startswith("./"):
        return origin + "/" + href[2:]
    if href.startswith("../"):
        path = urllib.parse.urlsplit(base).path.rstrip("/")
        path = "/".join(path.split("/")[:-1]) if "/" in path else ""
        return f"{urllib.parse.urlsplit(base).scheme}://{urllib.parse.urlsplit(base).netloc}{path}/{href[3:]}"
    return origin + "/" + href

def _url_host(url):
    try:
        return urllib.parse.urlsplit(url).netloc.lower()
    except Exception:
        return ""

# ============================================================
# MacCMS 通用解析（保持不变）
# ============================================================
def parse_maccms_cards(html, base, list_selector):
    items = []
    seen = set()
    start = 0
    while True:
        m = re.search(r'<a\b[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>(.*?)</a>',
                      html[start:], re.DOTALL)
        if not m:
            break
        start += m.start()
        block = m.group(1)
        end = start + m.end()

        detail_m = re.search(r'href=["\']([^"\']+)["\']', block)
        if not detail_m:
            continue
        detail_url = _abs_url(base, detail_m.group(1))

        pic_m = re.search(r'data-original=["\']([^"\']+)["\']', block)
        if not pic_m:
            pic_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', block)
        pic = _abs_url(base, pic_m.group(1)) if pic_m else ""

        title_m = re.search(r'<div\s+class="[^"]*module-item-title[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', block)
        if not title_m:
            title_m = re.search(r'<a[^>]+title=["\']([^"\']+)["\']', block)
        title = _strip_html(title_m.group(1)) if title_m else ""
        title = _clean_title(title)

        remark_m = re.search(r'module-item-text[^>]*>([^<]+)</', block)
        remark = _strip_html(remark_m.group(1)) if remark_m else ""
        remark = _clean_title(remark)

        m_id = re.search(r'/(?:voddetail|vodid)/(\d+)', detail_url)
        if not m_id:
            m_id = re.search(r'/(?:voddetail|vodid)/([A-Za-z0-9_]+)', detail_url)
        raw_id = m_id.group(1) if m_id else detail_url

        key = (raw_id, title)
        if key in seen:
            start = end
            continue
        seen.add(key)
        items.append({"_title": title or detail_url, "_pic": pic, "_remark": remark,
                      "_vod_id": raw_id, "_raw_href": detail_url})
        start = end
    return items

def parse_maccms_detail(html, base):
    def _find(pat, text=None):
        text = text if text is not None else html
        m = re.search(pat, text, re.DOTALL)
        return _strip_html(m.group(1)).strip() if m else ""

    title_m = re.search(r'<title[^>]*>([^<]+)</title>', html)
    detail_name = ""
    if title_m:
        detail_name = _strip_html(title_m.group(1))
        detail_name = re.sub(r"[\-\|]+[^-]+-.*$", "", detail_name).strip()

    name = _find(r'<h1[^>]*class="[^"]*module-info-title[^"]*"[^>]*>([^<]+)</h1>')
    if not name:
        name = _find(r'<h1[^>]*>([^<]+)</h1>') or detail_name

    pic = ""
    pic_m = re.search(r'<img[^>]*class="[^"]*module-info-img[^"]*"[^>]*>', html)
    if pic_m:
        src_m = re.search(r'data-original=["\']([^"\']+)["\']', pic_m.group(0))
        if not src_m:
            src_m = re.search(r'src=["\']([^"\']+)["\']', pic_m.group(0))
        if src_m:
            pic = _abs_url(base, src_m.group(1))
    if not pic:
        pic_m2 = re.search(r'<meta[^>]+itemprop="image"[^>]+content=["\']([^"\']+)["\']', html)
        if pic_m2:
            pic = _abs_url(base, pic_m2.group(1))

    desc_block = ""
    m = re.search(r'<div\s+class="[^"]*module-info-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        desc_block = m.group(1)

    def _row(label):
        pat = r'<(?:p|span|div)[^>]*>\s*' + label + r'\s*[:：]\s*([^<]+)'
        mm = re.search(pat, desc_block)
        return _strip_html(mm.group(1)) if mm else ""

    cls = _row("类型") or _row("类别")
    if not cls:
        cls_m = re.search(r'<meta[^>]+itemprop="genre"[^>]+content=["\']([^"\']+)["\']', html)
        cls = cls_m.group(1) if cls_m else ""
    actor = _row("主演") or _row("演员")
    director = _row("导演")
    score = _row("评分") or _row("分数")
    remark = _row("更新") or _row("集数") or _row("年份")

    desc = ""
    m = re.search(r'<div\s+class="[^"]*module-info-introduction-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        desc = _strip_html(m.group(1))
    if not desc:
        desc = _strip_html(re.search(r'<meta[^>]+name="description"[^>]+content=["\']([^"\']+)["\']', html).group(1)
                           if re.search(r'<meta[^>]+name="description"[^>]+content=["\']([^"\']+)["\']', html) else "")

    lines = []
    m = re.search(r'player_aaaa\s*=\s*([{.*}]*)\s*;', html, re.DOTALL)
    if m:
        raw = m.group(1)
        try:
            if not raw.startswith("{"):
                raw = "{" + raw + "}"
            obj = json.loads(raw)
            for name, ep_val in (obj.get("episode") or {}).items():
                url = ""
                if isinstance(ep_val, str):
                    if ep_val.startswith("http"):
                        url = ep_val
                    else:
                        url = _abs_url(base, ep_val)
                elif isinstance(ep_val, list):
                    url = _abs_url(base, ep_val[0]) if ep_val else ""
                lines.append({"from": obj.get("from") or name, "episodes": [{"name": name, "url": url}],
                              "detail_url": _abs_url(base, obj.get("detail_url") or "")})
        except Exception:
            pass
    if not lines:
        vodplay_urls = []
        for m in re.finditer(r'href=["\']([^"\']*/vodplay/[^"\']+)["\']', html):
            u = _abs_url(base, m.group(1))
            if u not in vodplay_urls:
                vodplay_urls.append(u)
        if vodplay_urls:
            lines.append({"from": "默认线路",
                          "episodes": [{"name": str(i + 1), "url": u} for i, u in enumerate(vodplay_urls)]})

    return {
        "raw": {"name": name, "pic": pic, "class": cls, "actor": actor,
                "director": director, "score": score, "remark": remark, "desc": desc},
        "lines": lines,
    }

def parse_maccms_play(html, referer_url):
    def _find_url(src):
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return _abs_url(referer_url, src)

    def _url_in(pattern, text):
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    m = re.search(r'player_aaaa\s*=\s*([{.*}]*)\s*;', html, re.DOTALL)
    if m:
        raw = m.group(1)
        try:
            obj = json.loads(raw if raw.startswith("{") else "{" + raw + "}")
            url = obj.get("url") or ""
            if url:
                url = url.replace("\\/", "/")
                return {"parse": int(obj.get("parse", 1)), "url": _find_url(url),
                        "header": {"Referer": referer_url, "User-Agent": HEADERS_UA}}
        except Exception:
            pass
        url = _url_in(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', m.group(1))
        if url:
            return {"parse": 1, "url": _find_url(url.replace("\\/", "/")),
                    "header": {"Referer": referer_url, "User-Agent": HEADERS_UA}}

    iframe_m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if iframe_m:
        return {"parse": 0, "url": _find_url(iframe_m.group(1)),
                "header": {"Referer": referer_url}}

    direct = re.search(r'https?://[^\s"\']+?\.(?:m3u8|mp4)(?:\?[^\s"\']*)?', html)
    if direct:
        return {"parse": 1, "url": direct.group(0),
                "header": {"Referer": referer_url, "User-Agent": HEADERS_UA}}

    for varname in ["video_url", "play_url", "playUrl", "m3u8Url", "url"]:
        m = re.search(rf"{varname}\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
        if m:
            u = m.group(1)
            if u.startswith("http"):
                return {"parse": 1, "url": u, "header": {"Referer": referer_url}}

    return {"parse": 0, "url": referer_url, "header": {"Referer": ""}}

# ============================================================
# Spider 主类（不再继承任何基类，所有方法签名适配 TVBox）
# ============================================================
class Spider:
    def __init__(self, extend=""):
        self.api_base = PAN_DEFAULT_API
        self.disk_types = list(PAN_DEFAULT_TYPES)
        self.enabled_sites = None
        self.site_base_override = {}
        self._extend_cfg = {}
        self.http_timeout = 12
        self._init_from(extend)
        # 本地 HTTP 标志
        self._local_http = True

    # -------- TVBox 生命周期 --------
    def init(self, extend=""):
        self._init_from(extend)
        return True

    def _init_from(self, extend=""):
        cfg = {}
        if extend:
            if isinstance(extend, str):
                try:
                    cfg = json.loads(extend) if extend.strip() else {}
                except Exception:
                    cfg = {}
            elif isinstance(extend, dict):
                cfg = dict(extend)
        self._extend_cfg = cfg
        self.api_base = (cfg.get("api") or PAN_DEFAULT_API).rstrip("/")
        u = cfg.get("types")
        if isinstance(u, list) and u:
            self.disk_types = [t for t in u if t in PAN_ALL_TYPES]
        s = cfg.get("sites")
        if isinstance(s, list) and s:
            self.enabled_sites = [x for x in s if x in SITE_BY_ID]
        self.site_base_override = cfg.get("site_base") or {}

    def destroy(self):
        pass

    def getName(self):
        return "玩偶盘搜8.0"

    # -------- HTTP 双环境 --------
    def _http_get(self, url, headers=None, timeout=None):
        if not url:
            return ""
        headers = dict(HEADERS_UA) if headers is None else dict(headers)
        headers.setdefault("User-Agent", HEADERS_UA)
        headers.setdefault("Accept", "text/html,application/xhtml+xml,*/*")
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        timeout = timeout or self.http_timeout
        try:
            # 尝试使用 self.req（TVBox 环境）
            if not getattr(self, "_local_http", True) and hasattr(self, "req"):
                try:
                    return self.req.get(url, headers=headers, timeout=timeout) or ""
                except Exception:
                    pass
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = resp.headers.get_content_charset() or "utf-8"
                try:
                    return raw.decode(enc, errors="replace")
                except Exception:
                    return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _http_post_json(self, url, body, timeout=15):
        data = json.dumps(body).encode("utf-8")
        headers = dict(HEADERS_PAN)
        if self.api_base != PAN_DEFAULT_API:
            headers["Origin"] = self.api_base
            headers["Referer"] = self.api_base + "/"
        try:
            if not getattr(self, "_local_http", True) and hasattr(self, "req"):
                try:
                    r = self.req.post(url, headers=headers, body=data, timeout=timeout)
                    if isinstance(r, dict):
                        return r
                    return json.loads(r) if r else {}
                except Exception:
                    pass
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return {"code": -1, "data": {}}

    # -------- PanSou 网盘搜索 --------
    def _pan_search(self, kw, disk_types=None):
        dt = disk_types or self.disk_types
        url = self.api_base.rstrip("/") + "/api/search"
        return self._http_post_json(url, {
            "kw": kw, "res": "merge", "src": "all", "cloud_types": dt,
        })

    def _render_pan_results(self, api_result, keyword=None, filter_type=None, keep_score=False):
        try:
            merged = ((api_result or {}).get("data") or {}).get("merged_by_type") or {}
            items = []
            for dtype, arr in merged.items():
                if filter_type and dtype != filter_type:
                    continue
                if dtype not in self.disk_types:
                    continue
                for it in (arr or []):
                    url = it.get("url") or it.get("share_url") or ""
                    if not url:
                        continue
                    note = _clean_title(it.get("note") or it.get("title") or it.get("name") or keyword or "")
                    password = it.get("password") or it.get("pwd") or ""
                    source = it.get("source") or ""
                    images = it.get("images") or []
                    pic = images[0] if images else ""
                    q_score = _quality_score(note)
                    label = PAN_TYPE_LABEL.get(dtype, dtype)
                    items.append({
                        "vod_id": f"pan@@{url}|{dtype}|{note}|{password}",
                        "vod_name": note,
                        "vod_pic": pic,
                        "vod_remarks": f"{label} · {q_score}分" + (f" · {source}" if source else ""),
                        "vod_class": " · ".join(_quality_tags(note)) or "网盘资源",
                        "type_name": f"盘搜-{label}",
                        "vod_play_from": label,
                        "vod_play_url": f"{note}$$${url}|{dtype}|{password}",
                        "_score": q_score,
                    })
            items.sort(key=lambda x: -x["_score"])
            if not keep_score:
                for x in items:
                    x.pop("_score", None)
            return {"list": items}
        except Exception as e:
            return {"list": [{"vod_name": f"解析失败: {e}", "vod_id": "0"}]}

    # -------- MacCMS 站抓取 --------
    def _site_base(self, site_id):
        site = SITE_BY_ID.get(site_id)
        if not site:
            return ""
        if site_id in self.site_base_override and self.site_base_override[site_id]:
            return self.site_base_override[site_id].rstrip("/")
        for dom in site["domains"]:
            head = self._http_get(dom + "/", timeout=6)
            if head:
                return dom.rstrip("/")
        return ""

    def _maccms_search(self, site_id, kw, page="1"):
        site = SITE_BY_ID.get(site_id)
        if not site:
            return []
        base = self._site_base(site_id)
        if not base:
            return []
        kw_q = urllib.parse.quote(kw)
        kw_param = site.get("search_kw_param", "wd")
        variants = [
            base + site["search_path"] + f"?{kw_param}={kw_q}&page={page}",
            base + f"/vodsearch/-------------.html?{kw_param}={kw_q}&page={page}",
            base + f"/vodsearch/{kw_q}.html?page={page}",
            base + f"/vodsearch/index.html?searchword={kw_q}&page={page}",
        ]
        for url in variants:
            html = self._http_get(url)
            if not html:
                continue
            cards = parse_maccms_cards(html, base, site["list_selector"])
            if cards:
                return cards
        return []

    def _maccms_category(self, site_id, cat_id, page="1"):
        site = SITE_BY_ID.get(site_id)
        if not site:
            return []
        base = self._site_base(site_id)
        if not base:
            return []
        p = str(page)
        variants = [
            base + (f"/vodshow/{cat_id}--------.html" if p == "1"
                    else f"/vodshow/{cat_id}--------{p}---.html"),
            base + (f"/vodtype/{cat_id}.html" if p == "1" else f"/vodtype/{cat_id}-{p}.html"),
            base + f"/vodtype/{cat_id}.html?page={p}",
            base + f"/vodshow/{cat_id}----------{p}.html",
        ]
        for url in variants:
            html = self._http_get(url)
            if not html:
                continue
            cards = parse_maccms_cards(html, base, site["list_selector"])
            if cards:
                return cards
        return []

    def _maccms_detail(self, site_id, raw_id):
        base = self._site_base(site_id)
        if not base:
            return {"raw": {}, "lines": []}
        variants = [base + f"/voddetail/{raw_id}.html", base + f"/vodid/{raw_id}.html"]
        for url in variants:
            html = self._http_get(url)
            if html:
                return parse_maccms_detail(html, base)
        return {"raw": {}, "lines": []}

    def _format_maccms_cards(self, cards, site_id):
        site = SITE_BY_ID.get(site_id)
        label = site["name"] if site else site_id
        items = []
        for c in cards:
            title = c.get("_title", "")
            score = _quality_score(title)
            href = c.get("_raw_href", "")
            items.append({
                "vod_id": "mac@@" + site_id + "@@" + c.get("_vod_id", ""),
                "vod_name": title,
                "vod_pic": c.get("_pic", ""),
                "vod_remarks": label + " · " + str(score) + "分" + ((" · " + c["_remark"]) if c.get("_remark") else ""),
                "vod_class": " · ".join(_quality_tags(title)) or "MacCMS",
                "type_name": "MacCMS-" + label,
                "vod_play_from": "详情页",
                "vod_play_url": title + "$$$" + href,
                "_score": score,
            })
        return items

    # ============================================================
    # TVBox 主接口（已修正签名）
    # ============================================================
    def homeContent(self, filter=False):
        """首页分类：MacCMS 各站的分类 + 盘搜网盘类型"""
        cls = []
        for site in MACCMS_SITES:
            for cid, cname in site["cats"]:
                cls.append({"type_id": "mac@@" + site["id"] + "@@" + cid,
                            "type_name": site["name"] + "-" + cname})
        for t in self.disk_types:
            label = PAN_TYPE_LABEL.get(t, t)
            cls.append({"type_id": "pan@@" + t, "type_name": "盘搜-" + label})
        return {"class": cls}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        """分类内容"""
        tid = str(tid or "")
        pg = str(pg or "1")
        try:
            if tid.startswith("mac@@"):
                parts = tid.split("@@")
                if len(parts) < 3:
                    return {"list": []}
                site_id, cat_id = parts[1], parts[2]
                cards = self._maccms_category(site_id, cat_id, pg)
                return {"list": self._format_maccms_cards(cards, site_id)}
            if tid.startswith("pan@@"):
                dtype = tid.split("@@")[1]
                if not self.enabled_sites:
                    return {"list": []}
                first_site = self.enabled_sites[0]
                page_var = {"1": "", "2": "page=2", "3": "page=3"}.get(pg, "page=" + pg)
                cards = []
                if page_var:
                    cards = self._maccms_search(first_site, "", pg)
                return {"list": self._format_maccms_cards(cards, first_site)}
        except Exception:
            return {"list": []}
        return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        """搜索：盘搜 + 8 个 MacCMS 站并行，按画质分排序"""
        if not key:
            return {"list": []}
        kw = _clean_title(key)
        merged = []
        # 1) 盘搜
        try:
            pan_res = self._pan_search(kw, self.disk_types)
            pan_items = self._render_pan_results(pan_res, keyword=kw, keep_score=True).get("list", [])
            merged.extend(pan_items)
        except Exception:
            pass
        # 2) 各 MacCMS 站
        sites = MACCMS_SITES if not self.enabled_sites else [s for s in MACCMS_SITES if s["id"] in self.enabled_sites]
        for site in sites:
            try:
                cards = self._maccms_search(site["id"], kw, str(pg))
                merged.extend(self._format_maccms_cards(cards, site["id"]))
            except Exception:
                continue
        merged.sort(key=lambda x: -x.get("_score", 0))
        for x in merged:
            x.pop("_score", None)
        return {"list": merged}

    def detailContent(self, ids):
        """详情"""
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            vid = str(vid or "")
            if vid.startswith("mac@@"):
                parts = vid.split("@@")
                if len(parts) < 3:
                    return {"list": []}
                site_id, raw_id = parts[1], parts[2]
                site = SITE_BY_ID.get(site_id)
                label = site["name"] if site else site_id
                det = self._maccms_detail(site_id, raw_id)
                raw = det.get("raw") or {}
                lines = det.get("lines") or []
                if not lines:
                    base = self._site_base(site_id)
                    if base:
                        lines = [{"from": "详情页",
                                  "episodes": [{"name": "1", "url": _abs_url(base, "")}]}]
                raw = {"name": "", "pic": "", "class": "", "actor": "", "director": "",
                       "score": "", "remark": "", "desc": ""} if not raw else raw
                play_froms = []
                play_urls = []
                for i, line in enumerate(lines):
                    from_name = line.get("from") or (label + "-线路" + str(i + 1))
                    eps = line.get("episodes") or []
                    if not eps and line.get("detail_url"):
                        eps = [{"name": "1", "url": line["detail_url"]}]
                    url_parts = []
                    for ep in eps:
                        ep_name = ep.get("name") or ""
                        ep_url = ep.get("url") or ""
                        abs_url = _abs_url(
                            self._site_base(site_id) + "/voddetail/" + raw_id + ".html",
                            ep_url
                        )
                        url_parts.append(ep_name + "$$$" + abs_url)
                    play_froms.append(from_name)
                    play_urls.append("|".join(url_parts))
                return {"list": [{
                    "vod_id": "mac@@" + site_id + "@@" + raw_id,
                    "vod_name": raw.get("name", ""),
                    "vod_pic": raw.get("pic", ""),
                    "vod_remarks": label + " · " + (raw.get("remark") or ""),
                    "vod_class": raw.get("class") or label,
                    "vod_actor": raw.get("actor") or "",
                    "vod_director": raw.get("director") or "",
                    "vod_score": raw.get("score") or "",
                    "type_name": "MacCMS-" + label,
                    "vod_content": raw.get("desc") or "",
                    "vod_play_from": "$$$".join(play_froms) if play_froms else label,
                    "vod_play_url": "$$$".join(play_urls) if play_urls else "",
                }]}
            # 网盘
            pan_raw = vid[5:] if vid.startswith("pan@@") else vid
            parts = pan_raw.split("|")
            url = parts[0] if parts else ""
            disk_type = parts[1] if len(parts) > 1 else ""
            note = parts[2] if len(parts) > 2 else ""
            pwd = parts[3] if len(parts) > 3 else ""
            label = PAN_TYPE_LABEL.get(disk_type, disk_type)
            return {"list": [{
                "vod_id": "pan@@" + pan_raw,
                "vod_name": note or url,
                "vod_remarks": label + " · 网盘直链",
                "vod_class": "网盘资源",
                "type_name": "盘搜-" + label,
                "vod_content": "网盘直链,请跳转到 " + label + " App 打开。\n" + (
                    "提取码: " + pwd if pwd else "无需提取码"),
                "vod_play_from": label,
                "vod_play_url": (note or url) + "$$$" + url + "|" + disk_type + "|" + pwd,
            }]}
        except Exception as e:
            return {"list": [{"vod_name": "详情错误: " + str(e), "vod_id": ""}]}

    def playerContent(self, flag, id, vipFlags=None):
        """播放"""
        try:
            id = str(id or "")
            if not id:
                return {"parse": 0, "url": ""}
            m = re.match(r"^(.*?)\$\$\$(.+)$", id, re.DOTALL)
            if m:
                tail = m.group(2)
            else:
                tail = id
            if "|" in tail and tail.count("|") >= 1 and not tail.startswith("http"):
                parts = tail.split("|")
                url = parts[0]
                disk_type = parts[1] if len(parts) > 1 else ""
                password = parts[2] if len(parts) > 2 else ""
                return {
                    "parse": 0,
                    "url": url,
                    "header": {},
                    "playUrl": url,
                    "ext": {
                        "disk_type": disk_type,
                        "disk_label": PAN_TYPE_LABEL.get(disk_type, disk_type),
                        "password": password,
                    },
                }
            ep_url = tail.strip()
            if not ep_url.startswith("http"):
                return {"parse": 0, "url": ""}
            return self._player_maccms(ep_url)
        except Exception:
            return {"parse": 0, "url": ""}

    def _player_maccms(self, ep_url):
        host = _url_host(ep_url)
        site_id = DOMAIN_TO_SITE.get(host, "")
        site = SITE_BY_ID.get(site_id)
        base = self._site_base(site_id) if site_id else ""
        play_html = self._http_get(ep_url)
        if not play_html:
            return {"parse": 0, "url": ep_url, "header": {"Referer": base + "/"}}
        parsed = parse_maccms_play(play_html, ep_url)
        return {
            "parse": parsed.get("parse", 0),
            "url": parsed.get("url") or ep_url,
            "header": parsed.get("header") or {"Referer": base + "/"},
            "playUrl": parsed.get("url") or ep_url,
            "ext": {
                "from_site": site_id,
                "site_name": site["name"] if site else "",
            },
        }

    # ---------- 兼容方法 ----------
    def homeVideoContent(self):
        """可选：首页视频内容（空）"""
        return {"list": []}

    def localProxy(self, param):
        return ""

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []


# ============================================================
# 本地调试
# ============================================================
if __name__ == "__main__":
    sp = Spider()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "home":
        print(json.dumps(sp.homeContent(), ensure_ascii=False, indent=2))
    elif cmd == "cat":
        tid = sys.argv[2]
        pg = sys.argv[3] if len(sys.argv) > 3 else "1"
        r = sp.categoryContent(tid, pg)
        print(f"分类 {tid} p{pg}: {len(r['list'])} 条")
        for v in r["list"][:20]:
            print(f"  {v['vod_id']:40s}  {v['vod_name'][:50]}  |  {v['vod_remarks'][:40]}")
    elif cmd == "search":
        kw = " ".join(sys.argv[2:])
        r = sp.searchContent(kw)
        print(f"搜索 {kw!r}: {len(r['list'])} 条")
        for i, v in enumerate(r["list"][:30], 1):
            print(f"  {i:2d}. [{v['type_name']}] {v['vod_name'][:45]}")
            print(f"       {v['vod_remarks'][:50]}")
    elif cmd == "detail":
        r = sp.detailContent(sys.argv[2])
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif cmd == "player":
        flag = sys.argv[2]
        pid = sys.argv[3]
        print(json.dumps(sp.playerContent(flag, pid), ensure_ascii=False, indent=2))
    elif cmd == "score":
        title = " ".join(sys.argv[2:])
        print(f"画质分: {_quality_score(title)}  tags: {_quality_tags(title)}")
    elif cmd == "types":
        print("网盘类型:", ", ".join(sp.disk_types))
        print("MacCMS 站:", ", ".join(s["id"] + "=" + s["name"] for s in MACCMS_SITES))
    elif cmd == "info":
        print("API:", sp.api_base)
        print("Types:", sp.disk_types)
        print("Sites enabled:", sp.enabled_sites or "all")
    else:
        print(__doc__)
        print()
        print("命令:")
        print("  home                    首页分类")
        print("  cat <tid> [page]        分类  (mac@@wanou@@1 / pan@@quark)")
        print("  search <keyword>        搜索")
        print("  detail <vod_id>         详情  (mac@@wanou@@123 / pan@@url|type|note)")
        print("  player <flag> <id>      播放")
        print("  score <title>           画质打分")
        print("  types                   类型清单")
        print("  info                    配置")