// 公众号一键粘贴助手 - popup 逻辑
// 在扩展弹窗里读取剪贴板富文本，转交给当前公众号页面的 content script 执行粘贴。
document.getElementById('go').addEventListener('click', async function () {
  var status = this;
  status.textContent = '读取剪贴板…';

  var html = '';
  try {
    var items = await navigator.clipboard.read();
    for (var i = 0; i < items.length; i++) {
      if (items[i].types.indexOf('text/html') >= 0) {
        var blob = await items[i].getType('text/html');
        html = await blob.text();
        break;
      }
    }
  } catch (e) {
    status.textContent = '读取失败：' + e.message;
    return;
  }

  if (!html) {
    status.textContent = '剪贴板无富文本，请先在发布系统点「复制到微信」';
    return;
  }

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (!tabs[0]) { status.textContent = '没有活动标签页'; return; }
    chrome.tabs.sendMessage(tabs[0].id, { action: 'paste' }, function (resp) {
      status.textContent = (resp && resp.ok) ? '已发送，请查看公众号编辑器' : '发送失败（请确认在公众号编辑页）';
    });
  });
});
