# -*- coding: utf-8 -*-
"""
夜社 (yeshe.tv) TVBox Python 爬虫 — 七大分类完整版
================================================================
分类体系：
  精选 (recommend)  : 跨分类聚合优质内容（首页推荐）
  视频 (2)          : AI短剧(13) / 擦边短剧(36) / 国产视频(11) / 日本AV(12) / 欧美无码(14) / 韩国BJ(35)
  动漫 (1)          : 同人作品(7) / 动画卡通(8) / 3D动漫(10) / 中文动漫(9) / 里番(32) / 泡面番(33)
  有声 (3)          : 有声小说(15) / 淫词艳曲(16) / 激情骚麦(17)
  漫画 (4)          : 韩国H漫(18) / 日本H漫(19) / 3D漫画(31)
  写真 (5)          : 秀人系列(20) / 网红COS(22) / 机构套图(21) / 内购私拍(23) / AI绘图(34) / 各国套图(24)
  小说 (6)          : 都市生活(25) / 学生校园(26) / 家庭乱伦(27) / 玄幻武侠(28) / 系统穿越(29) / 同人改编(30)

内容处理策略：
  - 视频/动漫/有声 → m3u8 直链 (parse=0)
  - 漫画/写真     → pics:// 协议 (图集浏览)
  - 小说           → novel:// 协议 (正文阅读)
================================================================
"""

import json
import re
import base64
from urllib import request, parse, error

SITE_NAME = '夜社'
BASE = 'https://xn--5h7vtfsm-wg0mze004clz4n.baitasi.org'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# ============================================================
# 六大分类体系（精选单独处理）
# ============================================================
TOP_CATS = [
    # (父分类名, 父ID, [(子ID, 子名称), ...])
    ('视频', 2, [(13, 'AI短剧'), (36, '擦边短剧'), (11, '国产视频'),
                 (12, '日本AV'), (14, '欧美无码'), (35, '韩国BJ')]),
    ('动漫', 1, [(7, '同人作品'), (8, '动画卡通'), (10, '3D动漫'),
                 (9, '中文动漫'), (32, '里番'), (33, '泡面番')]),
    ('有声', 3, [(15, '有声小说'), (16, '淫词艳曲'), (17, '激情骚麦')]),
    ('漫画', 4, [(18, '韩国H漫'), (19, '日本H漫'), (31, '3D漫画')]),
    ('写真', 5, [(20, '秀人系列'), (22, '网红COS'), (21, '机构套图'),
                 (23, '内购私拍'), (34, 'AI绘图'), (24, '各国套图')]),
    ('小说', 6, [(25, '都市生活'), (26, '学生校园'), (27, '家庭乱伦'),
                 (28, '玄幻武侠'), (29, '系统穿越'), (30, '同人改编')]),
]

# 内容类型分类
TYPE_VIDEO = {2, 13, 36, 11, 12, 14, 35, 1, 7, 8, 10, 9, 32, 33, 3, 15, 16, 17}
TYPE_COMIC = {4, 18, 19, 31}
TYPE_IMAGE = {5, 20, 22, 21, 23, 34, 24}
TYPE_NOVEL = {6, 25, 26, 27, 28, 29, 30}


# ============================================================
# HTTP 工具
# ============================================================
def _http_get(url, timeout=20):
    req = request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': BASE + '/',
    })
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except error.HTTPError as e:
        return e.read().decode('utf-8', errors='replace') if e.fp else ''
    except Exception:
        return ''


def decode_page(raw):
    """解码 base64 包装的 HTML"""
    if not raw:
        return ''
    if raw.lstrip()[:10].lower().startswith('<!doctype') or raw.lstrip()[:10].lower().startswith('<html'):
        return raw
    m = re.search(r'var\s+a\s*=\s*"([^"]+)"', raw)
    if not m:
        return raw
    try:
        b = base64.b64decode(m.group(1))
        d = b.decode('utf-8', errors='replace')
        d = d.replace('\\/', '/').replace('\\"', '"').replace('\\\\', '\\')
        if d.startswith('"') and d.endswith('"'):
            d = d[1:-1]
        d = re.sub(r'\\u([0-9A-Fa-f]{4})',
                   lambda m: chr(int(m.group(1), 16)), d)
        return d
    except Exception:
        return raw


def fetch(url, timeout=20):
    return decode_page(_http_get(url, timeout))


