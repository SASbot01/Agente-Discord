#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

# Matar proceso anterior si existe
if [ -f bot.pid ]; then
    kill $(cat bot.pid) 2>/dev/null
    rm bot.pid
fi

# Arrancar en background
nohup python3 main.py > bot.log 2>&1 &
echo $! > bot.pid

echo "Bot arrancado (PID: $(cat bot.pid))"
echo "Logs: tail -f bot.log"
