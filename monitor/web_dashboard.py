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
import glob
from datetime import datetime
from flask import Flask, jsonify, send_file, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trades.db")


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
    <h2>直近20件のトレード</h2>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>時刻(JST)</th><th>Loop</th><th>ペア</th><th>方向</th><th>売買金額</th><th>エントリー</th><th>決済</th><th>損益</th></tr></thead>
        <tbody id="tradelist"></tbody>
      </table>
    </div>
  </div>
  <div class="panel" style="margin-bottom:20px">
    <h2>AI分析 <span style="font-size:11px;font-weight:400;color:#475569">自動（毎週日曜2時）または手動実行</span></h2>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
      <button onclick="triggerAnalysis()" id="analyze-btn" style="font-size:13px;padding:8px 18px;background:#312e81;border:1px solid #4338ca;border-radius:6px;color:#a78bfa;cursor:pointer">今すぐ分析・改善を実行</button>
      <span id="analyze-status" style="font-size:12px;color:#64748b">状態を確認中...</span>
    </div>
    <div id="analyze-log" style="font-size:12px;color:#475569;font-family:monospace;background:#0f1117;padding:8px 12px;border-radius:6px;min-height:24px"></div>
  </div>
  <div class="panel" style="margin-bottom:20px">
    <h2>レポートダウンロード <span style="font-size:11px;font-weight:400;color:#475569">（PCのClaude Codeで手動分析する場合）</span></h2>
    <div id="dl-reports">読み込み中...</div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap">
      <a href="/download/db" style="display:inline-block;font-size:13px;padding:7px 14px;background:#1e2235;border:1px solid #2d3148;border-radius:6px;color:#60a5fa;text-decoration:none">trades.db ダウンロード</a>
      <a href="/download/config" style="display:inline-block;font-size:13px;padding:7px 14px;background:#1e2235;border:1px solid #2d3148;border-radius:6px;color:#60a5fa;text-decoration:none">config.yaml ダウンロード</a>
      <a id="dl-final" href="/download/final" style="display:none;font-size:13px;padding:7px 14px;background:#14532d;border:1px solid #166534;border-radius:6px;color:#34d399;text-decoration:none">最終レポート ダウンロード</a>
    </div>
  </div>
  <div class="panel" style="margin-bottom:20px">
    <h2>現在のトレード戦略</h2>
    <div id="strategy-panel" style="font-size:13px;color:#94a3b8;line-height:2">読み込み中...</div>
  </div>
  <div class="footer">30秒ごとに自動更新 &nbsp;|&nbsp; bitbank Public API</div>
</div>
<script>
let chart = null;

async function triggerAnalysis() {
  const btn = document.getElementById('analyze-btn');
  const status = document.getElementById('analyze-status');
  btn.disabled = true;
  btn.style.opacity = '0.5';
  status.textContent = '起動中...';
  try {
    const r = await fetch('/api/analyze', {method:'POST'});
    const d = await r.json();
    status.textContent = d.message;
    if (d.status === 'started') {
      status.style.color = '#34d399';
      pollAnalysisStatus();
    } else {
      btn.disabled = false;
      btn.style.opacity = '1';
    }
  } catch(e) {
    status.textContent = 'エラーが発生しました';
    btn.disabled = false;
    btn.style.opacity = '1';
  }
}

async function pollAnalysisStatus() {
  const btn = document.getElementById('analyze-btn');
  const status = document.getElementById('analyze-status');
  const log = document.getElementById('analyze-log');
  const r = await fetch('/api/analysis_status');
  const d = await r.json();
  log.textContent = d.last_log || '';
  if (d.running) {
    status.textContent = '分析実行中... (数分かかります)';
    status.style.color = '#fbbf24';
    setTimeout(pollAnalysisStatus, 5000);
  } else {
    status.textContent = d.latest_improvement
      ? `完了: ${d.latest_improvement}`
      : '待機中';
    status.style.color = '#34d399';
    btn.disabled = false;
    btn.style.opacity = '1';
    loadReports();
  }
}

