#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
努努影院 (nnyy.la) TVBox Python Spider

站点结构:
  - Cloudflare 防护（需浏览器 UA + Referer）
  - 列表页: /vodshow/{typeid}-----------.html (P1) /vodshow/{typeid}--------{page}---.html (Pn)
  - 播放页: /vodplay/{vod_id}-1-1.html
  - 播放加密: RC4(key=i_love_you) → HLS m3u8
  - 播放器: XGPlayer (ByteDance) + HLS
  - 搜索: /vodsearch/-------------.html?wd=keyword

分类: 1=电影 2=电视剧 3=综艺 4=动漫 6=纪录片
"""

import re, json, html as html_mod, sys, time
from urllib.parse import quote

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    from urllib.request import Request, urlopen
    from urllib.error import URLError


HOST = 'https://nnyy.la'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
RC4_KEY = 'i_love_you'
_PER_PAGE = 24  # 每页大约 24 条

CATEGORIES = [
    {'type_id': '1', 'type_name': '🎬 电影'},
    {'type_id': '2', 'type_name': '📺 电视剧'},
    {'type_id': '3', 'type_name': '🎤 综艺'},
    {'type_id': '4', 'type_name': '🎨 动漫'},
    {'type_id': '6', 'type_name': '📡 纪录片'},
]


class Spider(object):

    def __init__(self):
        self._session = None
        if _HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({'User-Agent': UA, 'Referer': HOST})
            self._session.timeout = 20

    def getName(self):
        return '努努影院'

    def getDependence(self):
        return []

    def init(self, extend=''):
        pass

    def isVideoFormat(self, url):
        return bool(url and ('.m3u8' in url or '.mp4' in url))

    def manualVideoCheck(self):
        return True

    def destroy(self):
        if self._session:
            self._session.close()

    def localProxy(self, param):
        return [404, 'text/plain', b'']

    def action(self, action):
        pass

    # ─── 内部工具方法 ───

    def _request(self, path, timeout=20):
        """GET 请求，返回 HTML 文本。"""
        url = HOST + path if path.startswith('/') else path
        try:
            if _HAS_REQUESTS:
                r = self._session.get(url, timeout=timeout)
                if r.status_code != 200:
                    return ''
                return r.text
            else:
                req = Request(url, headers={'User-Agent': UA, 'Referer': HOST, 'Accept': 'text/html'})
                resp = urlopen(req, timeout=timeout)
                if resp.status != 200:
                    return ''
                return resp.read().decode('utf-8', errors='replace')
        except Exception:
            return ''

    @staticmethod
    def _rc4_decrypt(hex_str):
        """RC4 解密：hex 字符串 → UTF-8 明文。"""
        encrypted = bytes.fromhex(hex_str)
        key_bytes = RC4_KEY.encode('utf-8')
        key_len = len(key_bytes)
        # KSA
        s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + s[i] + key_bytes[i % key_len]) % 256
            s[i], s[j] = s[j], s[i]
        # PRGA
        i = j = 0
        result = bytearray()
        for k in range(len(encrypted)):
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            result.append(encrypted[k] ^ s[(s[i] + s[j]) % 256])
        return result.decode('utf-8')

    @staticmethod
    def _page(pg):
        """安全页码归一。"""
        try:
            p = int(pg) if pg else 1
            return p if p > 0 else 1
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _clean_text(text):
        """去除 HTML 标签并转义。"""
        return html_mod.unescape(re.sub(r'<[^>]+>', '', text)).strip()

    def _category_path(self, tid, pg):
        """构造分类列表页 URL。"""
        if pg <= 1:
            return f'/vodshow/{tid}-----------.html'
        return f'/vodshow/{tid}--------{pg}---.html'

    def _parse_cards(self, html):
        """从列表/搜索页提取视频卡片。"""
        items = []
        lis = re.findall(r'<li>(.*?)</li>', html, re.DOTALL)
        for li in lis:
            link_m = re.search(r'href="(/vodplay/(\d+)-\d+-\d+\.html)"', li)
            if not link_m:
                continue
            vod_id = link_m.group(2)

            # 标题
            title_m = re.search(r'<h2><a[^>]*>(.*?)</a>', li)
            title = self._clean_text(title_m.group(1)) if title_m else '未知'

            # 封面图 (data-src)
            img_m = re.search(r'data-src="([^"]+)"', li)
            img = img_m.group(1).strip() if img_m else ''

            # 备注
            note_m = re.search(r'class="note"><span>(.*?)</span>', li)
            note = self._clean_text(note_m.group(1)) if note_m else ''

            # 评分
            rate_m = re.search(r'class="rate">(.*?)</span>', li)
            rate = self._clean_text(rate_m.group(1)) if rate_m else ''

            # 星级
            star_m = re.search(r'class="star star(\d+)"', li)
            star = star_m.group(1) if star_m else ''

            # 年份 + 地区
            countries = re.findall(r'class="orange">(.*?)</span>', li)
            year = self._clean_text(countries[0]) if len(countries) > 0 else ''
            area = self._clean_text(countries[1]) if len(countries) > 1 else ''

            # 拼接 remark
            remark_parts = []
            if note:
                remark_parts.append(note)
            if rate:
                remark_parts.append(f'评分{rate}')
            remark = ' | '.join(remark_parts)

            items.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': img,
                'vod_remarks': remark,
                'vod_year': year,
                'vod_area': area,
                'vod_score': f'{rate}分' if rate else '',
                '_star': star,
            })
        return items

    def _parse_pagecount(self, html, tid):
        """从分页链接提取总页数。
        分页 URL 格式: /vodshow/{tid}--------{page}---.html
        页码位于 type ID 后第 9 个字符（即 8 个破折号之后）。
        """
        pages = re.findall(rf'/vodshow/{re.escape(tid)}--------(\d+)-+\.html', html)
        if pages:
            return max(int(p) for p in pages)
        return 1

    def _parse_detail(self, html):
        """解析播放页：提取 urlDictionary + 线路 + 集数 + 元数据。"""
        result = {
            'vod_name': '未知',
            'vod_pic': '',
            'vod_content': '',
            'vod_year': '',
            'vod_area': '',
            'vod_director': '',
            'vod_actor': '',
            'vod_play_from': '',
            'vod_play_url': '',
        }

        # ── 标题 ──
        title_m = re.search(r'<title>(.*?)</title>', html)
        if title_m:
            raw = title_m.group(1)
            for suffix in [
                ' - 在线观看 - 电影 - 努努影院',
                ' - 在线观看 - 电视剧 - 努努影院',
                ' - 在线观看 - 综艺 - 努努影院',
                ' - 在线观看 - 动漫 - 努努影院',
            ]:
                raw = raw.replace(suffix, '')
            result['vod_name'] = html_mod.unescape(raw).strip()

        # ── 封面图 ──
        img_m = re.search(r'data-src="([^"]+)"', html)
        if img_m:
            result['vod_pic'] = img_m.group(1).strip()

        # ── 简介 (JSON-LD description) ──
        desc_m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if desc_m:
            result['vod_content'] = html_mod.unescape(desc_m.group(1))

        # ── 年份 ──
        year_m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
        if year_m:
            result['vod_year'] = year_m.group(1)

        # ── 地区 ──
        area_m = re.search(r'"@type":\s*"VideoObject"[^}]*"regionOfOrigin"[^:]*:\s*"([^"]+)"', html)
        if not area_m:
            area_m = re.search(r'"@type":\s*"Country"[^}]*"name"\s*:\s*"([^"]+)"', html)
        if area_m:
            result['vod_area'] = area_m.group(1)

        # ── 导演 ──
        director_m = re.search(r'"director"[^[]*\[([^\]]*)\]', html, re.DOTALL)
        if director_m:
            names = re.findall(r'"name"\s*:\s*"([^"]+)"', director_m.group(1))
            if names:
                result['vod_director'] = ' / '.join(html_mod.unescape(n) for n in names)

        # ── 演员 ──
        actor_m = re.search(r'"actor"[^[]*\[([^\]]*)\]', html, re.DOTALL)
        if actor_m:
            names = re.findall(r'"name"\s*:\s*"([^"]+)"', actor_m.group(1))
            if names:
                result['vod_actor'] = ' / '.join(html_mod.unescape(n) for n in names)

        # ── urlDictionary（RC4 加密的播放地址）──
        url_dict = {}
        for m in re.finditer(r'urlDictionary\[(\d+)\]\[(\d+)\]\s*=\s*"([^"]+)"', html):
            sid, nid, enc = m.groups()
            url_dict[(int(sid), int(nid))] = enc

        # 解密
        decrypted = {}
        for (sid, nid), enc in url_dict.items():
            try:
                decrypted[(sid, nid)] = self._rc4_decrypt(enc)
            except Exception:
                decrypted[(sid, nid)] = ''

        # ── 线路名 ──
        servers = {}
        for m in re.finditer(r'dt data-sid="(\d+)"[^>]*>(.*?)</dt>', html):
            sid, raw = m.groups()
            name = re.sub(r'\(\d+\)\s*', '', self._clean_text(raw))
            servers[int(sid)] = name

        # ── 集数列表 ──
        playlist = {}
        for m in re.finditer(r'<li data-sid="(\d+)" data-nid="(\d+)"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL):
            sid, nid, text = m.groups()
            name = self._clean_text(text)
            playlist[(int(sid), int(nid))] = name

        # ── 按 sid 顺序构建播放数据 ──
        from_parts = []
        url_parts = []
        for sid in sorted(servers.keys()):
            from_parts.append(servers.get(sid, f'线路{sid}'))
            eps = []
            for nid in sorted(nid for (s, nid) in playlist if s == sid):
                name = playlist.get((sid, nid), f'第{nid}集')
                url = decrypted.get((sid, nid), '')
                if url:
                    eps.append(f'{name}${url}')
            url_parts.append('#'.join(eps))

        result['vod_play_from'] = '$$$'.join(from_parts)
        result['vod_play_url'] = '$$$'.join(url_parts)
        return result

    # ─── TVBox 标准接口 ───

    def homeContent(self, filter=False):
        """首页导航分类。"""
        return {'class': CATEGORIES, 'filters': {}}

    def homeVideoContent(self):
        """首页推荐。"""
        html = self._request('/')
        items = self._parse_cards(html)
        total = len(items)
        return {
            'list': items,
            'page': 1,
            'pagecount': max(1, (total + _PER_PAGE - 1) // _PER_PAGE),
            'limit': _PER_PAGE,
            'total': total,
        }

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        """分类列表。"""
        pg = self._page(pg)
        path = self._category_path(tid, pg)
        html = self._request(path)
        if not html:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': _PER_PAGE, 'total': 0}
        items = self._parse_cards(html)
        pagecount = self._parse_pagecount(html, tid)
        total = max(len(items), pagecount * _PER_PAGE) if items else 0
        return {
            'list': items,
            'page': pg,
            'pagecount': pagecount,
            'limit': _PER_PAGE,
            'total': total,
        }

    def detailContent(self, ids):
        """详情 + 播放列表。"""
        if not ids:
            return {'list': []}
        vod_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        path = f'/vodplay/{vod_id}-1-1.html'
        html = self._request(path)
        if not html:
            return {'list': []}
        vod = self._parse_detail(html)
        vod['vod_id'] = vod_id
        return {'list': [vod]}

    def searchContent(self, key, quick=False, pg='1'):
        """搜索。"""
        pg = self._page(pg)
        kw = quote(key.strip(), encoding='utf-8')
        path = f'/vodsearch/-------------.html?wd={kw}'
        html = self._request(path)
        if not html:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': _PER_PAGE, 'total': 0}
        items = self._parse_cards(html)
        total = len(items)
        return {
            'list': items,
            'page': pg,
            'pagecount': 1,
            'limit': _PER_PAGE,
            'total': total,
        }

    def playerContent(self, flag, id, vipFlags=None):
        """返回播放地址（id 已是解密后的 m3u8 直链）。"""
        headers = {
            'User-Agent': UA,
            'Referer': HOST,
        }
        return {'parse': 0, 'url': id, 'header': headers}


# ═══ 冒烟测试 ═══
if __name__ == '__main__':
    sp = Spider()

    print('=== 1. 首页分类 ===')
    hc = sp.homeContent()
    print(f'  分类数: {len(hc["class"])}')
    for c in hc['class']:
        print(f'    {c["type_name"]} (id={c["type_id"]})')

    print('\n=== 2. 首页推荐 ===')
    hvc = sp.homeVideoContent()
    print(f'  视频数: {len(hvc["list"])}')
    if hvc['list']:
        v = hvc['list'][0]
        print(f'  首项: {v["vod_name"]} | {v["vod_remarks"]}')

    print('\n=== 3. 电影列表 (P1) ===')
    cc = sp.categoryContent('1', 1)
    print(f'  视频数: {len(cc["list"])} | 总页: {cc["pagecount"]}')
    if cc['list']:
        v = cc['list'][0]
        print(f'  首项: {v["vod_name"]} | {v["vod_remarks"]}')
        print(f'  图片: {v["vod_pic"][:60]}...')

    print('\n=== 4. 详情页 ===')
    if cc['list']:
        vid = cc['list'][0]['vod_id']
        dc = sp.detailContent(vid)
        if dc['list']:
            v = dc['list'][0]
            print(f'  标题: {v["vod_name"]}')
            print(f'  简介: {v["vod_content"][:80]}...')
            print(f'  线路: {v["vod_play_from"]}')
            play_urls = v['vod_play_url'].split('$$$')
            for i, (frm, urls) in enumerate(zip(v['vod_play_from'].split('$$$'), play_urls)):
                eps = urls.split('#') if urls else []
                print(f'    {frm}: {len(eps)} 集')
                if eps:
                    print(f'      首集: {eps[0][:80]}...')

    print('\n=== 5. 搜索 ===')
    sc = sp.searchContent('星球大战', pg='1')
    print(f'  结果数: {len(sc["list"])}')
    for v in sc['list'][:3]:
        print(f'    {v["vod_name"]} | {v["vod_remarks"]}')

    sp.destroy()
    print('\n✅ 冒烟测试完成')
