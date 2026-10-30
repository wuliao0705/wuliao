#!/usr/bin/python
# -*- coding: utf-8 -*-
import re, json, requests, urllib3, base64
from urllib.parse import quote, unquote
urllib3.disable_warnings()
import sys; sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 多域名兜底，优先使用 ext 传入的地址
    # 注意：xptta9.com 目前返回空壳页面，放到后面
    HOSTS = [
        'https://also.yvzwdvpxs.com',
        'https://xpxp618.com',
        'https://xptta9.com',
    ]
    UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'

    # AES 解密参数（从站点 JS 提取）
    IMG_KEY = b'f5d965df75336270'
    IMG_IV = b'97b60394abc2fbe1'

    CATS = [
        {'type_id': 'theme/detail/64/favorite', 'type_name': '网黄精选'},
        {'type_id': 'theme/detail/65/update', 'type_name': '国产探花'},
        {'type_id': 'theme/detail/68/update', 'type_name': '女性向'},
        {'type_id': 'theme/detail/73/update', 'type_name': '91原创'},
        {'type_id': 'theme/detail/74/update', 'type_name': '猎奇重口'},
        {'type_id': 'theme/detail/79/update', 'type_name': '糖心VIog'},
        {'type_id': 'popular/all', 'type_name': '日本AV'},
        {'type_id': 'actress/latest', 'type_name': '女优-最近更新'},
        {'type_id': 'actress/hot', 'type_name': '女优-热度优先'},
        {'type_id': 'actress/count', 'type_name': '女优-最多影片'},
        {'type_id': 'tags/3128/hot', 'type_name': '标签-自拍'},
        {'type_id': 'tags/9766/hot', 'type_name': '标签-网黄'},
        {'type_id': 'tags/9612/hot', 'type_name': '标签-国产'},
        {'type_id': 'tags/9776/hot', 'type_name': '标签-探花'},
        {'type_id': 'tags/9613/hot', 'type_name': '标签-欧美'},
        {'type_id': 'tags/3931/hot', 'type_name': '标签-韩国'},
        {'type_id': 'tags/673/hot', 'type_name': '标签-乱伦'},
        {'type_id': 'tags/196/hot', 'type_name': '标签-强奸'},
        {'type_id': 'tags/217/hot', 'type_name': '标签-NTR'},
        {'type_id': 'tags/9758/hot', 'type_name': '标签-绿帽'},
        {'type_id': 'tags/170/hot', 'type_name': '标签-巨乳'},
        {'type_id': 'tags/169/hot', 'type_name': '标签-熟女'},
        {'type_id': 'tags/231/hot', 'type_name': '标签-人妻'},
        {'type_id': 'tags/163/hot', 'type_name': '标签-萝莉'},
        {'type_id': 'tags/142/hot', 'type_name': '标签-黑丝'},
        {'type_id': 'tags/7155/hot', 'type_name': '标签-情趣内衣'},
        {'type_id': 'tags/7133/hot', 'type_name': '标签-JK'},
        {'type_id': 'tags/9768/hot', 'type_name': '标签-自慰'},
        {'type_id': 'tags/176/hot', 'type_name': '标签-潮吹'},
        {'type_id': 'tags/3401/hot', 'type_name': '标签-内射'},
        {'type_id': 'tags/3639/hot', 'type_name': '标签-浴室'},
        {'type_id': 'tags/3181/hot', 'type_name': '标签-野外'},
        {'type_id': 'tags/9541/hot', 'type_name': '标签-中文字幕'},
        {'type_id': 'tags/5187/hot', 'type_name': '标签-无码'},
        {'type_id': 'tags/9540/hot', 'type_name': '标签-4K'},
    ]

    def getName(self): return "xpxp618"

    def init(self, extend=""):
        self.extend = extend or ""
        self.host = None
        
        # 多域名自动探测：优先用 ext 传入的，否则逐个尝试
        candidates = []
        if self.extend and self.extend.startswith('http'):
            candidates.append(self.extend.rstrip('/'))
        candidates.extend(self.HOSTS)
        
        for h in candidates:
            try:
                r = requests.get(h + '/', headers={'User-Agent': self.UA}, timeout=8, verify=False, allow_redirects=True)
                # 关键修复：不仅检查状态码和长度，还要确认页面包含实际视频数据
                if r.status_code == 200 and len(r.text) > 5000 and '/videos/' in r.text and ('z-image-loader' in r.text or 'data-src' in r.text):
                    # 使用最终跳转后的 URL 作为 host（避免子域名漂移问题）
                    self.host = r.url.rstrip('/')
                    break
            except:
                continue
        
        # 兜底：如果都没检测到有效内容，用第一个候选
        if not self.host:
            self.host = candidates[0] if candidates else self.HOSTS[0]
            
        self.headers = {
            'User-Agent': self.UA,
            'Referer': self.host + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.headers)

    def _fetch(self, url, retries=2):
        for i in range(retries + 1):
            try:
                r = self.session.get(url, timeout=15, allow_redirects=True)
                r.encoding = 'utf-8'
                if r.status_code == 200 and len(r.text) > 100:
                    return r.text
            except:
                pass
        return ''

    def _fix(self, u):
        if not u: return ''
        if u.startswith('//'): return 'https:' + u
        if u.startswith('/'): return self.host + u
        if u.startswith('http'): return u
        return self.host + '/' + u

    def _extract_text(self, html):
        if not html: return ''
        return re.sub(r'<[^>]+>', '', html).strip()

    def _clean_title(self, title):
        if not title: return ''
        for s in [' - XP天堂', ' - ', '高清', '在线', '中文字幕', '无码']:
            title = title.replace(s, '')
        return title.strip()

    def _extract_zimg(self, block):
        """提取图片真实 URL，兼容 z-image-loader-url / data-src / x-image-loader-url 等"""
        if not block: return ''
        patterns = [
            r'z-image-loader-url\s*=\s*["\']([^"\']*)["\']',
            r'x-image-loader-url\s*=\s*["\']([^"\']*)["\']',
            r'data-src\s*=\s*["\']([^"\']*)["\']',
            r'data-original\s*=\s*["\']([^"\']*)["\']',
            r'data-bg\s*=\s*["\']([^"\']*)["\']',
            r'data-lazy-src\s*=\s*["\']([^"\']*)["\']',
            r'src\s*=\s*["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif))["\']',
        ]
        for p in patterns:
            m = re.search(p, block, re.DOTALL | re.IGNORECASE)
            if m:
                pic = m.group(1).strip()
                if pic.startswith('`') and pic.endswith('`'):
                    pic = pic[1:-1]
                # 过滤占位图
                if pic and not pic.startswith('blob:') and 'holder' not in pic and 'placeholder' not in pic:
                    return pic
        return ''

    def _is_ad_block(self, block):
        """判断是否为广告卡片：链接不是 /videos/ 开头即为广告"""
        if not block: return True
        a_match = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', block)
        if a_match:
            href = a_match.group(1)
            if not href.startswith('/videos/'):
                return True
        return False

    def _unpad_pkcs7(self, data):
        if not data: return data
        pad_len = data[-1]
        if 1 <= pad_len <= 16 and all(b == pad_len for b in data[-pad_len:]):
            return data[:-pad_len]
        return data

    def _decrypt_img_data(self, data):
        """AES 解密图片数据"""
        if not data: return None
        try:
            from Crypto.Cipher import AES
            if len(data) % 16 != 0:
                pad_len = 16 - (len(data) % 16)
                data = data + bytes([0]) * pad_len
            cipher = AES.new(self.IMG_KEY, AES.MODE_CBC, iv=self.IMG_IV)
            decrypted = cipher.decrypt(data)
            return self._unpad_pkcs7(decrypted)
        except Exception as e:
            return None

    def _proxy_img_url(self, url):
        """生成图片代理 URL，供 TVBox localProxy 解密"""
        if not url: return ''
        return f'http://127.0.0.1:9978/proxy?do=img&url={quote(url)}'

    # ==================== 首页 ====================

    def homeContent(self, filter):
        html = self._fetch(self.host + '/popular/all/')
        items = self._parse_video_list(html)
        if not items:
            html = self._fetch(self.host + '/')
            items = self._parse_video_list(html)
        return {'class': self.CATS, 'list': items[:30], 'filters': {}}

    def homeVideoContent(self):
        items = self.homeContent(False)['list']
        return {'list': items[:24], 'page': 1, 'pagecount': 1, 'limit': len(items), 'total': len(items)}

    # ==================== 分类 ====================

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        url = f'{self.host}/{tid}/'
        if page > 1:
            url += f'{page}/'

        html = self._fetch(url)
        if tid.startswith('actress/'):
            items = self._parse_actress_list(html)
        else:
            items = self._parse_video_list(html)

        total = 0
        per_page = 24
        pagecount = page
        total_match = re.search(r'data-rec-total="(\d+)"', html)
        per_page_match = re.search(r'data-rec-per-page="(\d+)"', html)
        if total_match:
            total = int(total_match.group(1))
        if per_page_match:
            per_page = int(per_page_match.group(1))
        if total and per_page:
            pagecount = (total + per_page - 1) // per_page
        else:
            total = len(items)
            pagecount = page if len(items) < per_page else page + 1

        return {
            'list': items,
            'page': page,
            'pagecount': pagecount,
            'limit': len(items),
            'total': total
        }

    # ==================== 详情 ====================

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, list) else ids)

        if vid.isdigit():
            # ===== 女优详情页 =====
            url = f'{self.host}/actress/detail/{vid}/'
            html = self._fetch(url)

            name = f'女优{vid}'
            og_match = re.search(r'<meta property="og:title" content="([^"]*)"', html)
            if og_match:
                name = self._clean_title(og_match.group(1))
            else:
                t_match = re.search(r'<title>(.*?)</title>', html)
                if t_match:
                    name = self._clean_title(t_match.group(1))

            pic_raw = self._extract_zimg(html)
            pic = ''
            if pic_raw:
                pic_data = self._fetch_img_and_decrypt(pic_raw)
                if pic_data:
                    pic = pic_data
                else:
                    pic = self._proxy_img_url(pic_raw)

            desc = ''
            desc_match = re.search(r'<meta property="og:description" content="([^"]*)"', html)
            if desc_match:
                desc = desc_match.group(1)

            videos = self._parse_video_list(html)
            if videos:
                play_urls = '#'.join([f"{v['vod_name']}${v['vod_id']}" for v in videos])
                vod = {
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': pic,
                    'vod_play_from': '默认线路',
                    'vod_play_url': play_urls,
                }
                if desc:
                    vod['vod_content'] = desc
                return {'list': [vod]}
            else:
                vod = {
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': pic,
                    'vod_play_from': '默认线路',
                    'vod_play_url': f'正片${vid}',
                }
                if desc:
                    vod['vod_content'] = desc
                return {'list': [vod]}
        else:
            # ===== 视频详情页 =====
            url = f'{self.host}/videos/{vid}/'
            html = self._fetch(url)

            title = self._extract_video_title(html) or f'视频{vid}'

            pic_raw = self._extract_pic(html)
            pic = ''
            if pic_raw:
                pic_data = self._fetch_img_and_decrypt(pic_raw)
                if pic_data:
                    pic = pic_data
                else:
                    pic = self._proxy_img_url(pic_raw)

            desc = ''
            for p in [r'<meta name="description" content="([^"]*)"', r'<meta property="og:description" content="([^"]*)"']:
                m = re.search(p, html)
                if m:
                    desc = m.group(1)
                    break

            tags = ''
            tags_match = re.search(r'<meta name="keywords" content="([^"]*)"', html)
            if tags_match:
                tags = tags_match.group(1)

            m3u8 = self._extract_m3u8(html)
            if m3u8:
                play_url = f"正片${m3u8}"
            else:
                play_url = f"正片${vid}"

            vod = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_play_from': '默认线路',
                'vod_play_url': play_url,
            }
            if desc:
                vod['vod_content'] = desc
            if tags:
                vod['vod_tag'] = tags

            return {'list': [vod]}

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = f'{self.host}/search/{quote(key)}/'
        if page > 1:
            url += f'{page}/'
        html = self._fetch(url)
        items = self._parse_video_list(html)
        return {
            'list': items,
            'page': page,
            'pagecount': page if len(items) < 24 else page + 1,
            'limit': len(items),
            'total': len(items)
        }

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags):
        hdr = {'Referer': self.host + '/', 'User-Agent': self.UA}

        if id.startswith('http') and ('.m3u8' in id or '.mp4' in id):
            return {'parse': 0, 'url': id, 'header': hdr}

        if id.isdigit():
            return {
                'parse': 1,
                'url': f'{self.host}/actress/detail/{id}/',
                'header': hdr
            }

        url = f'{self.host}/videos/{id}/'
        html = self._fetch(url)
        m3u8 = self._extract_m3u8(html)
        if m3u8:
            return {'parse': 0, 'url': m3u8, 'header': hdr}

        return {'parse': 1, 'url': url, 'header': hdr}

    # ==================== 本地代理（图片解密）====================

    def localProxy(self, param):
        """TVBox 本地代理：解密图片"""
        url = param.get('url', '')
        do = param.get('do', '')
        if not url:
            return [404, {}, '']

        try:
            url = unquote(url)
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                decrypted = self._decrypt_img_data(r.content)
                if decrypted:
                    ext = 'jpeg'
                    if url.endswith('.png'):
                        ext = 'png'
                    elif url.endswith('.gif'):
                        ext = 'gif'
                    headers = {
                        'Content-Type': f'image/{ext}',
                        'Cache-Control': 'max-age=86400',
                    }
                    return [200, headers, decrypted]
        except Exception as e:
            pass
        return [404, {}, '']

    # ==================== HTML解析辅助 ====================

    def _fetch_img_and_decrypt(self, url, timeout=10):
        """下载图片并解密，返回 base64 data URI"""
        if not url: return ''
        try:
            r = self.session.get(url, timeout=timeout)
            if r.status_code == 200:
                decrypted = self._decrypt_img_data(r.content)
                if decrypted:
                    ext = 'jpeg'
                    if url.endswith('.png'):
                        ext = 'png'
                    elif url.endswith('.gif'):
                        ext = 'gif'
                    b64 = base64.b64encode(decrypted).decode('utf-8')
                    return f'data:image/{ext};base64,{b64}'
        except:
            pass
        return ''

    def _parse_video_list(self, html):
        """解析视频列表，过滤广告，图片直接解密为 base64"""
        items = []
        if not html: return items
        seen = set()

        # 策略1: 匹配 bind_video_img 结构（普通视频列表）
        pattern1 = r'<div class="img-box cover-md bind_video_img">(.*?)</div>\s*</div>'
        blocks1 = re.findall(pattern1, html, re.DOTALL)
        
        for block in blocks1:
            if self._is_ad_block(block):
                continue
            
            vid_match = re.search(r'href="/videos/([^"/]+)/"', block)
            if not vid_match: continue
            vid = vid_match.group(1)
            if vid in seen: continue
            seen.add(vid)

            pic_raw = self._extract_zimg(block)
            # 关键修复：直接下载解密为 base64，不依赖 TVBox localProxy
            pic = ''
            if pic_raw:
                pic_data = self._fetch_img_and_decrypt(pic_raw, timeout=3)
                if pic_data:
                    pic = pic_data
                else:
                    pic = self._proxy_img_url(pic_raw)

            title = ''
            alt_match = re.search(r'alt="([^"]{3,})"', block)
            if alt_match:
                title = alt_match.group(1).strip()

            remark = ''
            # 时长在 absolute-bottom-right > label 里
            rem_match = re.search(r'class="absolute-bottom-right"[^>]*>.*?<span[^>]*class="label"[^>]*>(.*?)</span>', block, re.DOTALL)
            if rem_match:
                remark = self._extract_text(rem_match.group(1))
            if not remark:
                rem_match = re.search(r'class="label"[^>]*>(\d+:\d+)</span>', block)
                if rem_match:
                    remark = rem_match.group(1)

            items.append({
                'vod_id': vid,
                'vod_name': title or f'视频{vid}',
                'vod_pic': pic,
                'vod_remarks': remark,
            })

        # 策略2: 匹配 video-img-box 结构（精选区域）
        pattern2 = r'<div class="video-img-box">(.*?)</div>\s*</div>\s*</div>'
        blocks2 = re.findall(pattern2, html, re.DOTALL)
        
        for block in blocks2:
            if self._is_ad_block(block):
                continue
            
            vid_match = re.search(r'href="/videos/([^"/]+)/"', block)
            if not vid_match: continue
            vid = vid_match.group(1)
            if vid in seen: continue
            seen.add(vid)

            pic_raw = self._extract_zimg(block)
            pic = ''
            if pic_raw:
                pic_data = self._fetch_img_and_decrypt(pic_raw, timeout=3)
                if pic_data:
                    pic = pic_data
                else:
                    pic = self._proxy_img_url(pic_raw)

            title = ''
            alt_match = re.search(r'alt="([^"]{3,})"', block)
            if alt_match:
                title = alt_match.group(1).strip()

            remark = ''
            rem_match = re.search(r'class="ribbon[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
            if rem_match:
                remark = self._extract_text(rem_match.group(1))

            items.append({
                'vod_id': vid,
                'vod_name': title or f'视频{vid}',
                'vod_pic': pic,
                'vod_remarks': remark,
            })

        return items

    def _parse_actress_list(self, html):
        """解析女优列表页"""
        items = []
        if not html: return items
        
        blocks = re.split(r'<div class="col-6 col-sm-4 col-lg-3">', html)
        
        seen = set()
        for block in blocks[1:]:
            id_match = re.search(r'href="/actress/detail/(\d+)/"', block)
            if not id_match: continue
            aid = id_match.group(1)
            if aid in seen: continue
            seen.add(aid)

            title_match = re.search(r'<h6\s+class="title">(.*?)</h6>', block)
            name = self._extract_text(title_match.group(1)) if title_match else f'女优{aid}'

            count_match = re.search(r'<span>(\d+)\s*部影片</span>', block)
            count = self._extract_text(count_match.group(1)) + '部' if count_match else ''

            pic_raw = self._extract_zimg(block)
            pic = ''
            if pic_raw:
                pic_data = self._fetch_img_and_decrypt(pic_raw, timeout=3)
                if pic_data:
                    pic = pic_data
                else:
                    pic = self._proxy_img_url(pic_raw)

            items.append({
                'vod_id': aid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': count,
            })
        return items

    def _extract_video_title(self, html):
        if not html: return ''
        m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if m:
            return self._clean_title(m.group(1))
        m = re.search(r'<title>(.*?)</title>', html)
        if m:
            return self._clean_title(m.group(1))
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if m:
            return self._extract_text(m.group(1))
        return ''

    def _extract_pic(self, html):
        """提取视频封面，优先 video data-src，其次 meta/og/poster"""
        if not html: return ''
        m = re.search(r'<video[^>]+data-src="([^"]+)"', html)
        if m: return m.group(1)
        m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if m: 
            val = m.group(1)
            if 'logo' not in val:
                return val
        m = re.search(r'poster="([^"]+)"', html)
        if m: return m.group(1)
        m = re.search(r'<video[^>]+poster="([^"]+)"', html)
        if m: return m.group(1)
        m = re.search(r'z-image-loader-url="`([^`]+)`"', html)
        if m: return self._fix(m.group(1))
        m = re.search(r'x-image-loader-url="`([^`]+)`"', html)
        if m: return self._fix(m.group(1))
        m = re.search(r'z-image-loader-url="([^"]+)"', html)
        if m: return self._fix(m.group(1))
        return ''

    def _extract_m3u8(self, html):
        if not html: return ''
        patterns = [
            r'(https?://[^\s"\']+\.m3u8[^"\']*)',
            r'["\']([^\s"\']+\.m3u8)["\']',
            r'url\s*[:=]\s*["\']([^"\']+m3u8[^"\']*)["\']',
            r'src:\s*["\']([^"\']+m3u8[^"\']*)["\']',
            r'"file"\s*:\s*"([^"]+m3u8[^"]*)"',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                url = m.group(1)
                if url.startswith('http'): return url
        return ''
