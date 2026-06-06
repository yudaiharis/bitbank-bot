#!/bin/bash
sleep 40
URL=$(sudo journalctl -u cloudflared-quick --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
if [ -n "$URL" ]; then
  source /home/haris_apakabar/.bashrc 2>/dev/null
  WEBHOOK=$(grep SLACK_WEBHOOK_URL /home/haris_apakabar/.bashrc | cut -d'"' -f2)
  if [ -n "$WEBHOOK" ]; then
    curl -s -X POST "$WEBHOOK" \
      -H 'Content-type: application/json' \
      -d "{\"text\":\"🔗 *ダッシュボードURL更新*\n$URL\"}"
  fi
fi