async function loadReports() {
  try {
    const r = await fetch('/api/reports');
    const d = await r.json();
    const el = document.getElementById('dl-reports');
    if (d.reports.length === 0) {
      el.innerHTML = '<span style="color:#475569;font-size:13px">まだレポートがありません（Loop完了後に生成されます）</span>';
    } else {
      el.innerHTML = d.reports.map(r =>
        `<div class="scanner-row">
          <span class="pair">Loop ${r.loop} レポート</span>
          <span class="score">${r.updated}</span>
          <a href="/download/report/${r.loop}" style="font-size:12px;color:#60a5fa;text-decoration:none;padding:3px 10px;border:1px solid #2d3148;border-radius:4px">ダウンロード</a>
        </div>`
      ).join('');
    }
    if (d.has_final) {
      document.getElementById('dl-final').style.display = 'inline-block';
    }
  } catch(e) { console.error(e); }
}

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

    // スキャナー
    const sc = document.getElementById('scanner');
    if (d.scanner && d.scanner.length) {
      sc.innerHTML = d.scanner.map(r =>
        `<div class="scanner-row">
          <span class="pair ${r.active ? 'active' : ''}">${r.pair}${r.active ? ' ◀' : ''}</span>
          <span class="score">${Number(r.score).toFixed(4)}</span>
          <span class="price">¥${Number(r.last).toLocaleString()}</span>
        </div>`
      ).join('');
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

    // ストラテジー表示
    if (d.strategy) {
      const sp = document.getElementById('strategy-panel');
      const s = d.strategy;
      sp.innerHTML = `
        <ul style="list-style:none;padding:0;margin:0">
          <li>📌 <b>対象銘柄</b>：${s.active_pair}（ボラティリティスコア上位から自動選択・${s.scan_interval_min}分ごとに再スキャン）</li>
          <li>📐 <b>シグナル条件</b>：RSI(${s.rsi_period}) &lt; ${s.rsi_oversold} かつ 価格 &lt; ボリンジャーバンド下限 → <span style="color:#34d399">買い</span></li>
          <li style="margin-left:1.5em">RSI(${s.rsi_period}) &gt; ${s.rsi_overbought} かつ 価格 &gt; ボリンジャーバンド上限 → <span style="color:#f87171">売り</span></li>
          <li>📊 <b>ボリンジャーバンド</b>：期間 ${s.bb_period}・標準偏差 ${s.bb_std}σ</li>
          <li>💰 <b>1回の発注額</b>：残高の ${(s.position_size_pct*100).toFixed(0)}%（現在 ¥${Math.round(s.order_size).toLocaleString()} 相当）</li>
          <li>🛑 <b>ストップロス</b>：エントリーから -${(s.stop_loss_pct*100).toFixed(1)}%（損失限定）</li>
          <li>🎯 <b>テイクプロフィット</b>：エントリーから +${(s.take_profit_pct*100).toFixed(1)}%（利益確定）</li>
          <li>💸 <b>手数料</b>：Maker ${s.maker_fee}%（受取）/ Taker +${s.taker_fee}%（支払）・スプレッドも計上</li>
          <li>🔄 <b>PDCAサイクル</b>：${s.trades_per_loop}件ごとに自動分析・毎週日曜11時(JST)にClaude Codeが戦略改善</li>
          <li>🎯 <b>目標</b>：勝率 ${(s.target_win_rate*100).toFixed(0)}%以上 かつ 最大DD ${(s.target_max_drawdown*100).toFixed(0)}%以内を${s.target_consecutive}連続達成</li>
        </ul>`;
    }

  } catch(e) {
    console.error(e);
  }
}

