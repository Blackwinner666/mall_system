# -*- coding: utf-8 -*-
"""微信公众号 定时 / 批量发布 内置调度器 + 发布日志 / 分析。

与 app.py 解耦：
- 仅在 __main__ 启动调度线程时由 app 传入 app 引用（init_scheduler(app)）。
- DB 操作统一在 app.app_context() 内进行，并惰性 import get_db 以避免循环依赖。
- 表结构由 app.py 的 init_db() 负责创建（scheduled_posts / publish_queue / publish_log）。
"""
import threading
import time
import json
import os
import re as _re
import base64
import tempfile
import zlib
import struct
from datetime import datetime
from urllib.parse import urlparse

import requests

# 模块自身所在目录（C:\mall_system）。调度器守护线程的 cwd 是 system32，
# 不能用相对路径找本地图片，一律以 ROOT 为基准拼接绝对路径。
ROOT = os.path.dirname(os.path.abspath(__file__))

APP_REF = None
_SCHEDULER_STARTED = False


# ============================================================
# 启动 / 主循环
# ============================================================
def init_scheduler(app):
    global APP_REF, _SCHEDULER_STARTED
    APP_REF = app
    if _SCHEDULER_STARTED:
        return
    _SCHEDULER_STARTED = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _loop():
    """每 30 秒扫描一次到期任务与批量队列。"""
    import traceback
    while True:
        try:
            _tick()
        except Exception:
            # 不要静默吞掉异常，否则调度器卡住时无法排查
            traceback.print_exc()
        time.sleep(30)


def _get_db():
    from app import get_db
    return get_db()


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ============================================================
# 任务管理 API（供 app.py 的路由调用）
# ============================================================
def create_scheduled_post(title, digest, content, schedule_time, author='', ptype='single', mode='publish', cover_media_id=''):
    """mode: 'publish'（到时建草稿并提交发布）或 'draft'（到时仅建草稿）。
    cover_media_id: 生成阶段就上传好的封面永久素材 media_id，存进 media_id 列，供 _do_publish 用作草稿封面。
    """
    with APP_REF.app_context():
        db = _get_db()
        cur = db.execute(
            "INSERT INTO scheduled_posts (title, digest, content, author, schedule_time, status, type, mode, media_id, created_at) "
            "VALUES (?,?,?,?,?,'pending',?,?,?,?)",
            (title, digest, content, author, schedule_time, ptype, mode, cover_media_id or '', _now()))
        db.commit()
        return cur.lastrowid


def list_scheduled():
    with APP_REF.app_context():
        db = _get_db()
        rows = db.execute("SELECT * FROM scheduled_posts ORDER BY schedule_time DESC").fetchall()
        return [dict(r) for r in rows]


def cancel_scheduled(pid):
    """取消并删除一条定时任务（不可恢复）。"""
    with APP_REF.app_context():
        db = _get_db()
        db.execute("DELETE FROM scheduled_posts WHERE id=?", (pid,))
        db.commit()
        return True


def resolve_scheduled(pid, action, table='scheduled_posts'):
    """处理「发布失败但草稿已建好」的待决任务（status='needs_choice'）。

    action:
      'keep_draft' -> 草稿已在公众号草稿箱，仅标记为已转草稿（status='draft'）
      'clear'      -> 删除该条任务记录（清空此条内容）
    """
    if table not in ('scheduled_posts', 'publish_queue'):
        table = 'scheduled_posts'
    with APP_REF.app_context():
        db = _get_db()
        row = db.execute("SELECT * FROM %s WHERE id=?" % table, (pid,)).fetchone()
        if not row:
            return False, '任务不存在'
        if action == 'keep_draft':
            # 草稿早已建好（media_id 已在微信草稿箱），此处仅把记录标记为已转草稿
            db.execute("UPDATE %s SET status='draft', detail='用户已选择转为草稿，草稿已在公众号草稿箱' WHERE id=?" % table, (pid,))
            db.commit()
            log_publish('resolve', row['title'], 'draft', '用户选择转为草稿', db=db)
            return True, '已转为草稿'
        elif action == 'clear':
            db.execute("DELETE FROM %s WHERE id=?" % table, (pid,))
            db.commit()
            return True, '已清空该条内容'
        return False, '未知操作'


