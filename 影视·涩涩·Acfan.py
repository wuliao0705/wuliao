# -*- coding: utf-8 -*-
# AcFan移动版 ass.arvu25sx.work | 71us v7.3 | Nuxt SSR JSON-LD + decode换签播放 + 本地图代理
import sys, re, json, time, socket, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import http.server, socketserver
from urllib.parse import quote, urlparse, parse_qs
import requests
sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r
HOSTS = ['https://assss.arvu25sx.work', 'http://acpc.wamd.fun']
UA = 'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
IMG_DOM = 'https://9vc4q8rp20cf.dfgwsx.com'
PLAY_DOMS = ['https://vfs0yquy7pzo.dfgwsx.com', 'https://9vc4q8rp20cf.dfgwsx.com']
CATS = [('anime', '动漫'), ('comics', '漫画'), ('videos', '视频'), ('lifan', '里番'), ('guochan', '国产'),
         ('fanju', '番剧'), ('tongren', '同人'), ('3d', '3D'), ('yuanshen', '原神'), ('guoman', '国漫'),
         ('tiaojiao', '调教'), ('shaonv', '少女'), ('luoli', '萝莉'), ('ai', 'AI短剧'),
         ('jingxuan', '精选'), ('s1', '进站必看精选'), ('s96', '色色无限赛博AI'), ('s7', '同人色色次元'),
         ('s92', '经典里番佳作'), ('s97', '热身活络小视频'), ('s98', '必看人气创作者'), ('s90', '2026新番'),
         ('s86', 'ASMR舔耳'), ('s65', '乱伦禁忌'), ('s87', '第一人称主观视觉'), ('s28', '抖阴小视频'),
         ('s26', '粉穴少女'), ('s68', '泡面番'), ('s25', 'Cosplay少女'), ('s69', 'MMD动漫舞摇'),
         ('s67', 'Motion Anime'), ('s89', '原创有声剧')]
_API_T = {'anime': '动漫', 'videos': '视频', 'lifan': '里番', 'guochan': '国产', 'tongren': '同人', '3d': '3D',
          'yuanshen': '原神', 'fanju': '番剧', 'guoman': '国漫', 'tiaojiao': '调教', 'shaonv': '少女', 'luoli': '萝莉'}
WAMD = 'http://acpc.wamd.fun'
_IMG_SRV, _IMG_PORT, _IMG_S = None, 0, requests.Session()
_IMG_S.headers.update({'User-Agent': UA, 'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                       'Accept-Language': 'zh-CN,zh;q=0.9',
                       'Referer': 'https://assss.arvu25sx.work/mobile/anime',
                       'Sec-Fetch-Dest': 'image', 'Sec-Fetch-Mode': 'no-cors', 'Sec-Fetch-Site': 'cross-site'})
try:
    from PIL import Image as _PIL
    import io as _io
except Exception:
    _PIL, _io = None, None
_DK = b'2020-zq3-888'


def _af_dec(b):
    return bytes(v ^ _DK[i % 12] for i, v in enumerate(b[:100])) + b[100:]