load();
loadReports();
pollAnalysisStatus();
setInterval(load, 30000);
setInterval(loadReports, 60000);
setInterval(pollAnalysisStatus, 30000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/api/analyze", methods=["POST"])
def trigger_analysis():
    """手動で分析を即時起動"""
    import subprocess
    lock = os.path.join(os.path.dirname(__file__), "..", "reports/.analysis_running")
    if os.path.exists(lock):
        return jsonify({"status": "running", "message": "分析がすでに実行中です"})
    script = os.path.join(os.path.dirname(__file__), "..", "deploy/weekly_analysis.sh")
    if not os.path.exists(script):
        return jsonify({"status": "error", "message": "分析スクリプトが見つかりません"})
    subprocess.Popen(["bash", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({"status": "started", "message": "分析を開始しました（数分かかります）"})


@app.route("/api/analysis_status")
def analysis_status():
    """分析の実行状態を返す"""
    lock = os.path.join(os.path.dirname(__file__), "..", "reports/.analysis_running")
    log = os.path.join(os.path.dirname(__file__), "..", "reports/analysis.log")
    running = os.path.exists(lock)
    last_log = ""
    if os.path.exists(log):
        try:
            with open(log) as f:
                lines = f.readlines()
                last_log = lines[-1].strip() if lines else ""
        except Exception:
            pass
    # 最新の自動改善レポートを確認
    import glob
    improvements = sorted(glob.glob(
        os.path.join(os.path.dirname(__file__), "..", "reports/auto_improvement_*.md")
    ))
    latest_improvement = os.path.basename(improvements[-1]) if improvements else None
    return jsonify({
        "running": running,
        "last_log": last_log,
        "latest_improvement": latest_improvement,
    })


@app.route("/download/report/<int:loop_num>")
def download_report(loop_num):
    """ループレポートをMarkdownでダウンロード"""
    path = os.path.join(os.path.dirname(__file__), "..", f"reports/report_{loop_num}.md")
    if not os.path.exists(path):
        return Response("レポートが見つかりません", status=404)
    return send_file(os.path.abspath(path), as_attachment=True,
                     download_name=f"report_{loop_num}.md", mimetype="text/markdown")


@app.route("/download/final")
def download_final():
    """最終レポートをダウンロード"""
    path = os.path.join(os.path.dirname(__file__), "..", "reports/final_report.md")
    if not os.path.exists(path):
        return Response("最終レポートがまだ生成されていません", status=404)
    return send_file(os.path.abspath(path), as_attachment=True,
                     download_name="final_report.md", mimetype="text/markdown")


@app.route("/download/db")
def download_db():
    """trades.db をダウンロード（Claude Codeでの分析用）"""
    path = os.path.join(os.path.dirname(__file__), "..", "trades.db")
    if not os.path.exists(path):
        return Response("DBファイルが見つかりません", status=404)
    return send_file(os.path.abspath(path), as_attachment=True,
                     download_name="trades.db", mimetype="application/octet-stream")


@app.route("/download/config")
def download_config():
    """現在のconfig.yamlをダウンロード"""
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    if not os.path.exists(path):
        return Response("設定ファイルが見つかりません", status=404)
    return send_file(os.path.abspath(path), as_attachment=True,
                     download_name="config.yaml", mimetype="text/yaml")


@app.route("/api/reports")
def list_reports():
    """利用可能なレポート一覧を返す"""
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    files = glob.glob(os.path.join(reports_dir, "report_*.md"))
    result = []
    for f in sorted(files):
        name = os.path.basename(f)
        loop = name.replace("report_", "").replace(".md", "")
        try:
            size = os.path.getsize(f)
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
            result.append({"loop": int(loop), "size": size, "updated": mtime})
        except Exception:
            pass
    final = os.path.join(reports_dir, "final_report.md")
    has_final = os.path.exists(final)
    return jsonify({"reports": result, "has_final": has_final})


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

    # ストラテジー情報
    current_balance = round(last_balance)
    order_size = current_balance * cfg.get("position_size_pct", 0.05)
    strategy = {
        "active_pair":        active_pair,
        "scan_interval_min":  cfg.get("scan_interval_sec", 900) // 60,
        "rsi_period":         cfg.get("rsi_period", 14),
        "rsi_oversold":       cfg.get("rsi_oversold", 30),
        "rsi_overbought":     cfg.get("rsi_overbought", 70),
        "bb_period":          cfg.get("bb_period", 20),
        "bb_std":             cfg.get("bb_std", 2.0),
        "position_size_pct":  cfg.get("position_size_pct", 0.05),
        "order_size":         order_size,
        "stop_loss_pct":      cfg.get("stop_loss_pct", 0.02),
        "take_profit_pct":    cfg.get("take_profit_pct", 0.04),
        "maker_fee":          cfg.get("maker_fee", -0.0002) * 100,
        "taker_fee":          cfg.get("taker_fee", 0.0012) * 100,
        "trades_per_loop":    cfg.get("trades_per_loop", 50),
        "target_win_rate":    cfg.get("target_win_rate", 0.55),
        "target_max_drawdown": cfg.get("target_max_drawdown", 0.10),
        "target_consecutive": cfg.get("target_consecutive", 3),
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
    app.run(host="0.0.0.0", port=port, threaded=False, debug=False)


# ============================================================
# 損益グラフ専用ページ
# ============================================================
CHART_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>損益グラフ | bitbank bot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0}
header{background:#1a1d2e;border-bottom:1px solid #2d3148;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:15px;font-weight:600;color:#a78bfa}
header a{font-size:12px;color:#60a5fa;text-decoration:none}
.container{max-width:900px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.card{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:14px}
.card .label{font-size:11px;color:#64748b;margin-bottom:4px;text-transform:uppercase}
.card .value{font-size:20px;font-weight:600}
.green{color:#34d399}.red{color:#f87171}.blue{color:#60a5fa}.purple{color:#a78bfa}
.panel{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:16px;margin-bottom:16px}
.panel h2{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:14px;text-transform:uppercase}
canvas{width:100%!important}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:6px;color:#64748b;border-bottom:1px solid #2d3148}
td{padding:6px;border-bottom:1px solid #1e2235;font-variant-numeric:tabular-nums}
.footer{text-align:center;font-size:11px;color:#334155;padding:12px 0 24px}
</style>
</head>
<body>
<header>
  <h1>損益グラフ</h1>
  <div style="display:flex;gap:16px;align-items:center">
    <span id="ts" style="font-size:12px;color:#64748b"></span>
    <a href="/">← ダッシュボードに戻る</a>
  </div>
</header>
<div class="container">
  <div class="cards">
    <div class="card"><div class="label">開始残高</div><div class="value blue" id="initial">¥1,000,000</div></div>
    <div class="card"><div class="label">現在残高</div><div class="value blue" id="balance">-</div></div>
    <div class="card"><div class="label">総損益</div><div class="value" id="pnl">-</div></div>
    <div class="card"><div class="label">損益率</div><div class="value" id="pnl_pct">-</div></div>
    <div class="card"><div class="label">勝率</div><div class="value purple" id="winrate">-</div></div>
    <div class="card"><div class="label">最大DD</div><div class="value" id="maxdd">-</div></div>
    <div class="card"><div class="label">総手数料</div><div class="value" id="total_fee">-</div></div>
    <div class="card"><div class="label">取引件数</div><div class="value blue" id="trades">-</div></div>
  </div>

  <div class="panel">
    <h2>資産推移（開始: ¥1,000,000）</h2>
    <canvas id="balance-chart" height="280"></canvas>
  </div>

  <div class="panel">
    <h2>トレード別損益</h2>
    <canvas id="pnl-chart" height="200"></canvas>
  </div>

  <div class="panel">
    <h2>コスト内訳（累計）</h2>
    <canvas id="cost-chart" height="180"></canvas>
  </div>

  <div class="panel">
    <h2>取引履歴（直近50件）</h2>
    <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>時刻</th><th>ペア</th><th>方向</th>
        <th>エントリー</th><th>決済</th><th>損益</th><th>手数料</th><th>理由</th>
      </tr></thead>
      <tbody id="trade-table"></tbody>
    </table>
    </div>
  </div>
  <div class="footer">60秒ごとに自動更新</div>
</div>
<script>
let balChart = null, pnlChart = null, costChart = null;

async function load() {
  const r = await fetch('/api/chart_data');
  const d = await r.json();
  document.getElementById('ts').textContent = d.updated_at;

  const init = d.initial_balance;
  const bal  = d.balance;
  const pnl  = bal - init;
  const pct  = (pnl / init * 100);

  document.getElementById('initial').textContent  = '¥' + init.toLocaleString();
  document.getElementById('balance').textContent   = '¥' + Math.round(bal).toLocaleString();

  const pnlEl = document.getElementById('pnl');
  pnlEl.textContent = (pnl>=0?'+':'') + '¥' + Math.round(pnl).toLocaleString();
  pnlEl.className = 'value ' + (pnl>=0?'green':'red');

  const pctEl = document.getElementById('pnl_pct');
  pctEl.textContent = (pct>=0?'+':'') + pct.toFixed(2) + '%';
  pctEl.className = 'value ' + (pct>=0?'green':'red');

  document.getElementById('winrate').textContent   = (d.win_rate*100).toFixed(1) + '%';
  const ddEl = document.getElementById('maxdd');
  ddEl.textContent = (d.max_drawdown*100).toFixed(1) + '%';
  ddEl.className = 'value ' + (d.max_drawdown>0.08?'red':'green');
  document.getElementById('total_fee').textContent = '¥' + Math.round(d.total_fee).toLocaleString();
  document.getElementById('trades').textContent    = d.total_trades;

  // 資産推移グラフ
  const bLabels = d.balance_series.map(p=>p.t);
  const bVals   = d.balance_series.map(p=>p.b);
  if (!balChart) {
    balChart = new Chart(document.getElementById('balance-chart').getContext('2d'), {
      type:'line',
      data:{labels:bLabels, datasets:[
        {label:'残高', data:bVals, borderColor:'#60a5fa', backgroundColor:'rgba(96,165,250,0.08)', borderWidth:2, pointRadius:0, fill:true, tension:0.3},
        {label:'開始残高', data:bLabels.map(()=>init), borderColor:'#475569', borderWidth:1, borderDash:[4,4], pointRadius:0, fill:false},
      ]},
      options:{responsive:true, plugins:{legend:{labels:{color:'#94a3b8',font:{size:12}}}},
        scales:{x:{ticks:{color:'#475569',maxTicksLimit:8},grid:{color:'#1e2235'}},
                y:{ticks:{color:'#475569',callback:v=>'¥'+v.toLocaleString()},grid:{color:'#1e2235'}}}}
    });
  } else {
    balChart.data.labels = bLabels;
    balChart.data.datasets[0].data = bVals;
    balChart.data.datasets[1].data = bLabels.map(()=>init);
    balChart.update('none');
  }

  // トレード別損益棒グラフ
  const pLabels = d.trade_pnls.map((_,i)=>'#'+(i+1));
  const pVals   = d.trade_pnls.map(p=>p.pnl);
  const pColors = pVals.map(v=>v>=0?'rgba(52,211,153,0.7)':'rgba(248,113,113,0.7)');
  if (!pnlChart) {
    pnlChart = new Chart(document.getElementById('pnl-chart').getContext('2d'), {
      type:'bar',
      data:{labels:pLabels, datasets:[{label:'損益(円)', data:pVals, backgroundColor:pColors, borderWidth:0}]},
      options:{responsive:true, plugins:{legend:{display:false}},
        scales:{x:{ticks:{color:'#475569'},grid:{color:'#1e2235'}},
                y:{ticks:{color:'#475569',callback:v=>(v>=0?'+':'')+v.toLocaleString()},grid:{color:'#1e2235'}}}}
    });
  } else {
    pnlChart.data.labels = pLabels;
    pnlChart.data.datasets[0].data = pVals;
    pnlChart.data.datasets[0].backgroundColor = pColors;
    pnlChart.update('none');
  }

  // コスト内訳グラフ
  if (!costChart) {
    costChart = new Chart(document.getElementById('cost-chart').getContext('2d'), {
      type:'doughnut',
      data:{
        labels:['Maker受取（+）','Taker手数料','スプレッドコスト'],
        datasets:[{
          data:[
            Math.abs(d.cost_breakdown.maker_rebate),
            d.cost_breakdown.taker_fee,
            d.cost_breakdown.spread_cost
          ],
          backgroundColor:['rgba(52,211,153,0.7)','rgba(248,113,113,0.7)','rgba(251,191,36,0.7)'],
          borderWidth:0,
        }]
      },
      options:{responsive:true,plugins:{legend:{labels:{color:'#94a3b8',font:{size:12}}}}}
    });
  } else {
    costChart.data.datasets[0].data = [
      Math.abs(d.cost_breakdown.maker_rebate),
      d.cost_breakdown.taker_fee,
      d.cost_breakdown.spread_cost,
    ];
    costChart.update('none');
  }

  // 取引履歴テーブル
  const tbody = document.getElementById('trade-table');
  tbody.innerHTML = d.recent_trades.map(t=>{
    const pnl = t.pnl ?? 0;
    const ts  = (t.timestamp||'').substring(0,16).replace('T',' ');
    return `<tr>
      <td>${ts}</td><td>${t.pair}</td>
      <td style="color:${t.side==='buy'?'#34d399':'#f87171'}">${t.side.toUpperCase()}</td>
      <td>¥${Math.round(t.entry_price).toLocaleString()}</td>
      <td>${t.exit_price?'¥'+Math.round(t.exit_price).toLocaleString():'保有中'}</td>
      <td style="color:${pnl>=0?'#34d399':'#f87171'}">${t.status==='open'?'-':(pnl>=0?'+':'')+'¥'+Math.round(pnl).toLocaleString()}</td>
      <td style="color:#64748b">${t.fee?'¥'+Math.round(t.fee).toLocaleString():'-'}</td>
      <td style="color:#64748b">${t.reason||'-'}</td>
    </tr>`;
  }).join('');
}

load();
setInterval(load, 60000);
</script>
</body>
</html>"""


@app.route("/chart")
def chart_page():
    return CHART_HTML


@app.route("/api/chart_data")
def chart_data():
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}

    initial = cfg.get("initial_balance_jpy", 1_000_000)
    trades  = query("SELECT * FROM trades WHERE status='closed' ORDER BY timestamp")
    recent  = query("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 50")

    pnls    = [t["pnl"] for t in trades if t.get("pnl") is not None]
    fees    = [t["fee"] for t in trades if t.get("fee") is not None]
    wins    = [p for p in pnls if p > 0]
    win_rate = len(wins) / len(pnls) if pnls else 0
    total_fee = sum(fees)

    # 残高推移
    balance_series = []
    running = initial
    for t in trades:
        running += t.get("pnl", 0)
        ts = (t.get("timestamp") or "")[:16].replace("T", " ")
        balance_series.append({"t": ts, "b": round(running)})
    if not balance_series:
        balance_series = [{"t": "開始", "b": initial}]

    # ドローダウン
    peak = initial
    max_dd = 0.0
    running2 = initial
    for t in trades:
        running2 += t.get("pnl", 0)
        peak = max(peak, running2)
        dd = (peak - running2) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # コスト内訳（feeの符号で振り分け）
    maker_rebate = sum(t["fee"] for t in trades if t.get("fee", 0) < 0)
    taker_fee    = sum(t["fee"] for t in trades if t.get("fee", 0) > 0)
    spread_cost  = total_fee - maker_rebate - taker_fee

    return jsonify({
        "updated_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "initial_balance": initial,
        "balance":         round(running2),
        "win_rate":        round(win_rate, 4),
        "max_drawdown":    round(max_dd, 4),
        "total_trades":    len(pnls),
        "total_fee":       round(total_fee, 2),
        "balance_series":  balance_series,
        "trade_pnls":      [{"pnl": round(t["pnl"], 0)} for t in trades[-100:]],
        "cost_breakdown": {
            "maker_rebate": round(maker_rebate, 2),
            "taker_fee":    round(taker_fee, 2),
            "spread_cost":  round(spread_cost, 2),
        },
        "recent_trades": recent,
    })