def enqueue_batch(items):
    """items: list of dict{title, digest, content, author}"""
    with APP_REF.app_context():
        db = _get_db()
        ids = []
        for it in items:
            cur = db.execute(
                "INSERT INTO publish_queue (title, digest, content, author, status, created_at) "
                "VALUES (?,?,?,?,'queued',?)",
                (it.get('title', ''), it.get('digest', ''), it.get('content', ''),
                 it.get('author', ''), _now()))
            ids.append(cur.lastrowid)
        db.commit()
        return ids


def list_queue():
    with APP_REF.app_context():
        db = _get_db()
        rows = db.execute("SELECT * FROM publish_queue ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# ============================================================
# 发布核心（复用微信草稿接口）
# ============================================================
def _wechat_token(appid, appsecret):
    r = requests.get('https://api.weixin.qq.com/cgi-bin/token',
                     params={'grant_type': 'client_credential', 'appid': appid, 'secret': appsecret},
                     timeout=15).json()
    if 'access_token' not in r:
        raise Exception('获取微信token失败: ' + r.get('errmsg', str(r)))
    return r['access_token']


def _wechat_create_draft(appid, appsecret, articles):
    token = _wechat_token(appid, appsecret)
    # 必须用 UTF-8 字节发送且 ensure_ascii=False，否则 requests 的 json= 会生成 \uXXXX 转义，
    # 微信草稿接口在某些情况下会把转义序列当字面量保存，导致文章出现乱码。
    payload = json.dumps({'articles': articles}, ensure_ascii=False).encode('utf-8')
    resp = requests.post('https://api.weixin.qq.com/cgi-bin/draft/add',
                         params={'access_token': token},
                         data=payload,
                         headers={'Content-Type': 'application/json; charset=utf-8'},
                         timeout=30).json()
    if 'media_id' not in resp:
        raise Exception('微信草稿创建失败: ' + resp.get('errmsg', str(resp)))
    return resp['media_id']


def _wechat_publish(appid, appsecret, media_id):
    """把草稿提交「发布」（freepublish/submit）。

    发布与群发的区别：发布不会推送给粉丝、不占群发次数、一天可多次；
    粉丝需搜索文章标题或点你分享的链接才看得到。个人公众号（未认证）通常
    只能走这条路（群发接口需微信认证，会返回 48001）。
    发布是异步的，这里提交后轮询状态给出确定结果。"""
    token = _wx_token(appid, appsecret)
    resp = requests.post('https://api.weixin.qq.com/cgi-bin/freepublish/submit',
                         params={'access_token': token},
                         json={'media_id': media_id}, timeout=30).json()
    if resp.get('errcode', 0) != 0:
        return False, '微信发布提交失败: errcode=%s %s' % (resp.get('errcode'), resp.get('errmsg'))
    publish_id = resp.get('publish_id')
    # 轮询发布结果（最多约 16s），status: 0成功 1发布中 2原创失败 3常规失败 4审核不通过
    for _ in range(8):
        st = requests.get('https://api.weixin.qq.com/cgi-bin/freepublish/get',
                          params={'access_token': token, 'publish_id': publish_id}, timeout=30).json()
        status = st.get('publish_status')
        if status == 0:
            item = (st.get('article_detail') or {}).get('item', [{}])[0]
            url = item.get('article_url', '')
            return True, '已发布（不推送粉丝）publish_id=%s 链接=%s' % (publish_id, url)
        if status in (2, 3, 4):
            return False, '发布未通过: status=%s %s' % (status, st.get('errmsg', ''))
        time.sleep(2)
    return True, '已提交发布 publish_id=%s（发布中，稍后可在公众号查看）' % publish_id


# ============================================================
# 图片转微信 CDN（草稿接口只认自家图）
# ============================================================
_WX_IMG_CACHE = {}        # 本地路径 -> 微信 url（避免重复上传）
_WX_TOKEN_CACHE = {'token': None, 'exp': 0}


def _wx_token(appid, appsecret):
    now = time.time()
    if _WX_TOKEN_CACHE['token'] and _WX_TOKEN_CACHE['exp'] > now + 300:
        return _WX_TOKEN_CACHE['token']
    resp = requests.get('https://api.weixin.qq.com/cgi-bin/token',
                        params={'grant_type': 'client_credential', 'appid': appid, 'secret': appsecret},
                        timeout=15).json()
    if 'access_token' not in resp:
        raise Exception('获取微信token失败: ' + resp.get('errmsg', str(resp)))
    _WX_TOKEN_CACHE['token'] = resp['access_token']
    _WX_TOKEN_CACHE['exp'] = now + 7000
    return resp['access_token']


def _wx_upload_local(local_path, appid, appsecret):
    """上传一张本地图片到微信永久素材库（material/add_material，type=image），
    返回 (url, media_id)。注意：
    - 草稿 draft/add 正文图片只认永久素材库返回的 url（临时 media/uploadimg 会被拒）；
    - draft/add 还要求每篇图文带 thumb_media_id（封面），且必须是永久素材的 media_id。"""
    if not appid or not appsecret:
        raise Exception('未配置微信AppID/AppSecret')
    if local_path in _WX_IMG_CACHE:
        return _WX_IMG_CACHE[local_path]
    token = _wx_token(appid, appsecret)
    ext = local_path.lower()
    if ext.endswith(('.jpg', '.jpeg')):
        mime = 'image/jpeg'
    elif ext.endswith('.gif'):
        mime = 'image/gif'
    elif ext.endswith('.webp'):
        mime = 'image/webp'
    else:
        mime = 'image/png'
    with open(local_path, 'rb') as f:
        up = requests.post('https://api.weixin.qq.com/cgi-bin/material/add_material',
                           params={'access_token': token, 'type': 'image'},
                           files={'media': (os.path.basename(local_path), f, mime)},
                           timeout=60).json()
    if 'url' not in up or 'media_id' not in up:
        raise Exception('微信上传图片失败: ' + up.get('errmsg', str(up)))
    _WX_IMG_CACHE[local_path] = (up['url'], up['media_id'])
    return up['url'], up['media_id']


def _make_default_cover():
    """生成一张默认封面 PNG（纯色），返回临时文件路径。"""
    w, h, color = 900, 500, (7, 193, 96)  # 微信绿
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(color)
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    fd, p = tempfile.mkstemp(suffix='.png')
    with os.fdopen(fd, 'wb') as f:
        f.write(sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b''))
    return p


