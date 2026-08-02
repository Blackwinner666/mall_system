// 公众号一键粘贴助手 - content script (注入 mp.weixin.qq.com)
// 作用：在公众号图文编辑页注入一个浮标按钮，点击后把系统剪贴板里的
//       富文本 HTML 以"真实粘贴事件"方式塞进微信编辑器，保留全部内联样式。
// 数据来源：用户在本发布系统点过「复制到微信」后，富样式 HTML 已在系统剪贴板中。
(function () {
  if (window.__wxPasteInjected) return;
  window.__wxPasteInjected = true;

  function toast(msg, type) {
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;right:16px;top:16px;z-index:2147483647;max-width:300px;padding:10px 14px;' +
      'border-radius:8px;font-size:13px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#fff;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.25);line-height:1.5;' +
      (type === 'error' ? 'background:#e24b4a;' : type === 'success' ? 'background:#1d9e75;' : 'background:#333;');
    document.body.appendChild(t);
    setTimeout(function () { t.style.opacity = '0'; t.style.transition = 'opacity .4s'; setTimeout(function () { t.remove(); }, 400); }, 2800);
  }

  // 定位微信图文编辑器的正文可编辑区域
  // 策略：收集页面(含 iframe)所有 contenteditable 元素 -> 过滤可见的 -> 选面积最大的
  // （正文区远大于标题/作者等小富文本控件），避免选错元素。标题/作者输入框是普通
  // <input>，不参与，因此"没填标题作者"不影响正文粘贴。
  function findEditor() {
    var cands = [];
    function collect(doc) {
      if (!doc || !doc.querySelectorAll) return;
      var els = doc.querySelectorAll('[contenteditable="true"], [contenteditable=""], .edui-body');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (el.getAttribute('contenteditable') === 'false') continue;
        cands.push(el);
      }
    }
    collect(document);
    var iframes = document.querySelectorAll('iframe');
    for (var k = 0; k < iframes.length; k++) {
      try { collect(iframes[k].contentDocument || iframes[k].contentWindow.document); } catch (e) {}
    }
    window.__wxCandCount = cands.length;
    if (!cands.length) return null;
    var visible = cands.filter(function (el) {
      try {
        var r = el.getBoundingClientRect();
        var st = (el.ownerDocument.defaultView || window).getComputedStyle(el);
        return r.width > 40 && r.height > 40 && st.display !== 'none' && st.visibility !== 'hidden';
      } catch (e) { return false; }
    });
    var pool = visible.length ? visible : cands;
    var best = null, bestArea = -1;
    pool.forEach(function (el) {
      try {
        var r = el.getBoundingClientRect();
        var area = r.width * r.height;
        if (area > bestArea) { bestArea = area; best = el; }
      } catch (e) {}
    });
    return best;
  }

  // 读取系统剪贴板：正文 HTML（text/html）+ 标题/作者（text/plain 里我们写入的 JSON）
  async function readClipboard() {
    var res = { html: '', title: '', author: '' };
    try {
      var items = await navigator.clipboard.read();
      for (var i = 0; i < items.length; i++) {
        if (items[i].types.indexOf('text/html') >= 0) {
          var hb = await items[i].getType('text/html');
          var h = await hb.text();
          if (h && h.indexOf('<') >= 0) res.html = h;
        }
        if (items[i].types.indexOf('text/plain') >= 0) {
          var tb = await items[i].getType('text/plain');
          var t = await tb.text();
          try {
            var o = JSON.parse(t);
            if (o && typeof o === 'object') {
              if (o.title !== undefined) res.title = o.title || '';
              if (o.author !== undefined) res.author = o.author || '';
            }
          } catch (e) {}
        }
      }
    } catch (e) {
      console.warn('[wx-paste] clipboard read failed:', e);
    }
    return res;
  }

  // 在微信编辑页(含 iframe)定位标题/作者输入框；keywords 同时支持中文与英文（如 ['标题','title']）
  function findField(keywords) {
    if (typeof keywords === 'string') keywords = [keywords];
    var docs = [document];
    var iframes = document.querySelectorAll('iframe');
    for (var k = 0; k < iframes.length; k++) {
      try { docs.push(iframes[k].contentDocument || iframes[k].contentWindow.document); } catch (e) {}
    }
    for (var n = 0; n < keywords.length; n++) {
      var kw = keywords[n];
      var sels = ['#' + kw, '#js_' + kw, '.' + kw,
        'input[placeholder*="' + kw + '"]', 'textarea[placeholder*="' + kw + '"]',
        '[contenteditable="true"][placeholder*="' + kw + '"]'];
      for (var d = 0; d < docs.length; d++) {
        var doc = docs[d];
        if (!doc || !doc.querySelectorAll) continue;
        for (var i = 0; i < sels.length; i++) {
          var els = doc.querySelectorAll(sels[i]);
          for (var j = 0; j < els.length; j++) {
            try {
              var st = (els[j].ownerDocument.defaultView || window).getComputedStyle(els[j]);
              if (st.display === 'none' || st.visibility === 'hidden') continue;
            } catch (e) {}
            return els[j];
          }
        }
      }
    }
    return null;
  }

  // 把值填入输入框（input/textarea 设 value，contenteditable 设 innerText），并触发 input 事件让微信感知
  function fillField(keywords, value) {
    if (!value) return false;
    var el = findField(keywords);
    if (!el) { console.warn('[wx-paste] 未找到输入框:', keywords); return false; }
    try {
      var tag = (el.tagName || '').toLowerCase();
      el.focus();
      if (tag === 'input' || tag === 'textarea') el.value = value;
      else el.innerText = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    } catch (e) { return false; }
  }

  // 直接把 HTML 插入公众号编辑区（兼容 iframe 内编辑区与页面内 contenteditable）
  // 不依赖合成 paste 事件——微信新版编辑器不会从非受信(isTrusted=false)的
  // 合成 ClipboardEvent 中取内容插入，所以改用 insertHTML + DOM 兜底 + 触发 input 事件。
  function insertHtmlIntoEditor(target, html) {
    var doc = target.ownerDocument;
    var win = doc.defaultView || window;
    try { win.focus(); } catch (e) {}
    try { target.focus(); } catch (e) {}

    // 把选区定位到编辑区（当前无选区或选区不在编辑区内时放到末尾）
    try {
      var sel = win.getSelection();
      if (!sel || sel.rangeCount === 0 || !target.contains(sel.anchorNode)) {
        var r = doc.createRange();
        r.selectNodeContents(target);
        r.collapse(false);
        sel.removeAllRanges();
        sel.addRange(r);
      }
    } catch (e) {}

    // 主路径：在编辑区所属 document 上下文执行 insertHTML（微信能正常识别并保存）
    try {
      if (doc.execCommand && doc.execCommand('insertHTML', false, html)) {
        return true;
      }
    } catch (e) {}

    // 兜底：手动把 html 解析为节点插入当前选区，并触发 input 事件让微信感知
    try {
      var tmp = doc.createElement('div');
      tmp.innerHTML = html;
      var frag = doc.createDocumentFragment();
      while (tmp.firstChild) frag.appendChild(tmp.firstChild);
      var cur = (win.getSelection() && win.getSelection().rangeCount) ? win.getSelection().getRangeAt(0) : null;
      if (!cur || !target.contains(cur.commonAncestorContainer)) {
        cur = doc.createRange();
        cur.selectNodeContents(target);
        cur.collapse(false);
      }
      cur.deleteContents();
      cur.insertNode(frag);
      try { target.dispatchEvent(new win.Event('input', { bubbles: true })); } catch (e) {}
      try { target.dispatchEvent(new win.Event('change', { bubbles: true })); } catch (e) {}
      return true;
    } catch (e) {}
    return false;
  }

  function pasteHtml(html, meta) {
    meta = meta || {};
    var target = findEditor();
    if (!target) {
      console.warn('[wx-paste] 未找到正文编辑区，contenteditable 候选数=', window.__wxCandCount);
      toast('未找到正文编辑区，请先点一下正文再粘贴', 'error');
      return false;
    }
    // 主路径：真实粘贴。
    // 在声明 clipboardRead 权限的扩展 content script 里，execCommand('paste')
    // 会读取系统剪贴板（发布系统「复制到微信」已写入内联样式 HTML），
    // 并触发微信原生 paste handler —— 与手动 Ctrl+V 完全一致，内联样式全部保留。
    // 之后把标题/作者填进微信对应的 input（普通表单字段，与正文编辑区相互独立）。
    var doc = target.ownerDocument;
    var win = doc.defaultView || window;
    try { win.focus(); } catch (e) {}
    try { target.focus(); } catch (e) {}
    try {
      if (doc.execCommand && doc.execCommand('paste')) {
        var filled = [];
        if (fillField(['标题', 'title'], meta.title)) filled.push('标题');
        if (fillField(['作者', 'author'], meta.author)) filled.push('作者');
        var extra = filled.length ? '（' + filled.join('/') + '已自动填入）' : '';
        toast('已粘贴，样式已保留' + extra + '（与手动 Ctrl+V 一致）', 'success');
        return true;
      }
    } catch (e) {}
    // 兜底：极少数环境禁用 execCommand('paste')，退回 insertHTML
    // （内容能进，但微信可能清洗部分样式，提示用户改用手动 Ctrl+V）
    if (html && insertHtmlIntoEditor(target, html)) {
      fillField(['标题', 'title'], meta.title);
      fillField(['作者', 'author'], meta.author);
      toast('已用备用方式粘贴（部分样式可能未保留，建议手动 Ctrl+V）', 'warning');
      return true;
    }
    toast('粘贴失败，请尝试手动 Ctrl+V 粘贴', 'error');
    return false;
  }

  async function doPaste() {
    var data = await readClipboard();
    if (!data.html) {
      toast('剪贴板里没有富文本。请先在发布系统点「复制到微信」', 'error');
      return;
    }
    pasteHtml(data.html, { title: data.title, author: data.author });
  }

  // 浮标按钮
  var btn = document.createElement('div');
  btn.textContent = '📋 粘贴到公众号';
  btn.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:2147483647;cursor:pointer;' +
    'padding:12px 16px;border-radius:24px;background:#1d9e75;color:#fff;font-size:14px;font-weight:500;' +
    'font-family:-apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.3);user-select:none;';
  btn.addEventListener('click', doPaste);
  document.body.appendChild(btn);

  // 接收 popup 的粘贴指令
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg && msg.action === 'paste') {
      doPaste().then(function () { sendResponse({ ok: true }); });
      return true; // 保持异步通道
    }
  });
})();
