#!/usr/bin/env bash
set -e

# macOS Finder tek-tık başlatıcı (Universal path - no hardcoding)
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Başlık
printf '\e]2;Local-Notebook\a'
clear

echo "================================================="
echo "        📚 Local-Notebook Başlatılıyor...        "
echo "================================================="
echo ""

# Servisleri arka planda başlat
./start.sh up -d

echo ""
echo "Servislerin hazır olması bekleniyor..."
for _ in {1..20}; do
  if curl -s http://localhost:8081/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# Varsayılan tarayıcıda arayüzü aç
echo "Tarayıcı açılıyor: http://localhost:8080"
open "http://localhost:8080"

echo ""
echo "================================================="
echo "  ✅ Local-Notebook Başarıyla Çalışıyor!         "
echo "  🌐 Web Arayüzü: http://localhost:8080          "
echo "  🔌 Backend API: http://localhost:8081          "
echo "================================================="
echo ""
echo "İşlem Menüsü:"
echo "  [1] Tarayıcıyı Aç (http://localhost:8080)"
echo "  [2] Canlı Logları İzle (Çıkmak için Ctrl+C)"
echo "  [3] Servisleri Yeniden Başlat"
echo "  [4] Servisleri Tamamen Durdur ve Çık"
echo "  [5] Bu Pencereyi Kapat (Servisler arka planda çalışır)"
echo ""

while true; do
  read -r -p "Seçiminiz [1-5]: " choice
  case "$choice" in
    1)
      open "http://localhost:8080"
      ;;
    2)
      echo "Canlı loglar başlatılıyor... (Geri dönmek için Ctrl+C basın)"
      sleep 0.5
      ./start.sh logs -f || true
      echo ""
      ;;
    3)
      echo "Yeniden başlatılıyor..."
      ./start.sh restart
      sleep 1
      open "http://localhost:8080"
      ;;
    4)
      echo "Tüm servisler durduruluyor..."
      ./start.sh down
      echo "Kapandı. İyi çalışmalar!"
      sleep 1
      exit 0
      ;;
    5|q|Q)
      echo "Servisler arka planda çalışmaya devam ediyor."
      echo "Durdurmak istediğinizde './start.sh down' komutunu çalıştırabilirsiniz."
      sleep 1
      exit 0
      ;;
    *)
      echo "Geçerli bir seçenek giriniz (1, 2, 3, 4, 5)."
      ;;
  esac
done

