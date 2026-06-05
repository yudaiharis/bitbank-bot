"""
Slack Webhook通知モジュール
環境変数 SLACK_WEBHOOK_URL にWebhook URLを設定して使用
"""
import os
import json
import requests
from datetime import datetime


def _get_webhook_url() -> str | None:
    return os.environ.get("SLACK_WEBHOOK_URL")


def send(text: str, blocks: list = None) -> bool:
    """Slackにメッセージを送信。失敗してもボットを止めない"""
    url = _get_webhook_url()
    if not url:
        return False
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def notify_loop_complete(loop_num: int, result: dict):
    """ループ完了通知"""
    achieved = result.get("target_achieved", False)
    emoji = "✅" if achieved else "📊"
    pnl = result.get("total_pnl", 0)
    pnl_str = f"+¥{pnl:,.0f}" if pnl >= 0 else f"-¥{abs(pnl):,.0f}"

    text = f"{emoji} *bitbank bot — Loop {loop_num} 完了*"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} Loop {loop_num} 完了"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*勝率*\n{result.get('win_rate', 0)*100:.1f}%"},
            {"type": "mrkdwn", "text": f"*総損益*\n{pnl_str}"},
            {"type": "mrkdwn", "text": f"*最大DD*\n{result.get('max_drawdown', 0)*100:.1f}%"},
            {"type": "mrkdwn", "text": f"*最終残高*\n¥{result.get('final_balance', 0):,.0f}"},
        ]},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*目標達成*: {'✅ 達成' if achieved else '❌ 未達成'}\n"
                    f"*改善内容*: {result.get('improvements', 'なし')}"
        }},
    ]
    send(text, blocks)


def notify_auto_analysis(date_str: str, improvements: str):
    """週次自動分析完了通知"""
    text = f"🤖 *週次自動分析完了* ({date_str})"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🤖 週次自動分析完了"}},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*実行日時*: {date_str}\n*改善内容*: {improvements}"
        }},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": "ダッシュボードで詳細を確認してください。"
        }},
    ]
    send(text, blocks)


def notify_error(error_msg: str):
    """エラー通知"""
    text = f"🚨 *bitbank bot エラー*\n```{error_msg[:500]}```"
    send(text)


def notify_target_achieved(final_balance: float, loops: int):
    """目標達成通知"""
    text = "🎉 *目標達成！ペーパートレード完了*"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🎉 目標達成！"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*最終残高*\n¥{final_balance:,.0f}"},
            {"type": "mrkdwn", "text": f"*完了ループ数*\n{loops}"},
        ]},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": "final_report.md をダウンロードして詳細を確認してください。"
        }},
    ]
    send(text, blocks)


def notify_bot_started(mode: str, pair: str, balance: float):
    """ボット起動通知"""
    send(
        f"▶️ *bitbank bot 起動*\n"
        f"モード: {mode} | ペア: {pair} | 残高: ¥{balance:,.0f}"
    )


def test_notify():
    """接続テスト"""
    ok = send("✅ bitbank bot の Slack通知テスト成功！")
    print("通知送信:", "成功" if ok else "失敗（SLACK_WEBHOOK_URLを確認してください）")


if __name__ == "__main__":
    test_notify()
