<script>
// ==================== 基础工具 ====================
function q(id) { return document.getElementById(id); }

function pctStr(v) {
  if (v == null || v === '') return '-';
  v = parseFloat(v);
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
}

function pctCls(v) {
  if (v == null || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}

// ==================== API 请求 ====================
function f(url, ms) {
  if (!ms) ms = 10000;
  return new Promise(function(resolve, reject) {
    var x = new XMLHttpRequest();
    x.open('GET', url, true);
    x.setRequestHeader('Cache-Control', 'no-cache');
    x.timeout = ms;
    x.ontimeout = function() { reject(new Error('请求超时')); };
    x.onerror = function(e) { reject(new Error('网络错误')); };
    x.onload = function() {
      var s = x.status;
      if ((s >= 200 && s < 300) || s === 304) {
        var txt = x.responseText || '';
        if (s === 304 || !txt.trim()) {
          resolve({ code: 0, data: { items: [], total: 0 } });
        } else {
          try { resolve(JSON.parse(txt)); }
          catch(e) { resolve({ code: 0, data: { items: [], total: 0 } }); }
        }
      } else { reject(new Error('HTTP ' + s)); }
    };
    x.send();
  });
}

// ==================== 页面切换 ====================
var _curPage = 'rank';
var _prevPage = 'rank';

function switchPage(page) {
  if (page === _curPage) return;
  var pages = ['rank', 'pool', 'report', 'cross', 'macd', 'track', 'stock'];
  pages.forEach(function(p) {
    var el = q('page' + p.charAt(0).toUpperCase() + p.slice(1));
    if (el) el.style.display = 'none';
    var btn = document.querySelector('[data-page="' + p + '"]');
    if (btn) btn.classList.remove('on');
  });
  var mainEl = q('page' + page.charAt(0).toUpperCase() + page.slice(1));
  if (mainEl) mainEl.style.display = 'block';
  var curBtn = document.querySelector('[data-page="' + page + '"]');
  if (curBtn) curBtn.classList.add('on');
  _prevPage = _curPage;
  _curPage = page;
  q('backBtn').style.display = 'none';
  if (page === 'rank') loadRank(1);
  else if (page === 'pool') loadPool(1);
  else if (page === 'report') loadReport();
  else if (page === 'cross') loadCross(1);
  else if (page === 'macd') loadMacd(1);
  else if (page === 'track') loadTrack(1);
}

function goBack() { switchPage(_prevPage); }

// ==================== 排行榜 ====================
var _rankType = 'drawdown';

function setRankType(el, type) {
  _rankType = type;
  document.querySelectorAll('[data-t]').forEach(function(e) { e.classList.remove('on'); });
  if (el) el.classList.add('on');
  loadRank(1);
}

function loadRank(page) {
  var curPage = page || 1;
  var el = q('rankList');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/strategy/pool?type=' + _rankType + '&top=20').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败: ' + d.msg + '</div>'; return; }
    var items = d.data && d.data.items ? d.data.items : [];
    if (_rankType === 'drawdown') {
      items = items.filter(function(x) { return x.drawdown != null && x.drawdown > 0; })
                   .sort(function(a, b) { return b.drawdown - a.drawdown; });
    } else if (_rankType === 'fall_streak') {
      items = items.filter(function(x) { return (x.fall_days || 0) > 0; })
                   .sort(function(a, b) { return b.fall_days - a.fall_days; });
    } else if (_rankType === 'rise_total') {
      items = items.sort(function(a, b) { return (b.rise_5d_pct || 0) - (a.rise_5d_pct || 0); });
    } else if (_rankType === 'rise_streak') {
      items = items.filter(function(x) { return (x.rise_days || 0) > 0; })
                   .sort(function(a, b) { return b.rise_days - a.rise_days; });
    }
    var total = items.length;
    var PS = 20, pages = Math.ceil(total / PS), start = (curPage - 1) * PS;
    var TU = { drawdown: '%', rise_total: '%', rise_streak: '天', fall_streak: '天' };
    var TS = { drawdown: '回撤', rise_total: '5日涨幅', rise_streak: '连涨', fall_streak: '连跌' };
    if (items.length === 0) { el.innerHTML = '<div class="hint">暂无数据</div>'; }
    else {
      el.innerHTML = items.slice(start, start + PS).map(function(it, i) {
        var rn = start + i + 1, pct = it.pct_change || 0;
        var val;
        if (_rankType === 'drawdown') val = it.drawdown;
        else if (_rankType === 'rise_total') val = it.rise_5d_pct;
        else if (_rankType === 'rise_streak') val = it.rise_days;
        else val = it.fall_days;
        var valS = val != null ? (val > 0 && _rankType === 'rise_total' ? '+' : '') + Math.abs(val).toFixed(2) + TU[_rankType] : '-';
        var row = '<div class="crow" onclick="openStock(\'' + it.ts_code + '\')">';
        row += '<div class="rk ' + (rn <= 3 ? 't' : '') + '">' + rn + '</div>';
        row += '<div class="info"><div class="lbl">' + it.name + '</div><div class="cd">' + it.ts_code + (it.trade_date ? ' · ' + it.trade_date : '') + '</div></div>';
        row += '<div class="dt"><div class="pr2">' + (it.close || '-') + '</div><div class="cg ' + pctCls(pct) + '">' + pctStr(pct) + '</div><div class="mt">' + TS[_rankType] + ' ' + valS + '</div></div></div>';
        return row;
      }).join('');
    }
    var pg = q('rankPg');
    if (!pg) return;
    if (pages <= 1) { pg.innerHTML = ''; return; }
    var h = '<button ' + (curPage <= 1 ? 'disabled' : 'onclick="loadRank(' + (curPage - 1) + ')"') + '>‹ 上一页</button>';
    for (var pi = Math.max(1, curPage - 2); pi <= Math.min(pages, curPage + 2); pi++)
      h += '<button class="' + (pi === curPage ? 'cur' : '') + '" onclick="loadRank(' + pi + ')">' + pi + '</button>';
    h += '<button ' + (curPage >= pages ? 'disabled' : 'onclick="loadRank(' + (curPage + 1) + ')"') + '>下一页 ›</button>';
    h += '<span class="info">' + curPage + '/' + pages + ' 共' + total + '只</span>';
    pg.innerHTML = h;
  }).catch(function(e) { el.innerHTML = '<div class="hint">网络错误: ' + e.message + '</div>'; });
}

