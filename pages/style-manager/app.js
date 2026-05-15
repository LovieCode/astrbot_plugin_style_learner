/* ═══════════════════════════════════════════
   Style Learner — App Logic
   ═══════════════════════════════════════════ */

var EMOTIONS = ['开心', '惊讶', '无奈', '嘲讽', '鼓励', '生气', '悲伤', '撒娇', '认真', '好奇', '困惑', '恐惧', '嫌弃', '得意', '尴尬', '期待'];

var EMOTION_ICONS = {
  '开心': '😊', '惊讶': '😲', '无奈': '😮‍💨', '嘲讽': '😏', '鼓励': '💪',
  '生气': '😠', '悲伤': '😢', '撒娇': '🥺', '认真': '🤔', '好奇': '🧐',
  '困惑': '😵', '恐惧': '😨', '嫌弃': '🤢', '得意': '😎', '尴尬': '😅',
  '期待': '🤩', 'neutral': '😐'
};

var EMOTION_LUCIDE = {
  '开心': 'smile', '惊讶': 'sparkles', '无奈': 'meh', '嘲讽': 'meh', '鼓励': 'heart',
  '生气': 'angry', '悲伤': 'frown', '撒娇': 'heart', '认真': 'book', '好奇': 'search',
  '困惑': 'help-circle', '恐惧': 'alert-triangle', '嫌弃': 'thumbs-down', '得意': 'crown',
  '尴尬': 'meh', '期待': 'star', 'neutral': 'minus'
};



var UI_ICON = {
  'list': 'list', 'book': 'book-open', 'chart': 'bar-chart-3', 'settings': 'settings',
  'refresh': 'refresh-cw', 'save': 'save', 'edit': 'pencil', 'trash': 'trash-2',
  'check': 'check', 'cross': 'x', 'clock': 'clock', 'check-circle': 'check-circle',
  'x-circle': 'x-circle', 'search': 'search', 'filter': 'filter',
  'chat': 'message-circle', 'trending-up': 'trending-up', 'inbox': 'inbox',
  'book-open': 'book-open', 'clipboard': 'clipboard', 'file-text': 'file-text',
  'alert': 'alert-triangle', 'info': 'info', 'lightbulb': 'lightbulb',
  'globe': 'globe', 'robot': 'robot', 'user': 'user', 'star': 'star',
  'crown': 'crown', 'thumbs-up': 'thumbs-up', 'thumbs-down': 'thumbs-down',
  'award': 'award', 'smile': 'smile', 'meh': 'meh', 'frown': 'frown',
  'angry': 'angry', 'sparkles': 'sparkles', 'heart': 'heart',
  'help-circle': 'help-circle', 'alert-triangle': 'alert-triangle',
  'minus': 'minus', 'plus': 'plus', 'party-popper': 'party-popper',
  'rotate-ccw': 'rotate-ccw', 'clipboard': 'clipboard',
  'message-circle': 'message-circle', 'bar-chart-3': 'bar-chart-3',
};

function _i(name, cls) {
  return '<i data-lucide="' + (UI_ICON[name] || name) + '" class="icon-inline ' + (cls || '') + '"></i>';
}

var EMOTION_CSS = {
  '开心': 'happy', '高兴': 'happy', '愉快': 'happy', '兴奋': 'happy', '大笑': 'happy',
  '惊讶': 'surprised', '震惊': 'surprised', '惊叹': 'surprised', '意外': 'surprised',
  '无奈': 'helpless', '无语': 'helpless', '叹气': 'helpless', '无可奈何': 'helpless',
  '嘲讽': 'mock', '阴阳怪气': 'mock', '讽刺': 'mock', '挖苦': 'mock', '敷衍': 'mock',
  '鼓励': 'encourage', '加油': 'encourage', '安慰': 'encourage', '支持': 'encourage',
  '生气': 'angry', '愤怒': 'angry', '暴躁': 'angry', '不满': 'angry', '恼火': 'angry',
  '悲伤': 'sad', '难过': 'sad', '伤心': 'sad', 'emo': 'sad', '低落': 'sad',
  '撒娇': 'coquettish', '卖萌': 'coquettish', '可爱': 'coquettish', '讨好': 'coquettish',
  '认真': 'serious', '严肃': 'serious', '一本正经': 'serious', '理性': 'serious',
  '好奇': 'curious', '疑问': 'curious', '求知': 'curious', '请教': 'curious',
  '困惑': 'confused', '不懂': 'confused', '迷茫': 'confused', '疑惑': 'confused', '不解': 'confused',
  '恐惧': 'fearful', '害怕': 'fearful', '恐慌': 'fearful', '惊吓': 'fearful', '紧张': 'fearful',
  '嫌弃': 'disgusted', '讨厌': 'disgusted', '恶心': 'disgusted', '厌恶': 'disgusted', '反感': 'disgusted',
  '得意': 'proud', '自豪': 'proud', '炫耀': 'proud', '得瑟': 'proud', '自满': 'proud',
  '尴尬': 'embarrassed', '窘迫': 'embarrassed', '不好意思': 'embarrassed', '社死': 'embarrassed',
  '期待': 'expectant', '盼望': 'expectant', '憧憬': 'expectant', '愿望': 'expectant',
  'neutral': 'neutral'
};

/** 等待 AstrBot Plugin SDK 就绪 */
var _pluginPromise;
function PLUGIN() {
  if (!_pluginPromise) {
    _pluginPromise = new Promise(function (resolve) {
      var check = function () {
        var p = window.AstrBotPluginPage;
        if (p && typeof p.apiGet === 'function' && typeof p.apiPost === 'function') {
          resolve(p);
        } else {
          setTimeout(check, 50);
        }
      };
      check();
    });
  }
  return _pluginPromise;
}

var state = {
  exprPage: 1, exprTotal: 0, exprPageSize: 20,
  jargonPage: 1, jargonTotal: 0, jargonPageSize: 20,
  chatGroups: [],
};
var _exprSearchTimer = null;

/** 通用 API 调用 */
async function api(method, path, paramsOrBody) {
  var plugin = await PLUGIN();
  var res;
  if (method === 'GET') {
    res = await plugin.apiGet(path, paramsOrBody || {});
  } else {
    res = await plugin.apiPost(path, paramsOrBody || {});
  }
  var raw = typeof res === 'object' ? res : JSON.parse(res || '{}');
  if (raw && typeof raw === 'object' && !Array.isArray(raw) && ('success' in raw)) {
    return raw;
  }
  return { success: true, data: raw, total: Array.isArray(raw) ? raw.length : undefined };
}

/** HTML 转义 */
function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

/** 根据情绪名查找 CSS 类名 */
function lookupEmotionCss(emotionName) {
  if (!emotionName) return 'neutral';
  if (EMOTION_CSS[emotionName]) return EMOTION_CSS[emotionName];
  var lower = emotionName.toLowerCase();
  for (var k in EMOTION_CSS) {
    if (lower.indexOf(k) >= 0) return EMOTION_CSS[k];
  }
  return 'neutral';
}

/** 根据情绪名查找图标 */
function lookupEmotionIcon(emotionName) {
  if (!emotionName) return '😐';
  if (EMOTION_ICONS[emotionName]) return EMOTION_ICONS[emotionName];
  var lower = emotionName.toLowerCase();
  for (var k in EMOTION_ICONS) {
    if (lower.indexOf(k) >= 0) return EMOTION_ICONS[k];
  }
  return '💬';
}

