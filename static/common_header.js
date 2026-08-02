/*
 * 统一顶栏用户信息组件
 * 用法：在页面顶栏任意位置放置 <span data-user-slot></span>，引入本脚本后，
 * 会自动调用 /api/auth/me 填充当前登录用户的「头像 + 姓名 + 角色」。
 * 未登录时显示「未登录」（红色提示），方便随时查看登录状态。
 * 退出按钮由各页面自行保留（调用 /api/auth/logout）。
 */
(function () {
  var STYLE_ID = 'gh-style';
  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent =
      '.gh-box{display:inline-flex;align-items:center;gap:8px;font-size:13px;}' +
      '.gh-avatar{width:30px;height:30px;border-radius:50%;background:#534ab7;color:#fff;' +
      'display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex-shrink:0;}' +
      '.gh-name{font-weight:600;color:#1a1a2e;}' +
      '.gh-role{font-size:11px;padding:2px 8px;border-radius:10px;background:#eeedfe;color:#534ab7;}' +
      '.gh-off{font-size:11px;padding:2px 8px;border-radius:10px;background:#fdecec;color:#dc2626;}';
    document.head.appendChild(s);
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }
  window.__ghLogout = function () {
    fetch('/api/auth/logout', { method: 'POST' })
      .then(function () { location.href = '/login'; })
      .catch(function () { location.href = '/login'; });
  };
  function render(slot, d) {
    if (d && d.success && d.user) {
      var u = d.user;
      var initial = (u.display_name || u.username || '?').trim().charAt(0) || '?';
      var roleText = u.role === 'admin' ? '管理员' : '会员';
      slot.innerHTML =
        '<span class="gh-box">' +
        '<span class="gh-avatar">' + escapeHtml(initial) + '</span>' +
        '<span class="gh-name">' + escapeHtml(u.display_name || u.username) + '</span>' +
        '<span class="gh-role">' + roleText + '</span>' +
        '</span>';
    } else {
      slot.innerHTML = '<span class="gh-off">未登录</span>';
    }
  }
  function loadUser(cb) {
    fetch('/api/auth/me')
      .then(function (r) { return r.json(); })
      .then(function (d) { cb(d); })
      .catch(function () { cb({ success: false, logged_in: false }); });
  }
  window.initGlobalUser = function () {
    injectStyle();
    var slots = document.querySelectorAll('[data-user-slot]');
    for (var i = 0; i < slots.length; i++) {
      (function (slot) {
        loadUser(function (d) { render(slot, d); });
      })(slots[i]);
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.initGlobalUser);
  } else {
    window.initGlobalUser();
  }
})();