// ==================== 强势股池 ====================
function loadPool(page) {
  var curPage = page || 1;
  var el = q('poolList');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/strategy/pool?top=20').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败</div>'; return; }
    var items = d.data && d.data.items ? d.data.items : [];
    if (items.length === 0) { el.innerHTML = '<div class="hint">暂无数据</div>'; return; }
    el.innerHTML = items.map(function(it, i) {
      var pct = it.pct_change || 0;
      return '<div class="crow" onclick="openStock(\'' + it.ts_code + '\')">' +
        '<div class="rk">' + (i+1) + '</div>' +
        '<div class="info"><div class="lbl">' + it.name + '</div><div class="cd">' + (it.industry||'') + ' · ' + it.ts_code + '</div></div>' +
        '<div class="dt"><div class="pr2">' + (it.close||'-') + '</div><div class="cg ' + pctCls(pct) + '">' + pctStr(pct) + '</div><div class="mt">评分: ' + (it.score||'-') + '</div></div></div>';
    }).join('');
  }).catch(function() { el.innerHTML = '<div class="hint">网络错误</div>'; });
}

// ==================== 每日复盘 ====================
function loadReport() {
  var el = q('reportMk');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/report/daily').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败</div>'; return; }
    var m = d.data && d.data.market ? d.data.market : {};
    q('reportMk').innerHTML =
      '<div class="mk"><div class="mkL">' +
        '<span class="mkChip up">涨 ' + (m.rise_count||0) + '</span>' +
        '<span class="mkChip down">跌 ' + (m.fall_count||0) + '</span>' +
        '<span class="mkChip up">涨停 ' + (m.limit_up_count||0) + '</span>' +
        '<span class="mkChip down">跌停 ' + (m.limit_down_count||0) + '</span></div>' +
        '<div class="mkR"><div class="sco">' + (m.emotion_score||'--') + '</div><div class="scoL">情绪指数</div></div></div>' +
        '<div class="mkEm">' + (m.market_emotion||'') + '</div>';
    var sec = d.data && d.data.sector_analysis ? d.data.sector_analysis : [];
    q('luList').innerHTML = sec.length === 0 ? '<div class="hint">暂无板块数据</div>' :
      sec.map(function(s) {
        return '<div class="crow">' +
          '<div class="info"><div class="lbl">' + s.industry + '</div><div class="cd">均涨: ' + (s.avg_pct||0).toFixed(1) + '% | ' + (s.rise_count||0) + '只上涨 | 涨停' + (s.limit_up_count||0) + '</div></div>' +
          '<div class="dt"><div class="cg ' + (s.avg_pct >= 0 ? 'up' : 'down') + '">' + pctStr(s.avg_pct) + '</div></div></div>';
      }).join('');
    var concerns = d.data && d.data.concerns ? d.data.concerns : [];
    q('concernList').innerHTML = concerns.length ? '<div style="margin-top:6px">' + concerns.map(function(c){return '<div class="hint" style="padding:2px 0">⚠️ '+c+'</div>';}).join('') + '</div>' : '';
  }).catch(function() { el.innerHTML = '<div class="hint">网络错误</div>'; });
}

