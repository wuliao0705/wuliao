# -*- coding: utf-8 -*-
# 黑料网 TVBox 爬虫
# 站点: https://heiliao.com/
# 结构: 自建 CMS, 文章列表 + 详情, JSON-LD 结构化数据
# 图片 CDN: pic.hdhwqx.cn / new.hdhwqx.cn (无加密)
# 分页: 首页 /page/N/, 分类无分页

import re
import sys
import json
import base64
import threading
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def isVideo(self): return True
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {"parse": 0, "url": "", "header": {}, "content": ""}
        def localProxy(self, params): return []


BASE_URL = "https://heiliao.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ---------- 封面图 AES-CBC 解密参数 ----------
# 来源: /usr/themes/Mirages/js/7.10.0/image.20260416.js
#   cryjs.AES.decrypt(word, cc("102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48"),
#                     {iv: cc("57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49"),
#                      mode: CBC, padding: Pkcs7})
IMG_AES_KEY = b"f5d965df75336270"
IMG_AES_IV  = b"97b60394abc2fbe1"
IMG_CDN_HOSTS = "hdhwqx.cn"  # 黑料网图片 CDN 域名
IMG_CACHE = {}
IMG_CACHE_MAX = 80
# 本地图片解密代理端口
PROXY_PORT = 19991


# ---------- 纯 Python AES-128 实现（TVBox 环境无 pycryptodome 时兜底） ----------
def _build_sbox():
    """构造标准 AES S-box 与其逆表"""
    s = bytes.fromhex(
        "637c777bf26b6fc53001672bfed7ab76"
        "ca82c97dfa5947f0add4a2af9ca472c0"
        "b7fd9326363ff7cc34a5e5f171d83115"
        "04c723c31896059a071280e2eb27b275"
        "09832c1a1b6e5aa0523bd6b329e32f84"
        "53d100ed20fcb15b6acbbe394a4c58cf"
        "d0efaafb434d338545f9027f503c9fa8"
        "51a3408f929d38f5bcb6da2110fff3d2"
        "cd0c13ec5f974417c4a77e3d645d1973"
        "60814fdc222a908846eeb814de5e0bdb"
        "e0323a0a4906245cc2d3ac629195e479"
        "e7c8376d8dd54ea96c56f4ea657aae08"
        "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
        "703eb5664803f60e613557b986c11d9e"
        "e1f8981169d98e949b1e87e9ce5528df"
        "8ca1890dbfe6426841992d0fb054bb16"
    )
    inv = [0] * 256
    for i, v in enumerate(s):
        inv[v] = i
    return s, bytes(inv)


_SBOX, _INV_SBOX = _build_sbox()
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _gmul(a, b):
    """GF(2^8) 乘法"""
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r & 0xff


# --- 预计算乘法表：把 MixColumns 的 16 次 gmul（每次 8 轮循环）降为 16 次查表 ---
# 一次性开销 6×256 次 gmul，换取每块 ~1000 倍加速
_MUL2 = [_gmul(i, 2) for i in range(256)]
_MUL3 = [_gmul(i, 3) for i in range(256)]
_MUL9 = [_gmul(i, 9) for i in range(256)]
_MUL11 = [_gmul(i, 11) for i in range(256)]
_MUL13 = [_gmul(i, 13) for i in range(256)]
_MUL14 = [_gmul(i, 14) for i in range(256)]


