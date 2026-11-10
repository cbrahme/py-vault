#!/usr/bin/env python3
"""
PyVault Desktop GUI (PyQt6)
Modern, Apple-style macOS native interface for PyVault.
With dynamic Light and Dark mode theme toggling and persistent preference.
"""

import os
import sys
import io
import json
import threading
from typing import Optional

try:
    import qrcode
except ImportError:
    qrcode = None

from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPixmap, QImage, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QFrame
)

from core.models import Vault, VaultEntry, generate_password, copy_to_clipboard_timed
import sync_server

def get_vault_path() -> str:
    if os.environ.get("PYVAULT_PATH"):
        return os.environ["PYVAULT_PATH"]
    home_vault = os.path.expanduser("~/.pyvault/vault.enc")
    if os.path.exists(home_vault):
        return home_vault
    if os.path.exists("vault.enc"):
        return os.path.abspath("vault.enc")
    return home_vault

def get_prefs_path() -> str:
    if os.path.exists("preferences.json"):
        return os.path.abspath("preferences.json")
    return os.path.expanduser("~/.pyvault/preferences.json")

DEFAULT_VAULT_PATH = get_vault_path()
PREFS_FILE = get_prefs_path()


def make_qr_pixmap(data: str, size: int = 150) -> Optional[QPixmap]:
    if not qrcode:
        return None
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        qimg = QImage.fromData(buffer.getvalue())
        return QPixmap.fromImage(qimg).scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    except Exception:
        return None


# --- THEME DEFINITIONS ---

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1C1C1E;
}
QWidget {
    font-family: .AppleSystemUIFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #FFFFFF;
}
QLabel {
    color: #FFFFFF;
}

/* Specific Panel IDs to avoid cascade bugs */
QWidget#LeftPanel {
    background-color: #161618;
}
QWidget#RightPanel {
    background-color: #1C1C1E;
}
QFrame#Divider {
    background-color: #2D2D32;
    border: none;
}

QLineEdit {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    border-radius: 8px;
    padding: 10px 14px;
    color: #FFFFFF;
    font-size: 13px;
    selection-background-color: #0A84FF;
}
QLineEdit:focus {
    border: 1.5px solid #0A84FF;
    background-color: #2C2C2E;
}
QLineEdit::placeholder {
    color: #8E8E93;
}

QPushButton {
    background-color: #0A84FF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #0071E3;
}
QPushButton:pressed {
    background-color: #005BB5;
}

QPushButton#PrimaryBtn {
    background-color: #0A84FF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover {
    background-color: #0071E3;
}

QPushButton#SecondaryBtn {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    color: #FFFFFF;
    font-weight: 500;
    padding: 5px 10px;
}
QPushButton#SecondaryBtn:hover {
    background-color: #3A3A3C;
}
QPushButton#SecondaryBtn:pressed {
    background-color: #48484A;
}

QPushButton#ThemeIconBtn {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    border-radius: 16px;
    font-size: 14px;
    padding: 4px;
}
QPushButton#ThemeIconBtn:hover {
    background-color: #3A3A3C;
}

QPushButton#DangerBtn {
    background-color: rgba(255, 69, 58, 0.15);
    border: 1px solid rgba(255, 69, 58, 0.3);
    color: #FF453A;
    font-weight: 500;
}
QPushButton#DangerBtn:hover {
    background-color: rgba(255, 69, 58, 0.25);
}

QPushButton#LinkBtn {
    background: transparent;
    color: #2997FF;
    border: none;
    font-size: 13px;
    font-weight: normal;
    padding: 4px;
}
QPushButton#LinkBtn:hover {
    color: #70B4FF;
}

QListWidget {
    background-color: #161618;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget::item {
    border-radius: 8px;
    margin-bottom: 4px;
    border: none;
}
QListWidget::item:selected {
    background-color: #0A84FF;
}
QListWidget::item:hover:!selected {
    background-color: #2C2C2E;
}

QFrame#Card {
    background-color: #242426;
    border: 1px solid #323236;
    border-radius: 10px;
}
QFrame#HeroCard {
    background-color: #242426;
    border: 1px solid #323236;
    border-radius: 16px;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #F2F2F7;
}
QWidget {
    font-family: .AppleSystemUIFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #000000;
}
QLabel {
    color: #000000;
}

/* Specific Panel IDs to avoid cascade bugs */
QWidget#LeftPanel {
    background-color: #E5E5EA;
}
QWidget#RightPanel {
    background-color: #F2F2F7;
}
QFrame#Divider {
    background-color: #D1D1D6;
    border: none;
}

QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 8px;
    padding: 10px 14px;
    color: #000000;
    font-size: 13px;
    selection-background-color: #007AFF;
}
QLineEdit:focus {
    border: 1.5px solid #007AFF;
    background-color: #FFFFFF;
}
QLineEdit::placeholder {
    color: #8E8E93;
}

QPushButton {
    background-color: #007AFF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #0062CC;
}
QPushButton:pressed {
    background-color: #004FB0;
}

QPushButton#PrimaryBtn {
    background-color: #007AFF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover {
    background-color: #0062CC;
}

QPushButton#SecondaryBtn {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    color: #000000;
    font-weight: 500;
    padding: 5px 10px;
}
QPushButton#SecondaryBtn:hover {
    background-color: #E5E5EA;
}
QPushButton#SecondaryBtn:pressed {
    background-color: #D1D1D6;
}

QPushButton#ThemeIconBtn {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 16px;
    font-size: 14px;
    padding: 4px;
}
QPushButton#ThemeIconBtn:hover {
    background-color: #E5E5EA;
}

QPushButton#DangerBtn {
    background-color: rgba(255, 59, 48, 0.1);
    border: 1px solid rgba(255, 59, 48, 0.25);
    color: #FF3B30;
    font-weight: 500;
}
QPushButton#DangerBtn:hover {
    background-color: rgba(255, 59, 48, 0.2);
}

QPushButton#LinkBtn {
    background: transparent;
    color: #007AFF;
    border: none;
    font-size: 13px;
    font-weight: normal;
    padding: 4px;
}
QPushButton#LinkBtn:hover {
    color: #0051A8;
}

QListWidget {
    background-color: #E5E5EA;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget::item {
    border-radius: 8px;
    margin-bottom: 4px;
    border: none;
}
QListWidget::item:selected {
    background-color: #007AFF;
}
QListWidget::item:hover:!selected {
    background-color: #D1D1D6;
}

