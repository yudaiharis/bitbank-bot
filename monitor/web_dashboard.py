#!/usr/bin/env python3
"""
bitbank ペーパートレード Webダッシュボード
Flask + Chart.js でブラウザから状況確認
Usage: python monitor/web_dashboard.py
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
DB_PATH = os.environ.get(
    "TRADES_DB",
    os.path.join(os.path.dirname(__file__), "..", "trades.db")
)


def get_conn():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=()):
    conn = get_conn()
    if not conn:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>bitbank ペーパートレード</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
header{background:#1a1d2e;border-bottom:1px solid #2d3148;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:16px;font-weight:600;color:#a78bfa}
header span{font-size:12px;color:#64748b}
.container{max-width:1100px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.card{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:16px}
.card .label{font-size:11px;color:#64748b;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
.card .value{font-size:22px;font-weight:600}
.card .value.green{color:#34d399}
.card .value.red{color:#f87171}
.card .value.blue{color:#60a5fa}
.card .value.purple{color:#a78bfa}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
.panel{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:16px}
.panel h2{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:14px;text-transform:uppercase;letter-spacing:.05em}
.scanner-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1e2235}
.scanner-row:last-child{border-bottom:none}
.scanner-row .pair{font-size:14px;font-weight:500}
.scanner-row .pair.active{color:#34d399}
.scanner-row .score{font-size:13px;color:#94a3b8}
.scanner-row .price{font-size:13px;color:#e2e8f0;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 6px;color:#64748b;border-bottom:1px solid #2d3148;font-weight:500}
td{padding:7px 6px;border-bottom:1px solid #1e2235;font-variant-numeric:tabular-nums}
td.buy{color:#34d399}
td.sell{color:#f87171}
td.pos{color:#34d399}
td.neg{color:#f87171}
.badge{display:inline-block;font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600}
.badge-loop{background:#312e81;color:#a78bfa}
.badge-paper{background:#14532d;color:#34d399}
.footer{text-align:center;font-size:11px;color:#334155;padding:16px 0 24px}
canvas{max-height:220px}
</style>
</head>
<body>
<header>
  <h1>bitbank ペーパートレード</h1>
  <span id="ts">読み込み中...</span>
</header>
<div class="container">
  <div class="panel" style="margin-bottom:20px">
    <details id="strategy-details" open>
      <summary style="list-style:none;display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
        <h2 style="margin:0">現在のトレード戦略</h2>
        <span id="strategy-badge" style="font-size:12px;color:#60a5fa">▼ 折りたたむ</span>
      </summary>
      <div id="strategy-panel" style="font-size:13px;color:#94a3b8;line-height:2;margin-top:14px">読み込み中...</div>
    </details>
  </div>
  <div class="cards" id="cards">
    <div class="card"><div class="label">仮想残高</div><div class="value blue" id="balance">-</div></div>
    <div class="card"><div class="label">総損益</div><div class="value" id="pnl">-</div></div>
    <div class="card"><div class="label">勝率</div><div class="value purple" id="winrate">-</div></div>
    <div class="card"><div class="label">最大DD</div><div class="value" id="maxdd">-</div></div>
    <div class="card"><div class="label">取引件数</div><div class="value blue" id="trades">-</div></div>
    <div class="card"><div class="label">現在Loop</div><div class="value purple" id="loop">-</div></div>
  </div>
  <div style="background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:16px;margin-bottom:20px">
    <h2 style="font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:14px;text-transform:uppercase;letter-spacing:.05em">資産推移</h2>
    <canvas id="chart"></canvas>
  </div>
  <div class="grid2">
    <div class="panel">
      <h2>ボラティリティ TOP3</h2>
      <div id="scanner">データなし</div>
    </div>
    <div class="panel">
      <h2>ループ別結果</h2>
      <div id="loops">データなし</div>
    </div>
  </div>
  <div class="panel">
    <details id="trade-details">
      <summary style="list-style:none;display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
        <h2 style="margin:0">直近20件のトレード</h2>
        <span id="trade-summary-badge" style="font-size:12px;color:#60a5fa">▶ 表示する</span>
      </summary>
      <div style="overflow-x:auto;margin-top:14px">
        <table>
          <thead><tr><th>時刻(JST)</th><th>Loop</th><th>ペア</th><th>方向</th><th>売買金額</th><th>エントリー</th><th>決済</th><th>損益</th></tr></thead>
          <tbody id="tradelist"></tbody>
        </table>
      </div>
    </details>
  </div>
  <div class="panel" style="margin-bottom:20px" id="ci-panel">
    <details id="ci-details">
      <summary style="list-style:none;display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <h2 style="margin:0">GitHub Actions 自動改善履歴</h2>
          <span style="font-size:11px;color:#475569">毎週日曜 JST 02:00 自動実行</span>
          <a id="ci-actions-link" href="#" target="_blank"
             style="font-size:11px;color:#60a5fa;text-decoration:none">Actions ページ →</a>
        </div>
        <span id="ci-badge" style="font-size:12px;color:#60a5fa;white-space:nowrap;margin-left:8px">▶ 表示する</span>
      </summary>
      <div id="ci-content" style="font-size:13px;color:#64748b;margin-top:14px">読み込み中...</div>
    </details>
  </div>
  <div class="footer">30秒ごとに自動更新 &nbsp;|&nbsp; bitbank Public API</div>
</div>
<script>
let chart = null;


async function load() {
  try {
    const r = await fetch('/api/stats');
    const d = await r.json();
    document.getElementById('ts').textContent = d.updated_at + ' (30秒ごと更新)';

    // カード
    const bal = d.balance;
    const init = d.initial_balance;
    const pnl = bal - init;
    document.getElementById('balance').textContent = '¥' + bal.toLocaleString();
    const pnlEl = document.getElementById('pnl');
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + '¥' + Math.round(pnl).toLocaleString();
    pnlEl.className = 'value ' + (pnl >= 0 ? 'green' : 'red');
    document.getElementById('winrate').textContent = (d.win_rate * 100).toFixed(1) + '%';
    const ddEl = document.getElementById('maxdd');
    ddEl.textContent = (d.max_drawdown * 100).toFixed(1) + '%';
    ddEl.className = 'value ' + (d.max_drawdown > 0.08 ? 'red' : 'green');
    document.getElementById('trades').textContent = d.total_trades;
    document.getElementById('loop').textContent = 'Loop ' + d.current_loop;

    // 資産推移グラフ
    const labels = d.chart_data.map(p => p.t);
    const vals   = d.chart_data.map(p => p.b);
    if (!chart) {
      const ctx = document.getElementById('chart').getContext('2d');
      chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: '残高',
            data: vals,
            borderColor: '#60a5fa',
            backgroundColor: 'rgba(96,165,250,0.08)',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.3,
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#475569', maxTicksLimit: 8 }, grid: { color: '#1e2235' } },
            y: { ticks: { color: '#475569', callback: v => '¥' + v.toLocaleString() }, grid: { color: '#1e2235' } }
          }
        }
      });
    } else {
      chart.data.labels = labels;
      chart.data.datasets[0].data = vals;
      chart.update('none');
    }

    // スキャナー（ヘッダー付きテーブル）
    const sc = document.getElementById('scanner');
    if (d.scanner && d.scanner.length) {
      sc.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="border-bottom:1px solid #2d3148">
              <th style="text-align:left;padding:5px 4px;color:#64748b">ペア</th>
              <th style="padding:5px 4px;color:#64748b;text-align:right" title="ATR比率・出来高・値幅の加重合成スコア">ボラスコア</th>
              <th style="padding:5px 4px;color:#64748b;text-align:right">現在価格</th>
            </tr>
          </thead>
          <tbody>
            ${d.scanner.map(r => `
              <tr style="border-bottom:1px solid #1e2235">
                <td style="padding:6px 4px;font-weight:500;${r.active ? 'color:#34d399' : 'color:#e2e8f0'}">${r.pair}${r.active ? ' 🔵' : ''}</td>
                <td style="padding:6px 4px;text-align:right;color:#a78bfa">${Number(r.score).toFixed(4)}</td>
                <td style="padding:6px 4px;text-align:right;color:#e2e8f0">¥${Number(r.last).toLocaleString()}</td>
              </tr>`).join('')}
          </tbody>
        </table>`;
    } else {
      sc.innerHTML = '<div style="color:#475569;font-size:13px;padding:8px 0">スキャン待機中...</div>';
    }

    // ループ結果
    const lp = document.getElementById('loops');
    if (d.loop_results && d.loop_results.length) {
      lp.innerHTML = d.loop_results.map(r =>
        `<div class="scanner-row">
          <span class="pair">Loop ${r.loop_num} ${r.target_achieved ? '✅' : '❌'}</span>
          <span class="score">勝率 ${(r.win_rate*100).toFixed(1)}%</span>
          <span class="price ${r.total_pnl >= 0 ? 'pos' : 'neg'}">${r.total_pnl >= 0 ? '+' : ''}¥${Math.round(r.total_pnl).toLocaleString()}</span>
        </div>`
      ).join('');
    } else {
      lp.innerHTML = '<div style="color:#475569;font-size:13px;padding:8px 0">ループ未完了</div>';
    }

    // トレード履歴（UTC→JST変換・売買金額追加・理由列削除）
    const tradeCount = d.recent_trades.length;
    const badge = document.getElementById('trade-summary-badge');
    const det = document.getElementById('trade-details');
    if (badge) {
      badge.textContent = det && det.open
        ? `▼ 非表示にする（${tradeCount}件）`
        : `▶ 表示する（${tradeCount}件）`;
    }
    const tbody = document.getElementById('tradelist');
    tbody.innerHTML = d.recent_trades.map(t => {
      const pnl = t.pnl ?? 0;
      // UTC→JST変換（+9時間）
      let tsJST = '-';
      if (t.timestamp) {
        const utc = new Date(t.timestamp.replace(' ', 'T') + (t.timestamp.includes('T') ? '' : 'Z'));
        const jst = new Date(utc.getTime() + 9 * 60 * 60 * 1000);
        tsJST = jst.toISOString().substring(0, 16).replace('T', ' ');
      }
      const amount = t.amount_jpy ? '¥' + Math.round(t.amount_jpy).toLocaleString() : '-';
      return `<tr>
        <td>${tsJST}</td>
        <td><span class="badge badge-loop">${t.loop_num}</span></td>
        <td>${t.pair}</td>
        <td class="${t.side}">${t.side.toUpperCase()}</td>
        <td style="color:#94a3b8">${amount}</td>
        <td>¥${Math.round(t.entry_price).toLocaleString()}</td>
        <td>${t.exit_price ? '¥' + Math.round(t.exit_price).toLocaleString() : '保有中'}</td>
        <td class="${pnl >= 0 ? 'pos' : 'neg'}">${t.status === 'open' ? '-' : (pnl >= 0 ? '+' : '') + '¥' + Math.round(pnl).toLocaleString()}</td>
      </tr>`;
    }).join('');

    // ストラテジー表示（マルチペア・ペア別パラメータ対応）
    if (d.strategy) {
      const sp = document.getElementById('strategy-panel');
      const s = d.strategy;
      const pairRows = (s.pair_params_list || []).map(p => `
        <tr>
          <td style="color:#e2e8f0;font-weight:500;padding:5px 6px">${p.pair}</td>
          <td style="color:#94a3b8;padding:5px 6px;text-align:center">RSI &lt; ${p.rsi_oversold}</td>
          <td style="color:#94a3b8;padding:5px 6px;text-align:center">RSI &gt; ${p.rsi_overbought}</td>
          <td style="color:#f87171;padding:5px 6px;text-align:center">-${(p.stop_loss_pct*100).toFixed(1)}%</td>
          <td style="color:#34d399;padding:5px 6px;text-align:center">+${(p.take_profit_pct*100).toFixed(1)}%</td>
        </tr>`).join('');
      sp.innerHTML = `
        <div style="background:#0f1117;border-left:3px solid #a78bfa;padding:8px 12px;margin-bottom:14px;border-radius:0 6px 6px 0">
          🎯 <b style="color:#a78bfa">目標</b>：勝率 <b>${(s.target_win_rate*100).toFixed(0)}%以上</b> かつ 最大DD <b>${(s.target_max_drawdown*100).toFixed(0)}%以内</b> を <b>${s.target_consecutive}連続達成</b>（最大${s.trades_per_loop}件/ループ × PDCAで自動改善）
        </div>
        <ul style="list-style:none;padding:0;margin:0 0 14px 0">
          <li>📌 <b>対象銘柄</b>：${(s.pairs||[]).join(' / ')}（計${(s.pairs||[]).length}ペア・btc/eth/doge/link除外済み）</li>
          <li>🔀 <b>同時保有上限</b>：最大 <b>${s.max_simultaneous}</b> ポジション（全ペアを${s.trade_interval_sec}秒ごとに並列チェック）</li>
          <li>🕐 <b>足種</b>：<b>${s.candle_type}</b>（${s.scan_interval_min}分ごとにボラティリティ再スキャン）</li>
          <li>📐 <b>シグナル条件</b>：RSI(${s.rsi_period}) + ボリンジャーバンド（${s.bb_period}期間 ${s.bb_std}σ）逆張り戦略</li>
          <li style="margin-left:1.5em"><span style="color:#34d399">買い</span>：RSI &lt; 閾値 かつ 価格 &lt; BB下限（売られすぎ）</li>
          <li style="margin-left:1.5em"><span style="color:#f87171">売り</span>：RSI &gt; 閾値 かつ 価格 &gt; BB上限（買われすぎ）</li>
          ${s.use_htf_filter ? `<li>📈 <b>MTFトレンドフィルター</b>（1時間足 EMA${s.htf_ema_period}）</li>
          <li style="margin-left:1.5em">上昇トレンド → <span style="color:#34d399">買いのみ</span>許可（押し目買い）</li>
          <li style="margin-left:1.5em">下降トレンド → <span style="color:#f87171">売りのみ</span>許可（戻り売り）</li>
          <li style="margin-left:1.5em">横ばい（EMA傾き±${s.htf_flat_threshold}%以内）→ 両方向許可</li>` : ''}
          <li>🛡️ <b>リスク管理</b></li>
          <li style="margin-left:1.5em">含み損上限：残高の <b>${(s.max_unrealized_loss_pct*100).toFixed(0)}%</b> 超で新規エントリー停止</li>
          <li style="margin-left:1.5em">連続SLクールダウン：<b>${s.max_consecutive_sl}</b>連続SLで <b>${s.sl_cooldown_minutes}</b>分停止</li>
          <li style="margin-left:1.5em">相関フィルター：同グループ・同方向の重複禁止（${s.corr_display}）</li>
          <li>💰 <b>1ポジションあたり</b>：残高の ${(s.position_size_pct*100).toFixed(0)}%（現在 ¥${Math.round(s.order_size).toLocaleString()} 相当）</li>
          <li>💸 <b>手数料</b>：Maker ${s.maker_fee}%（受取）/ Taker +${s.taker_fee}%（支払）</li>
        </ul>
        <details id="pair-params-details" style="cursor:pointer">
          <summary style="font-size:12px;color:#60a5fa;padding:6px 0;user-select:none;list-style:none;display:flex;align-items:center;gap:6px">
            <span class="pp-arrow" style="font-size:10px">▶</span>
            ペア別パラメータを表示（5分足バックテスト最適化 + MTFフィルター検証済み）
          </summary>
          <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:8px">
            <thead>
              <tr style="border-bottom:1px solid #2d3148">
                <th style="text-align:left;padding:5px 6px;color:#64748b">ペア</th>
                <th style="padding:5px 6px;color:#64748b">RSI買い</th>
                <th style="padding:5px 6px;color:#64748b">RSI売り</th>
                <th style="padding:5px 6px;color:#64748b">SL</th>
                <th style="padding:5px 6px;color:#64748b">TP</th>
              </tr>
            </thead>
            <tbody>${pairRows}</tbody>
          </table>
        </details>`;
    }

  } catch(e) {
    console.error(e);
  }
}

// アコーディオン toggle（戦略・ペア別パラメータ・トレード履歴）
document.addEventListener('toggle', function(e) {
  // 現在のトレード戦略
  if (e.target.id === 'strategy-details') {
    var badge = document.getElementById('strategy-badge');
    if (badge) badge.textContent = e.target.open ? '▼ 折りたたむ' : '▶ 展開する';
  }
  // GitHub Actions 自動改善履歴
  if (e.target.id === 'ci-details') {
    var badge = document.getElementById('ci-badge');
    if (badge) badge.textContent = e.target.open ? '▼ 折りたたむ' : '▶ 表示する';
  }
  // ペア別パラメータの矢印
  if (e.target.id === 'pair-params-details') {
    var arrow = e.target.querySelector('.pp-arrow');
    if (arrow) arrow.textContent = e.target.open ? '▼' : '▶';
  }
  // トレード履歴のバッジ
  if (e.target.id === 'trade-details') {
    var badge = document.getElementById('trade-summary-badge');
    var count = document.getElementById('tradelist') ? document.getElementById('tradelist').rows.length : 0;
    if (badge) badge.textContent = e.target.open
      ? '▼ 非表示にする（' + count + '件）'
      : '▶ 表示する（' + count + '件）';
  }
}, true);

// ── GitHub Actions 改善履歴 ─────────────────────────────────
async function loadCI() {
  try {
    const r = await fetch('/api/github_actions');
    const d = await r.json();
    const el = document.getElementById('ci-content');

    if (d.error) {
      el.innerHTML = `<span style="color:#475569">${d.error}</span>`;
      return;
    }

    // Actions ページリンク
    const link = document.getElementById('ci-actions-link');
    if (link && d.actions_url) link.href = d.actions_url;

    // ── ワークフロー実行履歴テーブル ──
    const runRows = (d.runs || []).map(run => {
      const pass = run.conclusion === 'success';
      const fail = run.conclusion === 'failure';
      const badge = pass
        ? '<span style="background:#14532d;color:#34d399;padding:2px 8px;border-radius:4px;font-size:11px">PASS</span>'
        : fail
        ? '<span style="background:#7f1d1d;color:#f87171;padding:2px 8px;border-radius:4px;font-size:11px">FAIL</span>'
        : '<span style="background:#1e2235;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:11px">' + (run.conclusion || '実行中') + '</span>';
      return `<tr>
        <td style="padding:6px 8px">${run.date_jst}</td>
        <td style="padding:6px 8px">${badge}</td>
        <td style="padding:6px 8px;color:#94a3b8;font-size:12px">${run.summary || '—'}</td>
        <td style="padding:6px 8px">
          <a href="${run.url}" target="_blank"
             style="font-size:11px;color:#60a5fa;text-decoration:none">詳細 →</a>
        </td>
      </tr>`;
    }).join('');

    // ── 自動改善コミット一覧 ──
    const commitRows = (d.auto_commits || []).map(c => {
      const lines = c.message.split('\\n').filter(l => l.trim());
      const title = lines[0] || '';
      // サマリー行（対象Nペア | 平均勝率...）を探す
      const summaryLine = lines.find(l => l.includes('ペア') && l.includes('勝率')) || '';
      const diffLine = c.diff
        ? `<div style="margin-top:4px;font-family:monospace;font-size:11px;color:#a78bfa">config変更: ${c.diff}</div>`
        : '';
      return `<div style="border-bottom:1px solid #1e2235;padding:10px 0">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="color:#34d399;font-size:12px;font-weight:600">✅ 閾値合格・パラメータ更新</span>
              <a href="${c.url}" target="_blank"
                 style="font-size:10px;color:#60a5fa;text-decoration:none">${c.sha}</a>
            </div>
            ${summaryLine ? '<div style="color:#94a3b8;font-size:11px;margin-top:3px">' + summaryLine + '</div>' : ''}
            ${diffLine}
          </div>
          <div style="white-space:nowrap;font-size:11px;color:#475569">${c.date_jst}</div>
        </div>
      </div>`;
    }).join('');

    el.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px">
        <thead>
          <tr style="border-bottom:1px solid #2d3148">
            <th style="text-align:left;padding:5px 8px;color:#64748b">実行日時</th>
            <th style="padding:5px 8px;color:#64748b">結果</th>
            <th style="padding:5px 8px;color:#64748b;text-align:left">概要</th>
            <th style="padding:5px 8px;color:#64748b"></th>
          </tr>
        </thead>
        <tbody>${runRows || '<tr><td colspan="4" style="padding:12px;color:#475569">実行履歴なし</td></tr>'}</tbody>
      </table>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em">自動改善コミット履歴</div>
      ${commitRows || '<div style="color:#475569;font-size:13px">自動改善コミットなし</div>'}
    `;
  } catch(e) {
    document.getElementById('ci-content').innerHTML =
      '<span style="color:#475569">GitHub API 未設定（GITHUB_TOKEN / GITHUB_REPO が必要）</span>';
  }
}

load();
loadCI();
setInterval(load, 30000);
setInterval(loadCI, 300000);  // 5分ごとに更新
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/api/github_actions")
def github_actions():
    """GitHub Actions 実行履歴と自動改善コミットを返す"""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "yudaiharis/bitbank-bot")

    if not token:
        return jsonify({
            "error": "GITHUB_TOKEN 未設定 — コンテナ起動時に -e GITHUB_TOKEN=ghp_... を追加してください",
            "runs": [], "auto_commits": [], "actions_url": ""
        })

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{repo}"
    actions_url = f"https://github.com/{repo}/actions"

    def jst(iso: str) -> str:
        """ISO8601 UTC → JST 表示"""
        try:
            from datetime import timezone, timedelta
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            jst_dt = dt.astimezone(timezone(timedelta(hours=9)))
            return jst_dt.strftime("%Y-%m-%d %H:%M JST")
        except Exception:
            return iso[:16]

    # ── ワークフロー実行履歴（直近10件）──────────────────────
    runs_data = []
    try:
        import requests as req
        r = req.get(
            f"{base}/actions/workflows/weekly_backtest.yml/runs?per_page=10",
            headers=headers, timeout=8
        )
        if r.status_code == 200:
            for run in r.json().get("workflow_runs", []):
                # ジョブのサマリーを取得（threshold チェック出力）
                summary = ""
                try:
                    jobs_r = req.get(run["jobs_url"], headers=headers, timeout=5)
                    if jobs_r.status_code == 200:
                        for job in jobs_r.json().get("jobs", []):
                            if "閾値" in job.get("name", "") or "backtest" in job.get("name", "").lower():
                                summary = job.get("conclusion", "")
                except Exception:
                    pass

                runs_data.append({
                    "date_jst":   jst(run.get("created_at", "")),
                    "conclusion": run.get("conclusion", ""),
                    "summary":    summary,
                    "url":        run.get("html_url", ""),
                })
    except Exception as e:
        runs_data = [{"date_jst": "取得エラー", "conclusion": "error",
                      "summary": str(e), "url": ""}]

    # ── 自動改善コミット（"auto-optimize" を含むもの）──────────
    auto_commits = []
    try:
        r = req.get(f"{base}/commits?per_page=30", headers=headers, timeout=8)
        if r.status_code == 200:
            for c in r.json():
                msg = c.get("commit", {}).get("message", "")
                if "auto-optimize" in msg or "auto_optimize" in msg:
                    # コミットの config.yaml 差分を取得
                    diff_summary = ""
                    try:
                        detail = req.get(
                            f"{base}/commits/{c['sha']}",
                            headers=headers, timeout=5
                        )
                        if detail.status_code == 200:
                            for f_info in detail.json().get("files", []):
                                if f_info.get("filename") == "config.yaml":
                                    patch = f_info.get("patch", "")
                                    # 変更行だけ抜き出す
                                    changes = [
                                        ln[1:].strip()
                                        for ln in patch.split("\n")
                                        if ln.startswith("+") and not ln.startswith("+++")
                                        and any(k in ln for k in
                                            ["rsi_", "stop_loss", "take_profit", "ema_"])
                                    ]
                                    diff_summary = " / ".join(changes[:4])
                    except Exception:
                        pass

                    date_str = c.get("commit", {}).get("committer", {}).get("date", "")
                    auto_commits.append({
                        "date_jst": jst(date_str),
                        "message":  msg.replace("\n\n", "\\n").replace("\n", "\\n"),
                        "sha":      c["sha"][:7],
                        "url":      c.get("html_url", ""),
                        "diff":     diff_summary,
                    })
                if len(auto_commits) >= 10:
                    break
    except Exception:
        pass

    return jsonify({
        "actions_url":  actions_url,
        "runs":         runs_data,
        "auto_commits": auto_commits,
    })




@app.route("/api/stats")
def stats():
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}

    initial = cfg.get("initial_balance_jpy", 1_000_000)
    current_loop = cfg.get("pdca_loop", 1)

    trades = query(
        "SELECT * FROM trades WHERE status='closed' ORDER BY timestamp"
    )
    recent = query(
        "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20"
    )
    loop_results = query(
        "SELECT * FROM loop_results ORDER BY loop_num"
    )
    vol_log = query(
        "SELECT * FROM volatility_log ORDER BY timestamp DESC LIMIT 20"
    )

    # 統計計算
    pnls     = [t["pnl"] for t in trades if t.get("pnl") is not None]
    wins     = [p for p in pnls if p > 0]
    win_rate = len(wins) / len(pnls) if pnls else 0
    total_pnl = sum(pnls)

    # 残高推移（最新残高）
    last_balance = initial
    if trades:
        last_closed = [t for t in trades if t.get("balance_after")]
        if last_closed:
            last_balance = last_closed[-1]["balance_after"]

    # ドローダウン
    peak = initial
    max_dd = 0.0
    running = initial
    for t in trades:
        if t.get("pnl"):
            running += t["pnl"]
            peak = max(peak, running)
            dd = (peak - running) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

    # 資産推移グラフ用データ（最大100点）
    chart_data = []
    running = initial
    for t in trades[-100:]:
        running += t.get("pnl", 0)
        ts = t.get("timestamp", "")[:16].replace("T", " ")
        chart_data.append({"t": ts, "b": round(running)})
    if not chart_data:
        chart_data = [{"t": "開始", "b": initial}]

    # スキャナー（最新の volatility_log から・同一タイムスタンプのデータを使用）
    seen = set()
    scanner = []
    # 最新スキャン時刻を取得
    latest_scan = query(
        "SELECT timestamp FROM volatility_log ORDER BY timestamp DESC LIMIT 1"
    )
    if latest_scan:
        latest_ts = latest_scan[0]["timestamp"][:16]  # 分単位で比較
        recent_vol = query(
            "SELECT * FROM volatility_log WHERE timestamp LIKE ? ORDER BY score DESC",
            (latest_ts[:13] + "%",)  # 同じ時間帯のデータ
        )
        if not recent_vol:
            recent_vol = vol_log
    else:
        recent_vol = vol_log

    for r in recent_vol:
        if r["pair"] not in seen:
            seen.add(r["pair"])
            scanner.append({
                "pair":   r["pair"],
                "score":  r["score"],
                "last":   r["last_price"],
                "active": False,
            })
        if len(scanner) >= 3:
            break

    # アクティブペアを取得（最新トレードのペア）
    active_pair_row = query(
        "SELECT pair FROM trades ORDER BY timestamp DESC LIMIT 1"
    )
    active_pair = active_pair_row[0]["pair"] if active_pair_row else cfg.get("pairs", ["btc_jpy"])[0]
    for s in scanner:
        if s["pair"] == active_pair:
            s["active"] = True

    # ストラテジー情報（マルチペア・ペア別パラメータ対応）
    current_balance = round(last_balance)
    order_size = current_balance * cfg.get("position_size_pct", 0.05)
    pair_params = cfg.get("pair_params", {})
    pairs = cfg.get("pairs", [])

    # ペア別パラメータをリスト化（表示用）
    pair_params_list = []
    for p in pairs:
        overrides = pair_params.get(p, {})
        pair_params_list.append({
            "pair":           p,
            "rsi_oversold":   overrides.get("rsi_oversold",   cfg.get("rsi_oversold",   25)),
            "rsi_overbought": overrides.get("rsi_overbought", cfg.get("rsi_overbought", 65)),
            "stop_loss_pct":  overrides.get("stop_loss_pct",  cfg.get("stop_loss_pct",  0.020)),
            "take_profit_pct":overrides.get("take_profit_pct",cfg.get("take_profit_pct",0.040)),
        })

    # 相関グループを表示用文字列に変換
    corr_groups = cfg.get("correlation_groups", [])
    corr_display = " / ".join(
        "+".join(g) for g in corr_groups
    ) if corr_groups else "なし"

    strategy = {
        # ── 基本設定 ──────────────────────────────────────────
        "pairs":               pairs,
        "pair_params_list":    pair_params_list,
        "max_simultaneous":    cfg.get("max_simultaneous_positions", 4),
        "candle_type":         cfg.get("candle_type", "5min"),
        "scan_interval_min":   cfg.get("scan_interval_sec", 900) // 60,
        "trade_interval_sec":  cfg.get("trade_interval_sec", 300),
        # ── シグナル ──────────────────────────────────────────
        "rsi_period":          cfg.get("rsi_period", 14),
        "bb_period":           cfg.get("bb_period", 20),
        "bb_std":              cfg.get("bb_std", 2.0),
        # ── MTFフィルター ─────────────────────────────────────
        "use_htf_filter":      cfg.get("use_htf_filter", True),
        "htf_ema_period":      cfg.get("htf_ema_period", 20),
        "htf_flat_threshold":  cfg.get("htf_flat_threshold", 0.05),
        # ── リスク管理 ────────────────────────────────────────
        "position_size_pct":      cfg.get("position_size_pct", 0.05),
        "order_size":             order_size,
        "max_unrealized_loss_pct":cfg.get("max_unrealized_loss_pct", 0.05),
        "max_consecutive_sl":     cfg.get("max_consecutive_sl", 3),
        "sl_cooldown_minutes":    cfg.get("sl_cooldown_minutes", 60),
        "corr_display":           corr_display,
        # ── 手数料・PDCA ─────────────────────────────────────
        "maker_fee":           cfg.get("maker_fee", -0.0002) * 100,
        "taker_fee":           cfg.get("taker_fee", 0.0012) * 100,
        "trades_per_loop":     cfg.get("trades_per_loop", 50),
        "target_win_rate":     cfg.get("target_win_rate", 0.55),
        "target_max_drawdown": cfg.get("target_max_drawdown", 0.10),
        "target_consecutive":  cfg.get("target_consecutive", 3),
    }

    return jsonify({
        "updated_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "balance":        round(last_balance),
        "initial_balance": initial,
        "win_rate":       round(win_rate, 4),
        "max_drawdown":   round(max_dd, 4),
        "total_trades":   len(pnls),
        "total_pnl":      round(total_pnl),
        "current_loop":   current_loop,
        "chart_data":     chart_data,
        "scanner":        scanner,
        "loop_results":   loop_results,
        "recent_trades":  recent,
        "strategy":       strategy,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
