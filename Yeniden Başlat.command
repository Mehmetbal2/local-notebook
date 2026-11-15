#!/usr/bin/env bash
# Finder'dan çift tıklayın: Local Notebook'u (arka uç, arayüz ve SearXNG) yeniden başlatır.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
printf '\e]2;Local-Notebook yeniden başlatılıyor\a'
echo "Local Notebook yeniden başlatılıyor..."
./start.sh restart
echo ""
echo "Bitti. Bu pencereyi kapatabilirsiniz."