// ==================== MA趋势 ====================
function loadCross(page) {
  var curPage = page || 1;
  var el = q('crossList');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/strategy/golden_cross?top=100&page=' + curPage + '&page_size=50').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败</div>'; return; }
    var items = d.data && d.data.items ? d.data.items : [];
    if (items.length === 0) { el.innerHTML = '<div class="hint">暂无金叉信号</div>'; return; }
    el.innerHTML = items.map(function(it) {
      var pct = it.pct_change || 0;
      return '<div class="crow" onclick="openStock(\'' + it.ts_code + '\')">' +
        '<div class="info"><div class="lbl">' + it.name + '</div><div class="cd">' + it.ts_code + (it.trade_date ? ' · ' + it.trade_date : '') + '</div></div>' +
        '<div class="dt"><div class="pr2">' + (it.close||'-') + '</div><div class="cg ' + pctCls(pct) + '">' + pctStr(pct) + '</div><div class="mt">MA5:' + (it.ma5||'-') + ' MA20:' + (it.ma20||'-') + '</div></div></div>';
    }).join('');
  }).catch(function() { el.innerHTML = '<div class="hint">网络错误</div>'; });
}

// ==================== MACD信号 ====================
function loadMacd() {
  var el = q('macdList');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/strategy/macd_cross').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败</div>'; return; }
    var items = d.data && d.data.items ? d.data.items : [];
    if (items.length === 0) { el.innerHTML = '<div class="hint">暂无MACD信号</div>'; return; }
    el.innerHTML = items.map(function(it) {
      var pct = it.pct_change || 0;
      return '<div class="crow" onclick="openStock(\'' + it.ts_code + '\')">' +
        '<div class="info"><div class="lbl">' + it.name + '</div><div class="cd">' + it.ts_code + '</div></div>' +
        '<div class="dt"><div class="pr2">' + (it.close||'-') + '</div><div class="cg ' + pctCls(pct) + '">' + pctStr(pct) + '</div></div></div>';
    }).join('');
  }).catch(function() { el.innerHTML = '<div class="hint">网络错误</div>'; });
}

// ==================== 趋势追踪 ====================
function loadTrack(page) {
  var curPage = page || 1;
  var el = q('trackList');
  if (!el) return;
  el.innerHTML = '<div class="hint">加载中...</div>';
  f('/api/strategy/golden_cross/track?status=&page=' + curPage + '&page_size=30').then(function(d) {
    if (d.code !== 0) { el.innerHTML = '<div class="hint">加载失败</div>'; return; }
    var items = d.data && d.data.items ? d.data.items : [];
    if (items.length === 0) { el.innerHTML = '<div class="hint">暂无追踪记录</div>'; return; }
    el.innerHTML = items.map(function(it) {
      var pct = it.pct_change || 0;
      return '<div class="crow" onclick="openStock(\'' + it.ts_code + '\')">' +
        '<div class="info"><div class="lbl">' + it.name + '</div><div class="cd">' + it.ts_code + ' | ' + (it.trade_date||'') + ' | ' + (it.status === 0 ? '追踪中' : '已结束') + '</div></div>' +
        '<div class="dt"><div class="pr2">' + (it.close||'-') + '</div><div class="cg ' + pctCls(pct) + '">' + pctStr(pct) + '</div></div></div>';
    }).join('');
  }).catch(function() { el.innerHTML = '<div class="hint">网络错误</div>'; });
}