def abs_url(path):
    if not path:
        return path
    if path.startswith('http'):
        return path
    if path.startswith('//'):
        return 'https:' + path
    if path.startswith('/'):
        return BASE + path
    return BASE + '/' + path


def find_meta(html, name):
    m = re.search(r'<meta[^>]+name=["\']%s["\'][^>]+content=["\']([^"\']*)["\']' % name, html, re.I)
    if m:
        return m.group(1)
    m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']%s["\']' % name, html, re.I)
    return m.group(1) if m else ''


def _clean(s):
    if not s:
        return ''
    return re.sub(r'\s+', ' ', s).strip()


# ============================================================
# 列表解析
# ============================================================
def parse_cards(html):
    """解析列表卡片"""
    items = []
    for m in re.finditer(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']*)["\'][^>]*class=["\'][^"\']*module-poster-item[^"\']*["\'][^>]*>',
            html, re.I):
        start = m.end()
        nxt = re.search(r'<a\b[^>]*class=["\'][^"\']*module-poster-item[^"\']*["\'][^>]*>', html[start:], re.I)
        end = start + (nxt.start() if nxt else min(3000, len(html) - start))
        block = html[start:end]
        href = m.group(1)
        title = m.group(2)
        pic = ''
        pm = re.search(r'<img[^>]+(?:src|data-original|data-src)=["\']([^"\']+)["\']', block, re.I)
        if pm:
            pic = pm.group(1)
        tm = re.search(r'<div class="type">([^<]*)</div>', block)
        vod_class = tm.group(1).strip() if tm else ''
        epm = re.search(r'<(?:div|span) class="time">([^<]*)</(?:div|span)>', block)
        remark = epm.group(1).strip() if epm else ''
        tm_span = re.search(r'<div class="module-poster-time-info">(.*?)</div>', block, re.S)
        pub_time = ''
        play_count = ''
        if tm_span:
            spans = re.findall(r'<span>(.*?)</span>', tm_span.group(1), re.S)
            if len(spans) >= 2:
                pub_time = _clean(re.sub(r'<[^>]+>', '', spans[0]))
                play_count = _clean(re.sub(r'<[^>]+>', '', spans[1]))
        items.append({
            'href': href,
            'title': title,
            'pic': pic,
            'type': vod_class,
            'remark': remark,
            'pub_time': pub_time,
            'play_count': play_count,
        })
    return items


def extract_page_total(html):
    """提取总数和总页数"""
    total, pages = 0, 0
    m = re.search(r'共\s*(\d+)\s*条数据', html)
    if m:
        total = int(m.group(1))
    m = re.search(r'当前\s*(\d+)\s*/\s*(\d+)\s*页', html)
    if m:
        pages = int(m.group(2))
    if not pages:
        m = re.search(r'/filter/\d+/page/(\d+)\.html[^>]*title=["\']?尾页', html)
        if m:
            pages = int(m.group(1))
    return total, pages


# ============================================================
# 图片提取（漫画/写真）
# ============================================================
def extract_images_from_url(url):
    """Collect gallery/comic images, ignoring site chrome like the logo."""
    html = fetch(url)
    if not html:
        return []
    # The reader wraps pages in `.module-player-cartoon-list`; use it when
    # present so navigation icons never leak into the image list.
    block = re.search(r'<div class="module-player-cartoon-list">(.*?)</div>\s*</div>\s*</div>', html, re.S)
    scope = block.group(1) if block else html
    imgs = []
    for pattern in (r'<img[^>]+data-original=["\']([^"\']+)["\']',
                    r'<img[^>]+src=["\']([^"\']+)["\']'):
        for m in re.finditer(pattern, scope, re.I):
            src = m.group(1).strip()
            low = src.lower()
            if not src or low.startswith('data:'):
                continue
            if any(x in low for x in ('logo', 'icon', 'avatar', 'banner', '/ad', 'loading')):
                continue
            imgs.append(abs_url(src))
        if imgs:
            break
    seen = set()
    unique = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


