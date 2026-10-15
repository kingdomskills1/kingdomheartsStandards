import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "Image Viewer"
PROG_ID = "KingdomSkills.ImageViewer"
REGISTERED_APPS_KEY = r"Software\RegisteredApplications"
CAPABILITIES_KEY = r"Software\Image Studio\Capabilities"


def register_default_app(script_path, supported_formats):
    if os.name != "nt":
        raise RuntimeError(
            "Windows file association registration is only available on "
            "Windows."
        )

    import winreg

    if getattr(sys, "frozen", False):
        command_parts = [str(Path(sys.executable).resolve())]
    else:
        script_path = Path(script_path).resolve()
        pythonw_path = Path(sys.executable).with_name("pythonw.exe")
        executable = pythonw_path if pythonw_path.exists() else Path(sys.executable)
        command_parts = [str(executable), str(script_path)]

    command = subprocess.list2cmdline(command_parts) + ' "%1"'

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        rf"Software\Classes\{PROG_ID}"
    ) as prog_id_key:
        winreg.SetValueEx(prog_id_key, "", 0, winreg.REG_SZ, APP_NAME)

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        rf"Software\Classes\{PROG_ID}\shell\open\command"
    ) as command_key:
        winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, command)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CAPABILITIES_KEY) as key:
        winreg.SetValueEx(key, "ApplicationName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(
            key,
            "ApplicationDescription",
            0,
            winreg.REG_SZ,
            "View and browse image files.",
        )

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        rf"{CAPABILITIES_KEY}\FileAssociations"
    ) as associations_key:
        for extension in sorted(supported_formats):
            winreg.SetValueEx(
                associations_key,
                extension.lower(),
                0,
                winreg.REG_SZ,
                PROG_ID,
            )

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        REGISTERED_APPS_KEY
    ) as registered_apps_key:
        winreg.SetValueEx(
            registered_apps_key,
            APP_NAME,
            0,
            winreg.REG_SZ,
            CAPABILITIES_KEY,
        )

    for extension in supported_formats:
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\{extension.lower()}\OpenWithProgids"
        ) as open_with_key:
            winreg.SetValueEx(
                open_with_key,
                PROG_ID,
                0,
                winreg.REG_NONE,
                b"",
            )


def open_default_apps_settings():
    if os.name != "nt":
        raise RuntimeError(
            "Windows Default apps settings are only available on Windows."
        )

    os.startfile("ms-settings:defaultapps")
