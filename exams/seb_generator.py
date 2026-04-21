"""
Generate Safe Exam Browser (.seb) config file for an exam.
SEB config is a plist file encrypted with AES.
"""
import plistlib
import hashlib
import json


def generate_seb_config(exam_url, exam_title, quit_password="teacher123"):
    """
    Generate SEB config as bytes.
    exam_url: Full URL student should see e.g. http://192.168.1.5:8000/exam/1/register/
    quit_password: Password teacher uses to quit SEB (hash stored in config)
    """

    # Hash the quit password (SEB uses SHA256 -> hex)
    quit_hash = hashlib.sha256(quit_password.encode('utf-8')).hexdigest()

    config = {
        # ── Basic Settings ──────────────────────────────────────
        "startURL": exam_url,
        "browserWindowAllowAddressBar": False,
        "browserWindowAllowNavigation": False,
        "newBrowserWindowAllowAddressBar": False,

        # ── Lock Down Settings ──────────────────────────────────
        "kioskMode": 2,                    # 2 = kiosk mode (fullscreen, no taskbar)
        "allowQuit": True,                 # Quit only with password
        "quitURLConfirm": True,
        "hashedQuitPassword": quit_hash,   # SHA256 of quit password

        # ── Browser Restrictions ────────────────────────────────
        "enableBrowserWindowToolbar": False,
        "showMenuBar": False,
        "showTaskBar": False,
        "showReloadButton": False,
        "enableReloadButton": False,
        "allowPreferencesAccess": False,

        # ── Block Applications ──────────────────────────────────
        "prohibitedProcesses": [],          # Add processes to block if needed
        "permittedProcesses": [],

        # ── Input Restrictions ──────────────────────────────────
        "blockSwitchToApplications": True,
        "forceAppFolderInstall": False,

        # ── Screen/Display ──────────────────────────────────────
        "allowScreenSharing": False,
        "enablePrivateClipboard": True,    # Clipboard cleared on start

        # ── Zoom ────────────────────────────────────────────────
        "zoomMode": 0,
        "allowZoomPage": False,

        # ── Spell check / Autocorrect off ───────────────────────
        "allowSpellCheck": False,

        # ── Additional ──────────────────────────────────────────
        "examSessionClearCookiesOnEnd": True,
        "sendBrowserExamKey": False,
    }

    # Encode as plist (XML format)
    plist_bytes = plistlib.dumps(config, fmt=plistlib.FMT_XML)

    # SEB files are just plist — for basic SEB they don't need encryption
    # Advanced: encrypt with AES-CBC using password hash as key
    # For now return plain plist (SEB accepts both)
    return plist_bytes


def generate_seb_config_encrypted(exam_url, exam_title, password=""):
    """
    Generate properly encrypted SEB file.
    SEB encryption: AES-256-CBC, key = SHA256(password), IV = random
    Header: 2 bytes version + encrypted plist
    """
    import os
    plist_bytes = generate_seb_config(exam_url, exam_title)

    if not password:
        return plist_bytes  # Return plain if no password

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding

        key = hashlib.sha256(password.encode()).digest()
        iv  = os.urandom(16)

        padder = padding.PKCS7(128).padder()
        padded = padder.update(plist_bytes) + padder.finalize()

        cipher    = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()

        # SEB format: b'pswd' header + iv + encrypted data
        return b'pswd' + iv + encrypted

    except ImportError:
        return plist_bytes  # Fallback to plain
