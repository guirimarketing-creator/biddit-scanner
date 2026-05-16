#!/usr/bin/env bash
# One-shot setup for biddit-scanner on macOS.
# Run once: bash ~/biddit-scanner/setup.sh

set -e
SCANNER_DIR="$HOME/biddit-scanner"
cd "$SCANNER_DIR"

echo "=== Biddit Scanner Setup ==="

# 1. Create virtualenv
if [ ! -d "venv" ]; then
    echo "[1/5] Creating Python virtualenv (python3.13)..."
    python3.13 -m venv venv
else
    echo "[1/5] Removing old virtualenv and recreating with python3.13..."
    rm -rf venv
    python3.13 -m venv venv
fi

# 2. Install Python dependencies
echo "[2/5] Installing Python dependencies..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

# 3. Install Playwright Chromium browser
echo "[3/5] Installing Playwright Chromium..."
venv/bin/playwright install chromium

# 4. Create log directory
mkdir -p logs

# 5. Install launchd plist for weekly scheduling
PLIST_SRC="$SCANNER_DIR/com.biddit.scanner.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.biddit.scanner.plist"

echo "[4/5] Installing launchd plist (runs every Sunday at 08:00)..."
cp "$PLIST_SRC" "$PLIST_DST"

# Unload first in case already installed
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "      Scheduled job loaded. Verify with: launchctl list | grep biddit"

# 6. First run
echo "[5/5] Running first scan (limit 20 properties for speed test)..."
echo "      Full scan will run every Sunday automatically."
venv/bin/python main.py --limit 20

echo ""
echo "=== Setup complete! ==="
echo "Weekly reports saved to: $SCANNER_DIR/reports/"
echo "To run a full scan now: cd $SCANNER_DIR && venv/bin/python main.py"
echo "To re-analyze without re-scraping: venv/bin/python main.py --no-scrape"
