#!/bin/bash

set -e

echo "[1] Detecting server IP..."
SERVER=$(curl -s ifconfig.me)
USER="root"

echo "[2] Checking SSH key..."

if [ ! -f ~/.ssh/id_rsa.pub ]; then
  echo "Generuji SSH key..."
  ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
else
  echo "SSH key existuje"
fi

echo "[3] Kopíruji SSH key na server..."

ssh-copy-id ${USER}@${SERVER} || \
cat ~/.ssh/id_rsa.pub | ssh ${USER}@${SERVER} \
"mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

echo "[4] Instalace Ansible + tools..."

if command -v apt >/dev/null; then
  sudo apt update
  sudo apt install -y ansible git wget curl
elif command -v dnf >/dev/null; then
  sudo dnf install -y ansible git wget curl
elif command -v yum >/dev/null; then
  sudo yum install -y ansible git wget curl
else
  echo "Nepodporovaný package manager"
  exit 1
fi

echo "[5] Stažení deploy stacku..."

mkdir -p ~/deploy
cd ~/deploy

if [ ! -d "ansible-stack" ]; then
  git clone https://github.com/YOUR_REPO/ansible-stack.git
fi

cd ansible-stack

echo "[6] Spouštím interaktivní deployment..."

ansible-playbook -i "${SERVER}," -u ${USER} interactive_full.yml

echo ""
echo "✅ HOTOVO"
echo "👉 Admin: http://$SERVER:7080 (OLS pokud použit)"
echo "👉 Web:   http://$SERVER"
