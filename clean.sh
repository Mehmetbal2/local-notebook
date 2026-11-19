#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

DELETE_DATA=false
DELETE_DEPS=false

for arg in "$@"; do
  case "$arg" in
    -d|--data)
      DELETE_DATA=true
      ;;
    --deps)
      DELETE_DEPS=true
      ;;
    -h|--help)
      cat <<'EOF'
Kullanım: ./clean.sh [--data] [--deps]

Local Notebook'un çalışırken ürettiği ara dosyaları temizler.

Seçenekler:
  -d, --data     Ara dosyalara ek olarak veri klasörünü de siler
                 (LOCAL_NOTEBOOK_DATA_DIR, varsayılan ./local-notebook-data):
                 SQLite veritabanı, vektör deposu, yüklenen dosyalar ve Ayarlar'daki
                 LLM API anahtarları (düz metin). "yes" yazarak onay ister; geri alınamaz.
  --deps         frontend/node_modules ve frontend/dist klasörlerini de siler.
  -h, --help     Bu yardımı gösterir.

Örnekler:
  ./clean.sh              # Yalnızca önbellek ve ara dosyalar (güvenli)
  ./clean.sh --deps       # Ek olarak arayüz bağımlılıkları ve derleme çıktısı
  ./clean.sh --data       # Ara dosyalar ve tüm veriler (onay ister)

İpucu: Silme işlemi takılmasın diye önce ./start.sh down ile servisleri durdurun.
EOF
      exit 0
      ;;
    *)
      echo "Bilinmeyen seçenek: $arg" >&2
      echo "Kullanım için: ./clean.sh --help" >&2
      exit 1
      ;;
  esac
done

# ────────────────────────────────────────────────────────────────
# Ön kontrol: yerel servisler veya docker compose çalışıyor mu?
# ────────────────────────────────────────────────────────────────
SERVICES_RUNNING=false
if ./start.sh status 2>/dev/null | grep -q "RUNNING"; then
  SERVICES_RUNNING=true
elif command -v docker >/dev/null 2>&1 && [[ -n "$(docker compose ps -q 2>/dev/null)" ]]; then
  SERVICES_RUNNING=true
fi

if [[ "$SERVICES_RUNNING" == "true" ]]; then
  echo "Local Notebook servisleri çalışıyor."
  if [[ "$DELETE_DATA" == "true" ]]; then
    echo "Veriler silinmeden önce servisler durdurulmalı; aksi hâlde SQLite veritabanı bozulabilir."
    echo ""
    read -p "Servisler şimdi ./start.sh down ile durdurulsun mu? (devam için yes, iptal için başka bir şey): " stop_confirm
    if [[ "$stop_confirm" == "yes" ]]; then
      ./start.sh down
      echo ""
    else
      echo "İptal edildi. Önce ./start.sh down çalıştırıp bu betiği tekrar başlatın."
      exit 1
    fi
  else
    echo "(Ara dosyaların temizliği çalışan servisleri etkilemez; devam ediliyor.)"
    echo ""
  fi
fi

# ────────────────────────────────────────────────────────────────
# Bölüm 1: ara dosyalar (varsayılan, güvenli)
# ────────────────────────────────────────────────────────────────
echo "=== Ara dosyalar temizleniyor ==="

if [[ "$DELETE_DEPS" == "true" ]]; then
  echo "  [frontend] node_modules / dist"
  rm -rf frontend/node_modules frontend/dist
fi

echo "  [python]   __pycache__ / *.pyc / *.pyo / *.egg-info / .pytest_cache"
find backend services -type d \
  \( -name __pycache__ -o -name .pytest_cache -o -name "*.egg-info" \) \
  -exec rm -rf {} + 2>/dev/null || true
find backend services -type f \
  \( -name "*.pyc" -o -name "*.pyo" \) \
  -delete 2>/dev/null || true

echo "  [OS]       .DS_Store / Thumbs.db"
find . -type f \( -name ".DS_Store" -o -name "Thumbs.db" \) -delete 2>/dev/null || true

echo "Ara dosyalar temizlendi."
echo ""

# ────────────────────────────────────────────────────────────────
# Bölüm 2: veriler (--data ve "yes" onayı gerekir)
# ────────────────────────────────────────────────────────────────
if [[ "$DELETE_DATA" == "true" ]]; then
  DATA_DIR="${LOCAL_NOTEBOOK_DATA_DIR:-./local-notebook-data}"

  echo "=== Veri silme (tehlikeli, geri alınamaz) ==="
  echo ""
  echo "Aşağıdakiler kalıcı olarak silinecek:"
  echo ""
  echo "  [veri]   $DATA_DIR"
  if [[ -d "$DATA_DIR" ]]; then
    echo "           - SQLite veritabanı (kullanıcılar, tüm projeler, tüm sohbet geçmişi)"
    echo "           - Vektör deposu (indekslenmiş tüm belge vektörleri)"
    echo "           - Yüklenen PDF, ses ve notlar"
    echo "           - Ayarlar'daki LLM API anahtarları ve diğer ayarlar (düz metin)"
  else
    echo "           (yok, atlanıyor)"
  fi
  echo ""
  echo "  [legacy] backend/*.db / *.db-wal / *.db-shm / milvus_data.db* / uploads/"
  echo "           (eski sürümlerden kalan yollar; varsa onlar da silinir)"
  echo ""
  echo "Önce yedek almanız önerilir:"
  echo "  cp -r \"$DATA_DIR\" \"$DATA_DIR.backup.\$(date +%Y%m%d-%H%M%S)\""
  echo ""
  read -p "Silmek için yes yazın (başka her şey iptal eder): " confirm

  if [[ "$confirm" == "yes" ]]; then
    rm -rf "$DATA_DIR"
    rm -f backend/*.db backend/*.db-wal backend/*.db-shm 2>/dev/null || true
    rm -f backend/milvus_data.db* 2>/dev/null || true
    rm -rf backend/uploads 2>/dev/null || true
    echo ""
    echo "Veriler silindi."
  else
    echo ""
    echo "İptal edildi; veriler korundu."
  fi
fi
