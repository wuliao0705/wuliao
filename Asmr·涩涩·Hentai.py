# -*- coding: utf-8 -*-
"""
Hentai ASMR TVBox Spider
站点: https://hentaiasmr.moe
类型: WordPress + RetroTube 主题 + m3u8/直链播放
注意: 需要 curl_cffi 绕过 Cloudflare
"""
import re
import json
from urllib.parse import unquote, urljoin

try:
    import sys
    sys.path.append('..')
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def getName(self): return "Base"
        def init(self, extend=""): pass
        def homeContent(self, filter): return {"class": [], "filters": {}}
        def categoryContent(self, tid, pg, filter, extend):
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        def detailContent(self, ids): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None):
            return {"parse": 0, "url": "", "header": {}}
        def searchContent(self, key, quick, pg="1"):
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def localProxy(self, param): return [404, "text/plain", b""]


class Spider(BaseSpider):
    name = "HentaiASMR"
    HOST = "https://hentaiasmr.moe"
    PER_PAGE = 18

    # ── 分类 ────────────────────────────────────────────
    CATEGORIES = [
        ("latest",   "最新"),
        ("popular",  "热门"),
        ("most-viewed", "最多观看"),
        ("longest",  "最长"),
        ("random",   "随机"),
    ]

    def __init__(self):
        super().__init__()
        try:
            from curl_cffi import requests as creq
            self.creq = creq
            self.use_cffi = True
        except ImportError:
            import requests
            self.requests = requests
            self.use_cffi = False

    def init(self, extend=""):
        pass

    # ══════════════════════════════════════════════════════
    #  请求工具
    # ══════════════════════════════════════════════════════

    def _get(self, path):
        """GET 请求，自动选择 curl_cffi 或 requests"""
        url = urljoin(self.HOST, path)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.HOST + "/",
        }
        try:
            if self.use_cffi:
                r = self.creq.get(url, impersonate="chrome120", timeout=15, headers=headers, allow_redirects=True)
                return r.text if r.status_code == 200 else None
            else:
                import requests
                r = requests.get(url, timeout=15, headers=headers, verify=False)
                return r.text if r.status_code == 200 else None
        except Exception:
            return None

    # ══════════════════════════════════════════════════════
    #  解析工具
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _extract_rj(html):
        """提取 RJ 编号"""
        m = re.search(r'(RJ\d+)', html)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_link(card_html):
        """从卡片 HTML 提取链接"""
        m = re.search(r'href="(https?://[^"]*\.moe/[^"]+\.html)"', card_html)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_title(html):
        """从 HTML 提取标题"""
        # 优先从 <title> 标签
        m = re.search(r'<title>(.*?)</title>', html)
        if m:
            title = m.group(1)
            # 去掉站点名后缀
            for suf in [' &raquo; Feed', ' &raquo; Hentai ASMR', ' - Hentai ASMR']:
                if title.endswith(suf):
                    title = title[:-len(suf)]
            return title.strip()
        # 回退到 title 属性
        m = re.search(r'title="([^"]+)"', html)
        if m:
            return m.group(1).strip()
        # 回退到 span
        m = re.search(r'<span>([^<]+)</span>', html)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_cover(card_html):
        """从卡片 HTML 提取封面"""
        m = re.search(r'data-src="(https?://[^"]+)"', card_html)
        if m:
            return m.group(1)
        m = re.search(r'src="(https?://[^"]+)"', card_html)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_duration(card_html):
        """从卡片 HTML 提取时长"""
        m = re.search(r'class="duration"[^>]*><i[^>]*></i>([^<]+)', card_html)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _max_page(html):
        """从分页导航提取最大页数"""
        # 格式: <a href="https://hentaiasmr.moe/page/2027">最後</a>
        # 2027 是总帖子数相关的，实际需要找最大的合理页码
        pages = re.findall(r'href="[^"]*page/(\d+)"', html)
        if not pages:
            return 1
        nums = [int(p) for p in pages if p.isdigit()]
        if not nums:
            return 1
        # 如果有"最後"链接且数字异常大(>1000)，跳过
        has_last = '最後' in html or 'last' in html.lower()
        max_num = max(nums)
        if has_last and max_num > 1000:
            # 取第二大的
            nums.sort(reverse=True)
            return max(nums[1] if len(nums) > 1 else 1, 1)
        return max_num

    # ══════════════════════════════════════════════════════
    #  homeContent
    # ══════════════════════════════════════════════════════

    def homeContent(self, filter={}):
        classes = []
        filters = {}
        for tid, name in self.CATEGORIES:
            classes.append({"type_id": tid, "type_name": name})
            filters[tid] = []
        return {"class": classes, "filters": filters}

    # ══════════════════════════════════════════════════════
    #  homeVideoContent
    # ══════════════════════════════════════════════════════

    def homeVideoContent(self):
        return self._parse_list(self._get("/"))

    # ══════════════════════════════════════════════════════
    #  categoryContent
    # ══════════════════════════════════════════════════════

    def categoryContent(self, tid, pg, filter, extend):
        pg = max(int(pg or 1), 1)
        # 分类 URL: ?filter=latest 等
        if pg <= 1:
            path = f"/?ref=porndude&filter={tid}"
        else:
            path = f"/page/{pg}/?ref=porndude&filter={tid}"
        html = self._get(path)
        if not html:
            return self._empty_result(pg)
        max_p = self._max_page(html)
        return self._parse_list(html, pg, max_p)

    # ══════════════════════════════════════════════════════
    #  detailContent
    # ══════════════════════════════════════════════════════

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0]).strip()
        if not vid.startswith("http"):
            url = f"{self.HOST}/{vid}" if vid.startswith("/") else f"{self.HOST}/{vid}"
        else:
            url = vid
        html = self._get(url)
        if not html:
            return {"list": []}
        
        rj = self._extract_rj(html)
        title = self._extract_title(html)
        cover = self._extract_cover(html)
        # 清理标题中的站点信息
        for suf in [' &raquo; Feed', ' &raquo; Hentai ASMR', ' - Hentai ASMR', 'Hentai ASMR', 'Feed']:
            if suf in title:
                title = title.split(suf)[0].strip()
        
        # 尝试提取播放源
        play_url = url  # 默认直接跳转
        
        return {
            "list": [{
                "vod_id": vid,
                "vod_name": f"[{rj}] {title}" if rj else title,
                "vod_pic": cover,
                "vod_play_from": "HentaiASMR",
                "vod_play_url": f"播放${play_url}",
            }]
        }

    # ══════════════════════════════════════════════════════
    #  searchContent
    # ══════════════════════════════════════════════════════

    def searchContent(self, key, quick, pg="1"):
        pg = max(int(pg or 1), 1)
        path = f"/?s={key}" if pg == 1 else f"/?s={key}&page={pg}"
        html = self._get(path)
        if not html:
            return self._empty_result(pg)
        max_p = self._max_page(html)
        return self._parse_list(html, pg, max_p)

    # ══════════════════════════════════════════════════════
    #  playerContent
    # ══════════════════════════════════════════════════════

    def playerContent(self, flag, id, vipFlags=None):
        hdr = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": self.HOST + "/",
        }
        raw = str(id).strip()
        if raw.startswith("http"):
            return {"parse": 1, "url": raw, "header": hdr}
        return {"parse": 1, "url": f"{self.HOST}/{raw}", "header": hdr}

    # ══════════════════════════════════════════════════════
    #  列表解析
    # ══════════════════════════════════════════════════════

    def _parse_list(self, html, page=1, pagecount=1):
        """解析列表页 → 视频列表"""
        if not html:
            return self._empty_result(page)
        
        videos = []
        seen = set()
        
        # 提取所有卡片
        cards = re.findall(
            r'<article[^>]*class="[^"]*loop-video[^"]*"[^>]*>.*?</article>',
            html, re.S
        )
        
        for card in cards:
            link = self._extract_link(card)
            if not link or link in seen:
                continue
            seen.add(link)
            
            title = self._extract_title(card)
            cover = self._extract_cover(card)
            duration = self._extract_duration(card)
            
            videos.append({
                "vod_id": link,
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": duration,
            })
        
        total = pagecount * self.PER_PAGE if pagecount > 1 else len(videos)
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": total,
        }

    # ══════════════════════════════════════════════════════
    #  辅助
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _empty_result(pg):
        return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(m3u8|mp4|mp3|m4a|webm)\b', url, re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass


Spider = Spider