# ============================================================
# 小说正文提取
# ============================================================
def extract_novel_content(html):
    """从小说章节页提取正文"""
    patterns = [
        r'<div[^>]*id="nr"[^>]*>(.*?)</div>',
        r'<div[^>]*id="content"[^>]*>(.*?)</div>',
        r'<div[^>]*class="chapter-content"[^>]*>(.*?)</div>',
        r'<div[^>]*class="novel-content"[^>]*>(.*?)</div>',
        r'<div[^>]*class="read-content"[^>]*>(.*?)</div>',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.S)
        if m:
            content = re.sub(r'<[^>]+>', '', m.group(1))
            content = re.sub(r'\s+', ' ', content).strip()
            if len(content) > 20:
                return content
    # 备用：提取所有 <p>
    ps = re.findall(r'<p[^>]*>(.*?)</p>', html, re.S)
    if ps:
        content = ' '.join(re.sub(r'<[^>]+>', '', p).strip() for p in ps if p.strip())
        if len(content) > 20:
            return content
    return ''


# ============================================================
# 章节提取（视频/动漫/有声）
# ============================================================
def extract_play_chapters(html, vid=None, sid=None):
    """Extract every episode/chapter that belongs to THIS title only.

    The play page also renders a sidebar of recommended titles whose links use
    the same `/play/<vid>/<sid>/<ep>.html` shape, so filtering by vid/sid is
    what keeps foreign episodes out of the list.
    """
    chapters = []
    seen_href = set()
    generic = ('上一章', '下一章', '返回', '目录', '首页', '下一话', '上一话',
               '下一集', '上一集', '立即浏览', '播放')

    # 1. 从 <select> 提取
    for sel in re.findall(r'<select[^>]*class="[^"]*chapter[^"]*"[^>]*>.*?</select>', html, re.S | re.I):
        for opt in re.finditer(r'<option[^>]*value=["\']([^"\']+)["\'][^>]*>([^<]+)</option>', sel):
            href = opt.group(1).strip()
            name = _clean(opt.group(2))
            if href and name and '/play/' in href and href not in seen_href:
                sm = re.match(r'/play/(\d+)/(\d+)/(\d+)\.html', href)
                if sm and (vid is None or sm.group(1) == str(vid)) and (sid is None or sm.group(2) == str(sid)):
                    seen_href.add(href)
                    chapters.append({
                        'href': href,
                        'vid': sm.group(1),
                        'sid': sm.group(2),
                        'ep': int(sm.group(3)),
                        'name': name,
                    })

    # 2. 从所有 <a> 提取 /play/ 链接
    for m in re.finditer(r'<a\b[^>]*href=["\'](/play/[^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href = m.group(1).strip()
        name = _clean(re.sub(r'<[^>]+>', '', m.group(2)))
        if not name or any(kw in name for kw in generic):
            continue
        if href in seen_href:
            continue
        sm = re.match(r'/play/(\d+)/(\d+)/(\d+)\.html', href)
        if sm and (vid is None or sm.group(1) == str(vid)) and (sid is None or sm.group(2) == str(sid)):
            seen_href.add(href)
            chapters.append({
                'href': href,
                'vid': sm.group(1),
                'sid': sm.group(2),
                'ep': int(sm.group(3)),
                'name': name,
            })

    # 3. 用集号补全缺失/占位名称
    for ch in chapters:
        if not ch['name'] or ch['name'].isdigit():
            ch['name'] = '第%d集' % ch['ep']

    chapters.sort(key=lambda x: x['ep'])
    return chapters


# ============================================================
# 主爬虫类
# ============================================================
try:
    from base.spider import Spider as _TVBoxSpider

    class _SpiderBase(_TVBoxSpider):
        pass
except Exception:
    class _SpiderBase:
        def __init__(self, extend=''):
            self.extend = extend


class Spider(_SpiderBase):
    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except Exception:
            pass
        self.extend = {}

    def init(self, extend=""):
        cfg = {}
        if extend:
            if isinstance(extend, dict):
                cfg = extend
            else:
                try:
                    cfg = json.loads(extend) if extend else {}
                except Exception:
                    cfg = {}
        if isinstance(cfg, dict):
            self.extend = cfg
            custom_base = cfg.get('base') or cfg.get('host')
            if custom_base:
                global BASE
                BASE = str(custom_base).rstrip('/')

    @property
    def req(self):
        class _R:
            @staticmethod
            def get(url, **kw):
                return _http_get(url, timeout=kw.get('timeout', 20))

            @staticmethod
            def post(url, **kw):
                data = (kw.get('data') or kw.get('json'))
                if isinstance(data, str):
                    body = data.encode('utf-8')
                elif data is None:
                    body = b''
                else:
                    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                headers = {
                    'User-Agent': UA,
                    'Content-Type': 'application/json',
                    'Referer': BASE + '/',
                }
                headers.update(kw.get('headers') or {})
                req = request.Request(url, data=body, headers=headers, method='POST')
                try:
                    with request.urlopen(req, timeout=20) as r:
                        return r.read().decode('utf-8', errors='replace')
                except error.HTTPError as e:
                    return e.read().decode('utf-8', errors='replace') if e.fp else ''
                except Exception:
                    return ''

        return _R()

    # ============================================================
    # 分类（精选 + 六大分类）
    # ============================================================
    def homeContent(self, filter=None):
        """
        返回分类列表：
          精选 (recommend) → 跨分类聚合
          视频 (2)
          动漫 (1)
          有声 (3)
          漫画 (4)
          写真 (5)
          小说 (6)
        """
        # 父分类列表：精选使用特殊 ID "recommend"
        parent_cats = [
            ('精选', 'recommend'),
            ('视频', 2),
            ('动漫', 1),
            ('有声', 3),
            ('漫画', 4),
            ('写真', 5),
            ('小说', 6),
        ]

        classes = []
        filters = {}

        for parent_name, parent_id in parent_cats:
            classes.append({'type_id': str(parent_id), 'type_name': parent_name})

            # 精选不设子分类筛选（它本身是聚合）
            if parent_id == 'recommend':
                continue

            # 查找子分类
            subs = []
            for pname, pid, sublist in TOP_CATS:
                if pid == parent_id:
                    subs = sublist
                    break

            filter_values = [{'n': '全部', 'v': ''}]
            for sub_id, sub_name in subs:
                filter_values.append({'n': sub_name, 'v': str(sub_id)})

            filters[str(parent_id)] = [
                {'key': 'sub', 'name': '分类', 'value': filter_values}
            ]

        return {'class': classes, 'filters': filters}

    # ============================================================
    # 列表（支持精选聚合 + 子分类筛选）
    # ============================================================
    def categoryContent(self, tid='', pg='1', filter=None, extend=None, **kwargs):
        tid = str(tid).strip()

        # ---- 精选：跨分类聚合 ----
        if tid == 'recommend':
            return self._recommend_content(page=1)

        # ---- 子分类筛选 ----
        sub_tid = ''
        if extend and isinstance(extend, dict):
            sub_tid = extend.get('sub', '')
        if not sub_tid and filter and isinstance(filter, dict):
            sub_tid = filter.get('sub', '')

        actual_tid = sub_tid if sub_tid else tid

        try:
            page = int(pg)
        except Exception:
            page = 1

        # 判断是否为小说分类
        is_novel = actual_tid.isdigit() and int(actual_tid) in TYPE_NOVEL
        prefix = 'nfilter' if is_novel else 'filter'

        # 构建 URL
        if page <= 1:
            url = f'{BASE}/{prefix}/{actual_tid}.html'
        else:
            url = f'{BASE}/{prefix}/{actual_tid}/page/{page}.html'

        html = fetch(url)
        cards = parse_cards(html)
        total, pages = extract_page_total(html)

        vod_list = []
        seen = set()
        for c in cards:
            href = c['href']
            if '/novel/' in href:
                m = re.search(r'/novel/(\d+)\.html', href)
                if not m:
                    continue
                vid = 'n' + m.group(1)
            elif '/play/' in href:
                m = re.search(r'/play/(\d+)/(\d+)/\d+\.html', href)
                if not m:
                    continue
                vid = m.group(1) + '|' + m.group(2)
            elif '/detail/' in href:
                m = re.search(r'/detail/(\d+)\.html', href)
                if not m:
                    continue
                vid = m.group(1) + '|1'
            else:
                continue
            if vid in seen:
                continue
            seen.add(vid)
            is_novel_vid = vid.startswith('n')
            vod_list.append({
                'vod_id': vid + '|' + str(actual_tid),
                'vod_name': c['title'],
                'vod_pic': abs_url(c['pic']),
                'vod_remarks': c['remark'],
                'vod_year': '',
                'vod_score': '',
                'vod_area': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_class': c['type'],
                'vod_from': SITE_NAME,
                'vod_play_from': 'yeshevideo' if not is_novel_vid else 'yeshenovel',
                'vod_play_url': '',
                'vod_content': '',
                'vod_info': {'发布时间': c['pub_time'], '播放量': c['play_count']},
            })
        return {
            'total': total,
            'page': page,
            'pagecount': pages,
            'limit': 20,
            'list': vod_list,
        }

    # ============================================================
    # 精选内容聚合（从各分类取最新内容）
    # ============================================================
    def _recommend_content(self, page=1):
        """精选：从各分类中聚合内容"""
        vod_list = []
        seen = set()

        # 从所有分类中取最新内容（每个分类取前8条）
        for parent_name, parent_id, subs in TOP_CATS:
            try:
                url = f'{BASE}/filter/{parent_id}.html'
                html = fetch(url)
                if not html:
                    continue
                cards = parse_cards(html)
                count = 0
                for c in cards[:12]:  # 每个分类取前12条
                    href = c['href']
                    if '/novel/' in href:
                        m = re.search(r'/novel/(\d+)\.html', href)
                        if not m:
                            continue
                        vid = 'n' + m.group(1)
                    elif '/play/' in href:
                        m = re.search(r'/play/(\d+)/(\d+)/\d+\.html', href)
                        if not m:
                            continue
                        vid = m.group(1) + '|' + m.group(2)
                    elif '/detail/' in href:
                        m = re.search(r'/detail/(\d+)\.html', href)
                        if not m:
                            continue
                        vid = m.group(1) + '|1'
                    else:
                        continue
                    if vid in seen:
                        continue
                    seen.add(vid)
                    is_novel_vid = vid.startswith('n')
                    vod_list.append({
                        'vod_id': vid + '|' + str(parent_id),
                        'vod_name': c['title'],
                        'vod_pic': abs_url(c['pic']),
                        'vod_remarks': f'[{parent_name}] {c["remark"]}',
                        'vod_year': '',
                        'vod_score': '',
                        'vod_area': '',
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_class': c['type'],
                        'vod_from': SITE_NAME,
                        'vod_play_from': 'yeshevideo' if not is_novel_vid else 'yeshenovel',
                        'vod_play_url': '',
                        'vod_content': '',
                    })
                    count += 1
                    if count >= 12:
                        break
            except Exception:
                continue

        return {
            'total': len(vod_list),
            'page': 1,
            'pagecount': 1,
            'limit': 20,
            'list': vod_list,
        }

    # ============================================================
    # 搜索
    # ============================================================
    def searchContent(self, key='', quick=False, pg=1):
        key = str(key).strip()
        if not key:
            return {'total': 0, 'page': 1, 'pagecount': 0, 'limit': 20, 'list': []}
        try:
            page = int(pg)
        except Exception:
            page = 1
        q = parse.quote(key)
        url = f'{BASE}/vod/search/wd/{q}.html' if page <= 1 else f'{BASE}/vod/search/wd/{q}/page/{page}.html'
        html = fetch(url)
        cards = parse_cards(html)
        total, pages = extract_page_total(html)
        if not total:
            total = len(cards)
        vod_list = []
        seen = set()
        for c in cards:
            href = c['href']
            if '/novel/' in href:
                m = re.search(r'/novel/(\d+)\.html', href)
                if not m:
                    continue
                vid = 'n' + m.group(1)
            elif '/play/' in href:
                m = re.search(r'/play/(\d+)/(\d+)/\d+\.html', href)
                if not m:
                    continue
                vid = m.group(1) + '|' + m.group(2)
            else:
                continue
            if vid in seen:
                continue
            seen.add(vid)
            vod_list.append({
                'vod_id': vid,
                'vod_name': c['title'],
                'vod_pic': abs_url(c['pic']),
                'vod_remarks': c['remark'],
                'vod_class': c['type'],
                'vod_play_from': 'yeshevideo' if not vid.startswith('n') else 'yeshenovel',
            })
        return {
            'total': total,
            'page': page,
            'pagecount': pages or 1,
            'limit': 20,
            'list': vod_list,
        }

    # ============================================================
    # 详情
    # ============================================================
    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ''
        vid = str(ids).strip()

        # 小说
        if vid.startswith('n'):
            return self._detail_novel(vid[1:])

        parts = vid.split('|')
        if len(parts) < 2:
            return {'list': []}
        v_id, sid = parts[0], parts[1]
        category_id = parts[2] if len(parts) > 2 else ''

        # 获取播放页
        play_url = f'{BASE}/play/{v_id}/{sid}/1.html'
        html = fetch(play_url)
        if not html:
            return {'list': []}

        # 提取 player_aaaa
        pa = self._grab_player_aaaa(html) or {}
        vod_data = pa.get('vod_data') or {}
        is_video = bool(pa and pa.get('url'))

        # 基本信息
        title = vod_data.get('vod_name') or ''
        if not title:
            tm = re.search(r'<title>([^<]*)</title>', html)
            if tm:
                title = re.sub(r'\s*-.*$', '', tm.group(1)).strip()
        pic = vod_data.get('vod_pic') or ''
        if not pic:
            pm = re.search(r'vod_pic["\']?\s*[:=]\s*["\']([^"\']+)', html)
            pic = pm.group(1) if pm else ''
        vod_class = vod_data.get('vod_class') or ''
        desc = find_meta(html, 'description')
        if not desc:
            m = re.search(r'<div class="blurb">([^<]+)</div>', html)
            desc = m.group(1) if m else ''

        # ---------- 确定内容类型 ----------
        tid_int = int(category_id) if category_id.isdigit() else 0
        if tid_int in TYPE_COMIC:
            content_type = 'comic'
        elif tid_int in TYPE_IMAGE:
            content_type = 'image'
        elif tid_int in TYPE_NOVEL:
            content_type = 'novel'
        elif tid_int in TYPE_VIDEO:
            content_type = 'video'
        else:
            content_type = 'video' if is_video else 'image'

        # ---------- 漫画/写真：优先分话，其次整本图集 ----------
        if content_type in ('comic', 'image'):
            chapters = extract_play_chapters(html, v_id, sid)
            if chapters:
                eps = '#'.join(ch['name'] + '$' + ch['href'] for ch in chapters)
                return {
                    'list': [{
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': abs_url(pic),
                        'vod_class': vod_class,
                        'vod_remarks': f'{len(chapters)}话',
                        'vod_year': '',
                        'vod_score': '',
                        'vod_area': '',
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_play_from': 'yesheimage',
                        'vod_play_url': eps,
                        'vod_content': desc,
                        'vod_from': SITE_NAME,
                    }]
                }
            imgs = extract_images_from_url(play_url)
            if not imgs:
                imgs = extract_images_from_url(f'{BASE}/detail/{v_id}.html')
            if imgs:
                return {
                    'list': [{
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': abs_url(pic),
                        'vod_class': vod_class,
                        'vod_remarks': f'{len(imgs)}张',
                        'vod_year': '',
                        'vod_score': '',
                        'vod_area': '',
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_play_from': 'yesheimage',
                        'vod_play_url': '全集$pics://' + '&&'.join(imgs),
                        'vod_content': desc,
                        'vod_from': SITE_NAME,
                    }]
                }

        # ---------- 视频/动漫/有声：提取章节 ----------
        chapters = extract_play_chapters(html, v_id, sid)
        if not chapters:
            detail_url = f'{BASE}/detail/{v_id}.html'
            detail_html = fetch(detail_url)
            if detail_html:
                more = extract_play_chapters(detail_html, v_id, sid)
                seen = set()
                all_ch = chapters + more
                unique = []
                for ch in all_ch:
                    if ch['href'] not in seen:
                        seen.add(ch['href'])
                        unique.append(ch)
                chapters = unique
                chapters.sort(key=lambda x: x['ep'])

        # 构建播放链接
        if chapters:
            eps = []
            for ch in chapters:
                eps.append(ch['name'] + '$' + ch['href'])
            play_url_str = '#'.join(eps)
        else:
            play_url_str = '第1集$/play/%s/%s/1.html' % (v_id, sid)

        tags = []
        tag_block = re.search(r'<div class="module-info-tags">(.*?)</div></div></div>', html, re.S)
        if tag_block:
            for tm in re.finditer(r'<a[^>]+href="[^"]*"[^>]*>([^<]+)</a>', tag_block.group(1)):
                tags.append(tm.group(1).strip())
        vod_class = vod_class or ', '.join(tags)

        return {
            'list': [{
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': abs_url(pic),
                'vod_class': vod_class,
                'vod_remarks': f'全{len(chapters) or 1}集',
                'vod_year': '',
                'vod_score': '',
                'vod_area': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_play_from': 'yeshevideo',
                'vod_play_url': play_url_str,
                'vod_content': desc,
                'vod_from': SITE_NAME,
            }]
        }

    # ============================================================
    # 小说详情
    # ============================================================
    def _detail_novel(self, n_id):
        url = f'{BASE}/novel/{n_id}.html'
        html = fetch(url)
        if not html:
            return {'list': []}

        title = ''
        h1 = re.search(r'<div class="dinfo">\s*<h1>([^<]+)</h1>', html)
        if h1:
            title = h1.group(1).strip()
        if not title:
            h1 = re.search(r'<h1>([^<]+)</h1>', html)
            if h1:
                title = h1.group(1).strip()
        if not title:
            tm = re.search(r'<title>([^<]*)</title>', html)
            if tm:
                title = re.sub(r'\s*-\s*成人.*$', '', tm.group(1)).strip()

        pic = ''
        pm = re.search(r'<div class="img">\s*<img[^>]+data-original=["\']([^"\']+)["\']', html)
        if pm:
            pic = pm.group(1)
        if not pic:
            for im in re.finditer(r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']', html):
                u = im.group(1)
                if 'novs3.' in u or '/pic/' in u:
                    pic = u
                    break

        desc = find_meta(html, 'description')
        if not desc:
            m = re.search(r'<div class="blurb">([^<]+)</div>', html)
            desc = m.group(1) if m else ''

        tag_block = re.search(r'<div class="module-info-tags">(.*?)</div></div></div>', html, re.S)
        tags = []
        if tag_block:
            for tm in re.finditer(r'<a[^>]+href="[^"]*"[^>]*>([^<]+)</a>', tag_block.group(1)):
                tags.append(tm.group(1).strip())
        vod_class = ', '.join(tags)

        chapters = []
        seen_href = set()
        for m in re.finditer(r'<a\b[^>]*href=["\'](/nchpter/\d+/\d+\.html)["\'][^>]*>', html, re.I):
            href = m.group(1)
            if href in seen_href:
                continue
            name_match = re.search(r'>([^<]+)</a>', html[m.start():m.end() + 100])
            name = name_match.group(1).strip() if name_match else href.split('/')[-1].replace('.html', '')
            if name and not any(kw in name for kw in ['上一章', '下一章', '返回', '目录', '首页']):
                chapters.append({'href': href, 'name': name})
                seen_href.add(href)

        eps = []
        for ch in chapters:
            eps.append(ch['name'] + '$' + ch['href'])
        play_url = '#'.join(eps)

        return {
            'list': [{
                'vod_id': 'n' + n_id,
                'vod_name': title,
                'vod_pic': abs_url(pic),
                'vod_class': vod_class,
                'vod_remarks': f'全{len(chapters)}章',
                'vod_play_from': 'yeshenovel',
                'vod_play_url': play_url,
                'vod_content': desc,
                'vod_from': SITE_NAME,
            }]
        }

    # ============================================================
    # 播放
    # ============================================================
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id) if id else ''
        href = raw.split('$')[-1].strip()
        headers = {'User-Agent': UA, 'Referer': BASE + '/'}

        if not href:
            return {'parse': 0, 'url': '', 'header': headers}

        full_href = BASE + href if href.startswith('/') else href

        # 小说章节
        if href.startswith('/nchpter/'):
            html = fetch(full_href)
            if html:
                content = extract_novel_content(html)
                if content and len(content) > 20:
                    result = {'title': '章节', 'content': content}
                    return {
                        'parse': 0,
                        'url': f'novel://{json.dumps(result, ensure_ascii=False)}',
                        'header': headers
                    }
            return {'parse': 1, 'url': full_href, 'header': headers}

        # 图片协议直接返回
        if href.startswith('pics://'):
            return {'parse': 0, 'url': href, 'header': headers}

        # 视频/有声
        html = fetch(full_href)
        if not html:
            return {'parse': 1, 'url': full_href, 'header': headers}

        pa = self._grab_player_aaaa(html)
        url = (pa or {}).get('url') or ''
        if url and not url.startswith('http'):
            url = abs_url(url)

        headers['Referer'] = full_href
        if not url:
            # 尝试提取图片（漫画/写真兜底）
            imgs = extract_images_from_url(full_href)
            if imgs:
                return {
                    'parse': 0,
                    'url': 'pics://' + '&&'.join(imgs),
                    'header': headers
                }
            return {'parse': 1, 'url': full_href, 'header': headers}

        return {'parse': 0, 'url': url, 'header': headers}

    # ============================================================
    # 辅助
    # ============================================================
    def _grab_player_aaaa(self, html):
        m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\});?\s*</script>', html, re.S)
        if not m:
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', html, re.S)
        if not m:
            return {}
        raw = m.group(1)
        try:
            return json.loads(raw)
        except Exception:
            obj = {}
            for key in ['url', 'url_next', 'from', 'id', 'sid', 'nid', 'note']:
                km = re.search(r'"%s"\s*:\s*"([^"]*)"' % key, raw)
                if km:
                    obj[key] = km.group(1)
            dm = re.search(r'"vod_data"\s*:\s*(\{.*?\})', raw)
            if dm:
                try:
                    obj['vod_data'] = json.loads(dm.group(1))
                except Exception:
                    vd = {}
                    for k in ['vod_name', 'vod_pic', 'vod_class', 'vod_actor', 'vod_director', 'vod_blurb']:
                        km = re.search(r'"%s"\s*:\s*"([^"]*)"' % k, dm.group(1))
                        if km:
                            vd[k] = km.group(1)
                    obj['vod_data'] = vd
            return obj

    # ============================================================
    # 兼容方法
    # ============================================================
    def localProxy(self, param):
        return ''

    def isVideoFormat(self, url):
        return url and any(url.endswith(ext) for ext in ('.m3u8', '.mp4', '.flv', '.mkv', '.ts'))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return []

    def getVodDetail(self, vodId, **kwargs):
        return self.detailContent(vodId)

    def getAll(self, **kwargs):
        return self.homeContent()

    def getSearch(self, keys, page=1, **kwargs):
        return self.searchContent(keys, False, page)

    def getCategory(self, tuid, page=1, **kwargs):
        return self.categoryContent(str(tuid), str(page))

    def getPlayer(self, vodId, **kwargs):
        return self.playerContent(None, vodId)

    def homeVideoContent(self):
        return self._recommend_content(page=1)


