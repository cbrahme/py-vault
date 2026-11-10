# PyVault Architecture & Technical Specification

> **Design Goal:** A 100% self-built, fully auditable, zero-knowledge password management system across **Mac Laptop** and **Android Phone** with **zero JavaScript**, **zero third-party password managers**, and **zero cloud dependencies**.

---

## 1. System Overview & Philosophy

PyVault is built on the principle of **"Don't trust, verify."**

Commercial password managers rely on proprietary codebases, closed servers, or in-browser JavaScript execution environments that introduce broad attack surfaces. PyVault uses:
1. **Pure Python** on the Mac laptop (CLI and native PyQt6 desktop application packaged as a native macOS `.app` bundle).
2. **Native Kotlin** on the Android phone (Android standard SDK with Titan M2 hardware-backed security and native Android Autofill framework).
3. **Standard NIST Cryptography** (`AES-256-GCM` and `PBKDF2-HMAC-SHA256`) implemented directly in native platform runtimes, ensuring cross-platform binary compatibility.

```
┌──────────────────────────────────────┐                             ┌──────────────────────────────────────┐
│         Mac Laptop (Python)          │                             │        Android Phone (Kotlin)        │
│                                      │    Encrypted "vault.enc"    │                                      │
│  • PyCA `cryptography` library       │ <─────────────────────────> │  • Native `javax.crypto` + Keystore  │
│  • Native Mach-O arm64 launcher      │      (Wi-Fi / Air-gap)      │  • Titan M2 Hardware Biometrics      │
│  • Multi-threaded Sync Server        │                             │  • Native Android AutofillService    │
│  • Timed clipboard auto-clear        │                             │  • Zero-permission ML Kit QR Scanner │
└──────────────────────────────────────┘                             └──────────────────────────────────────┘
```

---

## 2. Cryptographic Specification (Dual-Slot Envelope)

PyVault uses **Envelope Encryption** (`PV02`). The vault payload is encrypted with an internal 256-bit random **Vault Key (VK)**, which is wrapped in two independent access slots:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        "vault.enc" (PV02 JSON Envelope)                │
├────────────────────────────────────────────────────────────────────────┤
│ • slot_pw : VK encrypted with Master Password  (PBKDF2 600,000 rounds) │
│ • slot_rc : VK encrypted with Recovery Key     (PBKDF2 100,000 rounds) │
│ • vault   : Account entries encrypted with VK  (AES-256-GCM)           │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Recovery Key Format
* **Structure:** `RCV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX`
* **Entropy:** 128-bit cryptographically secure random alphanumeric string (32 characters excluding ambiguous characters like 0/O and 1/I).
* **Usage:** If the Master Password is forgotten, entering the Recovery Key decrypts `slot_rc` to recover the Vault Key and immediately prompts the user to set a new Master Password (re-encrypting `slot_pw`).

### 2.2 Key Derivation Function (KDF)
* **Algorithm:** `PBKDF2-HMAC-SHA256`
* **Master Password Iterations:** 600,000 rounds (OWASP 2023+ standard for GPU brute-force resistance)
* **Recovery Key Iterations:** 100,000 rounds
* **Salt Size:** 16 bytes (128 bits)
* **Derived Key Length:** 32 bytes (256 bits)

### 2.3 Authenticated Encryption (AEAD)
* **Algorithm:** `AES-256-GCM` (Galois/Counter Mode)
* **Nonce Size:** 12 bytes (96 bits)
* **Tag Size:** 16 bytes (128 bits)
* **Associated Authenticated Data (AAD):** `b"SLOT_PW"` / `b"SLOT_RC"` (binds slot metadata to ciphertext to prevent cross-slot tampering)

---

## 3. Vault Data Format (Plaintext JSON Payload)

When decrypted in memory, the payload is serialized as UTF-8 encoded JSON:

```json
{
  "version": 1,
  "updated_at": 1730370000,
  "entries": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "title": "GitHub",
      "username": "suyash",
      "password": "CorrectHorseBatteryStaple#99",
      "url": "https://github.com",
      "notes": "Personal dev account",
      "updated_at": 1730370000
    }
  ]
}
```

---

## 4. Android Hardware-Backed Security & Autofill Architecture

### 4.1 Titan M2 Hardware Key Store (`BiometricHelper.kt`)
* Generates an AES-256-GCM key inside the Android Hardware Keystore (`AndroidKeyStore`).
* Requires hardware biometric authentication (`setUserAuthenticationRequired(true)`).
* Encrypts the Vault Key onto disk (`biometric_vault_key.enc`).
* When biometric authentication succeeds, Android Keystore releases the key into memory to unlock the vault without typing the Master Password.
* Invalided automatically if new biometrics are enrolled or if the master recovery key is used.

### 4.2 Android Autofill Framework (`PyVaultAutofillService.kt`)
* **Passive Presentation Policy:** Suggestions are offered exclusively as passive inline keyboard chips (Gboard) or dropdown datasets. No intrusive dialog is displayed on app launch, preventing collision with banking/sensitive apps that launch their own biometric prompt.
* **Option A (Smart Match):** Matches target app package name, web domain, title, or app label against vault entries.
* **Option B (Search Picker Fallback):** Displays a `[ 🔍 Search PyVault ]` chip leading to `AutofillPickerActivity` with real-time fuzzy search.
* **Biometric Gate:** Authentication runs in a translucent activity (`AutofillAuthActivity`), prompting for fingerprint verification before releasing credentials into the calling view.

