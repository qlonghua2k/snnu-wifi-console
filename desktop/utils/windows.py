from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from desktop.constants import APP_ROOT


def powershell_path() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return str(Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_exit_code(code: int) -> str:
    if code < 0:
        unsigned = code + (1 << 32)
    else:
        unsigned = code
    if unsigned == 0xC000013A:
        return f"{unsigned} (0x{unsigned:08X}, process was interrupted)"
    if unsigned > 0x7FFFFFFF:
        return f"{unsigned} (0x{unsigned:08X})"
    return str(code)


def format_command_error(label: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    suffix = f"exit code {format_exit_code(result.returncode)}"
    return f"{label} failed with {suffix}." + (f"\n{detail}" if detail else "")


def run_command(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(APP_ROOT),
        "capture_output": True,
        "text": True,
        "errors": "replace",
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def runas_and_wait(file_path: str, args: list[str], timeout: int = 300) -> int:
    if os.name != "nt":
        result = run_command([file_path, *args], timeout=timeout)
        return result.returncode

    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    ERROR_CANCELLED = 1223

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = file_path
    info.lpParameters = subprocess.list2cmdline(args)
    info.lpDirectory = str(APP_ROOT)
    info.nShow = SW_SHOWNORMAL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == ERROR_CANCELLED:
            raise RuntimeError("管理员授权已取消。")
        raise RuntimeError(f"管理员进程启动失败，Windows 错误码 {error}。")

    try:
        wait_ms = int(timeout * 1000)
        wait_result = kernel32.WaitForSingleObject(info.hProcess, wait_ms)
        if wait_result == WAIT_TIMEOUT:
            raise TimeoutError(f"管理员进程超过 {timeout} 秒仍未结束。")
        if wait_result != WAIT_OBJECT_0:
            raise RuntimeError(f"等待管理员进程失败，Windows 等待码 {wait_result}。")
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise RuntimeError(f"读取管理员进程退出码失败，Windows 错误码 {error}。")
        return int(exit_code.value)
    finally:
        if info.hProcess:
            kernel32.CloseHandle(info.hProcess)


def run_elevated_command(
    cmd: list[str],
    timeout: int = 300,
    label: str = "Administrator command",
    success_codes: set[int] | None = None,
) -> None:
    if not cmd:
        raise ValueError("Command cannot be empty.")
    allowed = success_codes or {0}
    if is_admin():
        result = run_command(cmd, timeout=timeout)
        if result.returncode not in allowed:
            raise RuntimeError(format_command_error(label, result))
        return

    exit_code = runas_and_wait(cmd[0], cmd[1:], timeout=timeout)
    if exit_code not in allowed:
        raise RuntimeError(f"{label} failed with exit code {format_exit_code(exit_code)}.")


def run_elevated_powershell(args: list[str]) -> None:
    hidden_args = args if "-WindowStyle" in args else ["-WindowStyle", "Hidden", *args]
    run_elevated_command([powershell_path(), *hidden_args], timeout=300, label="Administrator PowerShell")