QFrame#Card {
    background-color: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 10px;
}
QFrame#HeroCard {
    background-color: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 16px;
}
"""


class ThemeManager:
    current_theme: str = "dark"

    @classmethod
    def load(cls):
        if os.path.exists(PREFS_FILE):
            try:
                with open(PREFS_FILE, "r") as f:
                    data = json.load(f)
                    cls.current_theme = data.get("theme", "dark")
            except Exception:
                cls.current_theme = "dark"

    @classmethod
    def save(cls):
        try:
            with open(PREFS_FILE, "w") as f:
                json.dump({"theme": cls.current_theme}, f)
        except Exception:
            pass

    @classmethod
    def toggle(cls) -> str:
        cls.current_theme = "light" if cls.current_theme == "dark" else "dark"
        cls.save()
        return cls.current_theme

    @classmethod
    def get_stylesheet(cls) -> str:
        return DARK_STYLESHEET if cls.current_theme == "dark" else LIGHT_STYLESHEET

    @classmethod
    def is_dark(cls) -> bool:
        return cls.current_theme == "dark"


AVATAR_GRADIENTS = [
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0A84FF, stop:1 #005BB5)"),
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #30D158, stop:1 #248A3D)"),
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF9F0A, stop:1 #C97200)"),
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #BF5AF2, stop:1 #893CB8)"),
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #64D2FF, stop:1 #0082BD)"),
    ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF375F, stop:1 #B81438)"),
]


def get_avatar_gradient(title: str) -> str:
    h = sum(ord(c) for c in title) % len(AVATAR_GRADIENTS)
    return AVATAR_GRADIENTS[h]


class AccountListItemWidget(QWidget):
    def __init__(self, entry: VaultEntry, is_selected: bool = False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        initial = (entry.title[0:2].upper() if len(entry.title) >= 2 else entry.title.upper()) or "🔑"
        avatar = QLabel(initial)
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gradient = get_avatar_gradient(entry.title)
        avatar.setStyleSheet(f"""
            background: {gradient};
            color: #FFFFFF;
            font-weight: bold;
            font-size: 13px;
            border-radius: 8px;
        """)
        layout.addWidget(avatar)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        vbox.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel(entry.title)
        vbox.addWidget(self.lbl_title)

        user_text = entry.username if entry.username else (entry.url if entry.url else "No username")
        self.lbl_user = QLabel(user_text)
        vbox.addWidget(self.lbl_user)

        layout.addLayout(vbox)
        layout.addStretch()

        self.update_selected_state(is_selected)

    def update_selected_state(self, selected: bool):
        is_dark = ThemeManager.is_dark()
        if selected:
            self.lbl_title.setStyleSheet("font-weight: 600; font-size: 13.5px; color: #FFFFFF;")
            self.lbl_user.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.85);")
        else:
            title_color = "#FFFFFF" if is_dark else "#000000"
            sub_color = "#8E8E93" if is_dark else "#6C6C70"
            self.lbl_title.setStyleSheet(f"font-weight: 600; font-size: 13.5px; color: {title_color};")
            self.lbl_user.setStyleSheet(f"font-size: 12px; color: {sub_color};")


class RecoveryKeyDisplayDialog(QDialog):
    def __init__(self, recovery_key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Emergency Recovery Key")
        self.setFixedSize(520, 440)
        self.setStyleSheet(ThemeManager.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(18)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        icon = QLabel("⚠️")
        icon.setFont(QFont(".AppleSystemUIFont", 24))
        title = QLabel("Save Your Recovery Key")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        top_row.addWidget(icon)
        top_row.addWidget(title)
        top_row.addStretch()
        layout.addLayout(top_row)

        desc = QLabel(
            "If you ever forget your Master Password, this Emergency Key is the "
            "ONLY way to restore access to your passwords.\n\n"
            "Store it in a safe place (like a password safe or printed copy)."
        )
        desc.setStyleSheet("color: #8E8E93; font-size: 13px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("Card")
        k_layout = QVBoxLayout(card)
        k_layout.setContentsMargins(18, 16, 18, 16)

        lbl_key = QLabel(recovery_key)
        lbl_key.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        lbl_key.setStyleSheet("color: #30D158;" if ThemeManager.is_dark() else "color: #248A3D;")
        lbl_key.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_key.setWordWrap(True)
        k_layout.addWidget(lbl_key)
        layout.addWidget(card)

        btn_copy = QPushButton("Copy Recovery Key")
        btn_copy.setObjectName("SecondaryBtn")
        btn_copy.setFixedHeight(40)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)

        def on_copy():
            copy_to_clipboard_timed(recovery_key, 60)
            btn_copy.setText("✓ Copied to Clipboard! (60s)")
            btn_copy.setStyleSheet("color: #30D158; font-weight: 600;")

        btn_copy.clicked.connect(on_copy)
        layout.addWidget(btn_copy)

        layout.addStretch()

        btn_done = QPushButton("I Have Saved My Recovery Key")
        btn_done.setObjectName("PrimaryBtn")
        btn_done.setFixedHeight(44)
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.clicked.connect(self.accept)
        layout.addWidget(btn_done)


class RecoverVaultDialog(QDialog):
    def __init__(self, vault: Vault, parent=None):
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Recover Vault")
        self.setFixedSize(500, 480)
        self.setStyleSheet(ThemeManager.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(16)

        title = QLabel("Recover with Emergency Key")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Enter your 32-character Emergency Recovery Key to restore your vault and set a new password:")
        desc.setStyleSheet("color: #8E8E93; font-size: 13px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("RCV-XXXX-XXXX-XXXX-XXXX...")
        self.txt_key.setFixedHeight(42)
        layout.addWidget(self.txt_key)

        layout.addSpacing(6)
        lbl_new_pw = QLabel("CREATE NEW MASTER PASSWORD")
        lbl_new_pw.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_new_pw)

        self.txt_new_pw = QLineEdit()
        self.txt_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_new_pw.setPlaceholderText("New Master Password")
        self.txt_new_pw.setFixedHeight(42)
        layout.addWidget(self.txt_new_pw)

        self.txt_confirm_pw = QLineEdit()
        self.txt_confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_confirm_pw.setPlaceholderText("Confirm New Master Password")
        self.txt_confirm_pw.setFixedHeight(42)
        layout.addWidget(self.txt_confirm_pw)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("SecondaryBtn")
        btn_cancel.setFixedHeight(44)
        btn_cancel.clicked.connect(self.reject)

        btn_recover = QPushButton("Reset Password & Unlock")
        btn_recover.setObjectName("PrimaryBtn")
        btn_recover.setFixedHeight(44)
        btn_recover.clicked.connect(self.on_recover)

        btn_row.addWidget(btn_cancel, stretch=1)
        btn_row.addWidget(btn_recover, stretch=2)
        layout.addLayout(btn_row)

    def on_recover(self):
        rec_key = self.txt_key.text().strip()
        new_pw = self.txt_new_pw.text()
        confirm_pw = self.txt_confirm_pw.text()

        if not rec_key:
            QMessageBox.warning(self, "Error", "Please enter your Recovery Key.")
            return
        if not new_pw:
            QMessageBox.warning(self, "Error", "New Master Password cannot be empty.")
            return
        if new_pw != confirm_pw:
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            return

        try:
            self.vault.recover(rec_key)
            self.vault.reset_master_password(new_pw)
            QMessageBox.information(self, "Success", "Vault recovered! Your new Master Password is now active.")
            self.accept()
        except ValueError as e:
            QMessageBox.critical(self, "Recovery Failed", str(e))


class AddEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Item")
        self.setFixedSize(500, 560)
        self.setStyleSheet(ThemeManager.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_lbl = QLabel("Add New Account")
        title_lbl.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        subtitle_lbl = QLabel("Store credentials securely inside your encrypted vault.")
        subtitle_lbl.setStyleSheet("color: #8E8E93; font-size: 13px;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        layout.addLayout(title_box)

        f1 = QVBoxLayout()
        f1.setSpacing(6)
        lbl1 = QLabel("ACCOUNT NAME")
        lbl1.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. GitHub, Amazon, Google")
        self.txt_title.setFixedHeight(42)
        f1.addWidget(lbl1)
        f1.addWidget(self.txt_title)
        layout.addLayout(f1)

        f2 = QVBoxLayout()
        f2.setSpacing(6)
        lbl2 = QLabel("USERNAME / EMAIL")
        lbl2.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("user@example.com")
        self.txt_user.setFixedHeight(42)
        f2.addWidget(lbl2)
        f2.addWidget(self.txt_user)
        layout.addLayout(f2)

        f3 = QVBoxLayout()
        f3.setSpacing(6)
        lbl3 = QLabel("PASSWORD")
        lbl3.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")

        pass_row = QHBoxLayout()
        pass_row.setSpacing(8)
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText("Enter or generate password")
        self.txt_pass.setFixedHeight(42)

        btn_gen = QPushButton("⚡ Generate")
        btn_gen.setObjectName("SecondaryBtn")
        btn_gen.setFixedHeight(42)
        btn_gen.setFixedWidth(115)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.clicked.connect(self.on_generate)

        pass_row.addWidget(self.txt_pass, stretch=1)
        pass_row.addWidget(btn_gen)
        f3.addWidget(lbl3)
        f3.addLayout(pass_row)
        layout.addLayout(f3)

        f4 = QVBoxLayout()
        f4.setSpacing(6)
        lbl4 = QLabel("WEBSITE URL (OPTIONAL)")
        lbl4.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://github.com")
        self.txt_url.setFixedHeight(42)
        f4.addWidget(lbl4)
        f4.addWidget(self.txt_url)
        layout.addLayout(f4)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("SecondaryBtn")
        btn_cancel.setFixedHeight(44)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Account")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setFixedHeight(44)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel, stretch=1)
        btn_row.addWidget(btn_save, stretch=2)
        layout.addLayout(btn_row)

    def on_generate(self):
        pw = generate_password(20)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Normal)
        self.txt_pass.setText(pw)

    def get_data(self):
        return {
            "title": self.txt_title.text().strip(),
            "username": self.txt_user.text().strip(),
            "password": self.txt_pass.text(),
            "url": self.txt_url.text().strip(),
        }


class SyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wi-Fi Sync & Android Installer")
        self.setFixedSize(580, 420)
        self.setStyleSheet(ThemeManager.get_stylesheet())

        ip = sync_server.get_local_ip()
        pin = f"{sync_server.secrets.randbelow(900000) + 100000}"
        install_url = f"http://{ip}:{sync_server.PORT}/?pin={pin}"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Sync with Android Phone")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Scan the QR code to install PyVault on your phone, or enter the credentials below to sync passwords:")
        desc.setStyleSheet("color: #8E8E93; font-size: 13px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Content Row (QR Code on Left, Credentials on Right)
        row = QHBoxLayout()
        row.setSpacing(16)

        # Left: QR Box
        qr_pixmap = make_qr_pixmap(install_url, size=150)
        qr_card = QFrame()
        qr_card.setObjectName("Card")
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(14, 14, 14, 14)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if qr_pixmap:
            lbl_qr = QLabel()
            lbl_qr.setPixmap(qr_pixmap)
            lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_qr.setStyleSheet("background: white; border-radius: 8px; padding: 4px;")
            qr_layout.addWidget(lbl_qr)

        lbl_qr_sub = QLabel("Scan with Camera<br>to Install APK")
        lbl_qr_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_qr_sub.setStyleSheet("color: #8E8E93; font-size: 11px; margin-top: 6px;")
        qr_layout.addWidget(lbl_qr_sub)
        row.addWidget(qr_card)

        # Right: Credentials Card
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)

        lbl_sync_title = QLabel("WI-FI SYNC SERVER:")
        lbl_sync_title.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        card_layout.addWidget(lbl_sync_title)

        lbl_host = QLabel(f"Host:  <b>{ip}:{sync_server.PORT}</b>")
        lbl_host.setTextFormat(Qt.TextFormat.RichText)
        lbl_host.setFont(QFont(".AppleSystemUIFont", 14))
        card_layout.addWidget(lbl_host)

        pin_color = "#30D158" if ThemeManager.is_dark() else "#248A3D"
        lbl_pin = QLabel(f"PIN :  <span style='color: {pin_color}; font-weight: bold;'>{pin}</span>")
        lbl_pin.setTextFormat(Qt.TextFormat.RichText)
        lbl_pin.setFont(QFont(".AppleSystemUIFont", 18))
        card_layout.addWidget(lbl_pin)

        lbl_install = QLabel(f"Direct link: <a href='{install_url}' style='color: #0A84FF;'>{install_url}</a>")
        lbl_install.setOpenExternalLinks(True)
        lbl_install.setStyleSheet("font-size: 11px; margin-top: 4px;")
        card_layout.addWidget(lbl_install)

        card_layout.addStretch()
        row.addWidget(card, 1)
        layout.addLayout(row)

        def on_uploaded():
            if parent and hasattr(parent, "reload_vault_signal"):
                parent.reload_vault_signal.emit()

        sync_server.SyncHandler.on_vault_uploaded = on_uploaded

        self.server_holder = []
        self.sync_thread = threading.Thread(
            target=sync_server.run_sync_server,
            kwargs={"vault_path": DEFAULT_VAULT_PATH, "pin": pin, "server_holder": self.server_holder},
            daemon=True
        )
        self.sync_thread.start()

        layout.addStretch()
        btn_close = QPushButton("Done / Close Sync")
        btn_close.setObjectName("SecondaryBtn")
        btn_close.setFixedHeight(42)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def done(self, r):
        server = self.server_holder[0] if self.server_holder else None
        if server:
            def _stop():
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass
            threading.Thread(target=_stop, daemon=True).start()
        sync_server.SyncHandler.on_vault_uploaded = None
        super().done(r)


class PyVaultWindow(QMainWindow):
    reload_vault_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyVault")
        self.resize(880, 580)
        self.setMinimumSize(750, 480)

        ThemeManager.load()
        self.setStyleSheet(ThemeManager.get_stylesheet())

        self.vault: Optional[Vault] = None
        self.vault_key: Optional[bytes] = None
        self.envelope: Optional[dict] = None
        self.filtered_entries = []

        self.reload_vault_signal.connect(self.reload_active_vault)
        self.show_unlock_screen()

    def reload_active_vault(self):
        if not self.vault or not self.vault.vault_key:
            return

        try:
            self.vault.reload_from_disk()
            self.filter_entries()
            self.statusBar().showMessage("Vault updated via phone sync!", 4000)
            print("[+] Live refreshed desktop vault from phone upload!")
        except Exception as e:
            print("[!] Auto-reload error:", e)

    def toggle_theme(self):
        ThemeManager.toggle()
        # Set top-level stylesheet without cascading background-color onto children
        self.setStyleSheet(ThemeManager.get_stylesheet())

        # Update theme toggle button text/icon
        if hasattr(self, "btn_theme") and self.btn_theme:
            self.btn_theme.setText("☀️" if ThemeManager.is_dark() else "🌙")
            self.btn_theme.setToolTip("Switch to Light Mode" if ThemeManager.is_dark() else "Switch to Dark Mode")

        # Refresh list items to update text colors
        if hasattr(self, "list_widget") and self.list_widget:
            selected_row = self.list_widget.currentRow()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                widget = self.list_widget.itemWidget(item)
                if isinstance(widget, AccountListItemWidget):
                    widget.update_selected_state(i == selected_row)

    # --- SCREEN 1: APPLE HERO UNLOCK SCREEN ---
    def show_unlock_screen(self):
        self.vault = None

        central = QWidget()
        self.setCentralWidget(central)

        vbox = QVBoxLayout(central)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("HeroCard")
        card.setFixedWidth(400)
        box = QVBoxLayout(card)
        box.setContentsMargins(36, 40, 36, 36)
        box.setSpacing(16)

        # Top row inside hero card with Lock Badge and subtle Theme Icon Button on the right
        card_top = QHBoxLayout()
        card_top.addStretch()

        badge = QLabel("🔐")
        badge.setFixedSize(60, 60)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0A84FF, stop:1 #005BB5);
            font-size: 26px;
            border-radius: 16px;
        """)
        card_top.addWidget(badge)
        card_top.addStretch()

        box.addLayout(card_top)

        logo = QLabel("PyVault")
        logo.setFont(QFont(".AppleSystemUIFont", 24, QFont.Weight.Bold))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(logo)

        vault_file = Vault(DEFAULT_VAULT_PATH)
        is_new = not vault_file.exists
        subtitle_text = "Create your Master Password to get started." if is_new else "Enter your Master Password to unlock."

        sub = QLabel(subtitle_text)
        sub.setFont(QFont(".AppleSystemUIFont", 13))
        sub.setStyleSheet("color: #8E8E93;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        box.addWidget(sub)

        box.addSpacing(6)

        self.txt_unlock_pw = QLineEdit()
        self.txt_unlock_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_unlock_pw.setPlaceholderText("Master Password")
        self.txt_unlock_pw.setFixedHeight(44)
        self.txt_unlock_pw.returnPressed.connect(lambda: self.on_unlock_clicked(is_new))
        box.addWidget(self.txt_unlock_pw)

        btn_action = QPushButton("Initialize Vault" if is_new else "Unlock")
        btn_action.setObjectName("PrimaryBtn")
        btn_action.setFixedHeight(44)
        btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_action.clicked.connect(lambda: self.on_unlock_clicked(is_new))
        box.addWidget(btn_action)

        if not is_new:
            btn_forgot = QPushButton("Forgot Master Password? Use Recovery Key")
            btn_forgot.setObjectName("LinkBtn")
            btn_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_forgot.clicked.connect(self.on_forgot_password)
            box.addWidget(btn_forgot, alignment=Qt.AlignmentFlag.AlignCenter)

        # Subtle theme switcher at bottom of unlock card
        theme_btn_box = QHBoxLayout()
        theme_btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_unlock_theme = QPushButton("☀️ Light Mode" if ThemeManager.is_dark() else "🌙 Dark Mode")
        btn_unlock_theme.setObjectName("LinkBtn")
        btn_unlock_theme.clicked.connect(lambda: [self.toggle_theme(), btn_unlock_theme.setText("☀️ Light Mode" if ThemeManager.is_dark() else "🌙 Dark Mode")])
        theme_btn_box.addWidget(btn_unlock_theme)
        box.addLayout(theme_btn_box)

        vbox.addWidget(card)
        self.txt_unlock_pw.setFocus()

    def on_unlock_clicked(self, is_new: bool):
        pw = self.txt_unlock_pw.text()
        if not pw:
            QMessageBox.warning(self, "Error", "Master password cannot be empty.")
            return

        self.vault = Vault(DEFAULT_VAULT_PATH)
        if is_new:
            recovery_key = self.vault.initialize(pw)
            dlg = RecoveryKeyDisplayDialog(recovery_key, self)
            dlg.exec()
            self.show_dashboard_screen()
        else:
            try:
                self.vault.unlock(pw)
                self.show_dashboard_screen()
            except ValueError as e:
                QMessageBox.critical(self, "Access Denied", str(e))

    def on_forgot_password(self):
        vault_file = Vault(DEFAULT_VAULT_PATH)
        dlg = RecoverVaultDialog(vault_file, self)
        if dlg.exec():
            self.vault = vault_file
            self.show_dashboard_screen()

    # --- SCREEN 2: MACOS SPLIT VIEW DASHBOARD ---
    def show_dashboard_screen(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # LEFT SIDEBAR
        self.left_panel = QWidget()
        self.left_panel.setObjectName("LeftPanel")
        self.left_panel.setFixedWidth(300)
        left_box = QVBoxLayout(self.left_panel)
        left_box.setContentsMargins(16, 20, 16, 16)
        left_box.setSpacing(12)

        # Header with item count & Theme Toggle Button on Top Right of Sidebar!
        header_row = QHBoxLayout()
        header_title = QLabel("All Items")
        header_title.setFont(QFont(".AppleSystemUIFont", 18, QFont.Weight.Bold))
        header_row.addWidget(header_title)

        self.lbl_count = QLabel("0")
        self.lbl_count.setStyleSheet("""
            background-color: rgba(142, 142, 147, 0.2);
            color: #8E8E93;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 10px;
        """)
        header_row.addWidget(self.lbl_count)
        header_row.addStretch()

        # Modern macOS Circle Theme Toggle Icon Button in Sidebar Header!
        self.btn_theme = QPushButton("☀️" if ThemeManager.is_dark() else "🌙")
        self.btn_theme.setObjectName("ThemeIconBtn")
        self.btn_theme.setFixedSize(32, 32)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setToolTip("Switch to Light Mode" if ThemeManager.is_dark() else "Switch to Dark Mode")
        self.btn_theme.clicked.connect(self.toggle_theme)
        header_row.addWidget(self.btn_theme)

        left_box.addLayout(header_row)

        # Search Bar
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍  Search accounts...")
        self.txt_search.setFixedHeight(38)
        self.txt_search.textChanged.connect(self.filter_entries)
        left_box.addWidget(self.txt_search)

        # Accounts List with two-line items
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_entry_selected)
        left_box.addWidget(self.list_widget)

        # Bottom Actions: "+ New Item" Primary Button + "Sync" and "Lock"
        btn_add = QPushButton("+ New Item")
        btn_add.setObjectName("PrimaryBtn")
        btn_add.setFixedHeight(38)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.on_add_account)
        left_box.addWidget(btn_add)

        bot_row = QHBoxLayout()
        bot_row.setSpacing(8)

        btn_sync = QPushButton("Sync 🔄")
        btn_sync.setObjectName("SecondaryBtn")
        btn_sync.setFixedHeight(34)
        btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sync.clicked.connect(self.on_sync_dialog)
        bot_row.addWidget(btn_sync)

        btn_lock = QPushButton("Lock 🔒")
        btn_lock.setObjectName("SecondaryBtn")
        btn_lock.setFixedHeight(34)
        btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_lock.clicked.connect(self.show_unlock_screen)
        bot_row.addWidget(btn_lock)

        left_box.addLayout(bot_row)
        main_layout.addWidget(self.left_panel)

        # Vertical Divider Line
        self.divider = QFrame()
        self.divider.setObjectName("Divider")
        self.divider.setFrameShape(QFrame.Shape.VLine)
        self.divider.setFrameShadow(QFrame.Shadow.Plain)
        self.divider.setFixedWidth(1)
        main_layout.addWidget(self.divider)

        # RIGHT DETAIL PANEL
        self.right_panel = QWidget()
        self.right_panel.setObjectName("RightPanel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(36, 32, 36, 32)
        self.right_layout.setSpacing(20)
        main_layout.addWidget(self.right_panel, stretch=1)

        self.filter_entries()
        self.show_empty_detail()

    def filter_entries(self):
        query = self.txt_search.text().strip().lower()
        self.list_widget.clear()
        self.filtered_entries = []

        if not self.vault:
            return

        for entry in sorted(self.vault.entries, key=lambda x: x.title.lower()):
            if not query or query in entry.title.lower() or query in entry.username.lower():
                self.filtered_entries.append(entry)
                item = QListWidgetItem()
                item.setSizeHint(QSize(250, 58))
                widget = AccountListItemWidget(entry)
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, widget)

        self.lbl_count.setText(str(len(self.filtered_entries)))

    def on_entry_selected(self):
        row = self.list_widget.currentRow()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, AccountListItemWidget):
                widget.update_selected_state(i == row)

        if 0 <= row < len(self.filtered_entries):
            self.show_entry_detail(self.filtered_entries[row])

    def show_empty_detail(self):
        self._clear_layout(self.right_layout)
        empty_box = QVBoxLayout()
        empty_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.setSpacing(12)

        icon = QLabel("🔑")
        icon.setFont(QFont(".AppleSystemUIFont", 44))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(icon)

        lbl = QLabel("No Account Selected")
        lbl.setFont(QFont(".AppleSystemUIFont", 18, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(lbl)

        sub = QLabel("Select an account from the sidebar or click '+ New Item'")
        sub.setFont(QFont(".AppleSystemUIFont", 13))
        sub.setStyleSheet("color: #8E8E93;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(sub)

        self.right_layout.addLayout(empty_box)

    def show_entry_detail(self, entry: VaultEntry):
        self._clear_layout(self.right_layout)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(16)

        gradient = get_avatar_gradient(entry.title)
        initial = (entry.title[0:2].upper() if len(entry.title) >= 2 else entry.title.upper()) or "🔑"
        hero_avatar = QLabel(initial)
        hero_avatar.setFixedSize(54, 54)
        hero_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_avatar.setStyleSheet(f"""
            background: {gradient};
            color: #FFFFFF;
            font-weight: bold;
            font-size: 20px;
            border-radius: 14px;
        """)
        hero_row.addWidget(hero_avatar)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(entry.title)
        title.setFont(QFont(".AppleSystemUIFont", 24, QFont.Weight.Bold))
        title_box.addWidget(title)

        meta = QLabel("Login credential • Updated in PyVault")
        meta.setStyleSheet("color: #8E8E93; font-size: 12px;")
        title_box.addWidget(meta)
        hero_row.addLayout(title_box)
        hero_row.addStretch()
        self.right_layout.addLayout(hero_row)

        card = QFrame()
        card.setObjectName("Card")
        cbox = QVBoxLayout(card)
        cbox.setContentsMargins(18, 14, 18, 14)
        cbox.setSpacing(12)

        cbox.addLayout(self._make_field_row("USERNAME", entry.username, copy_text=entry.username))
        cbox.addWidget(self._make_field_divider())
        cbox.addLayout(self._make_field_row("PASSWORD", entry.password, copy_text=entry.password, is_password=True))

        if entry.url:
            cbox.addWidget(self._make_field_divider())
            cbox.addLayout(self._make_field_row("WEBSITE", entry.url, copy_text=entry.url))

        if entry.notes:
            cbox.addWidget(self._make_field_divider())
            cbox.addLayout(self._make_field_row("NOTES", entry.notes))

        self.right_layout.addWidget(card)
        self.right_layout.addStretch()

        btn_del = QPushButton("Delete Item")
        btn_del.setObjectName("DangerBtn")
        btn_del.setFixedWidth(120)
        btn_del.setFixedHeight(36)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda: self.on_delete_entry(entry))
        self.right_layout.addWidget(btn_del)

    def _make_field_row(self, label: str, value: str, copy_text: Optional[str] = None, is_password: bool = False):
        row = QHBoxLayout()
        row.setSpacing(12)

        vbox = QVBoxLayout()
        vbox.setSpacing(3)
        lbl_meta = QLabel(label)
        lbl_meta.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.Bold))
        lbl_meta.setStyleSheet("color: #8E8E93; letter-spacing: 0.5px;")
        vbox.addWidget(lbl_meta)

        disp_text = "••••••••••••••••" if is_password else (value if value else "Not set")
        val_lbl = QLabel(disp_text)
        val_lbl.setFont(QFont(".AppleSystemUIFont", 14))
        val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vbox.addWidget(val_lbl)
        row.addLayout(vbox)
        row.addStretch()

        if is_password:
            btn_toggle = QPushButton("Show")
            btn_toggle.setObjectName("SecondaryBtn")
            btn_toggle.setFixedSize(68, 32)
            btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            is_masked = [True]

            def on_toggle():
                if is_masked[0]:
                    val_lbl.setText(value)
                    btn_toggle.setText("Hide")
                    is_masked[0] = False
                else:
                    val_lbl.setText("••••••••••••••••")
                    btn_toggle.setText("Show")
                    is_masked[0] = True

            btn_toggle.clicked.connect(on_toggle)
            row.addWidget(btn_toggle)

        if copy_text:
            btn_copy = QPushButton("Copy")
            btn_copy.setObjectName("SecondaryBtn")
            btn_copy.setFixedSize(76, 32)
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)

            def on_copy():
                copy_to_clipboard_timed(copy_text, 20)
                btn_copy.setText("✓ Copied")
                btn_copy.setStyleSheet("color: #30D158; font-weight: 600;" if ThemeManager.is_dark() else "color: #248A3D; font-weight: 600;")
                QTimer.singleShot(2000, lambda: [
                    btn_copy.setText("Copy"),
                    btn_copy.setStyleSheet("")
                ])

            btn_copy.clicked.connect(on_copy)
            row.addWidget(btn_copy)

        return row

    def _make_field_divider(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFrameShadow(QFrame.Shadow.Plain)
        div_color = "#323236" if ThemeManager.is_dark() else "#E5E5EA"
        div.setStyleSheet(f"color: {div_color}; background-color: {div_color};")
        div.setFixedHeight(1)
        return div

    def on_delete_entry(self, entry: VaultEntry):
        res = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{entry.title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.vault.delete(entry.id)
            self.vault.save()
            self.filter_entries()
            self.show_empty_detail()

    def on_add_account(self):
        dlg = AddEntryDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            if not data["title"] or not data["password"]:
                QMessageBox.warning(self, "Error", "Title and Password are required.")
                return
            try:
                self.vault.add(
                    title=data["title"],
                    username=data["username"],
                    password=data["password"],
                    url=data["url"]
                )
                self.vault.save()
                self.filter_entries()
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))

    def on_sync_dialog(self):
        dlg = SyncDialog(self)
        dlg.exec()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyVault")
    
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    window = PyVaultWindow()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
