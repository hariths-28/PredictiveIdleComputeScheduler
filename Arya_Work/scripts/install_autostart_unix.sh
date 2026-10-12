#!/bin/bash
# ========================================================
# Phase 0 Step 4: Register Logger to Autostart on Login (Mac / Linux)
# ========================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
OS="$(uname -s)"

if [ "$OS" == "Darwin" ]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/com.predictiveidle.logger.plist"
    echo "Configuring macOS LaunchAgent in $PLIST_PATH..."
    mkdir -p "$HOME/Library/LaunchAgents"

    cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.predictiveidle.logger</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>$DIR/main.py</string>
        <string>--log-only</string>
        <string>--interval</string>
        <string>15</string>
        <string>--csv-file</string>
        <string>$DIR/laptop_telemetry.csv</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF
    launchctl unload "$PLIST_PATH" 2>/dev/null
    launchctl load "$PLIST_PATH"
    echo "[SUCCESS] macOS LaunchAgent installed and loaded!"

elif [ "$OS" == "Linux" ]; then
    AUTOSTART_DIR="$HOME/.config/autostart"
    DESKTOP_FILE="$AUTOSTART_DIR/idle_compute_logger.desktop"
    mkdir -p "$AUTOSTART_DIR"

    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Exec=python3 $DIR/main.py --log-only --interval 15 --csv-file $DIR/laptop_telemetry.csv
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Idle Compute Telemetry Logger
Comment=Continuous usage logger for IDP ML Oracle
EOF
    echo "[SUCCESS] Linux autostart desktop entry created at $DESKTOP_FILE!"
fi