_DEFAULT_COVER_MID = {'mid': None}

def _default_cover_mid(appid, appsecret):
    """没有正文图片时，用一张默认封面作为 thumb_media_id。"""
    if _DEFAULT_COVER_MID['mid']:
        return _DEFAULT_COVER_MID['mid']
    p = _make_default_cover()
    try:
        _, mid = _wx_upload_local(p, appid, appsecret)
    finally:
        try:
            os.remove(p)
        except Exception:
            pass
    _DEFAULT_COVER_MID['mid'] = mid
    return mid


def _resolve_image(url):
    """判断一张图该怎么处理：('keep', url) 已是微信图 / ('upload', 本地路径) 需上传 / ('drop', None) 丢弃。"""
    if not url:
        return ('drop', None)
    if 'mmbiz.qpic.cn' in url:          # 已经是微信 CDN 图，直接用
        return ('keep', url)
    if url.startswith('data:'):         # data URI -> 解码成临时文件再上传
        m = _re.match(r'data:image/([a-zA-Z0-9.+-]+);base64,(.+)', url, _re.S)
        if m:
            ext = {'jpeg': 'jpg', 'jpg': 'jpg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}.get(m.group(1).lower(), 'png')
            try:
                raw = base64.b64decode(m.group(2))
                fd, p = tempfile.mkstemp(suffix='.' + ext)
                with os.fdopen(fd, 'wb') as f:
                    f.write(raw)
                return ('upload', p)
            except Exception:
                return ('drop', None)
        return ('drop', None)
    parsed = urlparse(url)
    path = parsed.path.lstrip('/')
    # 本地文件：相对 static/... 或本服务器绝对地址，都按 ROOT 拼绝对路径（与 cwd 无关）
    for cand in (os.path.join(ROOT, path) if path else None,
                 os.path.join(ROOT, url.lstrip('/')) if url.lstrip('/') else None):
        if cand and os.path.exists(cand):
            return ('upload', cand)
    # 外链 http(s) -> 下载到临时文件再上传
    if url.startswith('http://') or url.startswith('https://'):
        try:
            r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200 and len(r.content) > 100:
                ctype = r.headers.get('Content-Type', '')
                ext = 'jpg'
                if 'png' in ctype:
                    ext = 'png'
                elif 'gif' in ctype:
                    ext = 'gif'
                elif 'webp' in ctype:
                    ext = 'webp'
                fd, p = tempfile.mkstemp(suffix='.' + ext)
                with os.fdopen(fd, 'wb') as f:
                    f.write(r.content)
                return ('upload', p)
        except Exception:
            return ('drop', None)
        return ('drop', None)
    return ('drop', None)


def _rewrite_images_to_wx(content, appid=None, appsecret=None):
    """把正文里所有非微信图片转成微信 CDN 地址。返回 (新content, 跳过的图片数)。

    处理范围：本地 static/... 图片、本服务器绝对地址、外链 http(s)、data URI、
    以及 秀米/公众号常见的 data-src 懒加载图。解析不到或上传失败的图会被丢弃，
    避免整篇草稿因一张坏图而报 invalid media_id。
    """
    if not content:
        return content, 0, None
    skipped = [0]
    first_mid = [None]

    def process_tag(m):
        tag = m.group(0)
        src = _re.search(r'src=["\']([^"\']*)["\']', tag)
        dsrc = _re.search(r'data-src=["\']([^"\']*)["\']', tag)
        cand = (dsrc.group(1) if (dsrc and dsrc.group(1)) else (src.group(1) if src else ''))
        if not cand:
            return ''                       # 没有任何图片源 -> 直接去掉空 img
        decision, val = _resolve_image(cand)
        if decision == 'keep':
            newtag = _re.sub(r'\s+data-src=["\'][^"\']*["\']', '', tag)
            return _re.sub(r'src=["\']([^"\']*)["\']', 'src="%s"' % val, newtag)
        if decision == 'upload':
            try:
                wx_url, wx_mid = _wx_upload_local(val, appid, appsecret)
                if first_mid[0] is None:
                    first_mid[0] = wx_mid
                newtag = _re.sub(r'\s+data-src=["\'][^"\']*["\']', '', tag)
                if src:
                    newtag = _re.sub(r'src=["\']([^"\']*)["\']', 'src="%s"' % wx_url, newtag)
                else:
                    newtag = tag.replace('<img', '<img src="%s"' % wx_url, 1)
                return newtag
            except Exception:
                skipped[0] += 1
                return ''
        skipped[0] += 1
        return ''

    new_content = _re.sub(r'<img\b[^>]*>', process_tag, content)
    return new_content, skipped[0], first_mid[0]


def _unescape_unicode(s):
    """防御性解码：如果字符串里出现字面量 \\uXXXX 转义，把它还原成中文。
    用于兼容历史数据或前端意外二次 JSON 转义的情况。"""
    if not isinstance(s, str):
        return s
    def repl(m):
        code = int(m.group(1) or m.group(2), 16)
        try:
            return chr(code)
        except ValueError:
            return m.group(0)
    # 只处理标准 \\uXXXX / \\UXXXXXXXX 转义，避免误伤普通反斜杠和正常中文
    return _re.sub(r'\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})', repl, s)


def _do_publish(title, digest, content, author, db, mode='publish', cover_mid=None):
    """执行「建草稿」(+ 可选「提交发布」)。

    返回 (ok:bool, detail:str, hint:str|None, media_id:str)。
    - 正常发布成功：ok=True, hint=None, media_id=草稿media_id
    - mode='draft' 且草稿已建好：ok=True, hint='draft_only'（按用户选择只建草稿）
    - 提交发布被微信拒绝（多为个人号无 API 发布权限 48001）：
      ok=False, hint='draft'（草稿已建好，等用户在「待处理」里选「转草稿」或「清空」），media_id=草稿media_id
    - 其它异常（图片/网络/未配置）：ok=False, hint=None
    """
    # 防御性解码：若 title/content 里含字面量 \\uXXXX，先还原成中文
    title = _unescape_unicode(title)
    digest = _unescape_unicode(digest)
    content = _unescape_unicode(content)
    author = _unescape_unicode(author)

    row = db.execute("SELECT value FROM store_settings WHERE key='wechat_appid'").fetchone()
    appid = row['value'] if row else ''
    row = db.execute("SELECT value FROM store_settings WHERE key='wechat_appsecret'").fetchone()
    appsecret = row['value'] if row else ''
    if not appid or not appsecret:
        return False, '未配置微信AppID/AppSecret', None, ''
    try:
        content, skipped, first_mid = _rewrite_images_to_wx(content, appid, appsecret)
        # draft/add 必须带封面 thumb_media_id（永久素材 media_id），否则报 invalid media_id
        thumb = first_mid if first_mid else (cover_mid or _default_cover_mid(appid, appsecret))
        mid = _wechat_create_draft(appid, appsecret, [{
            'title': title,
            'author': author or '',
            'digest': digest or '',
            'content': content or '',
            'thumb_media_id': thumb,
        }])
        # 仅建草稿模式：到此即完成（不提交发布）
        if mode == 'draft':
            detail = '草稿已创建（未提交发布）media_id=%s' % mid
            if skipped:
                detail += '（跳过 %d 张无法处理的图片）' % skipped
            return True, detail, 'draft_only', mid
        # 发布模式：提交 freepublish/submit（不推送粉丝、不占群发次数；认证号可用，个人号通常 48001）
        ok, detail = _wechat_publish(appid, appsecret, mid)
        if skipped:
            detail += '（跳过 %d 张无法处理的图片）' % skipped
        if ok:
            return True, detail, None, mid
        # 草稿已成功建好，但提交发布被拒（个人号无 API 发布权限）——不算失败，转「待处理」让用户抉择
        if '48001' in detail or 'api unauthorized' in detail:
            return False, '草稿已生成 media_id=%s（该账号无API发布权限，可点「作为草稿发布」保留或「清空」）' % mid, 'draft', mid
        return False, detail, None, mid
    except Exception as e:
        return False, str(e), None, ''


# ============================================================
# 调度执行
# ============================================================
def _tick():
    with APP_REF.app_context():
        db = _get_db()
        now = _now()
        # 1) 到期定时任务
        due = db.execute(
            "SELECT * FROM scheduled_posts WHERE status='pending' AND schedule_time <= ?",
            (now,)).fetchall()
        for row in due:
            # 先置为「发布中」，让前端知道正在处理（避免长时间停留在「等待发布」）
            db.execute("UPDATE scheduled_posts SET status='running', detail='正在发布中…' WHERE id=?", (row['id'],))
            db.commit()
            omode = row['mode'] if 'mode' in (row.keys() if hasattr(row, 'keys') else []) else 'publish'
            try:
                ok, detail, hint, mid = _do_publish(row['title'], row['digest'], row['content'], row['author'], db, mode=omode, cover_mid=row['media_id'])
            except Exception as e:
                ok, detail, hint, mid = False, '发布过程异常: ' + str(e), None, ''
            if ok and hint == 'draft_only':
                # 仅建草稿模式：草稿已建好即视为完成
                db.execute("UPDATE scheduled_posts SET status='draft', detail=?, media_id=?, published_at=? WHERE id=?",
                           (detail, mid, _now(), row['id']))
                log_publish('schedule', row['title'], 'draft', detail, db=db)
            elif ok:
                db.execute("UPDATE scheduled_posts SET status='done', detail=?, media_id=?, published_at=? WHERE id=?",
                           (detail, mid, _now(), row['id']))
                log_publish('schedule', row['title'], 'success', detail, db=db)
            elif hint == 'draft':
                # 草稿已建好，但提交发布被拒（账号无权限）——转「待处理」等用户抉择
                db.execute("UPDATE scheduled_posts SET status='needs_choice', detail=?, media_id=? WHERE id=?",
                           (detail, mid, row['id']))
                log_publish('schedule', row['title'], 'draft', detail, db=db)
            else:
                db.execute("UPDATE scheduled_posts SET status='failed', detail=?, media_id=? WHERE id=?",
                           (detail, mid, row['id']))
                log_publish('schedule', row['title'], 'fail', detail, db=db)
            db.commit()
        # 2) 批量队列（每次最多 5 条，间隔 2s 防频限）
        queued = db.execute(
            "SELECT * FROM publish_queue WHERE status='queued' ORDER BY id ASC LIMIT 5").fetchall()
        for row in queued:
            db.execute("UPDATE publish_queue SET status='running', detail='正在发布中…' WHERE id=?", (row['id'],))
            db.commit()
            omode = row['mode'] if 'mode' in (row.keys() if hasattr(row, 'keys') else []) else 'publish'
            try:
                ok, detail, hint, mid = _do_publish(row['title'], row['digest'], row['content'], row['author'], db, mode=omode, cover_mid=row['media_id'])
            except Exception as e:
                ok, detail, hint, mid = False, '发布过程异常: ' + str(e), None, ''
            if ok and hint == 'draft_only':
                db.execute("UPDATE publish_queue SET status='draft', detail=?, media_id=?, published_at=? WHERE id=?",
                           (detail, mid, _now(), row['id']))
                log_publish('batch', row['title'], 'draft', detail, db=db)
            elif ok:
                db.execute("UPDATE publish_queue SET status='done', detail=?, media_id=?, published_at=? WHERE id=?",
                           (detail, mid, _now(), row['id']))
                log_publish('batch', row['title'], 'success', detail, db=db)
            elif hint == 'draft':
                db.execute("UPDATE publish_queue SET status='needs_choice', detail=?, media_id=? WHERE id=?",
                           (detail, mid, row['id']))
                log_publish('batch', row['title'], 'draft', detail, db=db)
            else:
                db.execute("UPDATE publish_queue SET status='failed', detail=?, media_id=? WHERE id=?",
                           (detail, mid, row['id']))
                log_publish('batch', row['title'], 'fail', detail, db=db)
            db.commit()
            time.sleep(2)


# ============================================================
# 发布日志 / 分析
# ============================================================
def log_publish(channel, title, status, detail='', ptype='article', db=None):
    """写发布日志。

    - 调度器线程里由 _tick 调用时传 db=（复用 _tick 同一个连接/事务），
      这样不会与 _tick 未提交的事务争锁（之前的“独立连接/嵌套 app_context”都会
      触发 database is locked 而静默丢失日志）。
    - 请求线程里（前端上报 /api/publish/log-event）不传 db，则自己开一条独立连接。
    """
    own = db is None
    if own:
        import sqlite3
        from app import DATABASE
        conn = sqlite3.connect(DATABASE, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout=5000")
        db = conn
    try:
        db.execute(
            "INSERT INTO publish_log (ts, channel, title, status, detail, type) VALUES (?,?,?,?,?,?)",
            (_now(), channel, title, status, detail, ptype))
        if own:
            db.commit()
    finally:
        if own:
            db.close()


def get_analytics():
    with APP_REF.app_context():
        db = _get_db()
        total = db.execute("SELECT COUNT(*) AS c FROM publish_log").fetchone()['c']
        success = db.execute("SELECT COUNT(*) AS c FROM publish_log WHERE status='success'").fetchone()['c']
        fail = db.execute("SELECT COUNT(*) AS c FROM publish_log WHERE status='fail'").fetchone()['c']
        draft = db.execute("SELECT COUNT(*) AS c FROM publish_log WHERE status='draft'").fetchone()['c']
        # 按天
        by_day = db.execute(
            "SELECT substr(ts,1,10) AS day, COUNT(*) AS c, "
            "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok "
            "FROM publish_log GROUP BY day ORDER BY day DESC LIMIT 30").fetchall()
        # 按渠道
        by_channel = db.execute(
            "SELECT channel, COUNT(*) AS c, "
            "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok "
            "FROM publish_log GROUP BY channel").fetchall()
        # 定时/批量进度
        sched = db.execute(
            "SELECT status, COUNT(*) AS c FROM scheduled_posts GROUP BY status").fetchall()
        queue = db.execute(
            "SELECT status, COUNT(*) AS c FROM publish_queue GROUP BY status").fetchall()
        recent = db.execute(
            "SELECT ts, channel, title, status, detail FROM publish_log "
            "ORDER BY ts DESC LIMIT 20").fetchall()
        return {
            'total': total,
            'success': success,
            'fail': fail,
            'draft': draft,
            'success_rate': round(success / (success + fail) * 100, 1) if (success + fail) else 0,
            'by_day': [dict(r) for r in by_day],
            'by_channel': [dict(r) for r in by_channel],
            'scheduled': [dict(r) for r in sched],
            'queue': [dict(r) for r in queue],
            'recent': [dict(r) for r in recent],
        }
