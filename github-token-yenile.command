#!/bin/bash

set -e

REPO_DIR="$HOME/Desktop/Local-Notebook"
PUBLISH_SCRIPT="$REPO_DIR/local-notebook-data/publish.sh"

echo "======================================"
echo "       GitHub Token Yenileme"
echo "======================================"
echo

if [ ! -f "$PUBLISH_SCRIPT" ]; then
    echo "HATA: publish.sh dosyası bulunamadı:"
    echo "$PUBLISH_SCRIPT"
    read -p "Çıkmak için Enter..."
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "HATA: Git bulunamadı."
    read -p "Çıkmak için Enter..."
    exit 1
fi

if ! git credential-osxkeychain get </dev/null >/dev/null 2>&1; then
    echo "Bilgi: macOS Keychain credential helper kontrol edilemedi."
    echo "Git'in osxkeychain helper'ını kullanıp kullanmadığını kontrol edin:"
    git config --get credential.helper || true
    echo
fi

read -r -p "GitHub kullanıcı adın [Mehmetbal2]: " GITHUB_USER
GITHUB_USER="${GITHUB_USER:-Mehmetbal2}"

echo
read -r -s -p "Yeni GitHub Personal Access Token: " GITHUB_TOKEN
echo
echo

if [ -z "$GITHUB_TOKEN" ]; then
    echo "HATA: Token boş olamaz."
    read -p "Çıkmak için Enter..."
    exit 1
fi

# Token'ı komut satırı argümanına veya dosyaya yazmadan Keychain'e kaydet.
if ! printf 'protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n' \
    "$GITHUB_USER" "$GITHUB_TOKEN" | git credential-osxkeychain store; then
    unset GITHUB_TOKEN
    echo "HATA: Token Keychain'e kaydedilemedi."
    read -p "Çıkmak için Enter..."
    exit 1
fi

unset GITHUB_TOKEN

echo "Token macOS Anahtar Zinciri'ne kaydedildi."
echo
echo "Not: Token'da repo ve workflow izinleri bulunmalıdır."
echo
echo "======================================"
echo "       Publish işlemi başlıyor"
echo "======================================"
echo

cd "$REPO_DIR"
bash "$PUBLISH_SCRIPT"

echo
echo "======================================"
echo "       Publish işlemi başarılı"
echo "======================================"
echo
read -p "Çıkmak için Enter..."