### 4.3 Google Code Scanner QR Sync
* Uses `com.google.mlkit.vision.codescanner.GmsBarcodeScanning` for zero-permission barcode scanning out-of-process.
* Avoids demanding dangerous `CAMERA` permissions in `AndroidManifest.xml`.
* Auto-populates laptop IP and one-time PIN in the Android sync dialog.

---

## 5. macOS Native Application Architecture

### 5.1 Native Mach-O arm64 Launcher (`launcher.c`)
* Packaged as `/Applications/PyVault.app` with custom high-resolution `AppIcon.icns`.
* Compiled via Apple Clang into a native Mach-O 64-bit arm64 binary, avoiding shell script overhead and preventing LaunchServices from invoking Rosetta (x86_64) emulation.
* Bridges execution to a sandboxed Python runtime in `~/.pyvault/`.

### 5.2 Dynamic Vault Path Resolution
* Both the CLI and native desktop application resolve `vault.enc` seamlessly:
  1. `PYVAULT_PATH` environment variable (if defined)
  2. Local `./vault.enc` (if running in project repository)
  3. User data directory `~/.pyvault/vault.enc`
* Changes made in the GUI, CLI, or via Android phone upload stay 100% in sync across the same underlying encrypted file.

### 5.3 Multi-Threaded Sync Server & Web Installer (`sync_server.py`)
* Built with `ThreadingHTTPServer` to handle concurrent connections and avoid Keep-Alive socket blocking.
* **Web Landing Page & Direct APK Streaming:** Mobile browsers scanning the QR code can download the APK directly from `http://<ip>:8765/apk` with chunked transfer.
* **Live Vault Refresh Hook:** When phone uploads an updated vault, desktop GUI immediately reloads and re-decrypts in RAM without closing or relocking the window.

---

## 6. Project Directory Structure

```
pyvault/
├── ARCHITECTURE.md          # This complete architectural specification
├── README.md                # Quick-start instructions and user guide
├── requirements.txt         # Python dependencies (`cryptography`, `PyQt6`, `qrcode`, `pillow`)
├── venv/                    # Local Python virtual environment
├── AppIcon.icns             # High-resolution macOS app icon bundle
├── app_icon.png             # Application logo
├── build_icon.py            # Automated Pillow + iconutil ICNS generator
├── create_app_bundle.sh     # Native macOS .app compilation and installer script
├── launcher.c               # Native C Mach-O arm64 application launcher
├── cli.py                   # Mac CLI interface (add, get, list, search, sync)
├── gui.py                   # Native PyQt6 desktop GUI (dark mode, live sync)
├── sync_server.py           # Multi-threaded Wi-Fi sync server & APK installer
├── tests/
│   ├── test_crypto.py       # AES-256-GCM + PBKDF2 integrity and bit-flip tests
│   └── test_vault.py        # Vault lifecycle and envelope serialization tests
└── android/                 # Native Android Kotlin Project
    ├── app/
    │   ├── build.gradle.kts
    │   └── src/main/
    │       ├── AndroidManifest.xml
    │       ├── java/com/pyvault/
    │       │   ├── AutofillAuthActivity.kt   # Biometric verification for autofill
    │       │   ├── AutofillPickerActivity.kt # Searchable account picker for autofill
    │       │   ├── AutofillUtils.kt          # Domain parsing and autofill helpers
    │       │   ├── BiometricHelper.kt        # Titan M2 hardware keystore integration
    │       │   ├── Crypto.kt                 # Native javax.crypto mirror of crypto.py
    │       │   ├── MainActivity.kt           # Vault UI, search, QR scanner, sync
    │       │   ├── PyVaultAutofillService.kt # Android AutofillService provider
    │       │   ├── SyncClient.kt             # Wi-Fi sync client (upload & download)
    │       │   └── VaultModels.kt            # Kotlin data models matching JSON schema
    │       └── res/
    │           ├── layout/                   # Activity and dialog layouts
    │           ├── values/                   # Colors, dark themes, translucent styles
    │           └── xml/autofill_service.xml  # Autofill provider manifest metadata
    ├── build.gradle.kts
    └── settings.gradle.kts
```

---

## 7. Security & Threat Model

1. **Zero JavaScript:** Eliminates DOM injection, malicious extension scraping, and prototype pollution attacks.
2. **Zero Third-Party Cloud:** Vault data never leaves the local network unless explicitly transferred.
3. **Hardware-Backed Biometrics:** Fingerprint unlocking is cryptographically bound to the device's secure enclave / Titan M2 chip; extracting the database cannot yield passwords without device authentication.
4. **Passive Autofill Isolation:** PyVault never injects unauthorized overlays or prompts into third-party apps, preventing timing attacks and collision with banking biometric checks.
5. **Memory Hygiene:**
   * Python clears variables and overwrites sensitive bytearrays.
   * Android uses `CharArray` for passwords and wipes them after key derivation.
6. **Clipboard Hygiene:** Both Mac (`pbcopy`) and Android (`ClipboardManager.clearPrimaryClip()` with `EXTRA_IS_SENSITIVE = true`) purge copied passwords within 20 seconds.