// ==================== 个股详情 ====================
function openStock(code) {
  q('backBtn').style.display = 'block';
  switchPage('stock');
  var el = q('stockDetail');
  if (el) el.innerHTML = '<div class="hint">加载中...</div>';
  Promise.all([
    f('/api/stock/info?ts_code=' + encodeURIComponent(code)),
    f('/api/strategy/score?ts_code=' + encodeURIComponent(code)),
    f('/api/strategy/trend?ts_code=' + encodeURIComponent(code)),
  ]).then(function(results) {
    var info = (results[0] && results[0].code === 0) ? results[0].data : {};
    var score = (results[1] && results[1].code === 0) ? results[1].data : {};
    var trend = (results[2] && results[2].code === 0) ? results[2].data : {};
    var pct = info.pct_change || 0;
    var stEl = q('stockDetail');
    if (!stEl) return;
    var html = '<div class="crow" style="cursor:default"><div class="info"><div class="lbl" style="font-size:18px">' + (info.name || code) + '</div><div class="cd">' + code + (info.industry ? ' | '+info.industry : '') + '</div></div><div class="dt"><div class="pr2" style="font-size:20px">' + (info.latest_price||'-') + '</div><div class="cg ' + pctCls(pct) + '" style="font-size:16px">' + pctStr(pct) + '</div></div></div>';
    html += '<div class="crow" style="cursor:default"><div class="info"><div class="lbl">综合评分</div></div><div class="dt"><div class="pr2">' + (score.total_score||'-') + '</div><div class="cg">' + (score.level||'-') + '</div></div></div>';
    html += '<div class="crow" style="cursor:default"><div class="info"><div class="lbl">趋势</div><div class="cd">' + (trend.trend||'') + ' ' + (trend.trend_level||'') + '</div></div><div class="dt"><div class="mt">' + (trend.ma_arrangement||'-') + '</div></div></div>';
    if (trend.break_signals && trend.break_signals.length)
      html += '<div class="hint" style="color:#c62828;padding:4px 0">⚠️ ' + trend.break_signals.join(', ') + '</div>';
    if (trend.break_up_signals && trend.break_up_signals.length)
      html += '<div class="hint" style="color:#2e7d32;padding:4px 0">✅ ' + trend.break_up_signals.join(', ') + '</div>';
    stEl.innerHTML = html;
  }).catch(function() { if (el) el.innerHTML = '<div class="hint">加载失败</div>'; });
}

// ==================== 搜索 ====================
var _st = null;
function doSearch() {
  var v = q('inp').value.trim();
  if (_st) clearTimeout(_st);
  if (!v) { q('sres').classList.remove('open'); return; }
  _st = setTimeout(function() {
    f('/api/search?q=' + encodeURIComponent(v) + '&limit=20').then(function(d) {
      var items = d.data && d.data.items ? d.data.items : [];
      if (!items.length) {
        q('sres').innerHTML = '<div style="padding:16px;color:#aaa;text-align:center">未找到: ' + v + '</div>';
      } else {
        q('sres').innerHTML = items.map(function(x) {
          return '<div class="sri" onclick="openStock(\'' + x.ts_code + '\')"><div><div class="sn">' + x.name + '</div><div class="scd">' + x.ts_code + '</div></div><div class="sp"><div class="pr">' + (x.close||'-') + '</div><div class="cg ' + pctCls(x.pct_change) + '">' + pctStr(x.pct_change) + '</div></div></div>';
        }).join('');
      }
      q('sres').classList.add('open');
    }).catch(function() {});
  }, 300);
}

// ==================== 初始化 ====================
loadRank(1);
</script>
</body></html>
