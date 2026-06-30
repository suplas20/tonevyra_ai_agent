"""Small Win32 system tray adapter for the T-030 shell boundary."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ctypes import wintypes


NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NOTIFYICON_VERSION_4 = 4
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
WM_USER = 0x0400
WM_DESTROY = 0x0002
PM_REMOVE = 0x0001


LRESULT = ctypes.c_ssize_t
HICON = getattr(wintypes, "HICON", wintypes.HANDLE)
HCURSOR = getattr(wintypes, "HCURSOR", wintypes.HANDLE)
HBRUSH = getattr(wintypes, "HBRUSH", wintypes.HANDLE)
ATOM = getattr(wintypes, "ATOM", wintypes.WORD)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", HICON),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


@dataclass(frozen=True)
class NativeTrayResult:
    supported: bool
    added: bool
    removed: bool
    duration_seconds: float
    error_code: str | None = None
    error_message: str | None = None
    backend: str = "win32"


class NativeTrayIcon:
    """Create a hidden Win32 message window and register one notification icon."""

    def __init__(self, icon_path: Path, *, tooltip: str = "Tonevyra AI") -> None:
        self.icon_path = icon_path
        self.tooltip = tooltip[:127]
        self._class_name = f"TonevyraAITrayWindow{os.getpid()}"
        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._hinstance: int | None = None
        self._nid: NOTIFYICONDATAW | None = None
        self._wndproc = WNDPROC(self._window_proc)
        self._registered = False

    def show_for(self, duration_seconds: float) -> NativeTrayResult:
        started_at = time.monotonic()
        if os.name != "nt":
            return NativeTrayResult(False, False, False, 0.0, "UNSUPPORTED_PLATFORM", "Windows tray requires Win32")
        if not self.icon_path.is_file():
            return NativeTrayResult(False, False, False, 0.0, "TRAY_ICON_MISSING", str(self.icon_path))

        added = False
        removed = False
        try:
            self._create_window()
            added = self._add_icon()
            if not added:
                return _show_for_with_powershell(
                    self.icon_path,
                    self.tooltip,
                    duration_seconds,
                    previous_error=_last_error_message(),
                )
            self._pump_messages(max(0.0, duration_seconds))
            removed = self._remove_icon()
            return NativeTrayResult(True, True, removed, time.monotonic() - started_at)
        except OSError as exc:
            return NativeTrayResult(True, added, removed, time.monotonic() - started_at, exc.__class__.__name__, str(exc))
        finally:
            if added and not removed:
                self._remove_icon()
            self._destroy_window()

    def run_until_interrupted(self) -> NativeTrayResult:
        started_at = time.monotonic()
        if os.name != "nt":
            return NativeTrayResult(False, False, False, 0.0, "UNSUPPORTED_PLATFORM", "Windows tray requires Win32")
        if not self.icon_path.is_file():
            return NativeTrayResult(False, False, False, 0.0, "TRAY_ICON_MISSING", str(self.icon_path))

        added = False
        removed = False
        try:
            self._create_window()
            added = self._add_icon()
            if not added:
                return _run_powershell_until_interrupted(
                    self.icon_path,
                    self.tooltip,
                    previous_error=_last_error_message(),
                )
            while True:
                self._pump_messages(0.2)
        except KeyboardInterrupt:
            removed = self._remove_icon()
            return NativeTrayResult(True, added, removed, time.monotonic() - started_at)
        except OSError as exc:
            return NativeTrayResult(True, added, removed, time.monotonic() - started_at, exc.__class__.__name__, str(exc))
        finally:
            if added and not removed:
                self._remove_icon()
            self._destroy_window()

    def _create_window(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND

        self._hinstance = int(kernel32.GetModuleHandleW(None))
        window_class = WNDCLASSW(
            style=0,
            lpfnWndProc=self._wndproc,
            cbClsExtra=0,
            cbWndExtra=0,
            hInstance=self._hinstance,
            hIcon=None,
            hCursor=None,
            hbrBackground=None,
            lpszMenuName=None,
            lpszClassName=self._class_name,
        )
        atom = user32.RegisterClassW(ctypes.byref(window_class))
        if not atom:
            raise OSError(_last_error_message())
        self._registered = True

        hwnd = user32.CreateWindowExW(0, self._class_name, self._class_name, 0, 0, 0, 0, 0, None, None, self._hinstance, None)
        if not hwnd:
            raise OSError(_last_error_message())
        self._hwnd = int(hwnd)

    def _add_icon(self) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        hicon = user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not hicon:
            raise OSError(_last_error_message())
        self._hicon = int(hicon)

        nid = NOTIFYICONDATAW()
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_USER + 20
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip
        self._nid = nid

        added = False
        for cb_size in _notify_icon_data_sizes():
            nid.cbSize = cb_size
            added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
            if added:
                break
        if added:
            nid.uTimeoutOrVersion = NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
        return added

    def _remove_icon(self) -> bool:
        if self._nid is None:
            return False
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        removed = bool(shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid)))
        self._nid = None
        return removed

    def _destroy_window(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if self._hwnd:
            user32.DestroyWindow.argtypes = [wintypes.HWND]
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        if self._hicon:
            user32.DestroyIcon.argtypes = [HICON]
            user32.DestroyIcon(self._hicon)
            self._hicon = None
        if self._registered and self._hinstance:
            user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
            user32.UnregisterClassW(self._class_name, self._hinstance)
            self._registered = False

    def _pump_messages(self, duration_seconds: float) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]

        deadline = time.monotonic() + duration_seconds
        while time.monotonic() <= deadline:
            message = MSG()
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            time.sleep(0.05)

    def _window_proc(self, hwnd, msg, wparam, lparam):  # noqa: ANN001 - Win32 callback signature
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _last_error_message() -> str:
    error_code = ctypes.get_last_error()
    if not error_code:
        return "Win32 call failed without a last-error code"
    return f"Win32 error {error_code}"


def _notify_icon_data_sizes() -> tuple[int, ...]:
    """Return modern-to-legacy NOTIFYICONDATA sizes accepted by Shell_NotifyIcon."""

    return (
        ctypes.sizeof(NOTIFYICONDATAW),
        NOTIFYICONDATAW.guidItem.offset,
        NOTIFYICONDATAW.szInfo.offset,
        NOTIFYICONDATAW.dwState.offset,
    )


def _show_for_with_powershell(
    icon_path: Path,
    tooltip: str,
    duration_seconds: float,
    *,
    previous_error: str,
) -> NativeTrayResult:
    started_at = time.monotonic()
    command = _powershell_tray_command(icon_path, tooltip, duration_seconds=duration_seconds)
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        creationflags=_subprocess_creationflags(),
    )
    ok = result.returncode == 0
    return NativeTrayResult(
        supported=True,
        added=ok,
        removed=ok,
        duration_seconds=time.monotonic() - started_at,
        error_code=None if ok else "POWERSHELL_NOTIFYICON_FAILED",
        error_message=None if ok else f"{previous_error}; {result.stderr.strip() or result.stdout.strip()}",
        backend="windows_forms",
    )


def _run_powershell_until_interrupted(icon_path: Path, tooltip: str, *, previous_error: str) -> NativeTrayResult:
    started_at = time.monotonic()
    command = _powershell_tray_command(icon_path, tooltip, duration_seconds=None)
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_subprocess_creationflags(),
    )
    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return NativeTrayResult(True, True, True, time.monotonic() - started_at, backend="windows_forms")
    ok = return_code == 0
    stderr = ""
    if process.stderr is not None:
        stderr = process.stderr.read()
    return NativeTrayResult(
        supported=True,
        added=ok,
        removed=ok,
        duration_seconds=time.monotonic() - started_at,
        error_code=None if ok else "POWERSHELL_NOTIFYICON_FAILED",
        error_message=None if ok else f"{previous_error}; {stderr.strip()}",
        backend="windows_forms",
    )


def _subprocess_creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _powershell_tray_command(icon_path: Path, tooltip: str, *, duration_seconds: float | None) -> list[str]:
    escaped_icon = str(icon_path).replace("'", "''")
    escaped_tooltip = tooltip[:63].replace("'", "''")
    sleep_statement = (
        f"Start-Sleep -Milliseconds {max(1, int(duration_seconds * 1000))};"
        if duration_seconds is not None
        else "while ($true) { Start-Sleep -Seconds 1 };"
    )
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        f"$n.Icon=New-Object System.Drawing.Icon('{escaped_icon}');"
        f"$n.Text='{escaped_tooltip}';"
        "$n.Visible=$true;"
        "try {"
        f"{sleep_statement}"
        "} finally {"
        "$visible=$n.Visible;"
        "$n.Visible=$false;"
        "$n.Dispose();"
        "}"
        "if ($visible) { exit 0 } else { exit 3 }"
    )
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
