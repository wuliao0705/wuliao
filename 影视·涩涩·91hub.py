# -*- coding: utf-8 -*-
# 91hubw.com（91Hub 成人视频）—— TVBox / 影视仓 Python 爬虫源
#
# ============================ 站点结构备忘 ============================
# 技术栈：自研 PHP + Tailwind，服务端直出 HTML。
# 反爬：页面无 Cloudflare 挑战，纯 requests 直连即可；m3u8 与分片也不校验 Referer。
#       curl_cffi 仅作偶发失败时的兜底。
#
# 封面图（关键坑，v2 修复）：
#   列表卡片 img[data-src] 指向的**不是图片，而是 AES-CBC 加密的二进制**：
#     Content-Type: binary/octet-stream，首字节固定 3eaa708e8e5191ed…（不是图片魔数）
#   与 91crdj 同一套前端方案，**密钥完全相同**（同一开发商）：
#     key = f5d965df75336270   iv = 97b60394abc2fbe1   AES-CBC / NoPadding
#   实测跨首页 + 11 个分类 + 标签页 + 搜索页共 42 张图，解密后全部标准 JPEG，0 失败。
#   解法：vod_pic 指向 localProxy（type=img），代理内取密文 → AES 解密 → 回吐真图。
#   例外：详情页 og:image（/social-cover/{base64}.jpeg）是**明文 JPEG**，可直连，
#         不要送进解密代理（会把好图解坏）。代理内按魔数判断，明文则原样回吐。
#
# 列表（每页 23~24 条）：
#   /movie/{slug}/            11 个一级分类，见 CHANNELS
#   /movie/{slug}/page/N/     翻页（实测 p1/p2 无重叠；?page=N 也可用）
#   /tag/{urlencode标签}/     标签页 = 二级目录，同样支持 /page/N/
#   /search/{关键词}/         搜索（也支持 /search/?keyword=KW）
#   /search/{关键词}/page/N/  搜索翻页
#   注意：/search/?k= 与 ?wd= 都无效；?s= 走的是首页全局搜索（返回 83 条但混杂）。
#
# 二级目录（v2 新增）：
#   站点没有标签总览页（/tags/ /tag/ /topics/ 全 404），但每个 /movie/{slug}/ 页
#   底部有该分类的标签云。逐个分类抓取后得到 11 组共 261 项（去重 132 项），
#   做成 SUBCATS 常量：一级选分类 → 二级筛选器只展示该分类下的标签，
#   比一个 130 项的大杂烩列表好用。选中标签后走 /tag/{标签}/ 全站检索。
#
# 卡片：以 <div class="video-item" 为锚点切块，块内
#   href="/video/{id}/"                     影片地址，id 是纯数字
#   img[data-src]                           封面（每片不同，upload_01/ads/… .jpeg）
#   div.bg-black.rounded-large               时长
#   h3 > a                                  标题
#   a[href*=/tag/]                          标签
#   data-gsce231-publish-time                发布时间
#   data-gsce231-real-view-count             播放数
#
# 详情 /video/{id}/：
#   h1 标题（末尾带 " A片" 后缀，需剔除）
#   坑：详情页的 img[data-src] 是**广告 GIF**（所有片一样，别用）。
#       真封面在 og:image：/social-cover/{base64}.jpeg，base64 段解出来是
#       /upload_01/ads/…jpeg 的站内路径。social-cover 地址本身可直接取图（200
#       image/jpeg），所以直接用 og:image 即可，不必还原。
#
# 播放（关键）：
#   播放配置在 eval(function(p,a,c,k,e,d) 混淆块里，解包后：
#     'url'      : /media/m3u8/?url=<urlencode的CDN地址>&exp=<ts>&token=<sig>
#     'h264_url' : 同上（备用）
#     'api'      : /videos/player3/<hash>/<id>
#     'h_265'    : 通常为空
#   /media/m3u8/ 是站内代理，返回真 m3u8，内容里的 key 与分片都指向
#   xv.dzuxta.cn 且各自带 auth_key 签名。
#   m3u8 为 AES-128 加密（#EXT-X-KEY），分片首字节不是 0x47（因为已加密），
#   播放器按标准 HLS 流程自行取 key 解密即可，parse:0 直连可播。
#   token / auth_key 有时效 → 绝不缓存 m3u8，playerContent 里实时解包。

