# -*- coding: utf-8 -*-
# ---------------------------------------------------------------
# 沙发TV (52sofa.tv)  TVBox / 影视仓 / CatVod  Python 爬虫源
#
# 架构   : Nuxt3 SPA + 全加密 JSON API
# 协议   : POST /api/{path}
#          key  = HMAC-SHA256(salt="x3t8rvtaescfe38s", msg=requestId的hex字节)
#          body = base64( IV(16) + AES-CBC-Pkcs7( gzip( JSON ) ) )
#          resp = base64( IV(16) + AES-CBC-Pkcs7( gzip( JSON ) ) )   同 key
#          headers 必带 requestId / time / version / deviceType，
#          请求体必带非空 deviceId，否则返回 errorCode 2001「安全性错误DD!」
# 端点   : /system/info      站点配置
#          /movie/tag        分类 + 标签 + 年份 + 地区 + 语言 + 排序
#          /search/movie     列表 & 搜索（分页，支持 cat_id/tag_id/keyword/order/years/area/language）
#          /movie/detail     详情 + all_links(分集) + play_links(线路)
# 播放   : play_links[].m3u8_url → /api/m3u8/p/{hash}.m3u8（明文可直取，AES-128 HLS）
#          line1 / line2 实测可播；line3 常 403，已排到最后
# ---------------------------------------------------------------
import base64
import gzip
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def init(self, extend=""):
            pass

        def destroy(self):
            pass

        def getName(self):
            return ""

        def homeContent(self, filter=False):
            return {"class": []}

        def homeVideoContent(self):
            return {"list": []}

        def categoryContent(self, tid, pg="1", filter=False, extend=None):
            return {"list": []}

        def detailContent(self, ids):
            return {"list": []}

        def searchContent(self, key, quick=False, pg="1"):
            return {"list": []}

        def playerContent(self, flag, id, vipFlags=None):
            return {"parse": 0, "url": "", "header": {}}

        def localProxy(self, params):
            return []

        def isVideoFormat(self, url):
            return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)", url or ""))

        def manualVideoCheck(self):
            return False


# ---------------------------------------------------------------
# AES 实现：优先 pycryptodome，其次 cryptography，最后纯 Python 兜底
# ---------------------------------------------------------------
def _aes_cbc(key, iv, data, encrypt):
    try:
        from Crypto.Cipher import AES
        c = AES.new(key, AES.MODE_CBC, iv)
        return c.encrypt(data) if encrypt else c.decrypt(data)
    except ImportError:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        c = Cipher(algorithms.AES(key), modes.CBC(iv))
        op = c.encryptor() if encrypt else c.decryptor()
        return op.update(data) + op.finalize()
    except ImportError:
        pass
    raise RuntimeError("no AES backend (need pycryptodome or cryptography)")


def _aes_ecb_dec(key, data):
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_ECB).decrypt(data)
    except ImportError:
        pass
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    op = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return op.update(data) + op.finalize()


def _pad(b):
    n = 16 - len(b) % 16
    return b + bytes([n]) * n


def _unpad(b):
    if not b:
        return b
    n = b[-1]
    return b[:-n] if 0 < n <= 16 else b