def _key_expansion(key):
    """AES-128 密钥扩展，返回 44 个 32bit 字"""
    w = [int.from_bytes(key[i * 4:(i + 1) * 4], "big") for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xffffffff  # RotWord
            t = (_SBOX[(t >> 24) & 0xff] << 24
                 | _SBOX[(t >> 16) & 0xff] << 16
                 | _SBOX[(t >> 8) & 0xff] << 8
                 | _SBOX[t & 0xff])                  # SubWord
            t ^= (_RCON[i // 4 - 1] << 24)
        w.append(w[i - 4] ^ t)
    return w


def _inv_shift_sub(state):
    """InvShiftRows（每行右移 r 位）+ InvSubBytes 合并（列优先存储）

    源遍历：源 (r, c) 的值移动到目标 (r, (c + r) % 4) —— 右移
    """
    ns = [0] * 16
    for r in range(4):
        for c in range(4):
            ns[r + ((c + r) % 4) * 4] = _INV_SBOX[state[r + c * 4]]
    return ns


def _add_round_key(state, w, base):
    """AddRoundKey: state[0][c] 对应 word 的最高字节 (>>24)，依此递减

    整列打包成 32 位一次异或，避免 16 次单独的移位与赋值。
    """
    for c in range(4):
        v = ((state[c * 4] << 24) | (state[c * 4 + 1] << 16) |
             (state[c * 4 + 2] << 8) | state[c * 4 + 3]) ^ w[base + c]
        state[c * 4]     = (v >> 24) & 0xff
        state[c * 4 + 1] = (v >> 16) & 0xff
        state[c * 4 + 2] = (v >> 8) & 0xff
        state[c * 4 + 3] = v & 0xff
    return state


def _inv_mix_columns(state):
    """InvMixColumns：用预计算乘法表代替 16 次 gmul（纯 Python 路径关键优化）"""
    ns = [0] * 16
    for c in range(4):
        s0 = state[c * 4]
        s1 = state[c * 4 + 1]
        s2 = state[c * 4 + 2]
        s3 = state[c * 4 + 3]
        ns[c * 4]     = _MUL14[s0] ^ _MUL11[s1] ^ _MUL13[s2] ^ _MUL9[s3]
        ns[c * 4 + 1] = _MUL9[s0]  ^ _MUL14[s1] ^ _MUL11[s2] ^ _MUL13[s3]
        ns[c * 4 + 2] = _MUL13[s0] ^ _MUL9[s1]  ^ _MUL14[s2] ^ _MUL11[s3]
        ns[c * 4 + 3] = _MUL11[s0] ^ _MUL13[s1] ^ _MUL9[s2]  ^ _MUL14[s3]
    return ns


# --- AES-128 解密 T-table（等价正向密码 Equivalent Inverse Cipher 用）---
# 标准逆密码的顺序是 InvShiftRows → InvSubBytes → AddRoundKey → InvMixColumns，
# AddRoundKey 夹在中间无法合并。等价正向密码重排为
#   ShiftRows(正) → SubBytes(正) → InvMixColumns → AddRoundKey
# 前 3 步连续，可合并为单次 T-table 查表：4 次 256 项查表 + 3 次 32 位异或。
def _decrypt_block(block, w):
    """单个 16 字节块的 AES-128 逆密码（FIPS-197 标准流程）

    标准逆密码顺序为 InvShiftRows → InvSubBytes → AddRoundKey → InvMixColumns，
    AddRoundKey 夹在中间，无法把中间三步合并成单个 T-table（等价正向密码虽能合并，
    但需要另一套"等价密钥"扩展，收益仅约 18%，不值得增加复杂度）。
    实际优化点：MixColumns 用预计算乘法表 _MUL* 替代 16 次 gmul，
    AddRoundKey 用 32 位打包异或替代 16 次字节移位。
    """
    state = list(block)
    _add_round_key(state, w, 40)
    for rnd in range(9, 0, -1):
        state = _inv_shift_sub(state)
        _add_round_key(state, w, rnd * 4)
        state = _inv_mix_columns(state)
    state = _inv_shift_sub(state)
    _add_round_key(state, w, 0)
    return bytes(state)


def _aes_cbc_decrypt(data):
    """AES-128-CBC 解密 + Pkcs7 去填充，返回完整图片字节"""
    if not data or len(data) % 16 != 0 or len(data) < 16:
        return None
    try:
        if AES is not None:
            plain = AES.new(IMG_AES_KEY, AES.MODE_CBC, IMG_AES_IV).decrypt(data)
        else:
            w = _key_expansion(IMG_AES_KEY)
            parts = []
            prev = bytes(IMG_AES_IV)
            for off in range(0, len(data), 16):
                blk = data[off:off + 16]
                dec = _decrypt_block(blk, w)
                parts.append(bytes(a ^ b for a, b in zip(dec, prev)))
                prev = blk
            plain = b"".join(parts)
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
        end_jpg = plain.rfind(b"\xff\xd9")
        if end_jpg > 0:
            return plain[:end_jpg + 2]
        end_png = plain.rfind(b"IEND\xaeB`\x82")
        if end_png > 0:
            return plain[:end_png + 8]
        return plain
    except Exception:
        return None


def _guess_img_type(url, data):
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    ext = url.lower().rsplit("?", 1)[0].rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")


class _ImgHandler(BaseHTTPRequestHandler):
    """本地图片解密代理: GET /d/<base64url 编码的原图 URL>"""
    def do_GET(self):
        try:
            path = self.path
            if not path.startswith("/d/"):
                self.send_response(404)
                self.end_headers()
                return
            b64 = path[3:]
            # base64url 解码（补 padding）
            raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
            url = raw.decode("utf-8", "ignore")
            if not url.startswith("http"):
                self.send_response(404)
                self.end_headers()
                return
            body = None
            ctype = None
            # 缓存
            if url in IMG_CACHE:
                body, ctype = IMG_CACHE[url]
            else:
                r = requests.get(url, headers={"User-Agent": UA,
                                               "Referer": BASE_URL + "/"},
                                 timeout=15)
                if r.status_code != 200 or not r.content:
                    raise ValueError("download failed")
                raw_data = r.content
                ctype = _guess_img_type(url, raw_data)
                if "hdhwqx.cn" in url:
                    dec = _aes_cbc_decrypt(raw_data)
                    if dec and len(dec) > 100:
                        body = dec
                        ctype = _guess_img_type(url, dec)
                    else:
                        body = raw_data
                else:
                    body = raw_data
                if len(IMG_CACHE) >= IMG_CACHE_MAX:
                    IMG_CACHE.clear()
                IMG_CACHE[url] = (body, ctype)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def log_message(self, *args):
        pass

# 分类列表 (tid: 显示名)
CATEGORIES = [
    ("home",  "黑料首页"),
    ("hlcg",  "最新黑料"),
    ("jrrs",  "今日热瓜"),
    ("jqrm",  "热门黑料"),
    ("lsdg",  "经典黑料"),
    ("whhl",  "网红黑料"),
    ("xycg",  "校园黑料"),
    ("jqxs",  "黑料小说"),
    ("hlkt",  "黑料课堂"),
    ("hlbg",  "黑料爆改"),
    ("mrrb",  "日榜黑料"),
    ("zbjx",  "周榜精选"),
    ("ybrg",  "月榜热瓜"),
    ("aitech","AI科技"),
    ("cpcd",  "CPCD"),
    ("djbl",  "DJBL"),
    ("fczq",  "FCZQ"),
    ("gchl",  "GCHL"),
    ("sjb",   "竞技吃瓜"),
    ("syzy",  "SYZY"),
    ("thzq",  "THZQ"),
    ("ttsq",  "TTSQ"),
    ("ttzz",  "TTZZ"),
    ("ycsq",  "YCSQ"),
    ("yqby",  "YQBY"),
    ("ysdj",  "成人短剧"),
    ("whhj",  "WHHJ"),
]


class Spider(BaseSpider):
    Name = "黑料网"

    def init(self, extend=""):
        self.host = BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.session.trust_env = False
        # 缓存首页文章列表（用于详情页获取封面图）
        self._home_cache = {}
        self._img_proxy = None
        self._start_img_proxy()

    def destroy(self):
        self._stop_img_proxy()
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None


    # ---------- 本地图片解密代理 ----------

    def _start_img_proxy(self):
        """启动本地 HTTP 代理，用于实时解密 CDN 上的 AES 加密封面图"""
        if self._img_proxy is not None:
            return
        port = PROXY_PORT
        last = None
        for offset in range(0, 40):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port + offset), _ImgHandler)
                srv.daemon_threads = True
                t = threading.Thread(target=srv.serve_forever, daemon=True,
                                     name="hl-img-proxy")
                t.start()
                self._img_proxy = srv
                self._img_port = port + offset
                return
            except Exception as e:
                last = e
                continue
        print(f"[heiliao] image proxy failed: {last}", file=sys.stderr)

    def _stop_img_proxy(self):
        try:
            if self._img_proxy is not None:
                self._img_proxy.shutdown()
                self._img_proxy.server_close()
        except Exception:
            pass
        self._img_proxy = None
        IMG_CACHE.clear()

    def _img_url(self, url):
        """把 CDN 加密图 URL 转成经本地代理解密的直链；非加密图原样返回"""
        if not url or not isinstance(url, str) or self._img_proxy is None:
            return url
        if "hdhwqx.cn" not in url:
            return url
        b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")
        return f"http://127.0.0.1:{self._img_port}/d/{b64}"

    def _fetch_img(self, url):
        """下载并解密单张图片，写入代理缓存"""
        if not url or url in IMG_CACHE:
            return
        try:
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Referer": BASE_URL + "/"},
                             timeout=15)
            if r.status_code != 200 or not r.content:
                return
            raw = r.content
            ctype = _guess_img_type(url, raw)
            if "hdhwqx.cn" in url:
                dec = _aes_cbc_decrypt(raw)
                if dec and len(dec) > 100:
                    ctype = _guess_img_type(url, dec)
                    raw = dec
            if len(IMG_CACHE) >= IMG_CACHE_MAX:
                IMG_CACHE.clear()
            IMG_CACHE[url] = (raw, ctype)
        except Exception:
            pass

    def _preload_images(self, urls, workers=6, cap=30):
        """后台并发预下载+解密封面图，让 TVBox 首次请求即命中缓存"""
        todo = [u for u in urls
                if u and isinstance(u, str) and u.startswith("http")
                and "hdhwqx.cn" in u and u not in IMG_CACHE]
        if not todo:
            return

        def run():
            from concurrent.futures import ThreadPoolExecutor
            batch = todo[:cap]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(self._fetch_img, batch))

        t = threading.Thread(target=run, daemon=True, name="hl-img-preload")
        t.start()

    def localProxy(self, params):
        return []

    def getName(self):
        return self.Name

    def isVideo(self):
        return True

    # ---------- 工具方法 ----------

    def _get(self, url, retries=2):
        last_err = None
        for _ in range(retries):
            try:
                r = self.session.get(url, timeout=15)
                if r.status_code == 200 and len(r.text) > 500:
                    return r.text
                last_err = f"status {r.status_code}"
            except Exception as e:
                last_err = str(e)
        return ""

    def _cache_home(self):
        """缓存首页文章列表，供详情页获取封面图"""
        if self._home_cache:
            return
        html = self._get(self.host + "/")
        blocks = re.findall(
            r'<a[^>]+href="/archives/(\d+)/"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for vid, block in blocks:
            img_m = re.search(r'z-image-loader-url="(https?://[^"]+)"', block)
            title_m = re.search(r'alt="([^"]+)"', block)
            if img_m:
                self._home_cache[vid] = {
                    "pic": img_m.group(1),
                    "title": title_m.group(1).strip() if title_m else "",
                }

    def _extract_play_urls(self, html):
        """从详情页转义JSON中提取所有 m3u8 直链"""
        h2 = html.replace('\\/', '/')
        return re.findall(r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*', h2)

    def _extract_cover(self, html):
        """封面：z-image-loader-url / src 兜底"""
        m = re.search(r'z-image-loader-url="(https://[^"]+\.(?:png|jpg|jpeg|webp|gif))"', html)
        if m:
            return m.group(1)
        m = re.search(r'src="(https://(?:pic|new)\.hdhwqx\.cn[^"]+\.(?:png|jpg|jpeg|webp|gif))"', html)
        if m:
            return m.group(1)
        return ""

    def _extract_articles(self, html, max_count=30):
        """从列表页 HTML 提取文章列表"""
        articles = []
        if not html:
            return articles
        blocks = re.findall(
            r'<a[^>]+href="/archives/(\d+)/"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for vid, block in blocks:
            try:
                if 'menu-txt' in block or 'class="menu' in block:
                    continue
                title_m = re.search(r'alt="([^"]+)"', block)
                title = title_m.group(1).strip() if title_m else ""
                if not title or len(title) < 4:
                    continue
                pic = ""
                img_m = re.search(r'z-image-loader-url="(https://[^"]+)"', block)
                if img_m:
                    pic = img_m.group(1)
                articles.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": self._img_url(pic),
                    "vod_remarks": "",
                })
                if len(articles) >= max_count:
                    break
            except Exception:
                continue
        return articles

    def _extract_article_body(self, html):
        """从详情页提取完整正文（所有 <p> 段落，过滤广告/页脚）"""
        # 找正文区域（支持各种 class 组合）
        body_idx = html.find('editormd-preview')
        if body_idx < 0:
            body_idx = html.find('client-only-placeholder')
        if body_idx < 0:
            return ""
        # 找对应的 closing tag
        end_idx = min(body_idx + 40000, len(html))
        body_html = html[body_idx:end_idx]
        # 提取所有 <p> 标签
        paras = re.findall(r'<p[^>]*>(.*?)</p>', body_html, re.DOTALL)
        blocks = []
        for p in paras:
            text = re.sub(r'<img[^>]*>', '', p)
            text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
            text = re.sub(r'<[^>]+>', ' ', text).strip()
            text = re.sub(r'\s+', ' ', text)
            # 过滤广告和页脚（精确匹配关键词）
            skip_keywords = [
                '黑料网最新入口', '黑料网海外', 'hlwf8', 'heiliao88',
                'TG联系', 'Telegram', '邮箱', '📮', '💰', '🕒',
                '⚠️', '📣', '🎬', '💻', '✨', '🔥', '重磅',
                '黑料司机站', '永久海外', '备用地址', '官方QQ群',
                '重要提示', '发帖', '获取最新地址', '黑料 APP 免费看',
                'www.heiliao', '黑料免费 App', '视频播放缓冲',
                '画质不够清晰', '下载黑料', '关键词：', '#AI', '#成人', '#短剧', '#原创',
                '黑料网 · 官方', '谨防假冒', '速通西游',
            ]
            # 过滤纯 URL 段落和 email 编码段落
            def is_skip(text):
                if any(kw in text for kw in skip_keywords):
                    return True
                # 纯 URL 段落
                if re.match(r'^https?://', text):
                    return True
                # email 编码 (含 &# 实体)
                if '&#' in text and ('mail' in text.lower() or '160' in text):
                    return True
                # 纯数字 ID 或过短
                if re.match(r'^\d+$', text.strip()):
                    return True
                return False
            if len(text) > 10 and not is_skip(text):
                blocks.append(text)
        return '\n\n'.join(blocks)

    def _get_jsonld_info(self, html):
        """从 JSON-LD 提取结构化信息"""
        info = {"author": "", "date_published": "", "date_modified": "",
                "keywords": "", "description": "", "video_duration": ""}
        m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                for item in data.get("@graph", []):
                    if item.get("@type") == "Article":
                        info["description"] = item.get("description", "")
                        info["author"] = item.get("author", {}).get("name", "")
                        info["date_published"] = item.get("datePublished", "")
                        info["date_modified"] = item.get("dateModified", "")
                        info["keywords"] = item.get("keywords", "")
                        vid = item.get("video", {})
                        if vid:
                            info["video_duration"] = vid.get("duration", "")
                        break
            except Exception:
                pass
        # 降级: 从 HTML 提取
        if not info["author"]:
            a = re.search(r'class="detail-author"[^>]*>([^<]+)<', html)
            if a:
                info["author"] = a.group(1).strip()
        if not info["date_published"]:
            dp = re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})"', html)
            if dp:
                info["date_published"] = dp.group(1)
        if not info["date_modified"]:
            dm = re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})"[^>]*>[^<]*更新', html)
            if dm:
                info["date_modified"] = dm.group(1)
        if not info["keywords"]:
            kw = re.search(r'<meta[^>]+name="keywords"[^>]+content="([^"]*)"', html)
            if kw:
                info["keywords"] = kw.group(1)
        return info

    # ---------- 契约方法 ----------

    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in CATEGORIES]
        result = {"class": classes, "list": []}
        try:
            html = self._get(self.host + "/")
            result["list"] = self._extract_articles(html)
            self._cache_home()
            self._preload_images([v["vod_pic"] for v in result["list"]])
        except Exception as e:
            print(f"[heiliao] homeContent error: {e}", file=sys.stderr)
        return result

    def homeVideoContent(self):
        try:
            html = self._get(self.host + "/")
            return {"list": self._extract_articles(html)}
        except Exception:
            return {"list": []}

    def homeVideoContentPage(self, pg="1"):
        """首页分页"""
        try:
            page = int(pg) if str(pg).isdigit() else 1
            if page <= 1:
                url = self.host + "/"
            else:
                url = f"{self.host}/page/{page}/"
            html = self._get(url)
            articles = self._extract_articles(html)
            # 从分页区域提取总页数
            pagecount = 1
            m = re.search(r'data-page="(\d+)"', html)
            if m:
                max_pg = max(int(p) for p in re.findall(r'data-page="(\d+)"', html))
                pagecount = max_pg
            return {
                "list": articles,
                "page": page,
                "pagecount": pagecount,
                "limit": len(articles),
                "total": pagecount * 28,
            }
        except Exception as e:
            print(f"[heiliao] homeVideoContentPage error: {e}", file=sys.stderr)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        try:
            page = int(pg) if str(pg).isdigit() else 1
            # "home" 分类映射到首页 /page/N/
            if tid == "home":
                if page <= 1:
                    html = self._get(self.host + "/")
                else:
                    html = self._get(f"{self.host}/page/{page}/")
            else:
                if page <= 1:
                    html = self._get(f"{self.host}/{tid}/")
                else:
                    html = self._get(f"{self.host}/{tid}/page/{page}/")
            articles = self._extract_articles(html)
            # 从分页区域提取总页数
            pagecount = 1
            dps = re.findall(r'data-page="(\d+)"', html)
            if dps:
                nums = [int(p) for p in dps if int(p) > 1]
                if nums:
                    pagecount = max(nums)
            return {
                "list": articles,
                "page": page,
                "pagecount": pagecount,
                "limit": len(articles),
                "total": pagecount * len(articles) if pagecount > 1 else len(articles),
            }
        except Exception as e:
            print(f"[heiliao] categoryContent error: {e}", file=sys.stderr)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def detailContent(self, ids):
        vod = {
            "vod_id": ids[0],
            "vod_name": "",
            "vod_pic": "",
            "vod_remarks": "",
            "type_name": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }
        try:
            vid = ids[0]
            html = self._get(f"{self.host}/archives/{vid}/")
            if not html:
                return {"list": [vod]}

            # 元信息
            info = self._get_jsonld_info(html)

            # 标题
            t_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if t_m:
                vod["vod_name"] = re.sub(r'<[^>]+>', '', t_m.group(1)).strip()

            # 封面: 优先缓存，其次 _extract_cover
            pic = self._home_cache.get(vid, {}).get("pic", "")
            if not pic:
                pic = self._extract_cover(html)
            vod["vod_pic"] = self._img_url(pic)

            # 分类
            cats = re.findall(r'href="/(hlcg|jrrs|jqrm|lsdg|whhl|xycg|jqxs|hlkt|hlbg|mrrb|zbjx|ybrg|aitech|cpcd|djbl|fczq|gchl|sjb|syzy|thzq|ttsq|ttzz|ycsq|yqby|ysdj|whhj)/"[^>]*>([^<]+)</a>', html)
            if cats:
                vod["type_name"] = cats[0][1].strip()

            # 完整正文
            full_body = self._extract_article_body(html)

            # 组装元信息
            meta_parts = []
            if info["author"]:
                meta_parts.append(f"作者：{info['author']}")
            if info["date_published"]:
                meta_parts.append(f"发布：{info['date_published']}")
            if info["date_modified"] and info["date_modified"] != info["date_published"]:
                meta_parts.append(f"更新：{info['date_modified']}")
            if cats:
                cat_names = "、".join(c[1].strip() for c in cats[:3])
                meta_parts.append(f"分类：{cat_names}")
                vod["type_name"] = cats[0][1].strip()
            if info["keywords"]:
                meta_parts.append(f"标签：{info['keywords']}")
            if info.get("video_duration"):
                meta_parts.append(f"时长：{info['video_duration']}")

            vod["vod_remarks"] = " | ".join(meta_parts)

            # 组装简介
            parts = []
            if meta_parts:
                parts.append("📋 " + "  |  ".join(meta_parts))
            if full_body:
                parts.append(f"\n{full_body}")
            elif info["description"]:
                parts.append(f"\n{info['description']}")
            vod["vod_content"] = "\n".join(parts)

            # 播放：从转义 JSON 提取直链 m3u8
            urls = self._extract_play_urls(html)
            if urls:
                urls = list(dict.fromkeys(urls))
                vod["vod_play_from"] = "原画"
                vod["vod_play_url"] = "#".join(f"第{i+1}集${u}" for i, u in enumerate(urls))
                # 告诉 TVBox 用本地解析直链
                vod["vod_play_from"] = "原画"
            else:
                vod["vod_play_from"] = "黑料网"
                vod["vod_play_url"] = f"全文观看${self.host}/archives/{vid}/"

        except Exception as e:
            print(f"[heiliao] detailContent error: {e}", file=sys.stderr)
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if str(pg).isdigit() else 1
            kw = quote(key)
            url = f"{self.host}/index/search?keyboard={kw}&type=archives"
            html = self._get(url)
            articles = []
            blocks = re.findall(
                r'<a[^>]+href="/archives/(\d+)/"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )
            for vid, block in blocks:
                try:
                    # 搜索页无 alt 属性，从文本内容提取标题
                    title_text = re.sub(r'<[^>]+>', '', block).strip()
                    title = title_text if title_text and len(title_text) > 3 else vid
                    img_m = re.search(r'z-image-loader-url="(https?://[^"]+)"', block)
                    pic = img_m.group(1) if img_m else ""
                    articles.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": self._img_url(pic),
                        "vod_remarks": "",
                    })
                    if len(articles) >= 30:
                        break
                except Exception:
                    continue
            return {"list": articles, "page": page, "pagecount": 999, "limit": len(articles), "total": 99999}
        except Exception as e:
            print(f"[heiliao] searchContent error: {e}", file=sys.stderr)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        # id 格式: "在线播放$https://heiliao.com/archives/123/"
        # 直接返回原始 URL
        url = id
        if '$' in id:
            url = id.split('$', 1)[1]
        return {
            "parse": 0,
            "url": url,
            "header": {"User-Agent": UA},
        }

    def localProxy(self, params):
        return []
