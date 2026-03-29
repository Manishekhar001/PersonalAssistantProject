#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# EC2 Setup Script — run this ONCE after SSH-ing into your EC2 instance
# Usage: bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e  # Exit immediately if any command fails

echo "======================================"
echo " Personal Assistant — EC2 Setup"
echo "======================================"

# 1. Update system packages
echo "[1/7] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

# 2. Install Python 3.11 and pip
echo "[2/7] Installing Python 3.11..."
sudo apt-get install -y python3.11 python3.11-venv python3-pip git

# 3. Create virtual environment
echo "[3/7] Creating virtual environment..."
cd ~/personal-assistant
python3.11 -m venv venv
source venv/bin/activate

# 4. Install dependencies
echo "[4/7] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create data directory for SQLite
echo "[5/7] Creating data directory..."
mkdir -p data

# 6. Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  ⚠️  .env file created from template."
    echo "  👉  Edit it now: nano .env"
    echo "  Add all your API keys before starting the bot."
    echo ""
fi

# 7. Create a systemd service so the bot runs automatically and restarts on crash
echo "[6/7] Creating systemd service..."
sudo bash -c "cat > /etc/systemd/system/personal-assistant.service << EOF
[Unit]
Description=Personal Assistant Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python bot.py
Restart=always
RestartSec=5
EnvironmentFile=$(pwd)/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable personal-assistant

echo "[7/7] Done!"
echo ""
echo "======================================"
echo " Next steps:"
echo "======================================"
echo ""
echo "1. Fill in your API keys:"
echo "   nano .env"
echo ""
echo "2. Start the bot:"
echo "   sudo systemctl start personal-assistant"
echo ""
echo "3. Check if it's running:"
echo "   sudo systemctl status personal-assistant"
echo ""
echo "4. Watch live logs:"
echo "   sudo journalctl -u personal-assistant -f"
echo ""
echo "5. Restart after changes:"
echo "   sudo systemctl restart personal-assistant"
echo ""
echo "======================================"