class Spider(BaseSpider):
    HOST = "https://52sofa.tv"
    SALT = b"x3t8rvtaescfe38s"
    VERSION = "1.0.0"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 主分类（cat_id）；同名 id 是站点历史遗留，取内容最全的
    MAIN_CATS = [
        ("2", "连续剧"), ("1", "电影"), ("6", "短剧"), ("4", "动漫"),
        ("3", "综艺"), ("5", "纪录片"), ("8", "电影解说"), ("7", "音乐"),
    ]
    # 各主分类下的热门标签（cat_id -> [(tag_id, name)]）
    TAGS = {
        "1": [("222", "动作"), ("227", "喜剧"), ("235", "爱情"), ("226", "科幻"),
              ("236", "恐怖"), ("231", "悬疑"), ("234", "惊悚"), ("219", "剧情"),
              ("225", "奇幻"), ("242", "冒险"), ("239", "犯罪"), ("259", "战争"),
              ("245", "动画"), ("258", "纪录"), ("280", "灾难"), ("303", "经典"),
              ("260", "香港"), ("276", "台湾"), ("318", "欧美"), ("306", "日本"),
              ("243", "网络电影"), ("58", "近期热门")],
        "2": [("278", "国产剧"), ("25", "韩剧"), ("59", "日剧"), ("60", "欧美剧"),
              ("61", "港剧"), ("62", "台剧"), ("50", "泰剧"), ("63", "新马剧"),
              ("220", "言情"), ("228", "古装"), ("232", "玄幻"), ("238", "都市"),
              ("229", "历史"), ("233", "谍战"), ("241", "科幻"), ("252", "喜剧"),
              ("285", "武侠"), ("292", "罪案"), ("294", "青春"), ("295", "家庭"),
              ("301", "悬疑"), ("304", "宫廷"), ("299", "战争"), ("49", "其他剧")],
        "3": [("52", "国产综艺"), ("51", "韩国综艺"), ("40", "港台综艺"),
              ("38", "日本综艺"), ("45", "欧美综艺"), ("216", "真人秀"),
              ("224", "选秀"), ("254", "脱口秀"), ("261", "搞笑"), ("267", "竞技"),
              ("251", "网综"), ("288", "演唱会"), ("293", "晚会"), ("281", "访谈"),
              ("274", "情感"), ("35", "其他综艺")],
        "4": [("24", "国产动漫"), ("18", "日韩动漫"), ("46", "欧美动漫"),
              ("71", "港台动漫"), ("73", "国漫修仙"), ("221", "热血"),
              ("223", "格斗"), ("247", "机战"), ("290", "恋爱"), ("296", "校园"),
              ("305", "治愈"), ("257", "魔幻"), ("253", "科幻"), ("270", "爆笑"),
              ("57", "四月新番"), ("67", "七月新番"), ("68", "经典国漫"),
              ("271", "动画电影"), ("11", "其他动漫")],
        "5": [("230", "文化"), ("298", "探索")],
        "6": [("803", "逆袭"), ("804", "重生"), ("807", "穿越"), ("1246", "漫剧"),
              ("39", "甜宠"), ("37", "虐恋"), ("56", "复仇"), ("54", "系统"),
              ("55", "AI"), ("809", "神豪"), ("810", "萌宝"), ("811", "强者"),
              ("1240", "大女主"), ("1245", "古风"), ("320", "古装"),
              ("313", "现代"), ("312", "民国"), ("310", "年代"), ("308", "都市"),
              ("311", "职场"), ("315", "校园"), ("316", "宫廷"), ("309", "乡村"),
              ("1329", "擦边短剧"), ("34", "韩国"), ("42", "男男")],
        "7": [("287", "歌曲"), ("282", "MV"), ("302", "现场"), ("286", "舞蹈"),
              ("29", "摇滚"), ("30", "古典"), ("31", "民谣"), ("32", "网络歌曲")],
        "8": [("275", "电影解说"), ("279", "流行")],
    }
    YEARS = [("1", "2026"), ("2", "2025"), ("3", "2024"), ("4", "2023"), ("5", "更早")]
    AREAS = ["内地剧", "韩剧", "美剧", "港剧", "台剧", "日剧", "泰剧", "其他剧"]
    LANGS = ["国语", "粤语", "英语", "韩语", "日语", "泰语", "法语", "其他语"]
    ORDERS = [("new", "最新"), ("favorite", "人气"), ("ranking", "评分"), ("rand", "推荐")]

    PAGE_SIZE = 24
    LINE_ORDER = ["line1", "line2", "line4", "line5", "line3"]

    # 封面为 AES-128-ECB 加密的 .bnc；密钥来自 /system/info 的 img_key，
    # init 时动态拉取，这里只作为拉取失败时的兜底
    IMG_KEY_FALLBACK = "525202f9149e061d"
    IMG_MAGIC = [
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF8", "image/gif"),
        (b"RIFF", "image/webp"),
        (b"BM", "image/bmp"),
    ]

    # ------------------------------------------------------------------
    def getName(self):
        return "沙发TV"

    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Content-Type": "text/plain",
            "Origin": self.HOST,
            "Referer": self.HOST + "/",
            "version": self.VERSION,
            "deviceType": "web",
        }
        self.session = requests.Session()
        self.session.trust_env = False
        # deviceId 必须非空且稳定（服务端会校验）
        self.device_id = hashlib.md5(("tvbox-sofa-" + str(uuid.getnode())).encode()).hexdigest()
        self.token = ""
        self.img_key = self.IMG_KEY_FALLBACK
        try:
            r = self._api("/login/device", {"channel_code": None, "share_code": None})
            d = r.get("data") or {}
            tk, uid = d.get("token"), d.get("user_id") or d.get("userId")
            if tk:
                self.token = ("%s_%s" % (tk, uid)) if uid else tk
        except Exception as e:
            self._log("device login skip: %s" % e)
        # 封面解密密钥来自站点配置，随时可能轮换，动态拉取
        try:
            info = self._api("/system/info", {"channel_code": None, "share_code": None})
            k = ((info.get("data") or {}).get("img_key") or "").strip()
            if len(k) == 16:
                self.img_key = k
        except Exception as e:
            self._log("img_key fallback: %s" % e)
        return self

    def destroy(self):
        try:
            if getattr(self, "session", None):
                self.session.close()
        except Exception:
            pass
        self.session = None

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", url or ""))

    def manualVideoCheck(self):
        return False

    def _log(self, msg):
        try:
            print("[沙发TV] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 加密 API 调用
    # ------------------------------------------------------------------
    def _api(self, path, data=None, retry=2):
        last = None
        for _ in range(retry + 1):
            try:
                return self._api_once(path, data)
            except Exception as e:
                last = e
                self._log("api %s fail: %s" % (path, str(e)[:80]))
        raise last if last else RuntimeError("api failed")

    def _api_once(self, path, data):
        req_id = str(uuid.uuid4())
        key = hmac.new(self.SALT, bytes.fromhex(req_id.replace("-", "")),
                       hashlib.sha256).digest()
        payload = json.dumps({"data": data or {}, "token": self.token,
                              "deviceId": self.device_id},
                             separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        iv = os.urandom(16)
        body = base64.b64encode(iv + _aes_cbc(key, iv, _pad(gzip.compress(payload)), True))

        hdr = dict(self.headers)
        hdr["requestId"] = req_id
        hdr["time"] = str(int(time.time() * 1000))[:11]

        text = None
        try:
            r = self.session.post(self.HOST + "/api" + path, data=body,
                                  headers=hdr, timeout=20)
            text = r.text
        except Exception as e:
            self._log("requests fail: %s" % str(e)[:60])
            from curl_cffi import requests as cr
            r = cr.post(self.HOST + "/api" + path, data=body, headers=hdr,
                        impersonate="chrome120", timeout=20)
            text = r.text

        raw = base64.b64decode(text)
        dec = _unpad(_aes_cbc(key, raw[:16], raw[16:], False))
        try:
            dec = gzip.decompress(dec)
        except Exception:
            pass
        return json.loads(dec.decode("utf-8", "ignore"))

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", " ", str(s))
        for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                     ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")):
            s = s.replace(a, b)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _norm_id(ids):
        """兼容 list / str / 完整 url / detail/xxx / xxx@lid 形态"""
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        v = str(ids).strip()
        v = v.split("?")[0].split("#")[0]
        if "detail/" in v:
            v = v.rsplit("detail/", 1)[1]
        return v.strip("/").split("/")[0]

    def _vod(self, it):
        remarks = self._clean(it.get("duration")) or self._clean(it.get("update_status"))
        if remarks in ("0", "0集"):
            remarks = ""
        score = self._clean(it.get("score_value"))
        if score and score not in ("0", "0.0"):
            remarks = ("%s %s" % (remarks, score)).strip()
        return {
            "vod_id": str(it.get("id", "")),
            "vod_name": self._clean(it.get("name")),
            "vod_pic": self._proxy_pic(self._clean(it.get("img"))),
            "vod_remarks": remarks,
        }

    # ------------------------------------------------------------------
    # 封面：.bnc 是 AES-128-ECB 密文，播放器无法直接显示，
    #       走 localProxy 边下边解，返回真实图片字节
    # ------------------------------------------------------------------
    def _proxy_pic(self, url):
        if not url or not url.startswith("http"):
            return url or ""
        try:
            base = self.getProxyUrl()
        except Exception:
            return url          # 非 TVBox 环境（本地调试）直接返回原图
        enc = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
        return "%s&url=%s&type=img" % (base, enc)

    def _decrypt_pic(self, raw):
        """整体 AES-128-ECB 解密并去 PKCS7；返回 (mime, bytes)"""
        if not raw:
            return None, b""
        for magic, mime in self.IMG_MAGIC:
            if raw[:len(magic)] == magic:
                return mime, raw           # 已是明文，直接透传
        key = (self.img_key or self.IMG_KEY_FALLBACK).encode("utf-8")
        n = len(raw) // 16 * 16
        try:
            dec = _aes_ecb_dec(key, raw[:n]) + raw[n:]
        except Exception as e:
            self._log("pic decrypt fail: %s" % e)
            return None, b""
        dec = _unpad(dec)
        for magic, mime in self.IMG_MAGIC:
            if dec[:len(magic)] == magic:
                return mime, dec
        return None, b""

    def _page_result(self, d, pg):
        items = (d or {}).get("data") or []
        vods, seen = [], set()
        for it in items:
            vid = str(it.get("id", ""))
            if not vid or vid in seen:
                continue
            seen.add(vid)
            vods.append(self._vod(it))
        try:
            page = int((d or {}).get("current_page") or pg)
        except Exception:
            page = int(pg)
        try:
            count = int((d or {}).get("last_page") or 1)
        except Exception:
            count = 1
        return {"list": vods, "page": page, "pagecount": max(count, page),
                "limit": int((d or {}).get("page_size") or self.PAGE_SIZE),
                "total": int((d or {}).get("total") or len(vods))}

    # ------------------------------------------------------------------
    # 首页 / 分类
    # ------------------------------------------------------------------
    def homeContent(self, filter=False):
        classes = [{"type_id": c, "type_name": n} for c, n in self.MAIN_CATS]
        filters = {}
        for cid, _ in self.MAIN_CATS:
            blocks = []
            tags = self.TAGS.get(cid) or []
            if tags:
                blocks.append({"key": "tag_id", "name": "类型",
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": n, "v": v} for v, n in tags]})
            blocks.append({"key": "years", "name": "年份",
                           "value": [{"n": "全部", "v": ""}] +
                                    [{"n": n, "v": v} for v, n in self.YEARS]})
            if cid in ("1", "2", "4", "6"):
                blocks.append({"key": "area", "name": "地区",
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": a, "v": a} for a in self.AREAS]})
                blocks.append({"key": "language", "name": "语言",
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": a, "v": a} for a in self.LANGS]})
            blocks.append({"key": "order", "name": "排序",
                           "value": [{"n": n, "v": v} for v, n in self.ORDERS]})
            filters[cid] = blocks

        result = {"class": classes, "filters": filters}
        try:
            result["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            r = self._api("/search/movie", {"order": "new", "page": 1,
                                           "page_size": self.PAGE_SIZE})
            return {"list": self._page_result(r.get("data"), 1)["list"]}
        except Exception as e:
            self._log("home fail: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend if isinstance(extend, dict) else {}
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        body = {"cat_id": str(tid), "page": page, "page_size": self.PAGE_SIZE,
                "order": extend.get("order") or "new"}
        for k in ("tag_id", "years", "area", "language"):
            v = (extend.get(k) or "").strip()
            if v:
                body[k] = v
        try:
            r = self._api("/search/movie", body)
            return self._page_result(r.get("data"), page)
        except Exception as e:
            self._log("category fail: %s" % e)
            return {"list": [], "page": page, "pagecount": page,
                    "limit": self.PAGE_SIZE, "total": 0}

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def detailContent(self, ids):
        vid = self._norm_id(ids)
        if not vid:
            return {"list": []}
        try:
            r = self._api("/movie/detail", {"id": vid, "lid": "", "code": "",
                                            "nav_code": "home"})
        except Exception as e:
            self._log("detail fail: %s" % e)
            return {"list": []}
        if r.get("status") != "y":
            self._log("detail err: %s" % r.get("error"))
            return {"list": []}
        d = r.get("data") or {}

        eps = []
        for i, lk in enumerate(d.get("all_links") or []):
            lid = lk.get("id")
            if not lid:
                continue
            name = self._clean(lk.get("name")) or ("第%d集" % (i + 1))
            eps.append("%s$%s@%s" % (name, vid, lid))
        if not eps:
            eps = ["正片$%s@" % vid]

        codes = [(p.get("code"), self._clean(p.get("name")) or p.get("code"))
                 for p in (d.get("play_links") or []) if p.get("code")]
        if codes:
            codes.sort(key=lambda x: self.LINE_ORDER.index(x[0])
                       if x[0] in self.LINE_ORDER else len(self.LINE_ORDER))
            lines = ["%s|%s" % (n, c) for c, n in codes]
        else:
            lines = ["线路1|line1"]

        actors = ",".join([self._clean(u.get("nickname"))
                           for u in (d.get("user_id") or []) if u.get("nickname")])
        director = self._clean((d.get("director") or {}).get("nickname"))
        tags = ",".join([self._clean(t.get("name")) for t in (d.get("tags") or [])])

        remarks = self._clean(d.get("duration"))
        if not remarks or remarks in ("0", "0集"):
            n = len(eps)
            remarks = ("全%d集" % n) if n > 1 else ""
        score = self._clean(d.get("score_value"))
        if score and score not in ("0", "0.0"):
            remarks = ("%s %s分" % (remarks, score)).strip()

        vod = {
            "vod_id": vid,
            "vod_name": self._clean(d.get("name")),
            "vod_pic": self._proxy_pic(self._clean(d.get("img"))),
            "type_name": tags or self._clean(d.get("category_text")),
            "vod_year": self._clean(d.get("issue_year")),
            "vod_area": self._clean(d.get("area")),
            "vod_lang": self._clean(d.get("language")),
            "vod_remarks": remarks,
            "vod_actor": actors,
            "vod_director": director if director not in ("未知",) else "",
            "vod_content": self._clean(d.get("description")) or "暂无简介",
            "vod_play_from": "$$$".join(lines),
            "vod_play_url": "$$$".join(["#".join(eps) for _ in lines]),
        }
        return {"list": [vod]}

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        try:
            r = self._api("/search/movie", {"keywords": key, "page": page,
                                           "page_size": self.PAGE_SIZE})
            res = self._page_result(r.get("data"), page)
            kw = str(key or "").strip()
            if kw:
                hit = [v for v in res["list"] if kw in v["vod_name"]]
                if hit:
                    res["list"] = hit + [v for v in res["list"] if v not in hit]
            return res
        except Exception as e:
            self._log("search fail: %s" % e)
            return {"list": []}

    # ------------------------------------------------------------------
    # 播放：id = "{vid}@{lid}"，flag = "线路名|code"
    # ------------------------------------------------------------------
    def playerContent(self, flag, id, vipFlags=None):
        raw = id
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        raw = str(raw).strip()
        vid, _, lid = raw.partition("@")
        code = ""
        if flag and "|" in str(flag):
            code = str(flag).rsplit("|", 1)[1]

        try:
            r = self._api("/movie/detail", {"id": vid, "lid": lid, "code": code,
                                            "nav_code": "home"})
            pls = ((r.get("data") or {}).get("play_links")) or []
            pick = None
            for p in pls:
                if code and p.get("code") == code and p.get("m3u8_url"):
                    pick = p
                    break
            if pick is None:
                ordered = sorted([p for p in pls if p.get("m3u8_url")],
                                 key=lambda p: self.LINE_ORDER.index(p.get("code"))
                                 if p.get("code") in self.LINE_ORDER else len(self.LINE_ORDER))
                pick = ordered[0] if ordered else None
            if pick:
                u = pick["m3u8_url"]
                url = self.HOST + u if u.startswith("/") else u
                return {"parse": 0, "playUrl": "", "url": url,
                        "header": json.dumps({"User-Agent": self.UA,
                                              "Referer": self.HOST + "/"})}
        except Exception as e:
            self._log("player fail: %s" % e)
        return {"parse": 1, "playUrl": "",
                "url": "%s/home/detail/%s/%s" % (self.HOST, vid, lid),
                "header": json.dumps({"User-Agent": self.UA})}

    def localProxy(self, params):
        """type=img: 下载 .bnc 封面 → AES-128-ECB 解密 → 返回真实图片"""
        try:
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    params = {}
            params = params if isinstance(params, dict) else {}
            if str(params.get("type") or "img") != "img":
                return [404, "text/plain", b""]

            url = str(params.get("url") or "")
            if not url:
                return [404, "text/plain", b""]
            if not url.startswith("http"):
                try:
                    url = base64.urlsafe_b64decode(
                        url + "=" * ((4 - len(url) % 4) % 4)).decode("utf-8")
                except Exception:
                    return [404, "text/plain", b""]
            if not url.startswith("http"):
                return [404, "text/plain", b""]

            raw = b""
            hdr = {"User-Agent": self.UA, "Referer": self.HOST + "/"}
            try:
                r = self.session.get(url, headers=hdr, timeout=20)
                if r.status_code == 200:
                    raw = r.content
            except Exception as e:
                self._log("pic fetch fail: %s" % str(e)[:60])
            if not raw:
                try:
                    from curl_cffi import requests as cr
                    r = cr.get(url, headers=hdr, impersonate="chrome120", timeout=20)
                    if r.status_code == 200:
                        raw = r.content
                except Exception as e:
                    self._log("pic cffi fail: %s" % str(e)[:60])
            if not raw:
                return [502, "text/plain", b""]

            mime, data = self._decrypt_pic(raw)
            if not data:
                return [502, "text/plain", b""]
            return [200, mime or "image/jpeg", data]
        except Exception as e:
            self._log("localProxy fail: %s" % e)
            return [500, "text/plain", b""]
