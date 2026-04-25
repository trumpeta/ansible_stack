#!/bin/bash

set -e

read -rp "[1] Target server IP or hostname: " SERVER
read -rp "[2] SSH user [root]: " USER
USER=${USER:-root}

if [ -z "${SERVER}" ]; then
  echo "Cilovy server musi byt vyplnen."
  exit 1
fi

echo "[3] Checking SSH key..."

if [ ! -f ~/.ssh/id_rsa.pub ]; then
  echo "Generuji SSH key..."
  ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
else
  echo "SSH key existuje"
fi

echo "[4] Kopiruji SSH key na server..."

ssh-copy-id ${USER}@${SERVER} || \
cat ~/.ssh/id_rsa.pub | ssh ${USER}@${SERVER} \
"mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

echo "[5] Instalace Ansible + tools..."

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

echo "[6] Stazeni deploy stacku..."

mkdir -p ~/deploy
cd ~/deploy

if [ ! -d "ansible-stack" ]; then
  git clone https://github.com/trumpeta/ansible_stack.git ansible-stack
fi

cd ansible-stack

echo "[7] Spoustim interaktivni deployment..."

ansible-playbook -i "${SERVER}," -u ${USER} interactive_full.yml

echo ""
echo "HOTOVO"
echo "Admin: http://$SERVER:7080 (pokud byl zvolen OLS)"
echo "Web:   http://$SERVER"