def _af_mime(b):
    if b[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
        return 'image/webp'
    if b[:4] == b'\x89PNG':
        return 'image/png'
    if b[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    return ''


class _ImgH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = (parse_qs(urlparse(self.path).query).get('url') or [''])[0]
        body, code = b'', 404
        try:
            for at in range(2):
                try:
                    r = _IMG_S.get(u, timeout=8)
                    if r.status_code == 200:
                        b0 = r.content
                        body = _af_dec(b0)
                        if not _af_mime(body) and _af_mime(b0):
                            body = b0
                        code = 200
                        break
                except Exception:
                    pass
        except Exception:
            pass
        ct = _af_mime(body)
        if not ct and body and _PIL:
            try:
                im = _PIL.open(_io.BytesIO(body))
                im.load()
                if im.mode not in ('RGB', 'L'):
                    im = im.convert('RGB')
                buf = _io.BytesIO()
                im.save(buf, 'JPEG', quality=88)
                body, ct = buf.getvalue(), 'image/jpeg'
            except Exception:
                ct = ''
        if body and ct:
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass
        else:
            self.send_response(code)
            self.end_headers()

    def log_message(self, *a):
        pass


class _ImgSrv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def _ensure_img_srv():
    global _IMG_SRV, _IMG_PORT
    if _IMG_SRV is None:
        s = _ImgSrv(('127.0.0.1', 0), _ImgH)
        _IMG_PORT = s.server_address[1]
        threading.Thread(target=s.serve_forever, daemon=True).start()
        _IMG_SRV = s
    return _IMG_PORT


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.ua = UA
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': self.ua, 'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': self.base + '/'})
        self._cache = {}
        self._px = 'direct' not in str(extend or '')
        self._use_http = 'http' in str(extend or '')
        self._iport = 0
        if self._px:
            try:
                self._iport = _ensure_img_srv()
            except Exception:
                self._iport = 0

    def _img(self, u):
        u = self._clean_pic(u)
        if u and self._px and self._iport:
            return 'http://127.0.0.1:%d/proxy?url=%s' % (self._iport, quote(u, safe=''))
        return u

    def _get(self, url, timeout=(2, 5)):
        key = url
        if key in self._cache:
            return self._cache[key]
        hs = [self.base] + [x.rstrip('/') for x in HOSTS if x.rstrip('/') != self.base]
        hs = list(dict.fromkeys(hs))[:2]

        def trydom(h):
            try:
                r = requests.get(h + url, headers={'User-Agent': self.ua, 'Accept-Language': 'zh-CN,zh;q=0.9',
                                                   'Referer': h + '/'}, timeout=timeout)
                if r.status_code == 200 and len(r.text) > 500:
                    return h, r.text
            except Exception:
                pass
            return '', ''

        got = ('', '')
        if len(hs) == 1:
            got = trydom(hs[0])
        else:
            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    futs = {ex.submit(trydom, h): h for h in hs}
                    for f in as_completed(futs):
                        h, txt = f.result()
                        if txt:
                            got = (h, txt)
                            break
            except Exception:
                pass
        if got[1]:
            self.base = got[0]
            self._cache[key] = got[1]
            return got[1]
        return ''

    def _clean_pic(self, u):
        u = (u or '').replace('[object Object]', '').replace('\\/', '/').strip()
        if u.startswith('//'):
            u = 'https:' + u
        if u and re.match(r'https?://', u):
            if 'dfgwsx.com' in u:
                u = re.sub(r'^http://', 'https://', u) if not self._use_http else re.sub(r'^https://', 'http://', u)
        else:
            u = IMG_DOM + '/' + u.lstrip('/')
        return u

    def _ld_items(self, html):
        out = []
        for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                d = json.loads(j)
                for it in d.get('itemListElement', []) or []:
                    it = it.get('item', {}) if isinstance(it, dict) else {}
                    url = it.get('url', '')
                    m = re.search(r'/(?:play|comics)/(\d+)', url)
                    if not m:
                        continue
                    name = it.get('name', '')
                    pic = it.get('thumbnailUrl', '') or it.get('image', '')
                    if name:
                        prefix = '' if '/play/' in url else 'c'
                        out.append({'vod_id': prefix + m.group(1), 'vod_name': str(name).strip()[:60],
                                    'vod_pic': self._img(pic if isinstance(pic, str) else ''), 'vod_remarks': ''})
            except Exception:
                continue
        return out

    def _card_items(self, html):
        out = []
        seen = set()
        for m in re.finditer(r'href="([^"]*/play/(\d+)[^"]*)"[^>]*>', html):
            i = m.start()
            seg = html[i:i + 1200]
            alt = re.search(r'alt="([^"]+)"', seg)
            src = re.search(r'(?:data-src|src)="([^"]+)"', seg)
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            out.append({'vod_id': vid, 'vod_name': (alt.group(1).strip()[:60] if alt else ''),
                        'vod_pic': self._img(src.group(1) if src else ''), 'vod_remarks': ''})
        return out

    def _items(self, html):
        its = self._ld_items(html)
        if len(its) >= 6:
            return its
        return self._card_items(html)

    def homeContent(self, filter=False):
        r = {'class': [{'type_id': c[0], 'type_name': c[1]} for c in CATS]}
        r['list'] = self.categoryContent('anime', '1').get('list', [])
        return r

    def _api_items(self, ep, prm, maxn=40):
        out = []
        for h in HOSTS:
            try:
                r = requests.get(h.rstrip('/') + ep, params=prm,
                                 headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                if r.status_code == 200:
                    j = r.json()
                    d = j.get('data') or {}
                    items = d.get('data') if isinstance(d, dict) else []
                    if not items:
                        return out
                    dom = (((d.get('domain') or '').rstrip('/')) or IMG_DOM.rstrip('/'))
                    for it in items[:maxn]:
                        name = (it.get('title') or '').strip()
                        if not name:
                            continue
                        cs = it.get('coverImg') or []
                        pic = ''
                        if isinstance(cs, list) and cs:
                            pic = self._img(self._clean_pic(dom + '/' + str(cs[0]).lstrip('/')))
                        w = it.get('fakeWatchNum') or 0
                        out.append({'vod_id': str(it.get('videoId', '')), 'vod_name': name[:60], 'vod_pic': pic,
                                    'vod_remarks': ('%d万播放' % (w // 10000) if w >= 10000 else str(w))[:14]})
                    return out
            except Exception:
                pass
        return out

    def _station_items(self, sid, maxn=40):
        out = []
        for h in HOSTS:
            try:
                r = requests.get(h.rstrip('/') + '/api/station/public/getStationMore',
                                 params={'stationId': sid, 'page': 1, 'pageSize': maxn, 'sortType': 1},
                                 headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                if r.status_code == 200:
                    d = r.json().get('data') or {}
                    items = d.get('data') if isinstance(d, dict) else []
                    if not items:
                        return out
                    for it in items[:maxn]:
                        name = (it.get('title') or '').strip()
                        if not name:
                            continue
                        cs = it.get('coverImg') or []
                        pic = ''
                        if isinstance(cs, list) and cs:
                            pic = self._img(self._clean_pic(IMG_DOM + '/' + str(cs[0]).lstrip('/')))
                        w = it.get('fakeWatchNum') or 0
                        out.append({'vod_id': str(it.get('videoId', '')), 'vod_name': name[:60], 'vod_pic': pic,
                                    'vod_remarks': ('%d万播放' % (w // 10000) if w >= 10000 else str(w))[:14]})
                    return out
            except Exception:
                pass
        return out

    def homeVideoContent(self):
        jobs = [
            lambda: self._api_items('/api/video/public/newGetByClassify', {'page': 1, 'pageSize': 40, 'sortType': 1, 'classifyTitle': '动漫'}, 40),
            lambda: self._api_items('/api/video/public/newGetByClassify', {'page': 1, 'pageSize': 40, 'sortType': 1, 'classifyTitle': '视频'}, 40),
            lambda: self._api_items('/api/video/public/newGetByClassify', {'page': 1, 'pageSize': 40, 'sortType': 1, 'classifyTitle': '精选'}, 40),
            lambda: self._station_items(1, 40),
        ]
        out, seen = [], set()
        try:
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = [ex.submit(f) for f in jobs]
                for f in as_completed(futs):
                    for it in f.result() or []:
                        vid = it['vod_id']
                        if vid in seen:
                            continue
                        seen.add(vid)
                        out.append(it)
                        if len(out) >= 120:
                            break
        except Exception:
            pass
        if len(out) < 20:
            return self.categoryContent('anime', '1')
        return {'list': out}

    _AI_CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

    def _ai_epname(self, title):
        t = (title or '').strip()
        m = re.search(r'第([0-9一二三四五六七八九十百]+)(?:-(\d+))?\s*集|EP[\s_]*(\d+)|(\d{1,4})-(\d{1,4})\s*集', t, re.I)
        if not m:
            m2 = re.search(r'[\s_\-—]+(\d{1,3})\s*$', t)
            if m2 and not re.search(r'EP\s*\d+', t, re.I):
                return '第%s集' % m2.group(1).lstrip('0') or m2.group(1)
            return ''
        if m.group(3):
            return 'EP' + m.group(3)
        if m.group(4) and m.group(5):
            return '%s-%s集' % (m.group(4), m.group(5))
        a = m.group(1)
        if not a:
            return ''
        if m.group(2) and a.isdigit():
            return '第%s-%s集' % (a, m.group(2))
        if a.isdigit():
            return '第%s集' % a
        n = 0
        for c in a:
            n = n * 10 + self._AI_CN.get(c, 0)
        return '第%d集' % n if n else ''

    def _ai_gtitle(self, title):
        t = (title or '').strip()
        g = ''
        m = re.match(r'^(.+?)[\s_\-—]*第([0-9一二三四五六七八九十百]+)(?:-[0-9]+)?\s*集\s*$', t)
        if m:
            g = m.group(1)
        if not g:
            m2 = re.match(r'^(.+?)[\s_\-—]*EP[\s_]*\d+\s*$', t, re.I)
            if m2:
                g = m2.group(1)
        if not g:
            m3 = re.match(r'^(.+?)[\s_\-—]*(\d{1,4})-(\d{1,4})\s*集\s*$', t)
            if m3:
                g = m3.group(1)
        if not g:
            m4 = re.match(r'^(.+?)[：:]\s*第[一二三四五六七八九十百\d]+集', t)
            if m4 and len(m4.group(1)) >= 2:
                g = m4.group(1)
        if not g:
            m5 = re.search(r'^(.+?)[\s_\-—]*(\d{1,2})$', t)
            if m5 and '集' not in m5.group(1) and not re.search(r'[A-Za-z]{1,4}$|EP\s*\d+', m5.group(1), re.I):
                g = m5.group(1)
        if not g:
            m6 = re.match(r'^(.+?)[\s_\-—]*第([0-9一二三四五六七八九十百]+)集([\s\-—_:：].{0,14})$', t)
            if m6:
                rest = m6.group(3) or ''
                if not re.search(r'第[0-9一二三四五六七八九十百]+集|EP\s*\d+', rest, re.I):
                    g = m6.group(1)
        return (g or '').strip().strip(' 《》「」『』【】：:，,。')

    def _ai_fetch(self, params):
        for h in HOSTS:
            try:
                r = requests.get(h.rstrip('/') + '/api/station/public/getStationMore', params=params,
                                 headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                if r.status_code == 200:
                    j = r.json()
                    d = j.get('data') or {}
                    if isinstance(d, dict) and d.get('data'):
                        return d
            except Exception:
                pass
        return {}

    def _ai_groups(self):
        c = getattr(self, '_ai_gc', None)
        if c and time.time() - c[0] < 300:
            return c[1]
        d0 = self._ai_fetch({'stationId': 99, 'page': 1, 'pageSize': 100, 'sortType': 1})
        if not d0:
            return []
        rows = list(d0.get('data') or [])
        total = d0.get('total') or 0
        per = len(rows)

        def one(p):
            d = self._ai_fetch({'stationId': 99, 'page': p, 'pageSize': 100, 'sortType': 1})
            return d.get('data') if d else []

        if per and total > per:
            pages = -(-total // per)
            try:
                with ThreadPoolExecutor(max_workers=6) as ex:
                    futs = {ex.submit(one, p): p for p in range(2, min(pages, 20) + 1)}
                    for f in as_completed(futs):
                        rows += f.result() or []
            except Exception:
                pass
        if total:
            rows = rows[:total]
        gmap, single, order, rmap = {}, {}, [], {}
        for it in rows:
            vid = str(it.get('videoId') or '')
            title = (it.get('title') or '').strip()
            if not vid or not title:
                continue
            rmap[vid] = it
            cs = it.get('coverImg') or []
            cov = str(cs[0]).lstrip('/') if isinstance(cs, list) and cs else ''
            ep, gn = self._ai_epname(title), self._ai_gtitle(title)
            if ep and gn:
                kg = re.sub(r'[\s_\-—《》「」『』【】]+', '', gn)
                gmap.setdefault(kg, []).append({'vid': vid, 'ep': ep, 'title': title, 'cover': cov})
            else:
                single[vid] = it
        groups = []
        for gn, eps in gmap.items():
            seen, ue = set(), []
            for e in eps:
                if e['vid'] in seen:
                    continue
                seen.add(e['vid'])
                ue.append(e)
            if len(ue) > 1:
                ue.sort(key=lambda x: (re.sub(r'\D', '', x['ep']).zfill(4) if re.sub(r'\D', '', x['ep']) else 'z'))
                gmap[gn] = ue
                groups.append({'name': gn[:50], 'eps': ue, 'max_vid': max(int(e['vid']) for e in ue)})
            else:
                single.setdefault(ue[0]['vid'], rmap.get(ue[0]['vid']))
        if not groups and not single:
            return []
        out = [('g', g) for g in groups]
        out += [('s', vid) for vid in sorted(single, reverse=True)]
        out.sort(key=lambda x: -(x[1]['max_vid'] if x[0] == 'g' else int(x[1])))
        self._ai_gc = (time.time(), (out, gmap, single))
        return out, gmap, single

    def _ai_page(self, pn):
        all3 = self._ai_groups()
        if not all3:
            return {'list': [], 'page': pn, 'pagecount': 1}
        cards, gmap, single = all3
        tot = len(cards)
        sl = cards[(pn - 1) * 30: pn * 30]
        out = []
        for kind, v in sl:
            if kind == 'g':
                g = v
                ep0 = g['eps'][0]
                out.append({'vod_id': 'z' + str(ep0['vid']), 'vod_name': g['name'],
                            'vod_pic': self._img(self._clean_pic(IMG_DOM + '/' + self._ai_pic(g['eps']))),
                            'vod_remarks': '全%d集' % len(g['eps'])})
            else:
                it = single[v]
                cs = it.get('coverImg') or []
                pic = ''
                if isinstance(cs, list) and cs:
                    pic = self._img(self._clean_pic(IMG_DOM + '/' + str(cs[0]).lstrip('/')))
                w = it.get('fakeWatchNum') or 0
                out.append({'vod_id': str(v), 'vod_name': (it.get('title') or '').strip()[:60], 'vod_pic': pic,
                            'vod_remarks': ('%d万播放' % (w // 10000) if w >= 10000 else str(w))[:14]})
        return {'list': out, 'page': pn, 'pagecount': min(max(1, -(-tot // 30)), 200)}

    def _ai_pic(self, eps):
        for e in eps:
            c = e.get('cover')
            if c:
                return c
        for e in reversed(eps):
            try:
                h = self._get('/mobile/play/' + str(e['vid']))
                og = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', h or '')
                if og:
                    return og.group(1).replace('\\/', '').replace('https://vfs0yquy7pzo.dfgwsx.com/', '').replace('https://9vc4q8rp20cf.dfgwsx.com/', '')
            except Exception:
                pass
        return ''

    def _ai_host(self):
        h = getattr(self, '_ai_h', '')
        if h:
            return h
        for x in HOSTS:
            try:
                r = requests.get(x.rstrip('/') + '/api/station/public/stationsPc', params={'page': 1, 'pageSize': 1},
                                 headers={'User-Agent': UA}, timeout=(3, 5))
                if r.status_code == 200:
                    self._ai_h = x.rstrip('/')
                    return self._ai_h
            except Exception:
                pass
        self._ai_h = HOSTS[0].rstrip('/')
        return self._ai_h

    def _ai_epurl(self, e):
        vid = str(e['vid'])
        h = self._ai_host()
        nm, u = '', ''
        try:
            r = requests.get(h + '/mobile/play/' + vid,
                             headers={'User-Agent': UA, 'Referer': h + '/'}, timeout=(3, 30))
            if r.status_code == 200 and len(r.text) > 500:
                rels, fulls, mv = self._detail_data(r.text)
                rel, k = mv.get('v', '') or (rels[0] if rels else ''), mv.get('k', '')
                if rel and k:
                    nm = e['ep'] or e['title'][:20]
                    u = h + '/api/m3u8/public/decode/authPath?path=' + quote(rel, safe='') + \
                        '&auth_key=' + quote(k, safe='') + '&vid=' + vid
                elif mv.get('h'):
                    nm = e['ep'] or e['title'][:20]
                    u = mv['h'] if mv['h'].startswith('http') else PLAY_DOMS[0] + '/' + mv['h'].lstrip('/')
                elif rels:
                    nm = e['ep'] or e['title'][:20]
                    u = PLAY_DOMS[0] + '/' + rels[0].lstrip('/')
                elif fulls:
                    nm = e['ep'] or e['title'][:20]
                    u = fulls[0]
                if u:
                    self._ai_h = h
        except Exception:
            pass
        return nm, u

    def _ai_detail(self, gid):
        c = getattr(self, '_ai_dc', {}).get(gid)
        if c and time.time() - c[0] < 120:
            return c[1]
        all3 = self._ai_groups()
        if not all3:
            return {'list': []}
        cards, gmap, single = all3
        g = None
        for gn, eps in gmap.items():
            if any(str(e['vid']) == gid for e in eps):
                g = {'name': gn, 'eps': eps}
                break
        if not g:
            return {'list': []}
        got = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            for e, (nm, u) in zip(g['eps'], ex.map(self._ai_epurl, g['eps'])):
                if nm and u:
                    got[str(e['vid'])] = (nm, u)
        miss = [e for e in g['eps'] if str(e['vid']) not in got]
        if miss:
            def _fb(e):
                try:
                    dv = self.detailContent([str(e['vid'])])
                    fu = ((dv.get('list') or [{}])[0].get('vod_play_url') or '')
                    if '$' in fu:
                        u = fu.split('#')[0].split('$', 1)[1]
                        if u:
                            return str(e['vid']), (e['ep'] or e['title'][:20], u)
                except Exception:
                    pass
                return str(e['vid']), ('', '')
            with ThreadPoolExecutor(max_workers=5) as ex2:
                for vid, pr in ex2.map(_fb, miss):
                    if pr[1]:
                        got[vid] = pr
        pairs = [(got[str(e['vid'])][0], got[str(e['vid'])][1]) for e in g['eps'] if str(e['vid']) in got]
        if not pairs:
            return {'list': []}
        names = [n for n, _ in pairs]
        urls = [u for _, u in pairs]
        picp = self._ai_pic(g['eps'])
        vod = {'vod_id': 'z' + gid, 'vod_name': g['name'][:80],
               'vod_pic': self._img(self._clean_pic(IMG_DOM + '/' + picp)) if picp else '',
               'vod_remarks': '全%d集' % len(names),
               'vod_year': '', 'vod_area': '', 'vod_type': '', 'vod_content': ''}
        vod['vod_play_from'] = '正片'
        vod['vod_play_url'] = '#'.join('%s$%s' % (n, u) for n, u in zip(names, urls))
        res = {'list': [vod]}
        if not getattr(self, '_ai_dc', None):
            self._ai_dc = {}
        self._ai_dc[gid] = (time.time(), res)
        return res

    def categoryContent(self, tid, pg='1', filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        slug = str(tid or 'anime').strip().strip('/')
        m99 = re.match(r'^s(\d+)$', slug)
        if slug == 'ai':
            return self._ai_page(pn)
        if slug in ('jingxuan',) or m99:
            if slug == 'jingxuan':
                ep = '/api/video/public/newGetByClassify'
                prm = {'page': pn, 'pageSize': 30, 'sortType': 0, 'classifyTitle': '精选'}
            else:
                ep = '/api/station/public/getStationMore'
                prm = {'stationId': int(m99.group(1)), 'page': pn, 'pageSize': 30, 'sortType': 1}
            for h in HOSTS:
                try:
                    r = requests.get(h.rstrip('/') + ep, params=prm,
                                     headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                    if r.status_code == 200:
                        d = r.json().get('data') or {}
                        items = d.get('data') if isinstance(d, dict) else []
                        if items:
                            dom = (((d.get('domain') or '').rstrip('/')) or IMG_DOM.rstrip('/')) if slug == 'jingxuan' else IMG_DOM.rstrip('/')
                            out = []
                            for it in items[:60]:
                                name = (it.get('title') or '').strip()
                                if not name:
                                    continue
                                cs = it.get('coverImg') or []
                                pic = ''
                                if isinstance(cs, list) and cs:
                                    pic = self._img(self._clean_pic(dom + '/' + str(cs[0]).lstrip('/')))
                                w = it.get('fakeWatchNum') or 0
                                out.append({'vod_id': str(it.get('videoId', '')), 'vod_name': name[:60],
                                            'vod_pic': pic,
                                            'vod_remarks': ('%d万播放' % (w // 10000) if w >= 10000 else str(w))[:14]})
                            tot = d.get('total') or 0
                            return {'list': out, 'page': pn, 'pagecount': min(max(1, -(-tot // 30)), 500)}
                except Exception:
                    pass
            return {'list': [], 'page': pn, 'pagecount': 1}
        title = _API_T.get(slug)
        if title:
            ep = '/api/video/public/newGetByClassify'
            prm = {'page': pn, 'pageSize': 30, 'sortType': 0, 'classifyTitle': title}
            for h in HOSTS:
                try:
                    r = requests.get(h.rstrip('/') + ep, params=prm,
                                     headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                    if r.status_code == 200:
                        j = r.json()
                        d = j.get('data') or {}
                        items = d.get('data') if isinstance(d, dict) else []
                        if items:
                            dom = (((d.get('domain') or '').rstrip('/')) or IMG_DOM.rstrip('/'))
                            out = []
                            for it in items[:60]:
                                name = (it.get('title') or '').strip()
                                if not name:
                                    continue
                                cs = it.get('coverImg') or []
                                pic = ''
                                if isinstance(cs, list) and cs:
                                    pic = self._img(self._clean_pic(dom + '/' + str(cs[0]).lstrip('/')))
                                w = it.get('fakeWatchNum') or 0
                                out.append({'vod_id': str(it.get('videoId', '')), 'vod_name': name[:60], 'vod_pic': pic,
                                            'vod_remarks': ('%d万播放' % (w // 10000) if w >= 10000 else str(w))[:14]})
                            tot = d.get('total') or d.get('count') or 0
                            return {'list': out, 'page': pn, 'pagecount': min(max(1, -(-tot // 30)), 500)}
                except Exception:
                    pass
        if slug not in ('anime', 'videos', 'comics'):
            slug = 'anime'
        h = self._get('/mobile/comics/list/%d' % pn if slug == 'comics' else '/mobile/%s/page/%d' % (slug, pn),
                       (4, 35) if slug == 'comics' else (2, 5))
        if not h:
            return {'list': [], 'page': pn, 'pagecount': 1}
        if slug == 'comics':
            nxt = re.search(r'href="[^"]*/mobile/comics/list/%d"' % (pn + 1), h)
        else:
            nxt = re.search(r'href="[^"]*/mobile/%s/page/%d"' % (re.escape(slug), pn + 1), h)
        pc = pn + 1 if nxt else pn
        return {'list': self._items(h), 'page': pn, 'pagecount': min(pc, 30)}

    def _detail_data(self, html):
        m = re.search(r'id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        rels, fulls, main = [], [], {}
        if m:
            try:
                d = json.loads(m.group(1))
                n = len(d)

                def ref(v):
                    if isinstance(v, int) and 0 <= v < n:
                        t = d[v]
                        if isinstance(t, str):
                            return t
                        if isinstance(t, list) and t and isinstance(t[0], str):
                            return t[0]
                    if isinstance(v, str):
                        return v
                    return ''

                def walk(x):
                    if isinstance(x, dict):
                        if 'videoUrl' in x and 'authKey' in x and not main:
                            main['v'] = ref(x['videoUrl'])
                            main['k'] = ref(x.get('authKey'))
                            main['h'] = ref(x.get('hevcVideoUrl'))
                        for v in x.values():
                            walk(v)
                    elif isinstance(x, list):
                        for v in x:
                            walk(v)
                    elif isinstance(x, str) and '.m3u8' in x:
                        (fulls if x.startswith('http') else rels).append(x)
                walk(d)
            except Exception:
                pass
        return list(dict.fromkeys(rels)), list(dict.fromkeys(fulls)), main

    def _dec_url(self, rel, ak, hevc=False):
        return '%s/api/m3u8/public/decode/authPath?path=%s&auth_key=%s%s' % (
            self.base, quote(rel, safe=''), quote(ak, safe=''), '&hevc=1' if hevc else '')

    def _alt_dom(self):
        for x in HOSTS:
            d = x.rstrip('/')
            if d != self.base:
                return d
        return self.base

    def detailContent(self, ids):
        vid0 = str(ids[0]) if isinstance(ids, list) and ids else str(ids)
        if vid0.startswith('z'):
            return self._ai_detail(vid0[1:])
        is_c = vid0.startswith('c')
        vid = re.sub(r'\D', '', vid0)
        h = self._get('/mobile/comics/' + vid if is_c else '/mobile/play/' + vid, (4, 35) if is_c else (4, 18))
        if not h:
            return {'list': []}
        t = re.search(r'<title>([^<]*)</title>', h)
        name = t.group(1).strip() if t else ''
        name = re.split(r'\s*[-|]\s*(?:在线观看|AcFan|漫画详情)', name)[0].strip().replace('&amp;', '&').replace('&nbsp;', ' ')
        og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]*>', h)
        pic = ''
        if og:
            pc = re.search(r'content=["\']([^"\']+)', og.group(0))
            pic = pc.group(1).replace('\\/', '/') if pc else ''
        desc = ''
        if is_c:
            for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
                try:
                    d = json.loads(j)
                    if d.get('@type') == 'Book':
                        if not pic:
                            im = d.get('image')
                            pic = im if isinstance(im, str) else ''
                        g = d.get('genre') or ''
                        de = d.get('description') or ''
                        desc = '类型：%s\n%s' % (g, de) if g else str(de)
                        break
                except Exception:
                    continue
            vod = {'vod_id': vid0, 'vod_name': name[:80], 'vod_pic': self._img(pic), 'vod_remarks': '',
                   'vod_year': '', 'vod_area': '', 'vod_type': '漫画', 'vod_content': desc[:500]}
            return {'list': [vod]}
        rels, fulls, mv = self._detail_data(h)
        lines, urls = [], []
        mv_v, mv_h, mv_k = mv.get('v', '') or '', mv.get('h', '') or '', mv.get('k', '') or ''
        rel = mv_v or (rels[0] if rels else '')
        vq = '&vid=' + vid
        if rel and mv_k:
            lines.append('正片')
            urls.append(self._dec_url(rel, mv_k, False) + vq)
            lines.append('HEVC')
            urls.append(self._dec_url(rel, mv_k, True) + vq)
            lines.append('备用')
            ad = self._alt_dom()
            urls.append(ad + '/api/m3u8/public/decode/authPath?path=' + quote(rel, safe='') +
                        '&auth_key=' + quote(mv_k, safe='') + vq)
        elif mv_h:
            lines.append('正片')
            urls.append(mv_h if mv_h.startswith('http') else PLAY_DOMS[0] + '/' + mv_h.lstrip('/'))
        elif rels:
            lines.append('正片')
            urls.append(PLAY_DOMS[0] + '/' + rels[0].lstrip('/'))
        if not urls and fulls:
            lines, urls = ['正片'], [fulls[0]]
        vod = {'vod_id': vid, 'vod_name': name[:80], 'vod_pic': self._img(pic), 'vod_remarks': '', 'vod_year': '',
               'vod_area': '', 'vod_type': '', 'vod_content': ''}
        if urls:
            vod['vod_play_from'] = '$$$'.join(lines)
            vod['vod_play_url'] = '#'.join('%s$%s' % (n, u) for n, u in zip(lines, urls))
        return {'list': [vod]}

    def searchContent(self, key, quick=False, pg='1'):
        k = str(key or '').strip()
        if not k:
            return {'list': []}
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        for h in HOSTS:
            try:
                r = requests.get(h.rstrip('/') + '/api/search/public/keyWord',
                                 params={'searchWord': k, 'page': pn, 'pageSize': 20},
                                 headers={'User-Agent': self.ua, 'Referer': h.rstrip('/') + '/'}, timeout=(2, 5))
                if r.status_code == 200:
                    j = r.json()
                    d = j.get('data') or {}
                    v = d.get('videoList') or []
                    if v:
                        dom = (((d.get('domain') or '').rstrip('/')) or IMG_DOM.rstrip('/')) + '/'
                        out = []
                        for i in v[:40]:
                            cs = i.get('coverImg') or []
                            out.append({'vod_id': str(i.get('videoId', '')), 'vod_name': (i.get('title') or '').strip()[:60],
                                        'vod_pic': self._img(dom + cs[0].lstrip('/')) if cs else '', 'vod_remarks': ''})
                        return {'list': out, 'page': pn, 'pagecount': 1}
            except Exception:
                pass
        h = self._get('/mobile/search?keywords=' + quote(k) + ('&page=%d' % pn if pn > 1 else ''))
        if not h:
            return {'list': []}
        its = self._items(h)
        return {'list': its[:40], 'page': pn, 'pagecount': 1}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id or '')
        if url.startswith('http://') or url.startswith('https://'):
            return {'parse': 0, 'url': url, 'header': {'User-Agent': self.ua, 'Referer': self.base + '/'}}
        return {'parse': 0, 'url': url, 'header': {'User-Agent': self.ua, 'Referer': self.base + '/'}}
