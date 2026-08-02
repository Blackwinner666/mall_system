/*!
 * 后台统一侧边栏组件 —— 单一数据源
 * ------------------------------------------------------------------
 * 背景：此前每个后台页面各自硬编码/各自 renderSidebar() 生成一份侧栏，
 *      共 12 份副本，改一处必漏其他，导致「点每个界面侧栏不同步」。
 *      同时多数页面存在 .main 缺 min-width:0 的布局 BUG，
 *      内容变宽时横向溢出、整页 body 滚动，侧栏被顶出/滚出可视区。
 *
 * 本组件负责：
 *   1) 菜单数据唯一来源（商城组 / 公众号组）
 *   2) 按 location.pathname 自动判定所属分组 + 自动高亮当前项
 *   3) 注入统一的侧栏样式与固定侧栏布局修复
 *   4) 渲染进 #admin-sidebar 或 #sidebar，并保留 id="storeName" 供各页更新店名
 *
 * 用法：<script src="/static/admin_nav.js"></script>
 *      （自动执行；页面若已有 renderSidebar() 调用，会命中本组件导出的同名全局函数）
 */
(function () {
  'use strict';

  // ============ 菜单数据（唯一来源，改这里即可全站生效） ============
  var MALL_NAV = {
    title: '商城管理',
    items: [
      { href: '/admin/mall',        icon: '\u25C6', text: '数据概览' },
      { href: '/admin/store',       icon: '\u25C7', text: '店铺管理' },
      { href: '/admin/products',    icon: '\u2606', text: '商品管理' },
      { href: '/admin/orders',      icon: '\u2611', text: '订单管理' },
      { href: '/admin/after-sales', icon: '\u21BA', text: '售后管理' },
      { href: '/admin/customers',   icon: '\u263A', text: '客户管理' },
      { href: '/admin/settings',    icon: '\u2699', text: '商城设置' }
    ]
  };

  var WECHAT_NAV = {
    title: '公众号管理',
    items: [
      { href: '/admin/wechat',             icon: '\u25C6',     text: '概览' },
      { href: '/publish',                  icon: '\u270F',     text: '文章发布', external: true },
      { href: '/admin/template-designer',  icon: '\uD83E\uDDE9', text: '模板制作' },
      { href: '/admin/builtin-templates',  icon: '\uD83D\uDCD0', text: '内置模板管理' },
      { href: '/admin/generation-records', icon: '\uD83D\uDCDD', text: '生成记录' },
      { href: '/admin/publish-analytics',  icon: '\uD83D\uDCCA', text: '发布数据分析' }
    ]
  };

  // 属于公众号组的路径（其余归商城组）
  var WECHAT_PATHS = WECHAT_NAV.items.map(function (i) { return i.href; });

  function currentPath() {
    var p = (location.pathname || '/').replace(/\/+$/, '');
    return p === '' ? '/' : p;
  }

  function detectGroup() {
    var p = currentPath();
    // 显式声明优先：页面可写 <body data-nav-group="wechat">
    var declared = document.body && document.body.getAttribute('data-nav-group');
    if (declared === 'wechat') return WECHAT_NAV;
    if (declared === 'mall') return MALL_NAV;
    for (var i = 0; i < WECHAT_PATHS.length; i++) {
      if (p === WECHAT_PATHS[i] || p.indexOf(WECHAT_PATHS[i] + '/') === 0) return WECHAT_NAV;
    }
    return MALL_NAV;
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function buildHTML(group) {
    var p = currentPath();
    var rows = group.items.map(function (it) {
      var active = (p === it.href) ? ' active' : '';
      return '<a class="nav-item' + active + '" href="' + it.href + '">' +
             '<span class="icon">' + it.icon + '</span> ' + esc(it.text) + '</a>';
    }).join('');

    return '' +
      '<div class="sidebar-header">' +
        '<div class="logo">M</div>' +
        '<div class="name" id="storeName">百货商城</div>' +
      '</div>' +
      '<nav class="sidebar-nav">' +
        '<div class="nav-group">' +
          '<a class="nav-item nav-switch" href="/admin"><span class="icon">\u21C4</span> 切换系统</a>' +
        '</div>' +
        '<div class="nav-group">' +
          '<div class="nav-group-title">' + esc(group.title) + '</div>' +
          rows +
        '</div>' +
      '</nav>';
  }

  // ============ 统一样式 + 布局修复 ============
  var CSS = [
    /* 固定侧栏布局：避免整页 body 滚动导致侧栏被滚走 */
    'html,body{height:100%;overflow:hidden}',
    '.layout{display:flex;height:100vh;overflow:hidden}',
    /* min-width:0 是关键：flex 子项默认 min-width:auto，内容一宽就撑破容器产生横向溢出 */
    '.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}',
    '.content{flex:1;overflow-y:auto;min-width:0}',
    '.topbar{flex-shrink:0}',
    /* 侧栏外观统一 */
    '.sidebar{width:220px;background:#1a1a2e;color:#fff;flex-shrink:0;display:flex;flex-direction:column;overflow-y:auto}',
    '.sidebar-header{padding:20px;border-bottom:1px solid rgba(255,255,255,.1);display:flex;align-items:center;gap:10px;flex-shrink:0}',
    '.sidebar-header .logo{width:32px;height:32px;border-radius:8px;background:#4a6cf7;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0}',
    '.sidebar-header .name{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sidebar-nav{flex:1;padding:12px 0;overflow-y:auto}',
    '.nav-group{padding:0 12px;margin-bottom:8px}',
    '.nav-group-title{font-size:11px;color:rgba(255,255,255,.4);text-transform:uppercase;padding:8px 12px;letter-spacing:1px}',
    '.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;color:rgba(255,255,255,.7);text-decoration:none;font-size:14px;transition:.2s;cursor:pointer;margin:2px 0}',
    '.nav-item:hover{background:rgba(255,255,255,.08);color:#fff}',
    '.nav-item.active{background:#4a6cf7;color:#fff}',
    '.nav-item.nav-switch{background:rgba(74,108,247,.15);color:#aab6ff}',
    '.nav-item.nav-switch:hover{background:rgba(74,108,247,.28);color:#fff}',
    '.nav-item .icon{width:20px;text-align:center;font-size:15px;flex-shrink:0}',
    '.nav-item .badge{margin-left:auto;background:#e74c3c;color:#fff;font-size:11px;padding:2px 6px;border-radius:10px;min-width:18px;text-align:center}'
  ].join('\n');

  function injectCSS() {
    if (document.getElementById('admin-nav-css')) return;
    var st = document.createElement('style');
    st.id = 'admin-nav-css';
    st.textContent = CSS;
    // 追加到 head 末尾，确保覆盖页面内联的旧规则
    (document.head || document.documentElement).appendChild(st);
  }

  function mount() {
    injectCSS();
    var el = document.getElementById('admin-sidebar') ||
             document.getElementById('sidebar') ||
             document.querySelector('.sidebar');
    if (!el) return;
    if (!el.classList.contains('sidebar')) el.classList.add('sidebar');
    var prevName = null;
    var old = document.getElementById('storeName');
    if (old && old.textContent) prevName = old.textContent;
    el.innerHTML = buildHTML(detectGroup());
    // 保留页面已经取到的店名，避免重渲染后被重置为默认值
    if (prevName) {
      var n = document.getElementById('storeName');
      if (n) n.textContent = prevName;
    }
  }

  // 导出为全局，兼容各页面已有的 renderSidebar() 调用
  window.renderSidebar = mount;
  window.renderAdminSidebar = mount;

  // 角色混用的页面（如 /template-editor 管理员与普通用户共用）可写
  // <body data-nav-auto="off">，只注入样式修复、由页面自行决定何时挂载
  function autoDisabled() {
    return document.body && document.body.getAttribute('data-nav-auto') === 'off';
  }

  function boot() {
    injectCSS();
    if (autoDisabled()) return;
    mount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
