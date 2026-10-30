
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xvideos.com Spider v6.0 (final)
结合真实 DOM 结构制作:
- 分类目录: /best(最佳月度) + 标签索引(文件夹) + 频道索引(文件夹) + 明星索引(文件夹)
- 标签视频: /tags/{tag}/{n} 分页(注意偏移: n=1 是第2页)
- 频道/明星: 点击文件夹 → /{slug} 或 /models/{name} 作品列表
- 视频卡片: 双格式兼容:
    A) frame-block: data-src + <p class="title">
    B) thumb-block video: data-video JSON + <div class="title"> + duration
- 详情页: setVideoHLS/setVideoUrlHigh/setVideoUrlLow 提取多线路(base64)
"""
import re, json, base64, html as _html, ssl, warnings
from urllib.parse import quote

# ============ 全局关闭 SSL 证书校验 (修复: unable to get local issuer certificate) ============
# 安卓嵌入式 Python 的 CA 证书库常缺失/损坏, 这里在所有层面禁用校验证书
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    from curl_cffi import Session
except ImportError:
    import requests as _r
    class Session:
        def __init__(self, impersonate=None):
            self._s = _r.Session()
            self._s.verify = False          # 会话级关闭校验
        def get(self, *a, **kw):
            kw.setdefault('timeout', 20)
            kw.setdefault('verify', False)
            kw.setdefault('cert', None)
            return self._s.get(*a, **kw)
        @property
        def headers(self): return self._s.headers
        @headers.setter
        def headers(self, v): self._s.headers.update(v)

class Spider:
    host = "https://www.xvideos.com"
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    def __init__(self):
        self.s = Session(impersonate="chrome120")
        # curl_cffi/BoringSSL: verify must be set on the Session object, not per-request
        self.s.verify = False
        self.s.cert = None
        try:
            self.s.headers.update({
                'User-Agent': self.UA,
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': self.host + '/',
            })
        except Exception:
            pass
        self._request_count = 0
        self._max_retries = 3
        # 本地缓存: {url: (timestamp, response_text)}
        self._cache = {}
        self._cache_ttl = 120  # 缓存 120 秒

    def _get(self, url, **kw):
        """带重试的请求方法，应对 VPN 切换导致的网络不稳定"""
        kw.setdefault('timeout', 15)
        kw.setdefault('verify', False)
        kw.setdefault('cert', None)
        if url.startswith('/'):
            url = self.host + url
        
        import time
        # 检查缓存
        now = time.time()
        if url in self._cache:
            ts, cached_text = self._cache[url]
            if now - ts < self._cache_ttl:
                # 返回缓存的伪响应对象
                class _CachedResp:
                    def __init__(self, text):
                        self.text = text
                        self.status_code = 200
                        self.url = url
                        self._content = text.encode('utf-8', 'ignore')
                    def content(self):
                        return self._content
                return _CachedResp(cached_text)
        
        last_error = None
        for attempt in range(self._max_retries):
            try:
                self._request_count += 1
                r = self.s.get(url, **kw)
                if r.status_code == 200:
                    # 缓存成功响应
                    self._cache[url] = (now, r.text)
                    return r
                # 403/429/503 可能是限流或 Cloudflare 挑战，重试
                if r.status_code in (403, 429, 503, 502):
                    time.sleep(1 * (attempt + 1))
                    continue
                return r
            except Exception as e:
                last_error = e
                # VPN 切换时常出现连接错误，等待后重试
                if attempt < self._max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"[XVideos] Request failed after {self._max_retries} attempts: {e}")
                # 返回缓存作为最后手段
                if url in self._cache:
                    ts, cached_text = self._cache[url]
                    class _CachedResp:
                        def __init__(self, text):
                            self.text = text
                            self.status_code = 200
                            self.url = url
                            self._content = text.encode('utf-8', 'ignore')
                        def content(self):
                            return self._content
                    print(f"[XVideos] Using cached data for {url}")
                    return _CachedResp(cached_text)
                return None
        return None

    # ================ 视频卡片解析(双格式) =================
    def _parse_video_cards(self, html):
        cards, seen = [], set()
        if not html:
            return cards

        # 格式A: thumb-block video + data-video JSON + div.title
        pat_a = re.compile(
            r'<div[^>]*class="[^"]*thumb-block[^"]*(?:| video)[^"]*"[^>]*data-video=\'(\{.*?\})\'[^>]*>.*?'
            r'<a[^>]+href="(/video\.[^"]+)"[^>]*>.*?'
            r'<div[^>]*class="title"[^>]*title="([^"]*)"[^>]*>.*?'
            r'class="duration"[^>]*>([^<]+)</span>',
            re.S
        )
        for m in pat_a.finditer(html):
            vjson, vlink, title, dur = m.groups()
            if vlink in seen: continue
            seen.add(vlink)
            # 封面: 从 data-video JSON 拿 mozaiqueListing 或 img
            pic = ''
            try:
                vd = json.loads(vjson)
                pic = vd.get('mozaiqueListing', '') or vd.get('thumbUrl', '')
            except Exception:
                pass
            if not pic:
                seg = html[m.start():m.start()+600]
                pm = re.search(r'data-src="(https?://[^"\']+\.(?:jpg|jpeg|webp)[^"\']*)"', seg)
                pic = pm.group(1) if pm else ''
            cards.append({
                'vod_id': vlink,
                'vod_name': _html.unescape(title),
                'vod_pic': pic,
                'vod_remarks': dur,
                'style': {'type': 'rect', 'ratio': 1.33},
            })

        # 格式B: frame-block + data-src + p.title
        pat_b = re.compile(
            r'<div[^>]*class="[^"]*frame-block[^"]*"[^>]*>.*?'
            r'<a[^>]+href="(/video\.[^"]+)"[^>]*>.*?'
            r'data-src="(https?://[^"\']+\.(?:jpg|jpeg|webp)[^"\']*)".*?'
            r'</a>.*?'
            r'<p[^>]*class="title"[^>]*>(?:<a[^>]*title="([^"]*)"[^>]*>|)',
            re.S
        )
        for m in pat_b.finditer(html):
            vlink, thumb, title = m.groups()
            if vlink in seen: continue
            seen.add(vlink)
            seg = html[m.start():m.end()+500]
            dur_m = re.search(r'class="duration"[^>]*>([^<]+)</span>', seg)
            cards.append({
                'vod_id': vlink,
                'vod_name': _html.unescape(title or ''),
                'vod_pic': thumb,
                'vod_remarks': dur_m.group(1) if dur_m else '',
                'style': {'type': 'rect', 'ratio': 1.33},
            })

        # 格式C: 宽松（链接 + 附近 title/data-src）
        if not cards:
            for m in re.finditer(r'<a[^>]+href="(/video\.[^"]+)"[^>]*>', html):
                vlink = m.group(1)
                if vlink in seen: continue
                nxt = html.find('<a', m.end())
                seg = html[m.end(): nxt if nxt > 0 else m.end()+2500]
                t_m = re.search(r'title="([^"]*)"', seg)
                p_m = re.search(r'data-src="(https?://[^"\']+\.(?:jpg|jpeg|webp)[^"\']*)', seg)
                du_m = re.search(r'class="duration"[^>]*>([^<]+)</span>', seg)
                seen.add(vlink)
                cards.append({
                    'vod_id': vlink,
                    'vod_name': _html.unescape(t_m.group(1)) if t_m else '视频',
                    'vod_pic': p_m.group(1) if p_m else '',
                    'vod_remarks': du_m.group(1) if du_m else '',
                    'style': {'type': 'rect', 'ratio': 1.33},
                })
        return cards

    # ================ 分页解析 =================
    def _parse_pages(self, html, max_num=1000):
        """解析最大页码 (last-page / 最大数字), 兼容 ?k=&p=N 搜索格式"""
        m = re.findall(r'href="[^"]*?/(\d+)"\s+class="last-page"', html)
        if not m:
            m = re.findall(r'href="([^"]*p=)(\d+)"[^>]*class="last-page"', html)
            if m:
                return min(max(int(x[1]) for x in m), max_num)
        if m:
            return min(max(int(x) for x in m), max_num)
        return 1

    def _empty(self, pg=1):
        return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 30, 'total': 0}

    # ================ homeContent =================
    def homeContent(self, filter=False):
        classes = [
            {'type_id': '/best', 'type_name': '最佳视频'},
            {'type_id': '/tags', 'type_name': '标签分类'},
            {'type_id': '/channels-index', 'type_name': '频道大全'},
            {'type_id': '/pornstars-index', 'type_name': '明星大全'},
        ]
        try:
            r = self._get('/')
            vids = self._parse_video_cards(r.text)[:30] if r and r.status_code == 200 else []
        except Exception:
            vids = []
        return {'class': classes, 'list': vids}

    def homeVideoContent(self):
        try:
            r = self._get('/')
            vids = self._parse_video_cards(r.text) if r and r.status_code == 200 else []
        except Exception:
            vids = []
        return {'list': vids, 'page': 1, 'pagecount': 1, 'limit': len(vids), 'total': len(vids)}

    # ================ categoryContent =================
    def categoryContent(self, tid, pg=1, filter={}, extend={}):
        pg = max(int(pg) if str(pg).isdigit() else 1, 1)
        tid = str(tid)

        # ---- 视频列表: /best, /tags/{tag}, /lang/{lang} ----
        if tid in ('/best', '/new') or tid.startswith('/tags/') or tid.startswith('/lang/'):
            url = tid
            if pg > 1:
                if tid == '/best':
                    # /best 重定向到 /best/YYYY-MM，分页格式 /best/YYYY-MM/{n}
                    r0 = self._get('/best')
                    m = re.search(r'/best/(\d{4}-\d{2})', r0.url) if r0 else None
                    if m:
                        url = f'/best/{m.group(1)}/{pg-1}'
                    else:
                        url += f'/{pg-1}'
                else:
                    # /tags/{tag}, /lang/{lang} 分页偏移: 第N页 = .../{N-1}
                    url += f'/{pg-1}'
            r = self._get(url)
            if not r or r.status_code != 200:
                return self._empty(pg)
            vids = self._parse_video_cards(r.text)
            pages = self._parse_pages(r.text)
            # 分页偏移: 页面显示 max_page 个页码链接, 实际 pagecount = max_page + 1 (第1页无页码)
            if pages > 0 and pages >= pg:
                return {'list': vids, 'page': pg, 'pagecount': pages + 1,
                        'limit': 30, 'total': (pages + 1) * 30}
            return {'list': vids, 'page': pg, 'pagecount': max(pages, pg),
                    'limit': 30, 'total': max(pages, pg) * 30}

        # ---- 标签索引 ----
        if tid == '/tags':
            try:
                r = self._get('/tags')
                tags = []
                if r and r.status_code == 200:
                    seen = set()
                    for m in re.finditer(r'href="(/tags/[^"]+)"[^>]*>([^<]+)</a>', r.text):
                        href, name = m.group(1), m.group(2).strip()
                        if href in seen: continue
                        seen.add(href)
                        tags.append({'type_id': href, 'type_name': name})
                return {'list': tags, 'page': 1, 'pagecount': 1, 'limit': len(tags), 'total': len(tags)}
            except Exception:
                return self._empty(1)

        # ---- 标签详情页 ----
        if tid.startswith('/tags/'):
            return self.categoryContent(tid, pg)

        # ---- 频道索引 ----
        if tid == '/channels-index':
            try:
                r = self._get('/channels-index')
                chs = []
                if r and r.status_code == 200:
                    for m in re.finditer(r'href="(/[^"]+)"[^>]*>([^<]+)</a>', r.text):
                        href, name = m.group(1), m.group(2).strip()
                        if '/channels/' not in href: continue
                        chs.append({'type_id': href, 'type_name': name})
                return {'list': chs, 'page': 1, 'pagecount': 1, 'limit': len(chs), 'total': len(chs)}
            except Exception:
                return self._empty(1)

        # ---- 频道详情 ----
        if tid.startswith('/channels/'):
            url = tid if pg == 1 else f'{tid}/{pg-1}'
            r = self._get(url)
            if not r or r.status_code != 200:
                return self._empty(pg)
            vids = self._parse_video_cards(r.text)
            pages = self._parse_pages(r.text)
            return {'list': vids, 'page': pg, 'pagecount': max(pages+1, pg),
                    'limit': 30, 'total': max((pages+1)*30, 30)}

        # ---- 明星索引 ----
        if tid == '/pornstars-index':
            try:
                r = self._get('/pornstars-index')
                ps = []
                if r and r.status_code == 200:
                    for m in re.finditer(r'href="(/models/[^"]+)"[^>]*>([^<]+)</a>', r.text):
                        href, name = m.group(1), m.group(2).strip()
                        ps.append({'type_id': href, 'type_name': name})
                return {'list': ps, 'page': 1, 'pagecount': 1, 'limit': len(ps), 'total': len(ps)}
            except Exception:
                return self._empty(1)

        # ---- 明星详情 ----
        if tid.startswith('/models/'):
            url = tid if pg == 1 else f'{tid}/{pg-1}'
            r = self._get(url)
            if not r or r.status_code != 200:
                return self._empty(pg)
            vids = self._parse_video_cards(r.text)
            pages = self._parse_pages(r.text)
            return {'list': vids, 'page': pg, 'pagecount': max(pages+1, pg),
                    'limit': 30, 'total': max((pages+1)*30, 30)}

        return self._empty(pg)

    # ================ searchContent =================
    def searchContent(self, key, quick=False, pg=1):
        pg = max(int(pg) if str(pg).isdigit() else 1, 1)
        key = str(key).strip()
        if not key:
            return self._empty(pg)
        # 关键词 URL 编码后接 &p={offset}
        url = f'/?k={quote(key)}&p={pg-1}'
        r = self._get(url)
        if not r or r.status_code != 200:
            return self._empty(pg)
        vids = self._parse_video_cards(r.text)
        pages = self._parse_pages(r.text)
        return {'list': vids, 'page': pg, 'pagecount': max(pages+1, pg),
                'limit': 30, 'total': max((pages+1)*30, 30)}

    # ================ detailContent =================
    def detailContent(self, ids):
        out = []
        for vid in ids:
            try:
                url = vid if vid.startswith('http') else (self.host + vid)
                r = self._get(url)
                if not r or r.status_code != 200:
                    continue
                html = r.text

                # 标题
                title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
                title = _html.unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip() if title_m else '视频'

                # 简介
                desc_m = re.search(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', html, re.S)
                desc = _html.unescape(re.sub(r'<[^>]+>', '', desc_m.group(1))).strip() if desc_m else ''
                if not desc:
                    desc = f'{title}\n{self.host}{vid}'

                # 播放线路
                plays = []
                for key, label in [
                    ('setVideoHLS', 'HLS'),
                    ('setVideoUrlHigh', '1080P'),
                    ('setVideoUrlLow', '480P'),
                ]:
                    mm = re.search(rf"{key}\('([^']+)'", html)
                    if mm:
                        raw = mm.group(1)
                        try:
                            enc = base64.b64encode(raw.encode()).decode()
                        except Exception:
                            enc = raw
                        plays.append(f"{label}${enc}")

                vod_play_from = '$$$'.join([p.split('$')[0] for p in plays]) if plays else '在线播放'
                vod_play_url = '$$$'.join(plays) if plays else ''

                # 封面
                pic_m = re.search(r'<meta[^>]+itemprop="thumbnailUrl"[^>]+content="([^"]+)"', html)
                pic = pic_m.group(1) if pic_m else ''
                if not pic:
                    pic_m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
                    pic = pic_m.group(1) if pic_m else ''

                out.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': '',
                    'vod_director': '',
                    'vod_actor': '',
                    'vod_area': '',
                    'vod_lang': '',
                    'vod_year': '',
                    'vod_content': desc,
                    'vod_play_from': vod_play_from,
                    'vod_play_url': vod_play_url,
                    'style': {'type': 'rect', 'ratio': 1.33},
                })
            except Exception as e:
                print(f"[XVideos] detailContent error {vid}: {e}")
                continue
        return {'list': out}

    # ================ playerContent =================
    def playerContent(self, flag, id, vipFlags):
        """
        flag: 线路名
        id: 集数标识，这里约定为 base64(parse@@@@url)
        vipFlags: 可能为 None
        """
        try:
            raw = base64.b64decode(id).decode('utf-8', 'ignore')
        except Exception:
            raw = id
        parts = raw.split('@@@@', 1)
        parse = parts[0]
        url = parts[1] if len(parts) > 1 else raw
        if parse == 'parse' and url.startswith('http'):
            return {
                'parse': 0,
                'url': url,
                'header': {
                    'User-Agent': self.UA,
                    'Referer': self.host + '/',
                },
            }
        return {
            'parse': 0,
            'url': url,
            'header': {
                'User-Agent': self.UA,
                'Referer': self.host + '/',
            },
        }

    # ================ 其他契约方法 =================
    def init(self, extend=""):
        try:
            data = json.loads(extend) if extend else {}
        except Exception:
            data = {}
        self._headers = data.get('headers', {})
        return {}

    def getName(self):
        return 'Xvideos'

    def action(self, action):
        return {}

    def liveContent(self):
        return self._empty(1)

    def isVideoFormat(self, url):
        if not url:
            return False
        url = url.lower()
        return any(url.endswith(ext) for ext in
                   ('.m3u8', '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v'))

    def localProxy(self, req):
        return None

    def destroy(self):
        try:
            self.s.close()
        except Exception:
            pass
