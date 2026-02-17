#!/bin/bash
cd "$(dirname "$0")"

if [ -f bot.pid ]; then
    kill $(cat bot.pid) 2>/dev/null
    rm bot.pid
    echo "Bot detenido."
else
    echo "El bot no está corriendo."
fi
