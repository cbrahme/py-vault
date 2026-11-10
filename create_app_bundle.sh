#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$HOME/.pyvault"
APP_DIR="$PROJECT_DIR/PyVault.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

echo "=== 1. Syncing PyVault Runtime into $RUNTIME_DIR ==="
mkdir -p "$RUNTIME_DIR/core"

# Copy or sync venv
if [ ! -d "$RUNTIME_DIR/venv" ]; then
    echo "Copying virtual environment to $RUNTIME_DIR/venv..."
    cp -R "$PROJECT_DIR/venv" "$RUNTIME_DIR/venv"
fi

# Sync application source files
cp -R "$PROJECT_DIR/core/"* "$RUNTIME_DIR/core/"
cp "$PROJECT_DIR/gui.py" "$RUNTIME_DIR/"
cp "$PROJECT_DIR/sync_server.py" "$RUNTIME_DIR/"
cp "$PROJECT_DIR/cli.py" "$RUNTIME_DIR/"
cp "$PROJECT_DIR/app_icon.png" "$RUNTIME_DIR/"
ln -sfn "$PROJECT_DIR/downloads" "$RUNTIME_DIR/downloads"

# Migrate vault.enc if not already in runtime dir
if [ ! -f "$RUNTIME_DIR/vault.enc" ] && [ -f "$PROJECT_DIR/vault.enc" ]; then
    echo "Migrating vault.enc to $RUNTIME_DIR/vault.enc..."
    cp "$PROJECT_DIR/vault.enc" "$RUNTIME_DIR/vault.enc"
fi

echo "=== 2. Creating macOS App Bundle at $APP_DIR ==="
rm -rf "$APP_DIR"
mkdir -p "$MACOS"
mkdir -p "$RESOURCES"

# Copy Icons
if [ -f "$PROJECT_DIR/AppIcon.icns" ]; then
    cp "$PROJECT_DIR/AppIcon.icns" "$RESOURCES/AppIcon.icns"
fi
if [ -f "$PROJECT_DIR/app_icon.png" ]; then
    cp "$PROJECT_DIR/app_icon.png" "$RESOURCES/app_icon.png"
fi

# Compile Native Mach-O arm64 Launcher
echo "Compiling native Mach-O arm64 launcher..."
clang -arch arm64 -O2 "$PROJECT_DIR/launcher.c" -o "$MACOS/PyVault"
chmod +x "$MACOS/PyVault"

# Create Info.plist
cat << 'PLIST' > "$CONTENTS/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>PyVault</string>
    <key>CFBundleExecutable</key>
    <string>PyVault</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.pyvault.desktop</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>PyVault</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
    </array>
    <key>LSRequiresNativeExecution</key>
    <true/>
    <key>NSDesktopFolderUsageDescription</key>
    <string>PyVault requires access to import or export vaults.</string>
    <key>NSDocumentsFolderUsageDescription</key>
    <string>PyVault requires access to import or export vaults.</string>
    <key>NSDownloadsFolderUsageDescription</key>
    <string>PyVault requires access to serve downloaded APKs.</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 PyVault. All rights reserved.</string>
</dict>
</plist>
PLIST

# Create PkgInfo
echo "APPL????" > "$CONTENTS/PkgInfo"

# Code-sign bundle ad-hoc
codesign --force --deep -s - "$APP_DIR" 2>/dev/null || true

echo "=== 3. Installing to /Applications/PyVault.app ==="
rm -rf /Applications/PyVault.app
cp -R "$APP_DIR" /Applications/PyVault.app
codesign --force --deep -s - /Applications/PyVault.app 2>/dev/null || true

echo "=== PyVault.app successfully compiled, signed, and installed ==="