/** 显示 Toast 提示 */
function showToast(message, type) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  var icons = { success: 'check-circle', error: 'x-circle', info: 'info' };
  toast.innerHTML = _i(icons[type] || 'info', 'toast-icon') + ' ' + esc(message);
  container.appendChild(toast);
  setTimeout(function () {
    toast.classList.add('removing');
    setTimeout(function () { toast.remove(); }, 300);
  }, 3000);
}

/** 显示确认对话框 */
function showConfirm(message, icon) {
  return new Promise(function (resolve) {
    var html = '<div class="confirm-overlay" onclick="if(event.target===this)this.remove();resolve(false)">' +
      '<div class="confirm-dialog">' +
      '<div class="confirm-icon-wrap"><span class="confirm-icon">' + _i(icon || 'alert-triangle', 'confirm-lucide') + '</span></div>' +
      '<p>' + message + '</p>' +
      '<div class="confirm-actions">' +
      '<button class="btn-secondary" onclick="this.closest(\'.confirm-overlay\').remove();resolve(false)">取消</button>' +
      '<button class="btn-danger" onclick="this.closest(\'.confirm-overlay\').remove();resolve(true)">确认</button>' +
      '</div></div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
    if (typeof lucide !== 'undefined') lucide.createIcons();
    window.resolve = resolve;
  });
}

/** 渲染骨架屏占位 */
function renderSkeleton(count) {
  count = count || 5;
  var html = '';
  for (var i = 0; i < count; i++) {
    html += '<div class="skeleton skeleton-card"></div>';
  }
  return html;
}

/** 渲染空状态 */
function renderEmpty(icon, message, hint) {
  var iconHtml = (icon && /^[a-z][a-z-]*$/.test(icon)) ? _i(icon, 'empty-lucide') : (icon || '📭');
  return '<div class="empty-state">' +
    '<span class="empty-icon">' + iconHtml + '</span>' +
    '<p>' + (message || '暂无数据') + '</p>' +
    (hint ? '<span class="empty-hint">' + hint + '</span>' : '') +
    '</div>';
}

// ── Tab 切换 ──
document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); });
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    document.querySelectorAll('.tab-pane').forEach(function (p) { p.classList.remove('active'); });
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'expressions') loadExpressions();
    if (btn.dataset.tab === 'jargons') loadJargons();
    if (btn.dataset.tab === 'stats') loadStats();
    if (btn.dataset.tab === 'settings') { loadSettings(); loadPrompts(); }
  });
});

// ── 表达方式 ──