# ============================================================
# CLI 测试
# ============================================================
if __name__ == '__main__':
    import sys
    sp = Spider()
    if len(sys.argv) < 2:
        print('用法: python yeshe_spider.py <action> [args]')
        print('  home              - 显示分类')
        print('  cat <tid> [page]  - 分类列表 (tid=recommend 为精选)')
        print('  search <kw> [page]- 搜索')
        print('  detail <vid>      - 详情')
        print('  player <url>      - 播放')
        sys.exit(0)
    act = sys.argv[1]
    if act == 'home':
        print(json.dumps(sp.homeContent(), ensure_ascii=False, indent=2))
    elif act == 'cat':
        tid = sys.argv[2] if len(sys.argv) > 2 else '1'
        pg = sys.argv[3] if len(sys.argv) > 3 else '1'
        r = sp.categoryContent(tid, pg)
        print(f'total={r["total"]} pagecount={r["pagecount"]} count={len(r["list"])}')
        for v in r['list'][:5]:
            print(f'  {v["vod_id"]} {v["vod_name"]} {v["vod_remarks"]}')
    elif act == 'search':
        kw = sys.argv[2] if len(sys.argv) > 2 else ''
        pg = sys.argv[3] if len(sys.argv) > 3 else '1'
        r = sp.searchContent(kw, False, pg)
        print(f'total={r["total"]} count={len(r["list"])}')
        for v in r['list'][:5]:
            print(f'  {v["vod_id"]} {v["vod_name"]}')
    elif act == 'detail':
        vid = sys.argv[2] if len(sys.argv) > 2 else ''
        r = sp.detailContent(vid)
        if r.get('list'):
            v = r['list'][0]
            print(f'标题: {v["vod_name"]}')
            print(f'ID: {v["vod_id"]}')
            print(f'封面: {v["vod_pic"]}')
            print(f'线路: {v["vod_play_from"]}')
            play_url = v.get('vod_play_url', '')
            if play_url:
                if play_url.startswith('pics://'):
                    print(f'图片数: {len(play_url.split("&&"))}')
                else:
                    print(f'集数: {len(play_url.split("#"))}')
                print(f'播放链接: {play_url[:200]}')
    elif act == 'player':
        url = sys.argv[2] if len(sys.argv) > 2 else ''
        r = sp.playerContent(None, url)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print('未知命令')