import re
import sys
import time
import string
import base64
from urllib.parse import quote, unquote, urljoin

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, params): return []
        def getProxyUrl(self): return "http://127.0.0.1:9978/proxy?do=py"


class Spider(BaseSpider):

    HOST = "https://91hubw.com"

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # 11 个分类（slug 已是纯 ASCII，直接当 type_id 用）
    CHANNELS = [
        ("zxsj", "最新上架"),
        ("tjgn", "推荐给您"),
        ("tpzp", "偷拍自拍"),
        ("whmx", "网黄明星"),
        ("snsf", "熟女少妇"),
        ("llsn", "萝莉少女"),
        ("jtll", "家庭乱伦"),
        ("qjmj", "强奸迷奸"),
        ("hsam", "会所按摩"),
        ("lqzk", "猎奇重口"),
        ("jmtt", "禁漫天堂"),
    ]

    # 常用标签（全站汇总，搜索兜底与旧配置兼容用）
    TAGS = [
        "后入", "抱操", "极品少女", "清纯少女", "网黄主播", "推特网黄", "巨乳", "白虎",
        "口交", "中出", "自拍", "偷拍", "熟女", "人妻", "少妇", "制服", "丝袜", "美腿",
        "调教", "捆绑", "露出", "户外", "酒店", "学生", "医生", "护士", "空姐", "女仆",
        "母子", "姐弟", "兄妹", "翻牌", "探花", "约炮", "无套", "颜射", "口爆", "多人",
    ]

    # 各一级分类下的标签（= 二级目录），抓 /movie/{slug}/ 页标签云生成。
    # 站点没有标签总览页，只能逐分类采集；共 11 组 261 项（去重 132 项）。
    SUBCATS = {
        'zxsj': [
            '后入', '抱操', '极品少女', '清纯少女', 'andmlove', '巨乳', '推特网黄', '网黄主播', '白虎', '制服', '丝袜', '萌妹', '乱伦', '口交', 'AI成人短剧', 'AI短剧', '捆绑调教', '魔幻',
            '黑暗圣经', '下药迷奸', '内射', '强奸迷奸', '暴力', '中出', '剧情', '日韩三级', '探花', '探花泰浪', '小宝探花', '黑丝', '反差', '御姐', '胖哥探花', '丝袜诱惑', '制服诱惑', '大长腿',
        ],
        'tjgn': [
            '后入', '抱操', '极品少女', '清纯少女', 'andmlove', '巨乳', '推特网黄', '网黄主播', '白虎', '制服', '丝袜', '萌妹', '乱伦', '口交', 'AI成人短剧', 'AI短剧', '捆绑调教', '魔幻',
            '黑暗圣经', '下药迷奸', '内射', '强奸迷奸', '暴力', '中出', '剧情', '日韩三级', '探花', '探花泰浪', '小宝探花', '黑丝', '反差', '御姐', '胖哥探花', '丝袜诱惑', '制服诱惑', '大长腿',
        ],
        'tpzp': [
            '巨乳', '母狗', '自拍偷拍', '反差', '国产自拍', '偷拍自拍', '高颜值', '后入', '肥臀', '人妻', '高潮', '丝袜', '美乳', '口交', '少妇', '女上位', '国产', '少女',
        ],
        'whmx': [
            'andmlove', '巨乳', '推特网黄', '网黄主播', '白虎', '制服', '丝袜', '小橘妹妹', '少女', '后入', '蜜桃臀', '情趣', '乱伦', '口交', 'zxvipxx', '精神小妹', 'Mia', '台湾', '约炮',
            'AsyaxAsh', '玉足', '美腿', '黑丝', 'Bella贝拉', '潮喷', 'NTR', '婕咪', 'LunaLoveKiss', '肛交', '露娜妈妈', '御姐', '浅浅', 'Saki纱季', 'naomiiichannel', '车震',
            '野战', 'LMia', '女神',
        ],
        'snsf': [
            '口交', '后入', '少妇', '黑丝', '巨乳', '按摩店', '高潮', '偷情', '骑乘', '少妇熟女', '内射', '白虎', '嫩鲍', '老师', '乱伦', '人妻少妇', '师师', '熟女少妇', '熟女', '自慰', '调教',
        ],
        'llsn': [
            '丝袜', '巨乳', '极品少女', '清纯少女', '萌妹', '乱伦', '口交', '白虎', '捆绑', '黑丝', '后入', 'Coser', '制服', 'BBW', '母子', '野战', 'cos', '足交', '迷奸', 'JK', '内射',
            '网红', '二次元', '自慰', '调教', '白浆', '女仆', '骑乘',
        ],
        'jtll': [
            '丝袜', '家庭乱伦', '深喉口交', '白虎', '黑丝', '内射', '高潮', '后入', '骑乘', '口爆', '女仆', '巨乳', '调教', '自慰',
        ],
        'qjmj': [
            '下药迷奸', '内射', '强奸迷奸', '暴力', '制服诱惑', '后入', '国产', '白虎', '口交', '捆绑', '醉酒迷奸', '醉酒强奸', '黑丝', '粉穴',
        ],
        'hsam': [
            '白虎', '精油按摩', '高潮', '骑乘', '口交', '后入', '潮吹', 'spa', '内射', '按摩', '按摩会所', '少妇', '榨精', '乳推',
        ],
        'lqzk': [
            '巨乳', '自慰', '重口猎奇', '扩张', '母狗', '高潮', '丝袜', '异物', '骚穴', '颜射', '黑丝', '肛交', '肥臀', '拳交', '性虐',
        ],
        'jmtt': [
            'h动漫', '内射', '户外野战', '里番视频', 'NTR', '乳交', '耽美', '肛交', '3D成人动漫', '丝袜', '巨乳', '网袜', '潮吹', '御姐', '捆绑', '男同', '3P', '百合', 'SM', '双马尾',
            '无码', 'JK', '骑乘', '调教', '轮奸', '乱伦', '女仆',
        ],
    }

    # 封面图 AES-CBC 密钥（与 91crdj 同一套前端方案，密钥相同）
    IMG_KEY_RAW = "102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48"
    IMG_IV_RAW = "57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49"

    def getName(self):
        return "91Hub"

    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.HOST + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        self._cffi = None
        self._meta = {}      # id -> 列表页缓存
        return {}

    def destroy(self):
        try:
            if getattr(self, "session", None):
                self.session.close()
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def log(self, msg):
        try:
            print("[91hub] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass

    # ------------------------------------------------------------ 网络

    def cffi(self):
        if self._cffi is None:
            try:
                from curl_cffi import requests as cq
                self._cffi = cq.Session(impersonate="chrome124", timeout=30)
                self._cffi.headers.update(self.headers)
            except Exception:
                self._cffi = False
        return self._cffi

    def fetch(self, url, tries=3):
        last = ""
        for i in range(tries):
            try:
                r = self.session.get(url, timeout=25)
                if r.status_code == 200 and r.text:
                    return r.text
                if r.status_code == 404:
                    return ""
                last = "http %s" % r.status_code
            except Exception as e:
                last = type(e).__name__
            s = self.cffi()
            if s:
                try:
                    r = s.get(url)
                    if r.status_code == 200 and r.text:
                        return r.text
                except Exception as e:
                    last = type(e).__name__
            time.sleep(0.5 * (i + 1))
        self.log("fetch fail %s (%s)" % (url, last))
        return ""

    # ------------------------------------------------------------ eval 解包

    _D36 = string.digits + string.ascii_lowercase

    @classmethod
    def _sym(cls, n, a):
        out = "" if n < a else cls._sym(n // a, a)
        n = n % a
        return out + (chr(n + 29) if n > 35 else cls._D36[n])

    @classmethod
    def unpack(cls, js):
        """还原 eval(function(p,a,c,k,e,d){…}) 混淆（Dean Edwards packer）"""
        m = re.search(r"\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", js or "", re.S)
        if not m:
            return ""
        p, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split('|')
        for i in range(c - 1, -1, -1):
            if i < len(k) and k[i]:
                p = re.sub(r'\b' + re.escape(cls._sym(i, a)) + r'\b',
                           k[i].replace('\\', '\\\\'), p)
        return p

    # ------------------------------------------------------------ 工具

    @staticmethod
    def e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def d64(s):
        s = str(s or "")
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4)).decode("utf-8")

    @classmethod
    def _img_key_iv(cls):
        def conv(raw):
            return "".join(chr(int(x)) for x in raw.split("_")).encode("utf-8")
        return conv(cls.IMG_KEY_RAW), conv(cls.IMG_IV_RAW)

    def img_decrypt(self, body):
        """AES-CBC / NoPadding 解密封面密文。优先 pycryptodome，退 cryptography。"""
        key, iv = self._img_key_iv()
        data = body[:len(body) - len(body) % 16]
        if not data:
            return body
        try:
            from Crypto.Cipher import AES
            return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            c = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            return c.update(data) + c.finalize()
        except Exception as e:
            self.log("无 AES 库，封面无法解密: %s" % type(e).__name__)
            return body

    def proxy_url(self):
        try:
            u = self.getProxyUrl()
            return u if u else "http://127.0.0.1:9978/proxy?do=py"
        except Exception:
            return "http://127.0.0.1:9978/proxy?do=py"

    def proxy_img(self, url):
        """封面走本地代理解密。social-cover（明文 JPEG）与空值直接放行。"""
        if not url or not url.startswith("http"):
            return url or ""
        if "/social-cover/" in url:
            return url
        return "%s&type=img&url=%s" % (self.proxy_url(), self.e64(url))

    @staticmethod
    def _unesc(s):
        s = s or ""
        for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&#039;", "'"), ("&nbsp;", " ")):
            s = s.replace(a, b)
        return re.sub(r'\s+', ' ', s).strip()

    @staticmethod
    def _norm_ids(ids):
        """vod_id 是纯数字。兼容 list / str / int / 带 # 后缀 / 完整 URL。"""
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        v = str(ids or "").strip().split("#")[0].strip()
        m = re.search(r'/video/(\d+)', v)
        if m:
            return m.group(1)
        m = re.search(r'(\d{3,})', v)
        return m.group(1) if m else ""

    def list_url(self, tid, page=1):
        """type_id → 列表 URL。t_ 前缀=标签（兼容旧 ':' 与转义 '%3A'）"""
        t = str(tid or "zxsj").strip().replace("%3A", ":").replace("%3a", ":")
        if t.startswith("t:"):
            t = "t_" + t[2:]
        if t.startswith("t_"):
            path = "/tag/%s/" % quote(t[2:])
        else:
            path = "/movie/%s/" % t
        if int(page or 1) > 1:
            path += "page/%d/" % int(page)
        return self.HOST + path

    # ------------------------------------------------------------ 列表解析

    def parse_cards(self, html):
        vods = []
        if not html:
            return vods
        seen = set()
        for part in re.split(r'<div class="video-item"', html)[1:]:
            blk = part[:2400]
            m = re.search(r'/video/(\d+)/', blk)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic = self._unesc((re.search(r'data-src="(https://[^"]+)"', blk) or [None, ""])[1])
            pic = self.proxy_img(pic)      # 列表封面是 AES 密文，必须过代理解密
            title = self._unesc((re.search(
                r'<h3>\s*<a[^>]*>\s*([\s\S]{0,240}?)\s*</a>', blk) or [None, ""])[1])
            if not title:
                title = self._unesc((re.search(r'alt="([^"]{2,200})"', blk) or [None, ""])[1])
            dur = self._unesc((re.search(r'rounded-large[^>]*>\s*([\d:]+)\s*<', blk) or [None, ""])[1])
            views = (re.search(r'data-gsce231-real-view-count="(\d+)"', blk) or [None, ""])[1]
            date = (re.search(r'data-gsce231-publish-time="([\d-]+)', blk) or [None, ""])[1]
            remark = " · ".join([x for x in (dur, ("👁 " + views) if views else "") if x])
            self._meta[vid] = {"title": title, "pic": pic, "remark": remark, "date": date}
            vods.append({"vod_id": vid, "vod_name": title or vid,
                         "vod_pic": pic, "vod_remarks": remark})
        return vods

    @staticmethod
    def max_page(html):
        ps = [int(x) for x in re.findall(r'/page/(\d+)', html or "")]
        return max(ps) if ps else 1

    # ------------------------------------------------------------ 首页

    def homeContent(self, filter=False):
        classes = [{"type_id": t, "type_name": n} for t, n in self.CHANNELS]
        filters = {}
        if filter:
            # 二级目录：每个一级分类只展示自己的标签云，不做全站大杂烩
            for t, _ in self.CHANNELS:
                subs = self.SUBCATS.get(t) or self.TAGS
                filters[t] = [{
                    "key": "tag", "name": "二级分类",
                    "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in subs],
                }]
        data = {"class": classes, "filters": filters}
        try:
            data["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            data["list"] = []
        return data

    def homeVideoContent(self):
        vods = self.parse_cards(self.fetch(self.HOST + "/"))
        if not vods:
            vods = self.parse_cards(self.fetch(self.list_url("zxsj", 1)))
        return {"code": 1, "msg": "数据列表", "list": vods[:40]}

    # ------------------------------------------------------------ 分类

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend or {}
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        tag = (extend.get("tag") or "").strip()
        target = ("t_" + tag) if tag else tid

        html = self.fetch(self.list_url(target, page))
        vods = self.parse_cards(html)
        pc = self.max_page(html)
        if not vods and page > 1:
            pc = page - 1
        return {"code": 1, "msg": "数据列表", "list": vods, "page": page,
                "pagecount": max(pc, 1), "limit": 24, "total": max(pc, 1) * 24}

    # ------------------------------------------------------------ 详情

    def detailContent(self, ids):
        vid = self._norm_ids(ids)
        if not vid:
            return {"code": 0, "msg": "空 ids", "list": []}
        html = self.fetch("%s/video/%s/" % (self.HOST, vid))
        cached = self._meta.get(vid, {})

        title = self._unesc((re.search(r'<h1[^>]*>([\s\S]{0,300}?)</h1>', html or "") or [None, ""])[1])
        title = re.sub(r'\s*A片\s*$', '', title) or cached.get("title") or vid

        # 详情页 img[data-src] 是广告 GIF（所有片相同），真封面用 og:image
        # 注意 og:image 是 /social-cover/{base64}.jpeg 明文 JPEG，可直连，
        # proxy_img 内部会放行不做解密；缓存来的列表封面已是代理地址。
        pic = (re.search(r'property="og:image" content="([^"]+)', html or "") or [None, ""])[1] \
            or cached.get("pic") or ""
        pic = self.proxy_img(pic) if pic.startswith("http") else pic

        tags = [unquote(x) for x in dict.fromkeys(re.findall(r'/tag/([^"/]+)/"', html or ""))]
        date = (re.search(r'(\d{4}-\d{2}-\d{2})', html or "") or [None, ""])[1] or cached.get("date", "")

        content = "【%s】" % " | ".join([x for x in (
            ("发布 %s" % date) if date else "",
            ("标签 %s" % "、".join(tags[:6])) if tags else "",
        ) if x]) if (date or tags) else ""

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": "、".join(tags[:4]),
            "vod_year": date[:4],
            "vod_area": "国产",
            "vod_lang": "国语",
            "vod_remarks": cached.get("remark", ""),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": content,
            "vod_tag": ", ".join(tags[:20]),
            # token/auth_key 有时效 → 只存 id，playerContent 里实时解包
            "vod_play_from": "91Hub",
            "vod_play_url": "正片$%s" % vid,
        }
        return {"code": 1, "msg": "数据列表", "list": [vod],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    # ------------------------------------------------------------ 搜索

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        kw = str(key or "").strip()
        if not kw:
            return {"code": 0, "msg": "空关键词", "list": []}

        url = "%s/search/%s/" % (self.HOST, quote(kw))
        if page > 1:
            url += "page/%d/" % page
        html = self.fetch(url)
        vods = self.parse_cards(html)

        if not vods:
            # 兜底1：?keyword= 形态
            u2 = "%s/search/?keyword=%s" % (self.HOST, quote(kw))
            if page > 1:
                u2 += "&page=%d" % page
            html = self.fetch(u2)
            vods = self.parse_cards(html)
        if not vods and page == 1:
            # 兜底2：关键词命中标签
            if kw in self.TAGS:
                html = self.fetch(self.list_url("t_" + kw, 1))
                vods = self.parse_cards(html)
        pc = self.max_page(html)
        return {"code": 1, "msg": "数据列表", "list": vods, "page": page,
                "pagecount": max(pc, 1), "limit": 24, "total": max(pc, 1) * 24}

    # ------------------------------------------------------------ 播放

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        if raw.startswith("http"):
            return {"parse": 0, "playUrl": "", "url": raw, "header": {"User-Agent": self.UA}}

        vid = self._norm_ids(raw)
        url = ""
        for _ in range(2):
            html = self.fetch("%s/video/%s/" % (self.HOST, vid))
            i = (html or "").find('eval(function(p,a,c,k,e,')
            if i < 0:
                time.sleep(0.5)
                continue
            out = self.unpack(html[i:html.find('</script>', i)])
            m = re.search(r'"(/media/m3u8/[^"]+)"', out or "") or \
                re.search(r'"(https?://[^"]+\.m3u8[^"]*)"', out or "")
            if m:
                u = self._unesc(m.group(1)).replace("\\/", "/")
                url = u if u.startswith("http") else (self.HOST + u)
                break
            time.sleep(0.5)

        if not url:
            self.log("playerContent 未取到 m3u8: %s" % vid)
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        # 实测 m3u8 / key / 分片均不校验 Referer，直连即可
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": self.UA}}

    def localProxy(self, params):
        """本地代理：解密封面图。
        列表卡片 img[data-src] 返回的是 AES-CBC 密文（binary/octet-stream），
        与 91crdj 同一套前端方案、同一密钥。明文图（social-cover）原样回吐。"""
        params = params or {}
        ptype = str(params.get("type") or "img")
        raw = params.get("url") or ""
        try:
            url = self.d64(raw)
        except Exception:
            url = str(raw)
        if not url.startswith("http") or ptype != "img":
            return [404, "text/plain", b""]

        body = b""
        for i in range(3):
            try:
                r = self.session.get(url, timeout=20)
                if r.status_code == 200 and r.content:
                    body = r.content
                    break
            except Exception:
                pass
            time.sleep(0.4 * (i + 1))
        if not body:
            return [502, "text/plain", b""]

        def kind(b):
            if b[:2] == b'\xff\xd8':
                return "image/jpeg"
            if b[:8] == b'\x89PNG\r\n\x1a\n':
                return "image/png"
            if b[:3] == b'GIF':
                return "image/gif"
            if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
                return "image/webp"
            return ""

        # 已是明文图 → 直接回吐（别把好图解坏）
        ct = kind(body)
        if ct:
            return [200, ct, body]

        out = self.img_decrypt(body)
        ct = kind(out)
        if not ct:
            self.log("封面解密后魔数异常: %s" % out[:8].hex())
            return [200, "image/jpeg", body]
        return [200, ct, out]


# ------------------------------------------------------------------ 自测
if __name__ == "__main__":
    import urllib.parse as up

    s = Spider()
    s.init()

    print("=" * 20, "homeContent")
    h = s.homeContent(True)
    print("class  :", [c["type_name"] for c in h["class"]])
    print("二级目录:", [(t, len((h["filters"].get(t) or [{}])[0].get("value", [])) - 1)
                    for t, _ in s.CHANNELS])
    print("home   :", len(h.get("list", [])))
    for v in h.get("list", [])[:3]:
        print("   ", v["vod_id"], "|", v["vod_name"][:26], "|", v["vod_remarks"], "|", v["vod_pic"][:56])

    print("=" * 20, "categoryContent")
    for tid, name in s.CHANNELS[:5]:
        c = s.categoryContent(tid, "1")
        print("   %-6s %-6s n=%-3s pagecount=%s" % (tid, name, len(c["list"]), c["pagecount"]))
    p1 = s.categoryContent("tjgn", "1")["list"]
    p2 = s.categoryContent("tjgn", "2")["list"]
    ov = len({x["vod_id"] for x in p1} & {x["vod_id"] for x in p2})
    print("   tjgn p1=%d p2=%d overlap=%d" % (len(p1), len(p2), ov))
    ct = s.categoryContent("zxsj", "1", True, {"tag": "后入"})
    print("   二级 tag=后入  n=%-3s pagecount=%s" % (len(ct["list"]), ct["pagecount"]))
    ct2 = s.categoryContent("jmtt", "1", True, {"tag": "h动漫"})
    print("   二级 tag=h动漫 n=%-3s pagecount=%s" % (len(ct2["list"]), ct2["pagecount"]))
    print("   转义兼容 t%%3A后入 n=%s" % len(s.categoryContent("t%3A后入", "1")["list"]))

    print("=" * 20, "封面解密验证（localProxy type=img）")
    okc = badc = 0
    for v in p1[:4]:
        pu = v["vod_pic"]
        if "do=py" not in pu:
            print("   SKIP 非代理地址:", pu[:60]); continue
        q = dict(x.split("=", 1) for x in pu.split("?", 1)[1].split("&") if "=" in x)
        code, ct3, body = s.localProxy(q)
        good = code == 200 and body[:2] == b"\xff\xd8"
        okc += 1 if good else 0
        badc += 0 if good else 1
        print("   %s %s ct=%-11s bytes=%-7s magic=%s" % ("OK " if good else "BAD", code, ct3,
                                                        len(body), body[:4].hex()))
    print("   封面解密 %d/%d" % (okc, okc + badc))

    vid = p1[0]["vod_id"] if p1 else "308506"
    print("=" * 20, "detailContent ids 兼容", vid)
    for probe in (vid, [vid], int(vid), vid + "#x", "%s/video/%s/" % (s.HOST, vid)):
        it = (s.detailContent(probe).get("list") or [{}])[0]
        lbl = probe if len(str(probe)) < 26 else "…url…"
        print("   in=%-14r -> %s" % (lbl, it.get("vod_name", "")[:34]))
    it = s.detailContent(vid)["list"][0]
    print("   pic    :", it["vod_pic"][:74])
    print("   type   :", it["type_name"], "| year:", it["vod_year"], "| remark:", it["vod_remarks"])
    print("   tag    :", it["vod_tag"][:64])
    print("   content:", it["vod_content"][:74])

    print("=" * 20, "playerContent + 播放链验证")

    def try_get(url, timeout=35, tries=2):
        """CDN 偶发 RemoteDisconnected，自测里做容错重试"""
        for _ in range(tries):
            try:
                return s.session.get(url, timeout=timeout)
            except Exception:
                time.sleep(0.6)
        return None

    okc = 0
    for v in p1[:3]:
        p = s.playerContent("91Hub", v["vod_id"])
        u = p["url"]
        if not u:
            print("   %-8s 无地址" % v["vod_id"]); continue
        m = try_get(u, 25)
        if m is not None and m.status_code == 200 and "#EXT" in m.text:
            segs = [l.strip() for l in m.text.splitlines() if l.strip() and not l.startswith("#")]
            keys = re.findall(r'URI="([^"]+)"', m.text)
            rk = try_get(keys[0], 25) if keys else None
            rs = try_get(up.urljoin(u, segs[0]), 35) if segs else None
            print("   %-8s m3u8=200 segs=%-4s key=%s/%sB seg=%s/%sB AES=%s" % (
                v["vod_id"], len(segs),
                rk.status_code if rk is not None else "-", len(rk.content) if rk is not None else 0,
                rs.status_code if rs is not None else "-", len(rs.content) if rs is not None else 0,
                "EXT-X-KEY" in m.text))
            okc += 1
        else:
            print("   %-8s m3u8=%s" % (v["vod_id"], m.status_code if m is not None else "连接失败"))
    print("   播放可用 %d/3" % okc)

    print("=" * 20, "searchContent")
    for kw in ("中文", "后入", "探花"):
        r = s.searchContent(kw)
        print("   %-4s n=%-3s pagecount=%-3s %s" % (kw, len(r["list"]), r["pagecount"],
              [x["vod_name"][:16] for x in r["list"][:2]]))
    s.destroy()