/** 加载表达列表 */
async function loadExpressions() {
  var el = document.getElementById('expr-list');
  var infoEl = document.getElementById('expr-list-info');
  el.innerHTML = renderSkeleton(5);
  var emotion = document.getElementById('emotion-filter').value;
  var status = document.getElementById('status-filter').value;
  var chatId = document.getElementById('chat-filter').value;
  var search = document.getElementById('expr-search').value.trim();
  var pageSize = parseInt(document.getElementById('expr-page-size').value) || 20;
  state.exprPageSize = pageSize;
  var res = await api('GET', '/expressions', { emotion: emotion, status: status, chat_id: chatId, search: search, page: state.exprPage, page_size: pageSize });

  var success = res.success;
  var items = Array.isArray(res.data) ? res.data : (res.data && res.data.items) || [];
  var total = typeof res.total === 'number' ? res.total : (res.data && res.data.total) || items.length;
  if (!success) { el.innerHTML = renderEmpty('alert-triangle', '加载失败', '请检查网络连接后重试'); return; }
  state.exprTotal = total;
  infoEl.textContent = total ? '共 ' + total + ' 条' : '';
  if (items.length === 0) {
    var filterHint = search ? '未找到匹配表达方式' : (emotion !== 'all' ? '当前情绪筛选下暂无数据' : '');
    el.innerHTML = renderEmpty('search', filterHint || '暂无表达数据', filterHint ? '尝试修改筛选条件' : '群聊消息积累后将自动学习表达方式');
    return;
  }
  el.innerHTML = items.map(function (e) {
    var emotionName = e.emotion || 'neutral';
    var cssClass = lookupEmotionCss(emotionName);
    var emoIcon = EMOTION_LUCIDE[emotionName] || 'minus';
    var statusBadge = '';
    if (e.checked) {
      statusBadge = '<span class="status-badge checked">' + _i('check-circle') + ' 已审核</span>';
    } else {
      statusBadge = '<span class="status-badge pending">' + _i('clock') + ' 待审核</span>';
    }
    if (e.rejected) statusBadge = '<span class="status-badge rejected">' + _i('x-circle') + ' 已拒绝</span>';
    var _approved = e.checked && !e.rejected;
    var _rejected = e.rejected;
    var checkClick = 'checkExpr(' + e.id + ',' + (_approved ? 'false,false' : 'true,false') + ')';
    var rejectClick = 'checkExpr(' + e.id + ',true,' + (_rejected ? 'false' : 'true') + ')';
    return '<div class="item-card" data-id="' + e.id + '" role="listitem">' +
      '<div class="item-info">' +
      '<div><span class="emotion-tag ' + cssClass + '">' + _i(emoIcon) + ' ' + emotionName + '</span></div>' +
      '<strong>' + esc(e.situation) + '</strong>' +
      '<span class="expr-style">→ ' + esc(e.style) + '</span>' +
      '<div class="item-meta">' +
      '<span>' + _i('trending-up') + ' 学习 ' + (e.count || 0) + ' 次</span>' +
      '<span>' + _i('message-circle') + ' ' + esc(e._chat_name || e.chat_id || '?') + '</span>' +
      statusBadge +
      '</div></div>' +
      '<div class="item-actions">' +
      '<button class="btn-success btn-sm" onclick="' + checkClick + '" title="' + (_approved ? '撤销审核' : '审核通过') + '">' + _i('check') + '</button>' +
      '<button class="btn-danger btn-sm" onclick="' + rejectClick + '" title="' + (_rejected ? '撤销拒绝' : '拒绝') + '">' + _i('x') + '</button>' +
      '<button class="btn-secondary btn-sm" onclick="editExpr(' + e.id + ')" title="编辑">' + _i('edit') + '</button>' +
      '<button class="btn-ghost btn-sm" onclick="deleteExpr(' + e.id + ')" title="删除">' + _i('trash') + '</button>' +
      '</div></div>';
  }).join('');
  var totalPages = Math.ceil(state.exprTotal / pageSize);
  renderPagination('expr-pagination', state.exprPage, totalPages, function (p) { state.exprPage = p; loadExpressions(); });
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 审核表达方式 */
async function checkExpr(id, checked, rejected) {
  var actionLabel = '审核';
  if (!checked && !rejected) actionLabel = '撤销审核';
  else if (rejected) actionLabel = '拒绝';
  else actionLabel = '通过';
  await api('POST', '/expression/' + id + '/check', { checked: checked, rejected: rejected });
  showToast('已' + actionLabel + '表达 #' + id, rejected ? 'error' : 'success');
  loadExpressions();
}

/** 删除表达方式 */
async function deleteExpr(id) {
  var confirmed = await showConfirm('确定要删除此表达方式吗？此操作不可撤销。', 'trash-2');
  if (!confirmed) return;
  await api('POST', '/expression/' + id);
  showToast('已删除表达 #' + id, 'error');
  loadExpressions();
}

var _editId = null;

/** 编辑表达方式 */
async function editExpr(id) {
  _editId = id;
  var baseOptions = EMOTIONS.map(function (e) { return '<option value="' + e + '">' + (EMOTION_ICONS[e] || '') + ' ' + e + '</option>'; }).join('');
  var html = '<div class="modal-overlay" onclick="if(event.target===this)this.remove()">' +
    '<div class="modal"><h3>' + _i('edit') + ' 编辑表达方式</h3>' +
    '<label for="edit-emotion">情绪</label>' +
    '<select id="edit-emotion" onchange="onEditEmotionChange()">' +
    '<option value="">⏳ 加载中...</option>' +
    '</select>' +
    '<input id="edit-emotion-custom" type="text" placeholder="输入自定义情绪..." style="display:none;margin-top:6px;width:100%" />' +
    '<label for="edit-situation">情境描述</label><input id="edit-situation" placeholder="例如：群友分享好事时" />' +
    '<label for="edit-style">表达风格</label><input id="edit-style" placeholder="例如：使用 好耶！" />' +
    '<div class="modal-actions">' +
    '<button class="btn-secondary" onclick="this.closest(\'.modal-overlay\').remove()">取消</button>' +
    '<button class="btn-primary" onclick="saveEdit()">' + _i('save') + ' 保存</button>' +
    '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  try {
    var res = await api('GET', '/expression/' + id);
    if (res.success && res.data) {
      var curEmotion = res.data.emotion || 'neutral';
      var sel = document.getElementById('edit-emotion');
      var inBase = EMOTIONS.indexOf(curEmotion) >= 0;
      var optionsHtml = '';
      if (!inBase && curEmotion) {
        optionsHtml += '<option value="' + esc(curEmotion) + '" selected>' + esc(curEmotion) + '</option>';
      }
      optionsHtml += baseOptions;
      optionsHtml += '<option value="__custom__">✏️ 自定义...</option>';
      sel.innerHTML = optionsHtml;
      if (inBase) sel.value = curEmotion;
      document.getElementById('edit-situation').value = res.data.situation || '';
      document.getElementById('edit-style').value = res.data.style || '';
    }
  } catch (e) {
    showToast('无法加载表达数据', 'error');
  }
  document.getElementById('edit-situation').focus();
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 编辑情绪下拉变更处理 */
function onEditEmotionChange() {
  var sel = document.getElementById('edit-emotion');
  var customInput = document.getElementById('edit-emotion-custom');
  if (!sel || !customInput) return;
  if (sel.value === '__custom__') {
    customInput.style.display = 'block';
    customInput.focus();
  } else {
    customInput.style.display = 'none';
  }
}

/** 保存编辑 */
async function saveEdit() {
  var sel = document.getElementById('edit-emotion');
  var customInput = document.getElementById('edit-emotion-custom');
  var emotion;
  if (sel.value === '__custom__') {
    emotion = (customInput && customInput.value) ? customInput.value.trim() : '';
  } else {
    emotion = sel.value;
  }
  var situation = document.getElementById('edit-situation').value;
  var style = document.getElementById('edit-style').value;
  if (!situation.trim() || !style.trim()) { showToast('情境和风格不能为空', 'error'); return; }
  if (!emotion) { showToast('请选择或输入情绪', 'error'); return; }
  await api('POST', '/expression/' + _editId + '/edit', { emotion: emotion, situation: situation, style: style });
  document.querySelector('.modal-overlay').remove();
  showToast('表达方式已更新', 'success');
  loadExpressions();
}

// ── 黑话 ──

/** 加载黑话列表 */
async function loadJargons() {
  var el = document.getElementById('jargon-list');
  var infoEl = document.getElementById('jargon-list-info');
  el.innerHTML = renderSkeleton(5);
  var q = document.getElementById('jargon-search').value.trim();
  var pageSize = parseInt(document.getElementById('jargon-page-size').value) || 20;
  state.jargonPageSize = pageSize;
  var res = await api('GET', '/jargons', { search: q, page: state.jargonPage, page_size: pageSize });

  var success = res.success;
  var items = Array.isArray(res.data) ? res.data : (res.data && res.data.items) || [];
  var total = typeof res.total === 'number' ? res.total : (res.data && res.data.total) || items.length;
  if (!success) { el.innerHTML = renderEmpty('alert-triangle', '加载失败', '请检查网络连接后重试'); return; }
  state.jargonTotal = total;
  infoEl.textContent = total ? '共 ' + total + ' 条' : '';
  if (!items || items.length === 0) {
    var hint = q ? '未找到匹配黑话' : '暂无黑话数据';
    el.innerHTML = renderEmpty('search', hint, q ? '尝试修改搜索关键词' : '群聊消息积累后将自动挖掘黑话');
    return;
  }
  el.innerHTML = items.map(function (j) {
    var hasMeaning = j.meaning && j.meaning !== '待推断';
    var rejected = j.rejected;
    return '<div class="item-card' + (rejected ? ' item-card--rejected' : '') + '" data-id="' + j.id + '" role="listitem">' +
      '<div class="item-info">' +
      '<strong>' + _i('book-open') + ' ' + esc(j.content) + '</strong>' +
      '<div class="item-meta">' +
      '<span>含义: ' + _i('info') + ' ' + esc(j.meaning || '待推断') + '</span>' +
      '<span>' + _i('trending-up') + ' 次数: ' + (j.count || 0) + '</span>' +
      (j.is_global ? '<span class="status-badge checked">' + _i('globe') + ' 全局</span>' : '') +
      (hasMeaning ? '<span class="status-badge checked">' + _i('check-circle') + ' 已推断</span>' : '<span class="status-badge pending">' + _i('clock') + ' 待推断</span>') +
      (rejected ? '<span class="status-badge rejected">' + _i('x-circle') + ' 已拒绝</span>' : '') +
      '</div></div>' +
      '<div class="item-actions">' +
      '<button class="btn-success btn-sm" onclick="checkJargon(' + j.id + ',' + (!rejected) + ')" title="' + (rejected ? '撤销拒绝' : '拒绝') + '">' + _i('x') + '</button>' +
      '<button class="btn-secondary btn-sm" onclick="editJargon(' + j.id + ')" title="编辑含义">' + _i('edit') + '</button>' +
      '<button class="btn-ghost btn-sm" onclick="deleteJargon(' + j.id + ')" title="删除">' + _i('trash') + '</button>' +
      '</div></div>';
  }).join('');
  var totalPages = Math.ceil(state.jargonTotal / pageSize);
  renderPagination('jargon-pagination', state.jargonPage, totalPages, function (p) { state.jargonPage = p; loadJargons(); });
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

var _jargonId = null;

/** 编辑黑话含义 */
function editJargon(id) {
  _jargonId = id;
  var html = '<div class="modal-overlay" onclick="if(event.target===this)this.remove()">' +
    '<div class="modal"><h3>' + _i('edit') + ' 编辑黑话含义</h3>' +
    '<label for="edit-meaning">含义解释</label>' +
    '<textarea id="edit-meaning" rows="4" placeholder="输入该黑话的含义解释..."></textarea>' +
    '<div class="modal-actions">' +
    '<button class="btn-secondary" onclick="this.closest(\'.modal-overlay\').remove()">取消</button>' +
    '<button class="btn-primary" onclick="saveJargon()">' + _i('save') + ' 保存</button>' +
    '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  document.getElementById('edit-meaning').focus();
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 保存黑话含义 */
async function saveJargon() {
  var meaning = document.getElementById('edit-meaning').value;
  if (!meaning.trim()) { showToast('含义不能为空', 'error'); return; }
  await api('POST', '/jargon/' + _jargonId + '/meaning', { meaning: meaning });
  document.querySelector('.modal-overlay').remove();
  showToast('黑话含义已更新', 'success');
  loadJargons();
}

/** 审核/拒绝黑话 */
async function checkJargon(id, rejected) {
  await api('POST', '/jargon/' + id + '/check', { rejected: rejected });
  showToast(rejected ? '已拒绝黑话' : '已撤销拒绝', rejected ? 'error' : 'success');
  loadJargons();
}

/** 删除黑话 */
async function deleteJargon(id) {
  var confirmed = await showConfirm('确定要删除此黑话吗？此操作不可撤销。', 'trash-2');
  if (!confirmed) return;
  await api('POST', '/jargon/' + id);
  showToast('已删除黑话 #' + id, 'error');
  loadJargons();
}

// ── 统计 ──

/** 加载统计数据 */
async function loadStats() {
  var el = document.getElementById('stats-content');
  el.innerHTML = '<div class="stats-grid">' +
    '<div class="stat-card"><h3>' + _i('bar-chart-3') + ' 总览</h3><div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text-sm"></div></div>' +
    '<div class="stat-card"><h3>' + _i('smile') + ' 情绪分布</h3><div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text-sm"></div></div>' +
    '</div>';
  var res = await api('GET', '/statistics');
  var success = res.success, data = res.data;
  if (!success || !data) { el.innerHTML = renderEmpty('alert-triangle', '加载统计失败'); return; }
  var dist = data.emotion_distribution || {};
  console.log('StyleLearner stats dist:', JSON.stringify(dist));
  var hasEmotionData = Object.keys(dist).length > 0;
  var emotionHtml = hasEmotionData
    ? (function() {
        var values = Object.values(dist).map(Number);
        var maxCnt = Math.max.apply(null, values.concat([1]));
        var sorted = Object.keys(dist).sort(function (a, b) { return (Number(dist[b]) || 0) - (Number(dist[a]) || 0); });
        console.log('StyleLearner maxCnt:', maxCnt, 'values:', values);
        return sorted.map(function (e) {
          var cnt = Number(dist[e]) || 0;
          var cssClass = EMOTION_CSS[e] || lookupEmotionCss(e);
          var pct = Math.max(4, Math.round(cnt / maxCnt * 100));
          var cssColors = {'happy':'#34C759','surprised':'#FF9500','helpless':'#8E8E93','mock':'#E8A060','encourage':'#FF8FAB','angry':'#FF3B30','sad':'#AF52DE','coquettish':'#FF6482','serious':'#007AFF','curious':'#5AC8FA','confused':'#BF5AF2','fearful':'#8E8E93','disgusted':'#30D158','proud':'#FFD60A','embarrassed':'#FF375F','expectant':'#64D2FF','neutral':'#AEAEB2'};
          console.log('StyleLearner bar:', e, 'cnt:', cnt, 'pct:', pct, 'class:', cssClass);
          var c = cssColors[cssClass] || '#FF8FAB';
          return '<div class="emotion-stat-row">' +
            '<span class="emotion-tag ' + cssClass + '">' + _i(EMOTION_LUCIDE[e] || 'minus') + ' ' + e + '</span>' +
            '<span class="stat-bar-wrap" style="background-image:linear-gradient(90deg,' + c + ',' + c + ');background-size:' + pct + '% 100%;background-repeat:no-repeat"></span>' +
            '<span style="font-weight:600;min-width:30px;text-align:right">' + cnt + '</span>' +
            '</div>';
        }).join('');
      })()
    : '<div style="text-align:center;padding:24px 0;color:var(--color-text-muted);font-size:var(--text-sm)">暂无情绪分布数据</div>';
  el.innerHTML = '<div class="stats-grid">' +
    '<div class="stat-card">' +
    '<h3>' + _i('bar-chart-3') + ' 总体统计</h3>' +
    '<div class="stat-row"><span>表达方式总数</span><span class="stat-value">' + data.total_expressions + '</span></div>' +
    '<div class="stat-row"><span>' + _i('check-circle') + ' 已审核</span><span>' + data.checked_expressions + '</span></div>' +
    '<div class="stat-row"><span>' + _i('x-circle') + ' 已拒绝</span><span>' + data.rejected_expressions + '</span></div>' +
    '<div class="stat-row"><span>' + _i('book-open') + ' 黑话总数</span><span>' + data.total_jargons + '</span></div>' +
    '<div class="stat-row"><span>' + _i('check-circle') + ' 已完成推断</span><span>' + data.jargons_with_meaning + '</span></div>' +
    '<div class="stat-row"><span>' + _i('message-circle') + ' 群组数</span><span>' + data.chat_group_count + '</span></div>' +
    '</div>' +
    '<div class="stat-card">' +
    '<h3>' + _i('smile') + ' 情绪分布</h3>' +
    emotionHtml +
    '</div>' +
    '</div>' +
    '<div style="display:flex;gap:12px;align-items:center;margin:16px 0">' +
    '<button class="btn-primary" onclick="triggerLearn()">' + _i('refresh') + ' 手动触发学习</button>' +
    '<span style="font-size:12px;color:var(--color-text-muted)">每 30 分钟自动检查并触发学习</span>' +
    '</div>' +
    '<hr class="divider">' +
    '<div id="pending-section">' +
    '<h3 class="section-title">' + _i('inbox') + ' 待学习消息队列</h3>' +
    '<div id="pending-list">' + renderSkeleton(3) + '</div>' +
    '</div>';
  loadPendingSummary();
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 加载待学习消息摘要 */
async function loadPendingSummary() {
  var el = document.getElementById('pending-list');
  var res = await api('GET', '/pending-messages');
  var success = res.success, data = res.data;
  if (!success || !data || data.length === 0) { el.innerHTML = renderEmpty('inbox', '暂无待学习消息', '新消息将自动加入队列'); return; }
  el.innerHTML = data.map(function (g) {
    var readyHtml = g.ready ? '<span class="status-badge checked">' + _i('check-circle') + ' 可学习</span>' :
      '<span class="status-badge pending">' + _i('clock') + ' 还差 ' + (g.min_messages - g.count) + ' 条用户消息</span>';
    return '<div class="pending-item">' +
      '<div class="pending-info">' +
      '<strong>' + _i('message-circle') + ' ' + esc(g._chat_name || g.chat_id) + '</strong>' +
      '<span class="item-meta">用户消息: ' + g.count + '/' + g.min_messages + '（共' + g.total + '条） ' + readyHtml + '</span>' +
      '<div class="pending-preview">最近: ' + esc(g.last_message_preview || '(空)') + '</div>' +
      '</div>' +
      '<div class="item-actions">' +
      '<button class="btn-secondary btn-sm" onclick="viewPendingMessages(\'' + esc(g.chat_id) + '\')">' + _i('file-text') + ' 查看详情</button>' +
      '</div></div>';
  }).join('');
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 查看待学习消息详情 */
async function viewPendingMessages(chatId) {
  var res = await api('GET', '/pending-messages', { chat_id: chatId });
  var success = res.success, data = res.data;
  if (!success || !data) return;
  var html = '<div class="modal-overlay" onclick="if(event.target===this)this.remove()">' +
    '<div class="modal modal-wide">' +
    '<h3>' + _i('inbox') + ' 待学习消息 - ' + esc(chatId) + '（共 ' + data.length + ' 条）</h3>' +
    '<div class="pending-msg-list">' +
    (data.length === 0 ? renderEmpty('inbox', '消息已清空') : data.map(function (m) {
      var senderLabel = m.sender_name || (m.role === 'assistant' ? _i('robot') + ' Bot' : _i('user') + ' User');
      return '<div class="pending-msg ' + (m.role === 'assistant' ? 'msg-assistant' : 'msg-user') + '">' +
        '<span class="pending-msg-role">' + senderLabel + '</span>' +
        '<span class="pending-msg-text">' + esc(m.text) + '</span>' +
        '</div>';
    }).join('')) +
    '</div>' +
    '<div class="modal-actions">' +
    '<button class="btn-secondary" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>' +
    '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 手动触发学习 */
async function triggerLearn() {
  var btn = document.querySelector('#stats-content .btn-primary');
  if (btn) { btn.disabled = true; btn.innerHTML = _i('clock') + ' 学习中...'; }
  var res = await api('POST', '/trigger-learn');
  if (btn) { btn.disabled = false; btn.innerHTML = _i('refresh') + ' 手动触发学习'; }
  if (!res.success) {
    showToast(res.message || '触发失败', 'error');
    return;
  }
  var data = res.data || [];
  showToast(res.message || '已完成', 'success');
  showLearnResults(data);
  loadPendingSummary();
}

/** 显示学习结果 */
function showLearnResults(results) {
  var allItems = [];
  var errors = [];
  results.forEach(function (r) {
    if (r.error) { errors.push(esc(r._chat_name || r.chat_id) + ': ' + esc(r.error)); }
    (r.items || []).forEach(function (item) {
      item._chat_id = r.chat_id;
      item._chat_name = r._chat_name;
      item._message_count = r.message_count;
      allItems.push(item);
    });
  });
  var exprCount = allItems.filter(function (i) { return i.type === 'expression'; }).length;
  var jargonCount = allItems.filter(function (i) { return i.type === 'jargon'; }).length;
  var itemsHtml;
  if (allItems.length === 0) {
    var msgs = [];
    results.forEach(function (r) { msgs.push(_i('message-circle') + ' ' + esc(r._chat_name || r.chat_id) + ': ' + (r.message_count || 0) + ' 条消息'); });
    var errHtml = errors.length > 0
      ? '<div style="background:var(--color-danger-light);color:var(--color-danger);padding:12px;border-radius:8px;margin:8px 0;font-size:13px;font-weight:500">' + _i('alert') + ' ' + errors.join('<br>' + _i('alert') + ' ') + '</div>'
      : '<div style="background:var(--color-warning-light);padding:12px;border-radius:8px;margin:8px 0;font-size:13px">' + _i('lightbulb') + ' 检查 AstrBot 日志中的 <code>StyleLearner LLM caller</code> 输出定位具体原因</div>';
    itemsHtml = '<div class="empty-state"><span class="empty-icon">' + _i('search', 'empty-lucide') + '</span>' +
      '<p>没有学到新内容</p>' +
      '<span class="empty-hint">' + msgs.join(' · ') + '</span>' +
      errHtml + '</div>';
  } else {
    itemsHtml = allItems.map(function (item) {
      if (item.type === 'error') {
        return '<div class="pending-item" style="border-left:3px solid var(--color-danger)">' +
          '<div class="pending-info">' +
          '<strong style="color:var(--color-danger)">' + _i('alert') + ' ' + esc(item.content) + '</strong>' +
          '<div class="item-meta">' + _i('message-circle') + ' ' + esc(item._chat_name || item._chat_id) + '</div>' +
          '</div></div>';
      }
      if (item.type === 'expression') {
        var emoCss = EMOTION_CSS[item.emotion] || 'neutral';
        return '<div class="pending-item">' +
          '<div class="pending-info">' +
          '<span class="emotion-tag ' + emoCss + '">' + _i(EMOTION_LUCIDE[item.emotion] || 'minus') + ' ' + (item.emotion || '?') + '</span>' +
          '<strong>' + esc(item.situation) + '</strong> → ' + esc(item.style) +
          '<div class="item-meta">' + _i('message-circle') + ' ' + esc(item._chat_name || item._chat_id) + '</div>' +
          '</div>' +
          '<div class="item-actions">' +
          '<button class="btn-success btn-sm" onclick="checkNewExpr(this)">' + _i('check') + ' 通过</button>' +
          '<button class="btn-danger btn-sm" onclick="rejectNewExpr(this)">' + _i('x') + ' 拒绝</button>' +
          '</div></div>';
      } else {
        return '<div class="pending-item">' +
          '<div class="pending-info">' +
          '<strong>' + _i('book-open') + ' 黑话: ' + esc(item.content) + '</strong>' +
          '<div class="item-meta">' + _i('message-circle') + ' ' + esc(item._chat_name || item._chat_id) + '</div>' +
          '</div></div>';
      }
    }).join('');
  }
  window._learnResults = allItems;
  var html = '<div class="modal-overlay" onclick="if(event.target===this){this.remove();loadExpressions();loadPendingSummary()}">' +
    '<div class="modal modal-wide">' +
    '<h3>' + _i('party-popper') + ' 学习完成！</h3>' +
    '<p style="font-size:14px;color:var(--color-text-secondary);margin-bottom:12px">' +
    '共学到 ' + exprCount + ' 条表达方式、' + jargonCount + ' 条黑话</p>' +
    '<div class="pending-msg-list">' +
    itemsHtml +
    '</div>' +
    '<div class="modal-actions">' +
    '<button class="btn-secondary" onclick="this.closest(\'.modal-overlay\').remove();loadExpressions();loadPendingSummary()">关闭</button>' +
    '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 审核新学到的表达 */
async function checkNewExpr(btn) {
  var idx = Array.prototype.indexOf.call(btn.parentElement.parentElement.parentElement.children, btn.parentElement.parentElement);
  var item = window._learnResults[idx];
  if (!item || item.type !== 'expression') return;
  var db;
  try { db = (await api('GET', '/expressions', { chat_id: item._chat_id, page: 1, page_size: 100 })).data || []; } catch (e) { db = []; }
  var match = null;
  for (var i = 0; i < db.length; i++) {
    if (db[i].situation === item.situation && db[i].style === item.style) { match = db[i]; break; }
  }
  if (match) {
    await api('POST', '/expression/' + match.id + '/check', { checked: true, rejected: false });
    btn.innerHTML = _i('check-circle') + ' 已通过';
    btn.className = 'btn-secondary btn-sm';
    btn.disabled = true;
    var rejectBtn = btn.nextElementSibling;
    if (rejectBtn) rejectBtn.disabled = true;
    showToast('已审核通过 ' + esc(item.situation), 'success');
  }
}

/** 拒绝新学到的表达 */
async function rejectNewExpr(btn) {
  var idx = Array.prototype.indexOf.call(btn.parentElement.parentElement.parentElement.children, btn.parentElement.parentElement);
  var item = window._learnResults[idx];
  if (!item || item.type !== 'expression') return;
  var db;
  try { db = (await api('GET', '/expressions', { chat_id: item._chat_id, page: 1, page_size: 100 })).data || []; } catch (e) { db = []; }
  var match = null;
  for (var i = 0; i < db.length; i++) {
    if (db[i].situation === item.situation && db[i].style === item.style) { match = db[i]; break; }
  }
  if (match) {
    await api('POST', '/expression/' + match.id + '/check', { checked: true, rejected: true });
    btn.innerHTML = _i('x-circle') + ' 已拒绝';
    btn.className = 'btn-secondary btn-sm';
    btn.disabled = true;
    var approveBtn = btn.previousElementSibling;
    if (approveBtn) approveBtn.disabled = true;
    showToast('已拒绝 ' + esc(item.situation), 'error');
  }
}

// ── 设置 ──

var SETTINGS_GROUPS = {
  '基本设置': ['enable_expression_learning', 'enable_jargon_mining', 'injection_mode', 'selection_mode', 'expression_checked_only', 'all_global_jargon', 'all_global_expressions'],
  '阈值设置': ['min_messages_for_learning', 'learning_interval_minutes'],
  '跨群共享': ['expression_groups'],
  '自动审核': ['expression_auto_check_enabled', 'expression_auto_check_interval', 'expression_auto_check_count'],
  '管理设置': ['operator_chat_id', 'bot_name'],
  '模型覆盖': ['llm_model_override', 'learner_model_override', 'selection_model_override', 'check_model_override', 'infer_model_override'],
};

var SETTING_LABELS = {
  'enable_expression_learning': '启用表达学习',
  'enable_jargon_mining': '启用黑话挖掘',
  'injection_mode': '注入模式',
  'selection_mode': '表达选择模式',
  'expression_checked_only': '仅用审核通过的表达',
  'all_global_jargon': '黑话全局共享',
  'all_global_expressions': '表达方式全局共享',
  'expression_groups': '表达方式跨群共享组',
  'expression_auto_check_enabled': '启用自动审核',
  'expression_auto_check_interval': '自动审核间隔（秒）',
  'expression_auto_check_count': '每次审核数量',
  'min_messages_for_learning': '学习触发阈值（条）',
  'learning_interval_minutes': '学习间隔（分钟）',
  'operator_chat_id': '管理员会话 ID',
  'bot_name': 'Bot 名称',
  'llm_model_override': '全局模型覆盖',
  'learner_model_override': '学习模型',
  'selection_model_override': '选择模型',
  'check_model_override': '审核模型',
  'infer_model_override': '推断模型',
};

var SETTING_HINTS = {
  'enable_expression_learning': '从群聊消息中自动学习用户的表达方式和语言风格',
  'enable_jargon_mining': '自动识别群聊中的黑话/俚语/网络缩写，并推断其含义',
  'injection_mode': 'append=追加到用户消息末尾, tool=通过LLM工具调用注入, both=两者同时',
  'selection_mode': 'simple=情绪匹配权重抽样(快速省token), classic=随机候选池+LLM双层选择(更精准但费token)',
  'expression_checked_only': '开启后只注入已通过审核的表达方式，适合正式使用场景',
  'all_global_jargon': '开启后所有群聊共享同一套黑话库，关闭则每个群独立',
  'all_global_expressions': '开启后所有群聊共享同一套表达方式库，关闭则每个群独立。建议开启以避免跨会话无法使用',
  'expression_groups': '配置群聊分组，同一组内共享表达方式。格式: [[\"chat_id_1\",\"chat_id_2\"]]',
  'expression_auto_check_enabled': '后台定时自动审核未检查的表达方式(使用LLM评估)',
  'expression_auto_check_interval': '每次自动审核之间的间隔秒数',
  'expression_auto_check_count': '每次自动审核检查多少条表达方式',
  'min_messages_for_learning': '缓存多少条用户消息后触发一次学习',
  'learning_interval_minutes': '两次学习之间的最小间隔，避免频繁调用LLM',
  'operator_chat_id': 'unified_msg_origin格式，如aiocqhttp:friend_12345。用于接收表达审核提问',
  'bot_name': 'LLM prompt中的自我介绍名称，为空则使用平台默认名',
  'llm_model_override': '所有任务共用此模型(为空则使用系统默认)',
  'learner_model_override': '表达提取任务专用模型，为空则回退到全局覆盖或系统默认',
  'selection_model_override': '表达选择(classic模式)专用模型，为空则回退',
  'check_model_override': '表达审核/反思任务专用模型，为空则回退',
  'infer_model_override': '黑话含义推断专用模型，为空则回退',
};

var INJECTION_MODE_LABELS = { 'append': '追加到消息末尾', 'tool': 'LLM 工具调用', 'both': '两者同时' };
var SELECTION_MODE_LABELS = { 'simple': '简单模式 (情绪权重)', 'classic': 'Classic 模式 (LLM 选择)' };

/** 获取设置项所属分组 */
function getSettingGroup(key) {
  for (var group in SETTINGS_GROUPS) {
    if (SETTINGS_GROUPS[group].indexOf(key) >= 0) return group;
  }
  return '其他设置';
}

/** 构建设置项表单字段 */
function buildSettingField(key, value, knownChats) {
  var label = SETTING_LABELS[key] || key.replace(/_/g, ' ');
  var hint = SETTING_HINTS[key] || '';
  var hintHtml = hint ? '<div style="font-size:11px;color:var(--color-text-muted);margin-top:2px">' + esc(hint) + '</div>' : '';

  if (['enable_expression_learning', 'enable_jargon_mining', 'expression_checked_only', 'all_global_jargon', 'all_global_expressions', 'expression_auto_check_enabled'].indexOf(key) >= 0) {
    return '<label style="padding:6px 0;display:flex;align-items:flex-start;gap:6px;flex-direction:column"><span style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="s-' + key + '" ' + (value ? 'checked' : '') + ' /> ' + label + '</span>' + hintHtml + '</label>';
  }
  if (key === 'injection_mode') {
    return '<div class="setting-group">' +
      '<label class="setting-key">' + label + '</label>' +
      '<select id="s-' + key + '">' +
      ['append', 'tool', 'both'].map(function (o) { return '<option value="' + o + '" ' + (o === String(value) ? 'selected' : '') + '>' + (INJECTION_MODE_LABELS[o] || o) + '</option>'; }).join('') +
      '</select>' + hintHtml + '</div>';
  }
  if (key === 'selection_mode') {
    return '<div class="setting-group">' +
      '<label class="setting-key">' + label + '</label>' +
      '<select id="s-' + key + '">' +
      ['simple', 'classic'].map(function (o) { return '<option value="' + o + '" ' + (o === String(value) ? 'selected' : '') + '>' + (SELECTION_MODE_LABELS[o] || o) + '</option>'; }).join('') +
      '</select>' + hintHtml + '</div>';
  }

  if (key === 'operator_chat_id') {
    return buildOperatorChatField(value, knownChats, hintHtml);
  }

  if (key === 'expression_groups') {
    return buildExpressionGroupsField(value, knownChats, hintHtml);
  }

  if (['min_messages_for_learning', 'learning_interval_minutes', 'expression_auto_check_interval', 'expression_auto_check_count'].indexOf(key) >= 0) {
    var minVal = key === 'expression_auto_check_count' ? 1 : 1;
    return '<div class="setting-group">' +
      '<label class="setting-key">' + label + '</label>' +
      '<input type="number" id="s-' + key + '" value="' + esc(String(typeof value !== 'undefined' && value !== null ? value : minVal)) + '" min="' + minVal + '" style="width:120px" />' +
      hintHtml + '</div>';
  }
  return '<div class="setting-group">' +
    '<label class="setting-key">' + label + '</label>' +
    '<input type="text" id="s-' + key + '" value="' + esc(String(value || '')) + '" placeholder="' + (key.indexOf('model') >= 0 ? '留空使用默认模型' : '') + '" />' +
    hintHtml + '</div>';
}

/** 构建管理员会话 ID 字段 */
async function buildOperatorChatField(value, knownChats, hintHtml) {
  var chatOptions = '';
  for (var i = 0; i < knownChats.length; i++) {
    var c = knownChats[i];
    var display = c.chat_name ? c.chat_name + ' (' + c.chat_id + ')' : c.chat_id;
    chatOptions += '<option value="' + esc(c.chat_id) + '">' + esc(display) + '</option>';
  }
  return '<div class="setting-group">' +
    '<label class="setting-key">管理员会话 ID</label>' +
    '<input type="text" id="s-operator_chat_id" value="' + esc(String(value || '')) + '" list="known-chats-list" placeholder="选择已知会话或手动输入 unified_msg_origin" style="width:100%;max-width:480px" />' +
    '<datalist id="known-chats-list">' + chatOptions + '</datalist>' +
    hintHtml + '</div>';
}

/** 构建表达方式跨群共享组字段 */
function buildExpressionGroupsField(value, knownChats, hintHtml) {
  var displayValue = '';
  if (typeof value === 'object' && value !== null) {
    try { displayValue = JSON.stringify(value, null, 2); } catch (e) { displayValue = String(value || ''); }
  } else {
    displayValue = String(value || '');
  }
  var refHtml = '';
  if (knownChats.length > 0) {
    refHtml = '<div style="font-size:11px;color:var(--color-text-muted);margin-bottom:6px">已知会话: ';
    for (var i = 0; i < knownChats.length; i++) {
      var c = knownChats[i];
      var display = c.chat_name ? c.chat_name + ' (<code style="font-size:10px">' + esc(c.chat_id) + '</code>)' : '<code style="font-size:10px">' + esc(c.chat_id) + '</code>';
      refHtml += '<span style="margin-right:8px">' + display + '</span>';
    }
    refHtml += '</div>';
  }
  var example = knownChats.length > 0 && knownChats.length >= 2
    ? '[["' + esc(knownChats[0].chat_id) + '", "' + esc(knownChats[1].chat_id) + '"]]'
    : '[["群聊1_ID", "群聊2_ID"]]';
  return '<div class="setting-group" style="flex-direction:column;align-items:flex-start">' +
    '<label class="setting-key">表达方式跨群共享组</label>' +
    refHtml +
    '<textarea id="s-expression_groups" rows="5" style="width:100%;max-width:560px;font-family:monospace;font-size:12px" placeholder="' + esc(example) + '">' + esc(displayValue) + '</textarea>' +
    hintHtml + '</div>';
}

/** 加载设置 */
async function loadSettings() {
  var el = document.getElementById('settings-form');
  el.innerHTML = '<div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text-sm"></div>';
  var settingsRes = await api('GET', '/settings');
  var chatsRes = await api('GET', '/known-chats');
  var success = settingsRes.success, data = settingsRes.data;
  if (!success || !data) { el.innerHTML = renderEmpty('alert-triangle', '加载配置失败'); return; }
  var knownChats = (chatsRes.success && chatsRes.data) ? chatsRes.data : [];

  var groupsHtml = '';
  var seenKeys = {};
  for (var group in SETTINGS_GROUPS) {
    var fieldHtml = '';
    var keys = SETTINGS_GROUPS[group];
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      if (!(key in data)) continue;
      seenKeys[key] = true;
      fieldHtml += buildSettingField(key, data[key], knownChats);
    }
    if (fieldHtml) {
      groupsHtml += '<fieldset><legend>' + group + '</legend>' + fieldHtml + '</fieldset>';
    }
  }
  var restHtml = '';
  for (var k in data) {
    if (seenKeys[k]) continue;
    restHtml += buildSettingField(k, data[k], knownChats);
  }
  if (restHtml) {
    groupsHtml += '<fieldset><legend>其他设置</legend>' + restHtml + '</fieldset>';
  }
  el.innerHTML = groupsHtml || '<div class="empty-state">暂无配置项</div>';
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 保存设置 */
async function saveSettings() {
  var BOOL_KEYS = ['enable_expression_learning', 'enable_jargon_mining', 'expression_checked_only', 'all_global_jargon', 'all_global_expressions', 'expression_auto_check_enabled'];
  var INT_KEYS = ['min_messages_for_learning', 'learning_interval_minutes', 'expression_auto_check_interval', 'expression_auto_check_count'];
  var body = {};
  document.querySelectorAll('#settings-form input, #settings-form select, #settings-form textarea').forEach(function (el) {
    var key = el.id.replace(/^s-/, '');
    if (BOOL_KEYS.indexOf(key) >= 0) body[key] = el.checked;
    else if (INT_KEYS.indexOf(key) >= 0) body[key] = parseInt(el.value) || 0;
    else if (key === 'expression_groups') {
      try { body[key] = JSON.parse(el.value); } catch (e) { body[key] = el.value; }
    }
    else body[key] = el.value;
  });
  var btn = document.getElementById('save-settings-btn');
  btn.disabled = true;
  btn.innerHTML = _i('clock') + ' 保存中...';
  var res = await api('POST', '/settings', body);
  var msgEl = document.getElementById('save-msg');
  if (res.success) {
    msgEl.innerHTML = _i('check-circle') + ' 配置已保存，部分设置需重启插件生效';
    msgEl.style.color = 'var(--color-success)';
    showToast('配置保存成功', 'success');
  } else {
    msgEl.innerHTML = _i('x-circle') + ' 保存失败: ' + esc(res.message || '未知错误');
    msgEl.style.color = 'var(--color-danger)';
    showToast('配置保存失败', 'error');
  }
  btn.disabled = false;
  btn.innerHTML = _i('save') + ' 保存设置';
  setTimeout(function () { msgEl.textContent = ''; }, 4000);
}

// ── Prompt 模板 ──

/** 切换 Prompt 面板展开/收起 */
function togglePromptPanel(key) {
  var panel = document.getElementById('prompt-panel-' + key);
  var arrow = document.getElementById('prompt-arrow-' + key);
  if (!panel || !arrow) return;
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    arrow.textContent = '▼';
  } else {
    panel.style.display = 'none';
    arrow.textContent = '▶';
  }
}

/** 加载 Prompt 模板列表 */
async function loadPrompts() {
  var el = document.getElementById('prompts-form');
  el.innerHTML = '<div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text-sm"></div>';
  var res = await api('GET', '/prompts');
  if (!res.success || !res.data) { el.innerHTML = '<div class="empty-state"><p>加载失败</p></div>'; return; }
  el.innerHTML = res.data.map(function (p) {
    var value = p.custom || p.default;
    var isModified = p.custom ? ' (已自定义)' : '';
    var varsStr = p.variables.map(function (v) {
      var vName = typeof v === 'object' ? v.name : v;
      var vDesc = typeof v === 'object' ? v.desc : '';
      return '<code title="' + esc(vDesc) + '">' + esc(vName) + '</code>'
        + (vDesc ? ' <span class="var-desc">' + esc(vDesc) + '</span>' : '');
    }).join('');
    return '<div class="prompt-item">' +
      '<div class="prompt-header" onclick="togglePromptPanel(\'' + esc(p.key) + '\')" style="cursor:pointer;display:flex;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid var(--color-border)">' +
      '<span id="prompt-arrow-' + esc(p.key) + '" style="font-size:10px">▶</span>' +
      '<strong>' + esc(p.name) + '</strong>' +
      '<span style="font-size:12px;color:var(--color-text-muted)">' + esc(p.description) + '</span>' +
      (isModified ? '<span class="status-badge checked" style="font-size:11px">已自定义</span>' : '') +
      '</div>' +
      '<div id="prompt-panel-' + esc(p.key) + '" class="prompt-panel" style="display:none;padding:8px 0">' +
      '<div class="item-meta" style="margin-bottom:8px;line-height:2">可用变量：' + varsStr + '</div>' +
      '<textarea id="prompt-' + esc(p.key) + '" class="prompt-textarea" rows="10" spellcheck="false">' + esc(value) + '</textarea>' +
      '<div style="display:flex;gap:8px;margin-top:8px">' +
      '<button class="btn-primary btn-sm" onclick="savePrompt(\'' + esc(p.key) + '\')">' + _i('save') + ' 保存</button>' +
      '<button class="btn-ghost btn-sm" onclick="resetPrompt(\'' + esc(p.key) + '\')">' + _i('rotate-ccw') + ' 重置为默认</button>' +
      '<span id="prompt-msg-' + esc(p.key) + '" style="font-size:13px;line-height:32px"></span>' +
      '</div></div></div>';
  }).join('');
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 保存 Prompt 模板 */
async function savePrompt(key) {
  var textarea = document.getElementById('prompt-' + key);
  var value = textarea ? textarea.value : '';
  var msgEl = document.getElementById('prompt-msg-' + key);
  msgEl.innerHTML = _i('clock') + ' 保存中...';
  msgEl.style.color = 'var(--color-text-muted)';
  var res = await api('POST', '/prompts', { key: key, value: value });
  if (res.success) {
    msgEl.innerHTML = _i('check-circle') + ' 已保存';
    msgEl.style.color = 'var(--color-success)';
    showToast('Prompt 已保存', 'success');
  } else {
    msgEl.innerHTML = _i('x-circle') + ' ' + esc(res.message || '保存失败');
    msgEl.style.color = 'var(--color-danger)';
    showToast('保存失败', 'error');
  }
  setTimeout(function () { msgEl.innerHTML = ''; }, 3000);
}

/** 重置 Prompt 模板为默认值 */
async function resetPrompt(key) {
  var confirmed = await showConfirm('确定要重置为默认 Prompt 模板吗？当前的自定义内容将丢失。', 'rotate-ccw');
  if (!confirmed) return;
  var msgEl = document.getElementById('prompt-msg-' + key);
  msgEl.innerHTML = _i('clock') + ' 重置中...';
  msgEl.style.color = 'var(--color-text-muted)';
  var res = await api('POST', '/prompts', { key: key, value: '' });
  if (res.success) {
    var textarea = document.getElementById('prompt-' + key);
    msgEl.innerHTML = _i('check-circle') + ' 已重置';
    msgEl.style.color = 'var(--color-success)';
    showToast('Prompt 已重置为默认值', 'success');
    loadPrompts();
  } else {
    msgEl.innerHTML = _i('x-circle') + ' ' + esc(res.message || '重置失败');
    msgEl.style.color = 'var(--color-danger)';
  }
  setTimeout(function () { msgEl.innerHTML = ''; }, 3000);
}

// ── 群组 ──

/** 加载群组列表 */
async function loadChatGroups() {
  var res = await api('GET', '/chat-groups');
  var success = res.success, data = res.data;
  if (!success) return;
  state.chatGroups = data || [];
  var sel = document.getElementById('chat-filter');
  sel.innerHTML = '<option value="">💬 全部群</option>' + state.chatGroups.map(function (g) { return '<option value="' + esc(g.chat_id) + '">' + esc(g._chat_name || g.chat_id) + '</option>'; }).join('');

}

// ── 分页 ──

/** 渲染分页控件 */
function renderPagination(elId, current, total, onPage) {
  var el = document.getElementById(elId);
  if (total <= 0) { el.innerHTML = ''; return; }
  var isExpr = elId === 'expr-pagination';
  var html = '<span class="page-info">' + current + '/' + total + '</span>';
  var d = ' style="opacity:0.35;pointer-events:none"';
  html += '<button class="page-btn" onclick="setPage(1,' + isExpr + ')"' + (current <= 1 ? d : '') + '>‹‹</button>';
  html += '<button class="page-btn" onclick="setPage(' + (current - 1) + ',' + isExpr + ')"' + (current <= 1 ? d : '') + '>‹</button>';
  var start = Math.max(1, current - 2);
  var end = Math.min(total, current + 2);
  if (start > 1) html += '<button class="page-btn" onclick="setPage(1,' + isExpr + ')">1</button><span class="page-ellipsis">…</span>';
  for (var i = start; i <= end; i++) {
    html += '<button class="page-btn ' + (i === current ? 'active' : '') + '" onclick="setPage(' + i + ',' + isExpr + ')">' + i + '</button>';
  }
  if (end < total) html += '<span class="page-ellipsis">…</span><button class="page-btn" onclick="setPage(' + total + ',' + isExpr + ')">' + total + '</button>';
  html += '<button class="page-btn" onclick="setPage(' + (current + 1) + ',' + isExpr + ')"' + (current >= total ? d : '') + '>›</button>';
  html += '<button class="page-btn" onclick="setPage(' + total + ',' + isExpr + ')"' + (current >= total ? d : '') + '>››</button>';
  el.innerHTML = html;
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

/** 跳转分页 */
function setPage(p, isExpr) {
  if (isExpr) { state.exprPage = p; loadExpressions(); }
  else { state.jargonPage = p; loadJargons(); }
}

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', function () {
  loadChatGroups();
  loadExpressions();
  document.getElementById('emotion-filter').addEventListener('change', function () { state.exprPage = 1; loadExpressions(); });
  document.getElementById('status-filter').addEventListener('change', function () { state.exprPage = 1; loadExpressions(); });
  document.getElementById('chat-filter').addEventListener('change', function () { state.exprPage = 1; loadExpressions(); });
  document.getElementById('refresh-expr-btn').addEventListener('click', function () { loadExpressions(); });
  document.getElementById('expr-search').addEventListener('input', function () {
    clearTimeout(_exprSearchTimer);
    _exprSearchTimer = setTimeout(function () { state.exprPage = 1; loadExpressions(); }, 300);
  });
  document.getElementById('expr-page-size').addEventListener('change', function () { state.exprPage = 1; loadExpressions(); });
  document.getElementById('jargon-search').addEventListener('input', function () { state.jargonPage = 1; loadJargons(); });
  document.getElementById('jargon-page-size').addEventListener('change', function () { state.jargonPage = 1; loadJargons(); });
  document.getElementById('refresh-jargon-btn').addEventListener('click', function () { loadJargons(); });
  document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
  if (typeof lucide !== 'undefined') lucide.createIcons();
});
