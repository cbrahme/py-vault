# PyVault 🔐

> A 100% self-built, fully auditable, zero-knowledge password management system across **Mac Laptop** and **Android Phone** with **zero JavaScript**, **zero third-party password managers**, and **zero cloud dependencies**.

---

## Features

- **True Zero-Knowledge Security:** All data is encrypted with **AES-256-GCM** using keys derived via **PBKDF2-HMAC-SHA256 (600,000 rounds)**.
- **Titan M2 Hardware Biometrics:** Hardware-backed fingerprint unlock on Android (`AndroidKeyStore`) with 1-tap unlock from the lock screen.
- **Android Autofill Framework (`AutofillService`):** Autofill credentials directly inside any Android app or browser with fingerprint authentication.
  - **Option A (Smart Match):** Automatically matches app package names, titles, or web domains.
  - **Option B (Search Picker):** `[ 🔍 Search PyVault ]` chip with instant fuzzy search across all vault accounts.
  - **Passive Non-Intrusive Design:** Uses native keyboard chips (Gboard) and dropdown datasets—never displays disruptive popups on app launch, preventing collision with banking app biometrics.
- **Native macOS Application (`PyVault.app`):** Double-clickable native macOS app installed in `/Applications/PyVault.app` with a custom high-resolution icon (`AppIcon.icns`) and native Mach-O ARM64 launcher.
- **Zero-Permission QR Code Sync:** Scan your laptop's QR code using the Google Code Scanner API without granting dangerous camera permissions.
- **Multi-Threaded Sync Server & Web APK Installer:** Built-in multi-threaded server serves both the APK installer to mobile browsers and real-time live sync to the PyVault app.
- **Live Desktop Reload:** When your phone uploads an updated vault, your desktop GUI refreshes in real-time without locking or reopening the window.
- **Clipboard Hygiene:** Automatic 20-second clipboard wipe with `EXTRA_IS_SENSITIVE = true` to mask password previews in clipboard history.
- **Dual-Slot Recovery System:** 128-bit Emergency Recovery Key (`RCV-XXXX-...`) allows resetting forgotten master passwords while preserving all entries.

---

## Project Structure

```
pyvault/
├── ARCHITECTURE.md          # Complete technical and cryptographic specification
├── README.md                # Quick-start user guide
├── requirements.txt         # Python dependencies (`cryptography`, `PyQt6`, `qrcode`, `pillow`)
├── AppIcon.icns             # High-resolution macOS application icon
├── launcher.c               # Native C Mach-O arm64 application launcher
├── create_app_bundle.sh     # macOS .app compilation and installer script
├── cli.py                   # Mac CLI interface
├── gui.py                   # Mac Desktop GUI (native dark theme, live sync)
├── sync_server.py           # Multi-threaded Wi-Fi sync server & APK installer
├── tests/                   # Automated unit test suite
│   ├── test_crypto.py
│   └── test_vault.py
└── android/                 # Native Android Kotlin project
    └── app/src/main/
        ├── AndroidManifest.xml
        ├── java/com/pyvault/
        │   ├── AutofillAuthActivity.kt   # Biometric verification for autofill
        │   ├── AutofillPickerActivity.kt # Searchable account picker for autofill
        │   ├── BiometricHelper.kt        # Titan M2 hardware keystore integration
        │   ├── Crypto.kt                 # Native javax.crypto mirror of crypto.py
        │   ├── MainActivity.kt           # Android UI, search, QR scanner, sync
        │   ├── PyVaultAutofillService.kt # Android AutofillService provider
        │   ├── SyncClient.kt             # Wi-Fi sync client (upload & download)
        │   └── VaultModels.kt            # JSON data models
        └── res/                          # Dark mode layouts & autofill XML config
```

---

## 1. Quick Start: Mac Laptop

### Option A: Launch the Native macOS Application
PyVault is installed directly into `/Applications/PyVault.app`:
* Open **Spotlight** (`Cmd + Space`), type **PyVault**, and press **Enter**.
* Or double-click **PyVault** in your `/Applications` folder or Dock.

To rebuild or reinstall the application bundle from source at any time:
```bash
./create_app_bundle.sh
```

### Option B: Use the Command Line (CLI)
```bash
source venv/bin/activate

# 1. Initialize a new vault
python cli.py init

# 2. Add an account (generates a secure password or prompts for one)
python cli.py add github

# 3. Retrieve account (copies password to Mac clipboard for 20s)
python cli.py get github

# 4. Search accounts
python cli.py search git

# 5. List all accounts
python cli.py list

# 6. Generate a standalone random password
python cli.py generate -l 24
```

---

## 2. Syncing Between Laptop & Android Phone

PyVault syncs directly over your home Wi-Fi—no cloud company ever sees your vault.

1. **On your Laptop:**
   Click **Sync** in the Desktop GUI (or run `python cli.py sync`).
   A side-by-side card displays the universal QR code, laptop IP, and an ephemeral 6-digit PIN:
   ```
   ============================================================
              PyVault Local Wi-Fi Sync Server            
   ============================================================
     Laptop IP Address : 192.168.1.15
     Port              : 8765
     One-Time Sync PIN : 482910
   ============================================================
   ```

2. **On your Android Phone:**
   * **To Install the APK:** Scan the QR code using your phone's camera (or open `http://<laptop-ip>:8765` in Chrome/Edge). Tap **Download Android APK** and install.
   * **To Sync Passwords:** Open the PyVault app, tap **Sync**, and tap **📷 Scan QR Code on Laptop**. It automatically reads the host and PIN, then tap **Download from Laptop** (or **Upload to Laptop**).

---

## 3. Setting Up Android Autofill in Other Apps

Once PyVault is installed on your Android phone, enable it to autofill credentials in any app or web browser:

1. Open your phone's **Settings**.
2. Search for **Autofill** (or go to **Passwords, accounts & autofill** > **Autofill service**).
3. Select **PyVault** and confirm.
4. When logging into any app (e.g. Netflix, Amazon, Spotify):
   - Tap the username or password box.
   - Tap the **`PyVault`** chip on your keyboard (Gboard) or dropdown.
   - Touch your **fingerprint** to verify. PyVault will instantly populate your credentials!

---

## 4. Building the Android App from Source

The Android app is located in `android/`. You can build the installable `.apk` either via Android Studio or using Gradle:

### Option A: Command Line Build
```bash
cd android
./gradlew assembleDebug
```
The output `.apk` is generated at `android/app/build/outputs/apk/debug/app-debug.apk`.

### Option B: Using Android Studio
1. Open **Android Studio**.
2. Select **Open** and choose the `pyvault/android` directory.
3. Click **Build > Build Bundle(s) / APK(s) > Build APK(s)**.

---

## 5. Running Automated Tests

PyVault includes a comprehensive test suite covering AES-256-GCM integrity, PBKDF2 key derivation, bit-flip tampering prevention, and envelope serialization:

```bash
./venv/bin/python -m unittest discover -s tests
```
