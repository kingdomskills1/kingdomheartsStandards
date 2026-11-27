import base64
import ctypes
from concurrent.futures import ThreadPoolExecutor
import html
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from lxml import etree

try:
    import pystray
except ImportError:  # pragma: no cover - optional tray support
    pystray = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional enhancement
    Image = None
    ImageDraw = None
    ImageFont = None

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:  # pragma: no cover - optional browser helper
    webdriver = None
    Options = None
    By = None
    WebDriverWait = None
    TimeoutException = None

_SHARE_BOILERPLATE = (
    "This is a copy of a shared ChatGPT chat",
    "It won't be added to memory",
    "Report conversation",
    "ChatGPT is AI and can make mistakes",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
# Plain-text (``` fenced) blocks, e.g. the "Main Classification" tree, are
# screenshotted from the ChatGPT page just like tables.
SCREENSHOT_CODE_BLOCKS = True
# Same as tables: keep the real text under the screenshot. Set to False to
# insert only the screenshot image for each plain-text block.
KEEP_CODE_TEXT_AFTER_SCREENSHOT = True
# If the Chrome screenshot of a plain-text block is missing or fails, draw an
# identical-looking block ("</> Plain text" header, copy icons) with Pillow.
FALLBACK_RENDER_CODE_BLOCKS = True
# How plain-text (code block) images are made:
#   "clean"   - drawn with Pillow: light gray rounded box, no language label,
#               small copy icon top-right (the look of the Left-Handed Helix doc)
#   "chatgpt" - Chrome screenshot of the block from the ChatGPT page
CODE_BLOCK_IMAGE_STYLE = "clean"
_CONSOLE_CTRL_HANDLER = None
_CONSOLE_CLOSED_CALLBACK = None
_ACTIVE_DRIVERS = set()
_ACTIVE_DRIVERS_LOCK = threading.Lock()
_OUTPUT_LOCK = threading.Lock()
_OUTPUT_PATHS_LOCK = threading.Lock()
_WORD_COPY_LOCK = threading.Lock()
_JOB_HANDLE = None


def _bind_children_to_process_lifetime():
    """Windows: put this process in a kill-on-close Job Object.

    Every child process started afterwards (chromedriver, headless Chrome) is
    killed by Windows as soon as this process ends, however it ends.
    """
    global _JOB_HANDLE
    if os.name != "nt" or _JOB_HANDLE is not None:
        return False
    try:
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BASIC_LIMITS(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED_LIMITS(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMITS),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            return False
        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            return False
        _JOB_HANDLE = job  # keep the handle open for the life of the process
        return True
    except Exception:
        return False


def _start_chrome_driver():
    driver = webdriver.Chrome(options=_build_chrome_options())
    with _ACTIVE_DRIVERS_LOCK:
        _ACTIVE_DRIVERS.add(driver)
    return driver


def _stop_chrome_driver(driver):
    with _ACTIVE_DRIVERS_LOCK:
        _ACTIVE_DRIVERS.discard(driver)
    try:
        driver.quit()
    except Exception:
        pass


def _kill_all_chrome_drivers():
    """Kill every chromedriver/Chrome process this app started."""
    with _ACTIVE_DRIVERS_LOCK:
        drivers = list(_ACTIVE_DRIVERS)
        _ACTIVE_DRIVERS.clear()
    for driver in drivers:
        pid = None
        try:
            pid = driver.service.process.pid
        except Exception:
            pass
        if pid and os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                    timeout=5,
                )
                continue
            except Exception:
                pass
        try:
            driver.quit()
        except Exception:
            pass


def _force_exit():
    """Stop all browser processes and end this process completely."""
    try:
        _kill_all_chrome_drivers()
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(0)


def _install_console_close_handler():
    """Closing the console window only hides it; the GUI keeps running."""
    global _CONSOLE_CTRL_HANDLER
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32.dll")
    except (AttributeError, OSError):
        return False

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong)
    def _handler(ctrl_type):
        if ctrl_type == 2:  # CTRL_CLOSE_EVENT: user clicked X on the console
            # Detach from the console so Windows closes only the console
            # window and keeps this GUI process alive (console is "hidden").
            hide_program_console()
            callback = _CONSOLE_CLOSED_CALLBACK
            if callback is not None:
                try:
                    callback()
                except Exception:
                    pass
            return 1
        if ctrl_type in (5, 6):  # LOGOFF / SHUTDOWN
            _force_exit()
        return 0

    try:
        kernel32.SetConsoleCtrlHandler.argtypes = [
            ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong),
            ctypes.c_int,
        ]
        kernel32.SetConsoleCtrlHandler.restype = ctypes.c_int
        if kernel32.SetConsoleCtrlHandler(_handler, 1):
            _CONSOLE_CTRL_HANDLER = _handler
            return True
    except (AttributeError, ValueError):
        pass
    return False


def app_state_path():
    base_dir = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return base_dir / "ChatGPTToDocx" / "state.json"


def show_program_console():
    """Open a console window for this Windows GUI app when bundled with --windowed."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32.dll")
    except (AttributeError, OSError):
        return False
    if kernel32.GetConsoleWindow() == 0:
        if not kernel32.AllocConsole():
            return False
    _install_console_close_handler()
    sys.stdin = open("CONIN$", "r", encoding="utf-8", buffering=1)
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    return True


def hide_program_console():
    """Detach the process from its console so the GUI can continue running."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32.dll")
    except (AttributeError, OSError):
        return False
    if kernel32.GetConsoleWindow() == 0:
        return False
    kernel32.FreeConsole()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "close"):
                stream.close()
        except OSError:
            pass
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
    return True


@dataclass(frozen=True)
class SharedImage:
    placeholder: str
    data: bytes


@dataclass(frozen=True)
class PastedTextFormat:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    background: str | None = None
    font_name: str | None = None
    font_size: float | None = None


@dataclass(frozen=True)
class PastedTextRun:
    text: str
    format: PastedTextFormat = PastedTextFormat()


@dataclass(frozen=True)
class PastedTextParagraph:
    runs: tuple[PastedTextRun, ...]


def _css_color(value):
    value = value.strip().lower()
    if value in {"", "transparent", "initial", "inherit", "none"}:
        return None
    named_colors = {
        "black": "000000",
        "white": "FFFFFF",
        "red": "FF0000",
        "green": "008000",
        "blue": "0000FF",
        "yellow": "FFFF00",
        "gray": "808080",
        "grey": "808080",
        "gray25": "D9D9D9",
        "grey25": "D9D9D9",
        "lightgray": "D3D3D3",
        "lightgrey": "D3D3D3",
        "silver": "C0C0C0",
        "maroon": "800000",
        "purple": "800080",
        "fuchsia": "FF00FF",
        "lime": "00FF00",
        "olive": "808000",
        "navy": "000080",
        "teal": "008080",
        "aqua": "00FFFF",
        "orange": "FFA500",
    }
    if value in named_colors:
        return named_colors[value]
    if value.startswith("#"):
        digits = value[1:]
        if re.fullmatch(r"[0-9a-f]{3}", digits):
            return "".join(character * 2 for character in digits).upper()
        if re.fullmatch(r"[0-9a-f]{6}", digits):
            return digits.upper()
    match = re.fullmatch(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
        r"(?:\s*,\s*[\d.]+)?\s*\)",
        value,
    )
    if match:
        channels = tuple(int(channel) for channel in match.groups())
        if all(channel <= 255 for channel in channels):
            return "".join(f"{channel:02X}" for channel in channels)
    return None


def _style_declarations(value):
    styles = {}
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        name, content = declaration.split(":", 1)
        styles[name.strip().lower()] = content.strip()
    return styles


class _PastedHtmlParser(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "blockquote",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "pre",
    }

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.paragraphs = [[]]
        self.style_stack = [PastedTextFormat()]
        self.open_tags = []
        self.ignored_tags = []
        self.rules = self._css_rules(html)
        self.feed(html)
        self.close()
        self._trim_paragraph()
        while len(self.paragraphs) > 1 and not self.paragraphs[-1]:
            self.paragraphs.pop()

    @staticmethod
    def _css_rules(html):
        rules = {}
        for block in re.findall(
            r"<style\b[^>]*>(.*?)</style\s*>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            for selectors, declarations in re.findall(
                r"([^{}]+)\{([^{}]*)\}",
                block,
            ):
                for selector in selectors.split(","):
                    selector = selector.strip()
                    if selector:
                        rules[selector] = _style_declarations(declarations)
        return rules

    def _trim_paragraph(self):
        if not self.paragraphs or not self.paragraphs[-1]:
            return
        runs = self.paragraphs[-1]
        first = runs[0]
        trimmed = first.text.lstrip()
        if trimmed != first.text:
            if trimmed:
                runs[0] = PastedTextRun(trimmed, first.format)
            else:
                runs.pop(0)
        if runs:
            last = runs[-1]
            trimmed = last.text.rstrip()
            if trimmed:
                runs[-1] = PastedTextRun(trimmed, last.format)
            else:
                runs.pop()

    def _next_paragraph(self):
        self._trim_paragraph()
        if self.paragraphs[-1]:
            self.paragraphs.append([])

    def _current_style(self, tag, attributes):
        current = self.style_stack[-1]
        declarations = {}
        classes = dict(attributes).get("class", "").split()
        for class_name in classes:
            declarations.update(
                self.rules.get(f".{class_name}", {})
            )
            declarations.update(
                self.rules.get(f"{tag}.{class_name}", {})
            )
        declarations.update(
            self.rules.get(tag, {})
        )
        attributes = dict(attributes)
        declarations.update(_style_declarations(attributes.get("style", "")))

        bold = current.bold or tag in {"b", "strong"}
        italic = current.italic or tag in {"i", "em"}
        underline = current.underline or tag in {"u", "ins"}
        if declarations.get("font-weight", "").lower() in {
            "bold",
            "bolder",
            "600",
            "700",
            "800",
            "900",
        }:
            bold = True
        if declarations.get("font-style", "").lower() in {
            "italic",
            "oblique",
        }:
            italic = True
        if "underline" in declarations.get("text-decoration", "").lower():
            underline = True

        color = current.color
        background = current.background
        font_name = current.font_name
        font_size = current.font_size
        if "color" in declarations:
            color = _css_color(declarations["color"]) or color
        background_value = declarations.get(
            "background-color",
            declarations.get("background", ""),
        )
        if not background_value and declarations.get("mso-highlight"):
            background_value = declarations["mso-highlight"]
        if background_value:
            background = _css_color(background_value) or background
        if attributes.get("color"):
            color = _css_color(attributes["color"]) or color
        if attributes.get("face"):
            font_name = attributes["face"].split(",")[0].strip(" '\"")
        if declarations.get("font-family"):
            font_name = (
                declarations["font-family"]
                .split(",")[0]
                .strip(" '\"")
            )
        size = declarations.get("font-size", "")
        size_match = re.fullmatch(r"([\d.]+)\s*(pt|px)?", size.lower())
        if size_match:
            font_size = float(size_match.group(1))
            if size_match.group(2) == "px":
                font_size *= 0.75
        elif attributes.get("size", "").isdigit():
            font_size = (int(attributes["size"]) + 5) * 2
        return PastedTextFormat(
            bold=bold,
            italic=italic,
            underline=underline,
            color=color,
            background=background,
            font_name=font_name,
            font_size=font_size,
        )

    def _append_text(self, text):
        text = re.sub(r"[ \t\r\n\f]+", " ", text)
        if not text:
            return
        runs = self.paragraphs[-1]
        current_format = self.style_stack[-1]
        if runs and runs[-1].format == current_format:
            previous = runs[-1]
            if previous.text.endswith(" ") and text.startswith(" "):
                text = text[1:]
            if text:
                runs[-1] = PastedTextRun(previous.text + text, current_format)
        elif text:
            runs.append(PastedTextRun(text, current_format))

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "style", "script", "title"}:
            self.ignored_tags.append(tag)
            return
        if self.ignored_tags:
            return
        if tag == "br":
            self._next_paragraph()
            return
        if tag in {"meta", "link", "img", "hr", "input"}:
            return
        if tag in self.BLOCK_TAGS:
            self._next_paragraph()
        self.style_stack.append(self._current_style(tag, attrs))
        self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignored_tags:
            if tag == self.ignored_tags[-1]:
                self.ignored_tags.pop()
            return
        if tag in self.BLOCK_TAGS:
            self._next_paragraph()
        if tag in self.open_tags:
            matching_tag = len(self.open_tags) - 1 - self.open_tags[::-1].index(tag)
            del self.open_tags[matching_tag:]
            del self.style_stack[matching_tag + 1 :]

    def handle_data(self, data):
        if not self.ignored_tags:
            self._append_text(data)


def parse_pasted_html(html):
    style_blocks = re.findall(
        r"<style\b[^>]*>.*?</style\s*>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html_without_styles = re.sub(
        r"<style\b[^>]*>.*?</style\s*>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    parser = _PastedHtmlParser(
        "\n".join(style_blocks) + html_without_styles
    )
    return tuple(
        PastedTextParagraph(tuple(paragraph))
        for paragraph in parser.paragraphs
        if paragraph
    )


def _clipboard_html():
    if not hasattr(ctypes, "windll"):
        return None
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    clipboard_format = user32.RegisterClipboardFormatW("HTML Format")
    if not clipboard_format:
        return None
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(clipboard_format)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            raw_html = ctypes.string_at(pointer, kernel32.GlobalSize(handle))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    header = raw_html[:4096]
    match = re.search(rb"StartFragment:(\d+)", header)
    end_match = re.search(rb"EndFragment:(\d+)", header)
    if match and end_match:
        start = int(match.group(1))
        end = int(end_match.group(1))
        if 0 <= start <= end <= len(raw_html):
            raw_html = raw_html[start:end]
    else:
        start_marker = raw_html.find(b"<!--StartFragment-->")
        end_marker = raw_html.find(b"<!--EndFragment-->")
        if start_marker >= 0 and end_marker >= start_marker:
            raw_html = raw_html[
                start_marker + len(b"<!--StartFragment-->") : end_marker
            ]
    return raw_html.decode("utf-8-sig", errors="replace")


def validate_share_url(url):
    parsed = urlparse(url.strip())
    allowed_hosts = {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"}
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or not (
            parsed.path.startswith("/share/")
            or parsed.path.startswith("/s/")
        )
    ):
        raise ValueError(
            "Enter a public ChatGPT share link beginning with "
            "https://chatgpt.com/share/ or https://chatgpt.com/s/."
        )
    return parsed.geturl()


def _content_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            text for item in content if (text := _content_text(item))
        ).strip()
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"].strip()
        if "parts" in content:
            return _content_text(content["parts"])
    return ""


def _with_citation_titles(text, references):
    for reference in references:
        if not isinstance(reference, dict):
            continue
        marker = reference.get("matched_text")
        alt = reference.get("alt")
        if not isinstance(marker, str) or not marker.startswith("\ue200cite"):
            continue
        if not isinstance(alt, str):
            text = text.replace(marker, "")
            continue
        titles = re.findall(r"\[([^\]]+)\]\([^)]+\)", alt)
        if not titles:
            text = text.replace(marker, "")
            continue

        def replace_marker(_match):
            start = text.rfind("\n", 0, _match.start()) + 1
            end = text.find("\n", _match.end())
            paragraph = text[start:] if end == -1 else text[start:end]
            return "" if any(
                title.casefold() in paragraph.casefold()
                for title in titles
            ) else ", ".join(titles)

        text = re.sub(re.escape(marker), replace_marker, text)
    return text


def _assistant_message_records(value):
    records = []

    def visit(item):
        if isinstance(item, dict):
            author = item.get("author")
            role = author.get("role") if isinstance(author, dict) else item.get("role")
            content = item.get("content")
            if role == "assistant" and content is not None:
                text = _content_text(content)
                if text:
                    metadata = item.get("metadata")
                    references = (
                        metadata.get("content_references", [])
                        if isinstance(metadata, dict)
                        else []
                    )
                    if isinstance(references, list):
                        text = _with_citation_titles(text, references)
                    records.append((text, metadata))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return records


def _assistant_messages(value):
    return [text for text, _metadata in _assistant_message_records(value)]


def _latest_record_from_json_scripts(soup):
    candidates = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        records = _assistant_message_records(data)
        if records:
            candidates.append(records)

    if not candidates:
        return None
    return max(candidates, key=len)[-1]


def _latest_record_from_react_router_stream(soup):
    candidates = []
    stream_pattern = re.compile(
        r"streamController\.enqueue\((\"(?:\\.|[^\"\\])*\")\)"
    )
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        chunks = [
            json.loads(match.group(1))
            for match in stream_pattern.finditer(raw)
        ]
        if not chunks:
            continue
        try:
            data = json.loads("".join(chunks))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list):
            continue

        def resolve(index, depth=0, active=None):
            if (
                depth > 50
                or not isinstance(index, int)
                or index < 0
                or index >= len(data)
            ):
                return index
            if active is None:
                active = set()
            if index in active:
                return None

            node = data[index]
            if isinstance(node, dict):
                active.add(index)
                result = {}
                for key, value in node.items():
                    if not key.startswith("_") or not key[1:].isdigit():
                        continue
                    resolved_key = resolve(int(key[1:]), depth + 1, active)
                    if (
                        isinstance(value, int)
                        and 0 <= value < len(data)
                        and isinstance(data[value], (dict, list, str))
                    ):
                        resolved_value = resolve(value, depth + 1, active)
                    else:
                        resolved_value = value
                    result[str(resolved_key)] = resolved_value
                active.remove(index)
                return result
            if isinstance(node, list):
                active.add(index)
                result = [
                    resolve(value, depth + 1, active)
                    if (
                        isinstance(value, int)
                        and 0 <= value < len(data)
                        and isinstance(data[value], (dict, list, str))
                    )
                    else value
                    for value in node
                ]
                active.remove(index)
                return result
            return node

        records = _assistant_message_records(resolve(0))
        if records:
            candidates.append(records)

    if not candidates:
        return None
    return max(candidates, key=len)[-1]


def _latest_response_record(html):
    soup = BeautifulSoup(html, "html.parser")
    record = _latest_record_from_json_scripts(soup)
    if record:
        return record
    record = _latest_record_from_react_router_stream(soup)
    if record:
        return record

    rendered_messages = soup.select('[data-message-author-role="assistant"]')
    for message in reversed(rendered_messages):
        text = message.get_text("\n", strip=True)
        if text:
            return text, {}

    raise ValueError(
        "No assistant reply was found. Check that the link is a public "
        "ChatGPT shared conversation."
    )


def _image_specs(text, metadata, skipped=None):
    placeholders = list(
        re.finditer(r"<AsyncImage(?:Group)?\b[^>]*?/?>", text)
    )
    components = (
        metadata.get("genui_components", [])
        if isinstance(metadata, dict)
        else []
    )
    components_by_type = {
        component_type: [
            component
            for component in components
            if isinstance(component, dict)
            and component.get("type") == component_type
        ]
        for component_type in ("async_image", "async_image_group")
    }
    placeholders_by_type = {
        component_type: [
            placeholder
            for placeholder in placeholders
            if placeholder.group().startswith("<AsyncImageGroup")
            == (component_type == "async_image_group")
        ]
        for component_type in components_by_type
    }
    if any(
        len(placeholders_by_type[component_type])
        != len(components_by_type[component_type])
        for component_type in components_by_type
    ):
        raise ValueError(
            "The shared reply contains images, but their image data could "
            "not be matched to the reply. Try sharing the conversation again."
        )

    specs = []
    component_indices = {component_type: 0 for component_type in components_by_type}
    for placeholder in placeholders:
        component_type = (
            "async_image_group"
            if placeholder.group().startswith("<AsyncImageGroup")
            else "async_image"
        )
        component_index = component_indices[component_type]
        component_indices[component_type] += 1
        component = components_by_type[component_type][component_index]
        safe_urls = component.get("safe_urls", [])
        image_urls = [
            item.get("url")
            for item in safe_urls
            if isinstance(item, dict)
            and isinstance(item.get("url"), str)
            and item["url"].startswith("https://images.openai.com/")
        ]
        if component_type == "async_image_group":
            group_urls = (
                [url for url in image_urls if "purpose=fullsize" in url]
                or [url for url in image_urls if "purpose=inline" in url]
                or image_urls
            )
            if not group_urls:
                # ChatGPT gave no downloadable file for this group: skip it
                # instead of failing the whole conversion.
                print("[images] skipped an image group with no downloadable images")
                if skipped is not None:
                    skipped.append("an image group with no downloadable images")
                continue
            specs.extend((placeholder.group(), url) for url in group_urls)
            continue
        url = next(
            (item for item in image_urls if "purpose=fullsize" in item),
            next(
                (item for item in image_urls if "purpose=inline" in item),
                image_urls[0] if image_urls else None,
            ),
        )
        if not url:
            # No downloadable file (e.g. an image that expired or was never
            # shared): skip it instead of failing the whole conversion.
            print("[images] skipped an image with no downloadable file")
            if skipped is not None:
                skipped.append("an image with no downloadable file")
            continue
        specs.append((placeholder.group(), url))
    return specs


def _download_shared_image(placeholder, url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "images.openai.com":
        raise ValueError("The shared image URL is not a trusted ChatGPT image.")
    with requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        stream=True,
        allow_redirects=False,
    ) as response:
        response.raise_for_status()
        if response.headers.get("Content-Type", "").split(";")[0].lower() not in {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/tiff",
            "image/bmp",
        }:
            raise ValueError("ChatGPT returned an unsupported image format.")
        data = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("A shared image exceeds the 20 MB size limit.")
    return SharedImage(placeholder=placeholder, data=bytes(data))


def _fetch_response_record(url):
    share_url = validate_share_url(url)
    response = requests.get(
        share_url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    text, metadata = _latest_response_record(response.text)
    text = _replace_entity_tags(text)
    return _normalize_image_placeholders(text), metadata


def fetch_latest_response_with_images(url, skipped=None):
    """Returns (text, images). Anything skipped is described in `skipped`."""
    text, metadata = _fetch_response_record(url)
    images = []
    image_specs = _image_specs(text, metadata, skipped)
    if image_specs:
        worker_count = min(4, len(image_specs))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(_download_shared_image, placeholder, image_url)
                for placeholder, image_url in image_specs
            ]
            for future in futures:
                try:
                    images.append(future.result())
                except Exception as error:  # one bad image must not stop the document
                    print(f"[images] could not download an image: {error}")
                    if skipped is not None:
                        skipped.append(f"an image that failed to download ({error})")
    return text, images


def fetch_latest_response(url):
    text, _metadata = _fetch_response_record(url)
    return text


def extract_latest_response(html):
    text, _metadata = _latest_response_record(html)
    return _normalize_image_placeholders(_replace_entity_tags(text))


_IMAGE_PLACEHOLDER_RE = re.compile(r"<AsyncImage(?:Group)?\b[^>]*?/?>")
_ROW_TAG_RE = re.compile(
    r"(<row\b[^>]*>)(.*?)(</row\s*>)",
    re.IGNORECASE | re.DOTALL,
)
_ENTITY_TAG_RE = re.compile(
    r"<Entity\b[^>]*?\bvalue\s*=\s*(?:\"([^\"]*)\"|'([^']*)')[^>]*?/>",
    re.IGNORECASE,
)
_ENTITY_PAIRED_RE = re.compile(
    r"<Entity\b[^>]*?>(.*?)</Entity\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _replace_entity_tags(text):
    """<Entity value="Cube" .../> -> Cube  (and <Entity ...>Cube</Entity> -> Cube)."""
    text = _ENTITY_TAG_RE.sub(
        lambda match: match.group(1) if match.group(1) is not None else match.group(2),
        text,
    )
    return _ENTITY_PAIRED_RE.sub(lambda match: match.group(1), text)


def _normalize_image_placeholders(text):
    """Keep row images after their text and collapse each tag onto its own line."""
    def move_row_images_after_content(match):
        row_content = match.group(2)
        image_tags = list(_IMAGE_PLACEHOLDER_RE.finditer(row_content))
        if not image_tags:
            return match.group(0)
        content = _IMAGE_PLACEHOLDER_RE.sub("", row_content).rstrip()
        if not content.strip() or image_tags[-1].end() == len(row_content.rstrip()):
            return match.group(0)
        images = "\n".join(image.group().strip() for image in image_tags)
        return f"{match.group(1)}{content}\n{images}\n{match.group(3)}"

    text = _ROW_TAG_RE.sub(move_row_images_after_content, text)
    return _IMAGE_PLACEHOLDER_RE.sub(
        lambda match: "\n" + re.sub(r"\s+", " ", match.group()).strip() + "\n",
        text,
    )


# ChatGPT "widget" elements, e.g.
#   <title size="xl" color="default" tabularNums>6</title>
#   <text color="secondary" size="xs">Four equal sides and four 90° angles.</text>
# Only matched when they carry at least one attribute, so plain prose that
# mentions <text> or <title> is left alone.
_WIDGET_TEXT_RE = re.compile(
    r"<(title|text|badge)(\s+[^<>]*?)\s*>(.*?)</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_LAYOUT_TAG_RE = re.compile(r"</?(?:box|row|divider|grid-item|grid)\b[^>]*?/?>", re.IGNORECASE)
_WIDGET_SIZES_PT = {
    "title": {"xs": 11, "sm": 12, "md": 14, "lg": 16, "xl": 20, "2xl": 24, "3xl": 28},
    "text": {"xs": 9, "sm": 10, "md": 12, "lg": 14, "xl": 16},
}
_WIDGET_DEFAULT_SIZE_PT = {"title": 14, "text": 12}
_WIDGET_COLORS = {
    "secondary": RGBColor(0x6B, 0x6B, 0x6B),
    "tertiary": RGBColor(0x8E, 0x8E, 0x8E),
}


def _widget_attribute(attributes, name):
    match = re.search(
        r"(?<![\w-])" + name + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        attributes,
        re.IGNORECASE,
    )
    if not match:
        return None
    for group in match.groups():
        if group is not None:
            return group
    return None


def _normalize_widget_text_segment(text):
    if not _WIDGET_TEXT_RE.search(text):
        return text
    # an element that wraps over several lines becomes a single line
    text = _WIDGET_TEXT_RE.sub(
        lambda match: re.sub(r"\s*\n\s*", " ", match.group(0)),
        text,
    )
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        remainder = _LAYOUT_TAG_RE.sub("", _WIDGET_TEXT_RE.sub("", stripped)).strip()
        if stripped and _WIDGET_TEXT_RE.search(stripped) and not remainder:
            # a line holding only widget elements (and <box>/<row> tags):
            # put every element on its own line
            lines.extend(match.group(0) for match in _WIDGET_TEXT_RE.finditer(stripped))
        else:
            lines.append(line)
    return "\n".join(lines)


def _normalize_widget_text(text):
    """Make every <title ...>/<text ...> widget element its own single line.

    Fenced code blocks are left untouched.
    """
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    for position in range(0, len(parts), 2):
        parts[position] = _normalize_widget_text_segment(parts[position])
    return "".join(parts)


_BADGE_STYLES = {  # color name -> (text color, background fill)
    "success": ("1B7F3B", "DFF5E6"),
    "danger": ("B42318", "FDE7E6"),
    "error": ("B42318", "FDE7E6"),
    "warning": ("B54708", "FEF0C7"),
    "caution": ("B54708", "FEF0C7"),
    "info": ("175CD3", "E1EDFF"),
    "primary": ("175CD3", "E1EDFF"),
    "secondary": ("475467", "EAECF0"),
}


def _add_badge(document, attributes, inner):
    color_name = (_widget_attribute(attributes, "color") or "").lower()
    text_color, fill = _BADGE_STYLES.get(color_name, _BADGE_STYLES["secondary"])
    paragraph = document.add_paragraph()
    _add_inline_runs(paragraph, inner.strip(), bold=True)
    for run in paragraph.runs:
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor.from_string(text_color)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:color"), "auto")
        shading.set(qn("w:fill"), fill)
        run._r.get_or_add_rPr().append(shading)
    paragraph.paragraph_format.space_after = Pt(6)
    return paragraph


def _add_widget_text(document, kind, attributes, inner):
    kind = kind.lower()
    if kind == "badge":
        return _add_badge(document, attributes, inner)
    is_title = kind == "title"
    size_name = (_widget_attribute(attributes, "size") or "").lower()
    color_name = (_widget_attribute(attributes, "color") or "").lower()
    size_pt = _WIDGET_SIZES_PT[kind].get(size_name, _WIDGET_DEFAULT_SIZE_PT[kind])
    color = _WIDGET_COLORS.get(color_name)
    paragraph = document.add_paragraph()
    _add_inline_runs(paragraph, inner.strip(), bold=is_title)
    for run in paragraph.runs:
        run.font.size = Pt(size_pt)
        if color is not None:
            run.font.color.rgb = color
    paragraph.paragraph_format.space_before = Pt(6) if is_title else Pt(0)
    paragraph.paragraph_format.space_after = Pt(0) if is_title else Pt(8)
    paragraph.paragraph_format.keep_with_next = is_title
    return paragraph


def _clean_inline_text(text):
    text = _replace_entity_tags(text)
    text = _IMAGE_PLACEHOLDER_RE.sub("", text)
    text = _WIDGET_TEXT_RE.sub(
        lambda match: match.group(3)
        + (
            ""
            if match.end() >= len(match.string) or match.string[match.end()].isspace()
            else " "
        ),
        text,
    )
    text = re.sub(
        r"</?(?:box|row|divider|grid-item|grid)\b[^>]*?/?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</?cites?\b[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # <Link ref="turn123search0" title="Wolfram MathWorld"/>  ->  Wolfram MathWorld
    text = re.sub(
        r'<Link\b[^>]*?\btitle\s*=\s*"([^"]*)"[^>]*?/?>(?:\s*</Link>)?',
        lambda match: html.unescape(match.group(1)),
        text,
        flags=re.IGNORECASE,
    )
    # Any leftover <Link .../> or </Link> with no title
    text = re.sub(r"</?Link\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(
        "\ue200url\ue202(.*?)\ue202.*?\ue201",
        r"\1",
        text,
    )
    text = re.sub(
        "\ue200entity\ue202\\[[^,\\]]+,\\s*\"([^\"]+)\"\\]\ue201",
        r"\1",
        text,
    )
    text = re.sub("\ue200cite\ue202.*?\ue201", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\ue200.*?\ue201", "", text)
    return text


def _main_heading(text):
    in_code_block = False
    has_classification_path = any(
        re.match(
            r"^#{1,3}\s+Recommended Classification Path\s*$",
            line.strip(),
            re.IGNORECASE,
        )
        for line in text.splitlines()
    )
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        heading = re.match(r"^#\s+(.+)$", line.strip())
        if not heading:
            continue
        title = re.sub(
            r"^\d+(?:\.\d+)*[.)]?\s+",
            "",
            heading.group(1),
        )
        if has_classification_path:
            title_parts = re.split(r"\s+—\s+", title)
            if len(title_parts) >= 3:
                title = title_parts[-1]
        title = _clean_inline_text(title)
        title = re.sub(r"[*_`]", "", title).strip()
        return title
    return ""


def default_output_path(text, desktop=None):
    desktop_path = Path(desktop) if desktop is not None else Path.home() / "Desktop"
    title = _main_heading(text)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title:
        title = "chatgpt-response"
    if re.match(
        r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",
        title,
        re.IGNORECASE,
    ):
        title = f"_{title}"
    title = title[:120].rstrip(" .") or "chatgpt-response"

    candidate = desktop_path / f"{title}.docx"
    suffix = 2
    while candidate.exists():
        candidate = desktop_path / f"{title} ({suffix}).docx"
        suffix += 1
    return candidate


def _math_element(tag):
    return OxmlElement(f"m:{tag}")


def _math_rpr():
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), "Cambria Math")
    fonts.set(qn("w:hAnsi"), "Cambria Math")
    rpr.append(fonts)
    return rpr


def _math_ctrl_pr():
    control = _math_element("ctrlPr")
    control.append(_math_rpr())
    return control


def _math_run(text):
    run = _math_element("r")
    run.append(_math_rpr())
    text_element = _math_element("t")
    text_element.set(
        "{http://www.w3.org/XML/1998/namespace}space",
        "preserve",
    )
    text_element.text = text
    run.append(text_element)
    return run


def _append_script_content(container, argument):
    math_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    if argument.tag in {
        f"{{{math_namespace}}}e",
        f"{{{math_namespace}}}sub",
        f"{{{math_namespace}}}sup",
    }:
        for child in list(argument):
            _append_script_content(container, child)
    else:
        container.append(argument)


_MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
# A big operator's body ends at a relation / separator / binary +,- (outside
# of brackets), so  \sum_i \lambda_i P_i = 1  puts "lambda_i P_i" in the body.
_NARY_STOP_CHARS = "=+-\u2212<>,;:|\u2223)]}\u27e9\u2264\u2265\u2260\u2208\u2209\u2282\u2286\u2283\u2287\u2192\u21d2\u21d4\u2194\u223c\u2248\u2261\u2225\u2227\u2228\u222a\u2229"


def _math_run_text(node):
    if not node.tag.endswith("}r"):
        return None
    return "".join(t.text or "" for t in node.iter(f"{{{_MATH_NS}}}t"))


def _merge_nary_bodies(nodes):
    merged = []
    index = 0
    while index < len(nodes):
        node = nodes[index]
        index += 1
        merged.append(node)
        if not (
            node.tag.endswith("}nary")
            and node.find(f"{{{_MATH_NS}}}e") is None
        ):
            continue
        body_nodes = []
        depth = 0
        while index < len(nodes):
            candidate = nodes[index]
            text = _math_run_text(candidate)
            if text is not None and text != "":
                if len(text) == 1 and text in "([\u27e8":
                    depth += 1
                elif len(text) == 1 and text in ")]\u27e9" and depth > 0:
                    depth -= 1
                elif depth == 0 and (
                    text.strip() == ""
                    or (len(text) == 1 and text in _NARY_STOP_CHARS)
                ):
                    break
            body_nodes.append(candidate)
            index += 1
        if body_nodes:
            body = _math_element("e")
            for body_node in _merge_nary_bodies(body_nodes):
                _append_script_content(body, body_node)
            node.append(body)
    return merged


def _normalize_nary(math):
    """Give every n-ary operator the full  properties/sub/sup/e  shape.

    OMML requires sub, sup and e on m:nary. When a limit is missing, hide it
    explicitly; otherwise Word shows an empty dotted placeholder box.
    """
    for nary in list(math.iter(f"{{{_MATH_NS}}}nary")):
        props = nary.find(f"{{{_MATH_NS}}}naryPr")
        if props is None:
            props = _math_element("naryPr")
        parts = {}
        for name in ("sub", "sup", "e"):
            parts[name] = nary.find(f"{{{_MATH_NS}}}{name}")
        for name, hide in (("sub", "subHide"), ("sup", "supHide")):
            if parts[name] is None:
                parts[name] = _math_element(name)
                if props.find(f"{{{_MATH_NS}}}{hide}") is None:
                    flag = _math_element(hide)
                    flag.set(f"{{{_MATH_NS}}}val", "1")
                    control = props.find(f"{{{_MATH_NS}}}ctrlPr")
                    if control is not None:
                        control.addprevious(flag)
                    else:
                        props.append(flag)
        if parts["e"] is None:
            parts["e"] = _math_element("e")
        for child in list(nary):
            nary.remove(child)
        for child in (props, parts["sub"], parts["sup"], parts["e"]):
            nary.append(child)


# LaTeX math alphabets -> Unicode "Mathematical Alphanumeric Symbols".
# (upper_start, lower_start, digit_start, exceptions)
_MATH_ALPHABETS = {
    "mathcal": (0x1D49C, 0x1D4B6, None, {
        "B": "\u212c", "E": "\u2130", "F": "\u2131", "H": "\u210b",
        "I": "\u2110", "L": "\u2112", "M": "\u2133", "R": "\u211b",
        "e": "\u212f", "g": "\u210a", "o": "\u2134",
    }),
    "mathbb": (0x1D538, 0x1D552, 0x1D7D8, {
        "C": "\u2102", "H": "\u210d", "N": "\u2115", "P": "\u2119",
        "Q": "\u211a", "R": "\u211d", "Z": "\u2124",
    }),
    "mathfrak": (0x1D504, 0x1D51E, None, {
        "C": "\u212d", "H": "\u210c", "I": "\u2111", "R": "\u211c",
        "Z": "\u2128",
    }),
    "mathsf": (0x1D5A0, 0x1D5BA, 0x1D7E2, {}),
    "mathtt": (0x1D670, 0x1D68A, 0x1D7F6, {}),
}
_MATH_ALPHABETS["mathscr"] = _MATH_ALPHABETS["mathcal"]


def _map_math_alphabet(text, command):
    upper, lower, digit, exceptions = _MATH_ALPHABETS[command]
    result = []
    for character in text:
        if character in exceptions:
            result.append(exceptions[character])
        elif "A" <= character <= "Z" and upper:
            result.append(chr(upper + ord(character) - ord("A")))
        elif "a" <= character <= "z" and lower:
            result.append(chr(lower + ord(character) - ord("a")))
        elif "0" <= character <= "9" and digit:
            result.append(chr(digit + ord(character) - ord("0")))
        else:
            result.append(character)
    return "".join(result)


class _MathParser:
    COMMANDS = {
        "alpha": "α",
        "beta": "β",
        "gamma": "γ",
        "Gamma": "Γ",
        "delta": "δ",
        "Delta": "Δ",
        "theta": "θ",
        "Theta": "Θ",
        "lambda": "λ",
        "Lambda": "Λ",
        "ell": "ℓ",
        "mu": "μ",
        "pi": "π",
        "Pi": "Π",
        "rho": "ρ",
        "sigma": "σ",
        "Sigma": "Σ",
        "phi": "φ",
        "Phi": "Φ",
        "omega": "ω",
        "Omega": "Ω",
        "epsilon": "ϵ",
        "varepsilon": "ε",
        "zeta": "ζ",
        "eta": "η",
        "vartheta": "ϑ",
        "iota": "ι",
        "kappa": "κ",
        "nu": "ν",
        "xi": "ξ",
        "Xi": "Ξ",
        "varrho": "ϱ",
        "varsigma": "ς",
        "tau": "τ",
        "upsilon": "υ",
        "Upsilon": "Υ",
        "varphi": "φ",
        "chi": "χ",
        "psi": "ψ",
        "Psi": "Ψ",
        "cdot": "·",
        "cdots": "⋯",
        "odot": "⊙",
        "dots": "…",
        "ldots": "…",
        "vdots": "⋮",
        "ddots": "⋱",
        "sum": "∑",
        "prod": "∏",
        "int": "∫",
        "sin": "sin",
        "cos": "cos",
        "tan": "tan",
        "log": "log",
        "ln": "ln",
        "lim": "lim",
        "max": "max",
        "min": "min",
        "det": "det",
        "times": "×",
        "div": "÷",
        "pm": "±",
        "quad": "\u2003",
        "qquad": "\u2003\u2003",
        "le": "≤",
        "leq": "≤",
        "ge": "≥",
        "geq": "≥",
        "parallel": "∥",
        "neq": "≠",
        "ne": "≠",
        "in": "∈",
        "notin": "∉",
        "to": "→",
        "rightarrow": "→",
        "leftarrow": "←",
        "infty": "∞",
        "approx": "≈",
        "equiv": "≡",
        "circ": "∘",
        "angle": "∠",
        "triangle": "△",
        "bigtriangleup": "△",
        "triangledown": "▽",
        "square": "□",
        "degree": "°",
        "measuredangle": "∡",
        "perp": "⊥",
        "vert": "|",
        "mid": "\u2223",
        "subset": "⊂",
        "supset": "⊃",
        "subseteq": "⊆",
        "supseteq": "⊇",
        "subsetneq": "⊊",
        "supsetneq": "⊋",
        "cup": "∪",
        "cap": "∩",
        "setminus": "∖",
        "emptyset": "∅",
        "varnothing": "∅",
        "ni": "∋",
        "forall": "∀",
        "exists": "∃",
        "neg": "¬",
        "lnot": "¬",
        "land": "∧",
        "wedge": "∧",
        "lor": "∨",
        "vee": "∨",
        "cong": "≅",
        "sim": "∼",
        "propto": "∝",
        "mp": "∓",
        "ast": "∗",
        "star": "⋆",
        "bullet": "∙",
        "oplus": "⊕",
        "otimes": "⊗",
        "partial": "∂",
        "nabla": "∇",
        "hbar": "ℏ",
        "aleph": "ℵ",
        "prime": "′",
        "Rightarrow": "⇒",
        "Leftarrow": "⇐",
        "Leftrightarrow": "⇔",
        "leftrightarrow": "↔",
        "mapsto": "↦",
        "implies": "⟹",
        "iff": "⟺",
        "langle": "⟨",
        "rangle": "⟩",
        "lceil": "⌈",
        "rceil": "⌉",
        "lfloor": "⌊",
        "rfloor": "⌋",
        "therefore": "∴",
        "because": "∵",
        "ll": "≪",
        "gg": "≫",
        "nmid": "\u2224",
        "bigcap": "\u22c2",
        "bigcup": "\u22c3",
        "bigvee": "\u22c1",
        "bigwedge": "\u22c0",
        "bigoplus": "\u2a01",
        "bigotimes": "\u2a02",
        "coprod": "\u2210",
        "lVert": "\u2016",
        "rVert": "\u2016",
        "Vert": "\u2016",
        "|": "\u2016",
        "lbrace": "{",
        "rbrace": "}",
        ",": "\u2009",
        ";": "\u2004",
        ":": "\u2005",
        ">": "\u2005",
        " ": "\u00a0",
        "!": "",
        "lvert": "|",
        "rvert": "|",
        "{": "{",
        "}": "}",
        "%": "%",
        "_": "_",
        "#": "#",
        "$": "$",
        "&": "&",
    }

    ACCENTS = {
        "vec": "\u20d7",
        "overrightarrow": "\u20d7",
        "hat": "\u0302",
        "widehat": "\u0302",
        "tilde": "\u0303",
        "widetilde": "\u0303",
        "bar": "\u0305",
        "dot": "\u0307",
        "ddot": "\u0308",
        "acute": "\u0301",
        "grave": "\u0300",
        "breve": "\u0306",
        "check": "\u030c",
    }

    NARY_COMMANDS = {
        "sum", "prod", "int", "bigcap", "bigcup", "bigvee", "bigwedge",
        "bigoplus", "bigotimes", "coprod",
    }

    # Function names are typeset upright (plain style), not italic.
    FUNCTION_NAMES = {
        "sin", "cos", "tan", "cot", "sec", "csc",
        "log", "ln", "lim", "max", "min", "det", "exp",
    }

    def __init__(self, expression):
        # x^\circ and x^{\circ} mean "degrees", not the ring operator
        expression = re.sub(
            r"\^\s*\{\s*\\circ\s*\}|\^\s*\\circ(?![A-Za-z])",
            r"^{\\degree}",
            expression,
        )
        self.tokens = re.findall(self.TOKEN_RE, expression)
        self.position = 0

    def _group(self, preserve_whitespace=False):
        if self.position < len(self.tokens) and self.tokens[self.position] == "{":
            self.position += 1
            nodes = _merge_nary_bodies(self._sequence("}", preserve_whitespace))
            if self.position < len(self.tokens):
                self.position += 1
            container = _math_element("e")
            for node in nodes:
                container.append(node)
            return container
        return self._atom()

    TOKEN_RE = (
        r"\\[A-Za-z]+|\\.|[A-Za-z]+|\d+(?:\.\d+)?|"
        r"\s+|."
    )

    def _read_delimiter(self):
        while self.position < len(self.tokens) and self.tokens[self.position].isspace():
            self.position += 1
        if self.position >= len(self.tokens):
            return ""
        delimiter = self.tokens[self.position]
        self.position += 1
        if delimiter in {".", "\\."}:
            return ""
        if delimiter.startswith("\\"):
            return self.COMMANDS.get(delimiter[1:], delimiter[1:])
        return delimiter

    def _script_argument(self):
        # TeX: an unbraced sub/superscript is ONE character, so
        # \lambda_iP_i is lambda_i followed by P_i (not lambda_{iP}).
        while self.position < len(self.tokens) and self.tokens[self.position].isspace():
            self.position += 1
        if self.position < len(self.tokens):
            token = self.tokens[self.position]
            if len(token) > 1 and token.isalpha():
                self.tokens[self.position : self.position + 1] = re.findall(
                    self.TOKEN_RE, token[1:]
                )
                return _math_run(token[0])
        return self._group()

    def _stacked_rows(self):
        while self.position < len(self.tokens) and self.tokens[self.position].isspace():
            self.position += 1
        if not (self.position < len(self.tokens) and self.tokens[self.position] == "{"):
            return [[self._group()]]
        self.position += 1
        rows = []
        while True:
            rows.append(_merge_nary_bodies(self._sequence({"}", "\\\\"})))
            if self.position >= len(self.tokens):
                break
            token = self.tokens[self.position]
            self.position += 1
            if token == "}":
                break
        while len(rows) > 1 and not rows[-1]:
            rows.pop()
        return rows

    def _fraction_argument(self):
        while self.position < len(self.tokens) and self.tokens[self.position].isspace():
            self.position += 1
        if self.position < len(self.tokens):
            token = self.tokens[self.position]
            # TeX: an unbraced \frac argument is ONE character, so
            # \frac52.3 is 5/2 followed by ".3" and \frac ab is a/b.
            if token[0].isalnum():
                rest = token[1:]
                self.tokens[self.position : self.position + 1] = re.findall(
                    self.TOKEN_RE, rest
                )
                return _math_run(token[0])
        return self._group()

    def _atom(self):
        if self.position >= len(self.tokens):
            return _math_run("")
        token = self.tokens[self.position]
        self.position += 1
        if token == "{":
            self.position -= 1
            return self._group()

        if token.startswith("\\"):
            command = token[1:]
            if command == "left":
                begin_char = self._read_delimiter()
                parts = [_merge_nary_bodies(self._sequence({"\\right", "\\middle"}))]
                separator_char = None
                end_char = ""
                while self.position < len(self.tokens):
                    closing_token = self.tokens[self.position]
                    self.position += 1
                    if closing_token == "\\middle":
                        found = self._read_delimiter()
                        if separator_char is None:
                            separator_char = found
                        parts.append(
                            _merge_nary_bodies(
                                self._sequence({"\\right", "\\middle"})
                            )
                        )
                    else:
                        end_char = self._read_delimiter()
                        break
                delimiter_node = _math_element("d")
                properties = _math_element("dPr")
                for tag, value in (
                    ("begChr", begin_char),
                    ("sepChr", separator_char),
                    ("endChr", end_char),
                ):
                    if value is None:
                        continue
                    char_node = _math_element(tag)
                    char_node.set(f"{{{_MATH_NS}}}val", value)
                    properties.append(char_node)
                properties.append(_math_ctrl_pr())
                delimiter_node.append(properties)
                for part_nodes in parts:
                    part = _math_element("e")
                    for part_node in part_nodes:
                        _append_script_content(part, part_node)
                    delimiter_node.append(part)
                return delimiter_node
            if command == "substack":
                rows = self._stacked_rows()
                array = _math_element("eqArr")
                properties = _math_element("eqArrPr")
                base_justify = _math_element("baseJc")
                base_justify.set(f"{{{_MATH_NS}}}val", "center")
                properties.append(base_justify)
                properties.append(_math_ctrl_pr())
                array.append(properties)
                for row_nodes in rows:
                    row = _math_element("e")
                    for row_node in row_nodes:
                        _append_script_content(row, row_node)
                    array.append(row)
                return array
            if command in {"left", "right", "middle"}:
                if self.position < len(self.tokens):
                    delimiter = self.tokens[self.position]
                    self.position += 1
                    if delimiter in {".", "\\."}:
                        return _math_run("")
                    if delimiter.startswith("\\"):
                        delimiter = self.COMMANDS.get(
                            delimiter[1:],
                            delimiter[1:],
                        )
                    return _math_run(delimiter)
                return _math_run("")
            if command == "frac":
                numerator = self._fraction_argument()
                denominator = self._fraction_argument()
                fraction = _math_element("f")
                fraction.append(_math_element("fPr"))
                for tag, value in (("num", numerator), ("den", denominator)):
                    part = _math_element(tag)
                    _append_script_content(part, value)
                    fraction.append(part)
                return fraction
            if command in self.ACCENTS:
                accent = _math_element("acc")
                properties = _math_element("accPr")
                accent_char = _math_element("chr")
                accent_char.set(f"{{{_MATH_NS}}}val", self.ACCENTS[command])
                properties.append(accent_char)
                properties.append(_math_ctrl_pr())
                accent.append(properties)
                expression = _math_element("e")
                _append_script_content(expression, self._script_argument())
                accent.append(expression)
                return accent
            if command == "overline":
                over = _math_element("bar")
                properties = _math_element("barPr")
                position = _math_element("pos")
                position.set(f"{{{_MATH_NS}}}val", "top")
                properties.append(position)
                properties.append(_math_ctrl_pr())
                over.append(properties)
                expression = _math_element("e")
                _append_script_content(expression, self._script_argument())
                over.append(expression)
                return over
            if command == "sqrt":
                radicand = self._group()
                radical = _math_element("rad")
                properties = _math_element("radPr")
                degree_hidden = _math_element("degHide")
                degree_hidden.set(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/math}val",
                    "1",
                )
                properties.append(degree_hidden)
                radical.append(properties)
                radical.append(_math_element("deg"))
                expression = _math_element("e")
                _append_script_content(expression, radicand)
                radical.append(expression)
                return radical
            if command == "boxed":
                content = self._group()
                border_box = _math_element("borderBox")
                properties = _math_element("borderBoxPr")
                properties.append(_math_ctrl_pr())
                border_box.append(properties)
                expression = _math_element("e")
                _append_script_content(expression, content)
                border_box.append(expression)
                return border_box
            if command == "operatorname":
                if self.position < len(self.tokens) and self.tokens[self.position] == "*":
                    self.position += 1
                content = self._group()
                math_namespace = (
                    "http://schemas.openxmlformats.org/officeDocument/2006/math"
                )
                children = list(content)
                if children and all(
                    child.tag == f"{{{math_namespace}}}r" for child in children
                ):
                    # operator names are upright text: one plain-style run
                    name = "".join(
                        text.text or ""
                        for child in children
                        for text in child.iter(f"{{{math_namespace}}}t")
                    )
                    run = _math_run(name)
                    properties = _math_element("rPr")
                    style = _math_element("sty")
                    style.set(f"{{{math_namespace}}}val", "p")
                    properties.append(style)
                    run.insert(0, properties)
                    return run
                return content
            if command in _MATH_ALPHABETS:
                content = self._group()
                for text_node in content.iter(f"{{{_MATH_NS}}}t"):
                    text_node.text = _map_math_alphabet(
                        text_node.text or "", command
                    )
                children = list(content)
                if content.tag == f"{{{_MATH_NS}}}e":
                    if len(children) == 1:
                        return children[0]
                    box = _math_element("box")
                    box.append(content)
                    return box
                return content
            if command == "mathbf":
                content = self._group()
                math_namespace = (
                    "http://schemas.openxmlformats.org/officeDocument/2006/math"
                )
                for run in content.iter(f"{{{math_namespace}}}r"):
                    properties = run.find(f"{{{math_namespace}}}rPr")
                    if properties is None:
                        properties = _math_element("rPr")
                        run.insert(0, properties)
                    style = properties.find(f"{{{math_namespace}}}sty")
                    if style is None:
                        style = _math_element("sty")
                        properties.append(style)
                    style.set(
                        f"{{{math_namespace}}}val",
                        "b",
                    )
                return content
            if command == "text":
                content = self._group(preserve_whitespace=True)
                for run in content.iter(f"{{{_MATH_NS}}}r"):
                    run_properties = run.find(f"{{{_MATH_NS}}}rPr")
                    if run_properties is None:
                        run_properties = _math_element("rPr")
                        run.insert(0, run_properties)
                    run_properties.append(_math_element("nor"))
                return content
            if command == "mathrm":
                return self._group()
            if command in self.NARY_COMMANDS:
                nary = _math_element("nary")
                properties = _math_element("naryPr")
                symbol = _math_element("chr")
                symbol.set(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/math}val",
                    self.COMMANDS[command],
                )
                properties.append(symbol)
                limit_location = _math_element("limLoc")
                limit_location.set(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/math}val",
                    "undOvr",
                )
                properties.append(limit_location)
                properties.append(_math_ctrl_pr())
                nary.append(properties)
                return nary
            if command in self.FUNCTION_NAMES:
                run = _math_run(command)
                properties = _math_element("rPr")
                style = _math_element("sty")
                style.set(f"{{{_MATH_NS}}}val", "p")
                properties.append(style)
                run.insert(0, properties)
                return run
            if command in self.COMMANDS:
                return _math_run(self.COMMANDS[command])
            return _math_run(command)
        if token == "-":
            return _math_run("\u2212")
        return _math_run(token)

    def _sequence(self, closing=None, preserve_whitespace=False):
        if closing is None:
            closings = set()
        elif isinstance(closing, str):
            closings = {closing}
        else:
            closings = set(closing)
        nodes = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token in closings:
                break
            if token.isspace() and not preserve_whitespace:
                self.position += 1
                continue
            if token in {"^", "_"} and nodes:
                self.position += 1
                script = self._script_argument()
                base = nodes.pop()
                if base.tag.endswith("}nary"):
                    part = _math_element("sub" if token == "_" else "sup")
                    _append_script_content(part, script)
                    base.append(part)
                    nodes.append(base)
                    continue
                has_sub = base.tag.endswith(("}sSub", "}sSubSup"))
                has_sup = base.tag.endswith(("}sSup", "}sSubSup"))
                if has_sub or has_sup:
                    namespaces = {
                        "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"
                    }
                    old_expression = base.find("m:e", namespaces=namespaces)
                    old_sub = base.find("m:sub", namespaces=namespaces)
                    old_sup = base.find("m:sup", namespaces=namespaces)
                    needs_both_scripts = (
                        token == "^" and has_sub
                    ) or (
                        token == "_" and has_sup
                    )
                    if needs_both_scripts:
                        script_tag = "sSubSup"
                    else:
                        script_tag = "sSup" if token == "^" else "sSub"
                    script_node = _math_element(script_tag)
                    if script_node.tag.endswith("sSubSup"):
                        properties = _math_element("sSubSupPr")
                        properties.append(_math_ctrl_pr())
                        script_node.append(properties)
                    else:
                        properties = _math_element("sSupPr" if token == "^" else "sSubPr")
                        properties.append(_math_ctrl_pr())
                        script_node.append(properties)
                    script_node.append(old_expression)
                    sub = script if token == "_" else old_sub
                    sup = script if token == "^" else old_sup
                    if sub is not None:
                        part = _math_element("sub")
                        _append_script_content(part, sub)
                        script_node.append(part)
                    if sup is not None:
                        part = _math_element("sup")
                        _append_script_content(part, sup)
                        script_node.append(part)
                    base = script_node
                else:
                    script_node = _math_element("sSup" if token == "^" else "sSub")
                    properties = _math_element("sSupPr" if token == "^" else "sSubPr")
                    properties.append(_math_ctrl_pr())
                    script_node.append(properties)
                    expression = _math_element("e")
                    _append_script_content(expression, base)
                    script_node.append(expression)
                    part = _math_element("sup" if token == "^" else "sub")
                    _append_script_content(part, script)
                    script_node.append(part)
                    base = script_node
                nodes.append(base)
                continue
            nodes.append(self._atom())
        return nodes

    def parse(self):
        expression = _math_element("oMath")
        nodes = _merge_nary_bodies(self._sequence())
        for node in nodes:
            expression.append(node)
        return expression


def _add_math(paragraph, expression, display=False, alignment=None):
    math = _MathParser(expression).parse()
    _normalize_nary(math)
    if display:
        display_math = _math_element("oMathPara")
        if alignment is not None:
            properties = _math_element("oMathParaPr")
            justification = _math_element("jc")
            justification.set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/math}val",
                alignment,
            )
            properties.append(justification)
            display_math.append(properties)
        display_math.append(math)
        paragraph._p.append(display_math)
    else:
        paragraph._p.append(math)


def _add_pasted_text(document, paragraphs):
    for pasted_paragraph in paragraphs:
        paragraph = document.add_paragraph()
        for pasted_run in pasted_paragraph.runs:
            run = paragraph.add_run(pasted_run.text)
            formatting = pasted_run.format
            run.bold = formatting.bold
            run.italic = formatting.italic
            run.underline = formatting.underline
            if formatting.color:
                run.font.color.rgb = RGBColor.from_string(formatting.color)
            if formatting.font_name:
                run.font.name = formatting.font_name
            if formatting.font_size:
                run.font.size = Pt(formatting.font_size)
            if formatting.background:
                shading = OxmlElement("w:shd")
                shading.set(qn("w:val"), "clear")
                shading.set(qn("w:color"), "auto")
                shading.set(qn("w:fill"), formatting.background)
                run._r.get_or_add_rPr().append(shading)


def _numbered_section_heading(text):
    stripped = re.sub(r"^#{1,6}\s+", "", text.strip())
    match = re.fullmatch(
        r"(?:\*\*)?(\d+(?:\.\d+)*\.?)\s+(.+?)(?:\*\*)?",
        stripped,
    )
    if (
        match
        and "." not in match.group(1).rstrip(".")
        and not (stripped.startswith("**") and stripped.endswith("**"))
    ):
        return None
    return match


def _numbered_heading_level(section_heading):
    if section_heading is None:
        return None
    return max(3, len(section_heading.group(1).rstrip(".").split(".")) + 1)


def _heading_level(line):
    stripped = line.strip()
    heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
    if heading:
        numbered_heading = _numbered_section_heading(stripped)
        return _numbered_heading_level(numbered_heading) or len(
            heading.group(1)
        )
    return _numbered_heading_level(_numbered_section_heading(stripped))


def _next_content_is_subheading(lines, start_index, heading_level):
    for line in lines[start_index + 1 :]:
        stripped = line.strip()
        if (
            not stripped
            or re.match(r"^(---+|___+|\*\*\*+)\s*$", stripped)
            or re.fullmatch(
                r"</?(?:box|row|divider|grid-item|grid)\b[^>]*?/?>",
                stripped,
                re.IGNORECASE,
            )
        ):
            continue
        if stripped.startswith("```"):
            return False
        return _heading_level(line) == heading_level + 1
    return False


def _strip_redundant_table_symbol_parentheses(expression):
    match = re.fullmatch(
        r"\(\s*([A-Za-z]_\{?[A-Za-z0-9]+\}?)\s*\)",
        expression.strip(),
    )
    return match.group(1) if match else expression


def _table_math_description_parts(expression):
    value = expression.strip()
    formula = ""
    description = ""
    if value.startswith("("):
        depth = 0
        closing_index = None
        for index, character in enumerate(value):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    closing_index = index
                    break
        if closing_index is not None:
            formula = value[1:closing_index].strip()
            description = value[closing_index + 1 :].strip()
    if not description:
        suffix = re.search(
            r"\s*(?P<description>for\s*a\s*right\s*circular\s*cone)\s*$",
            value,
            re.IGNORECASE,
        )
        if suffix:
            formula = value[:suffix.start()].strip().strip("() ")
            description = suffix.group("description").strip()
    if not formula or not description or not re.search(
        r"\\[A-Za-z]+|[=^_*/+<>≤≥π]",
        formula,
    ):
        return None
    return formula, description


def _has_table_math_with_description(text):
    for match in re.finditer(
        r"\\\((.+?)\\\)|\$(.+?)\$",
        text,
    ):
        expression = match.group(1) or match.group(2)
        if _table_math_description_parts(expression):
            return True
    return False


def _has_table_math_with_surrounding_text(text):
    for match in re.finditer(r"\\\(.+?\\\)|\\\[.+?\\\]|\$.+?\$", text):
        if text[:match.start()].strip() or text[match.end():].strip():
            return True
    return False


def _add_table_math_with_description(paragraph, expression):
    parts = _table_math_description_parts(expression)
    if not parts:
        return False
    formula, description = parts
    formula = re.sub(r"\\ell\b", "l", formula)
    _add_math(paragraph, formula)
    if re.fullmatch(r"forarightcircularcone", description, re.IGNORECASE):
        description = "for a right circular cone"
    separator = (
        ""
        if paragraph.runs and paragraph.runs[-1].text.endswith((" ", "\t"))
        else " "
    )
    paragraph.add_run(f"{separator}{_clean_inline_text(description)}")
    return True


def _add_table_math_with_units(paragraph, expression):
    value = expression.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    match = re.fullmatch(
        r"Square\s*units\s*,?\s*such\s*as\s*"
        r"\(?\s*(?P<unit>[A-Za-z]+\s*(?:\^\s*\{?\d+\}?|\d+))\s*\)?",
        value,
        re.IGNORECASE,
    )
    if not match:
        return False
    unit = re.fullmatch(
        r"(?P<base>[A-Za-z]+)\s*(?:\^\s*\{?(?P<caret>\d+)\}?|(?P<compact>\d+))",
        match.group("unit"),
    )
    if not unit:
        return False
    exponent = unit.group("caret") or unit.group("compact")
    paragraph.add_run("Square units, such as ")
    _add_math(paragraph, f"{unit.group('base')}^{exponent}")
    return True


def _add_labeled_table_math(paragraph, expression, table_cell_label):
    if _add_table_math_with_description(paragraph, expression):
        return True
    if (
        table_cell_label is not None
        and table_cell_label.strip().casefold() == "measurement units"
    ):
        return _add_table_math_with_units(paragraph, expression)
    return False


def _add_inline_runs(
    paragraph,
    text,
    table_math=False,
    table_cell_label=None,
    bold=False,
    italic=False,
):
    text = text.strip()
    inline_table_math = (
        table_math
        and (
            _has_table_math_with_description(text)
            or _has_table_math_with_surrounding_text(text)
            or (
                table_cell_label is not None
                and table_cell_label.strip().casefold()
                in {"lateral area", "measurement units"}
            )
        )
    )
    token_pattern = re.compile(
        r"(\\\(.+?\\\)|\\\[.+?\\\]|\$.+?\$|\(\\[A-Za-z]+[^()]*\)|"
        r"\*\*.+?\*\*|__.+?__|"
        r"(?<!\*)\*[^*]+\*(?!\*)|(?<!_)_[^_]+_(?!_)|`[^`]+`)"
    )
    position = 0
    for match in token_pattern.finditer(text):
        if match.start() > position:
            run = paragraph.add_run(_clean_inline_text(text[position:match.start()]))
            run.bold = bold
            run.italic = italic
        token = match.group()
        if token.startswith((r"\(", r"\[")):
            expression = token[2:-2]
            if table_math:
                expression = _strip_redundant_table_symbol_parentheses(
                    expression
                )
            if not _add_labeled_table_math(
                paragraph,
                expression,
                table_cell_label,
            ):
                if table_math and inline_table_math:
                    expression = re.sub(r"\\ell\b", "l", expression)
                _add_math(
                    paragraph,
                    expression,
                    display=table_math and not inline_table_math,
                    alignment=(
                        "left" if table_math and not inline_table_math else None
                    ),
                )
        elif token.startswith("(\\") and token.endswith(")"):
            for piece in ("(", None, ")"):
                if piece is None:
                    _add_math(paragraph, token[1:-1])
                else:
                    run = paragraph.add_run(piece)
                    run.bold = bold
                    run.italic = italic
        elif token.startswith("$"):
            expression = token[1:-1]
            if table_math:
                expression = _strip_redundant_table_symbol_parentheses(
                    expression
                )
            if not _add_labeled_table_math(
                paragraph,
                expression,
                table_cell_label,
            ):
                if table_math and inline_table_math:
                    expression = re.sub(r"\\ell\b", "l", expression)
                _add_math(
                    paragraph,
                    expression,
                    display=table_math and not inline_table_math,
                    alignment=(
                        "left" if table_math and not inline_table_math else None
                    ),
                )
        elif token.startswith(("**", "__")):
            _add_inline_runs(
                paragraph,
                token[2:-2],
                table_math=table_math,
                table_cell_label=table_cell_label,
                bold=True,
                italic=italic,
            )
        elif token.startswith(("`",)):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.bold = bold
            run.italic = italic
        else:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
            run.bold = bold
        position = match.end()
    if position < len(text):
        run = paragraph.add_run(_clean_inline_text(text[position:]))
        run.bold = bold
        run.italic = italic
    while paragraph.runs and paragraph._p[-1] is paragraph.runs[-1]._r:
        run = paragraph.runs[-1]
        trimmed = run.text.rstrip()
        if trimmed == run.text:
            break
        if trimmed:
            run.text = trimmed
            break
        run._r.getparent().remove(run._r)


def _is_bare_math_table_cell(text):
    value = text.strip()
    if not value:
        return False
    if re.search(r"(?:\*\*.+?\*\*|__.+__)", value):
        return False
    if re.fullmatch(r"(?:\\\(.+?\\\)|\\\[.+?\\\]|\$.+?\$)", value):
        return False
    if re.fullmatch(r"(?:[A-Za-z](?:_\{?[A-Za-z0-9]+\}?)?|\d+[A-Za-z])", value):
        return True
    has_latex_syntax = re.search(
        r"\\[A-Za-z]+|[_^{}=+*/<>≤≥]|\s-\s",
        value,
    )
    return bool(
        has_latex_syntax
        and re.fullmatch(
            r"[A-Za-z0-9\s\\{}_^.,=+\-*/()|<>≤≥πρ]+",
            value,
        )
    )


def _default_table_font(size):
    if ImageFont is None:
        return None
    candidate_paths = (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
        r"C:\Windows\Fonts\verdana.ttf",
    )
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def _render_table_png(rows):
    if not rows or Image is None or ImageDraw is None or ImageFont is None:
        return b""
    max_columns = max(len(row) for row in rows)
    normalized_rows = [
        list(row) + [""] * (max_columns - len(row)) for row in rows
    ]
    padding_x = 12
    padding_y = 10
    row_height = 28
    col_widths = [max(80, 0) for _ in range(max_columns)]
    for row_index, row in enumerate(normalized_rows):
        for column_index, value in enumerate(row):
            text = str(value).strip() if value is not None else ""
            if not text:
                text = ""
            font = _default_table_font(12)
            bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(
                (0, 0), text, font=font
            )
            width = max(80, bbox[2] - bbox[0] + padding_x * 2)
            if row_index == 0:
                width = max(width, 110)
            col_widths[column_index] = max(col_widths[column_index], width)

    image_width = sum(col_widths) + 6
    image_height = row_height * len(normalized_rows) + 6
    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)
    border_color = (30, 30, 30)
    header_fill = (238, 238, 238)
    text_color = (0, 0, 0)
    font = _default_table_font(12)

    x_cursor = 3
    y_cursor = 3
    for row_index, row in enumerate(normalized_rows):
        fill_color = header_fill if row_index == 0 else "white"
        current_x = x_cursor
        for column_index, value in enumerate(row):
            cell_width = col_widths[column_index]
            cell_rect = [current_x, y_cursor, current_x + cell_width, y_cursor + row_height]
            draw.rectangle(cell_rect, fill=fill_color, outline=border_color)
            text = str(value).strip() if value is not None else ""
            if text:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                text_x = current_x + padding_x
                text_y = y_cursor + (row_height - text_height) // 2
                draw.text((text_x, text_y), text, font=font, fill=text_color)
            current_x += cell_width
        y_cursor += row_height

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fenced_code_blocks(text):
    """Lines of every ``` fenced block in the reply, in order."""
    blocks = []
    current = []
    inside = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if inside:
                blocks.append(current)
                current = []
            inside = not inside
            continue
        if inside:
            current.append(line)
    if inside:
        blocks.append(current)
    return blocks


def _text_without_code_blocks(text):
    kept = []
    inside = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)


def _count_markdown_tables(text):
    """Count tables the same way the document builder will turn them into tables.

    (The old regex let whitespace match across newlines, so a table followed
    by a blank line and a "---" rule was counted twice.)
    """
    lines = _text_without_code_blocks(text).splitlines()
    count = 0
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("|") and index + 1 < len(lines):
            separator = lines[index + 1].strip()
            if re.match(r"^\|?[\s:|-]+\|?$", separator) and "-" in separator:
                body_rows = 0
                while index < len(lines) and lines[index].strip().startswith("|"):
                    first_cell = lines[index].strip().strip("|").split("|")[0]
                    if not re.match(r"^\s*:?-+:?\s*$", first_cell):
                        body_rows += 1
                    index += 1
                if body_rows > 1:
                    count += 1
                continue
        index += 1
    return count


def _code_block_label(info):
    info = (info or "").strip().split()[0].lower() if (info or "").strip() else ""
    if info in {"", "text", "plaintext", "plain", "txt"}:
        return "Plain text"
    names = {"js": "JavaScript", "javascript": "JavaScript", "py": "Python",
             "python": "Python", "json": "JSON", "html": "HTML", "css": "CSS",
             "bash": "Bash", "sh": "Shell", "sql": "SQL", "yaml": "YAML",
             "xml": "XML", "latex": "LaTeX", "ts": "TypeScript"}
    return names.get(info, info.capitalize())


def _first_font(paths, size):
    if ImageFont is None:
        return None
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_code_block_png(lines, label="Plain text"):
    """Draw a ChatGPT-style code block: gray rounded box, header, mono text."""
    if Image is None or ImageDraw is None or ImageFont is None:
        return b""
    mono_paths = (
        r"C:\Windows\Fonts\consola.ttf",
        "consola.ttf",
        "DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "LiberationMono-Regular.ttf",
    )
    bold_paths = (
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    scale = 2  # draw at 2x, then downsample for smooth edges
    mono = _first_font(mono_paths, 24)
    try:  # size the font so one character is ~6.4 px wide (ChatGPT's look)
        em_width = mono.getlength("M") / 24
        mono = _first_font(mono_paths, max(8.0, 6.4 * scale / em_width))
    except Exception:
        pass
    header_font = _first_font(bold_paths, 15 * scale)
    lines = [line.replace("\t", "    ").rstrip() for line in lines] or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text_width = max(
        (probe.textlength(line, font=mono) for line in lines), default=0
    )
    width = int(max(746 * scale, text_width + 40 * scale))
    line_height = int(19.3 * scale)
    header_height = 46 * scale
    height = header_height + line_height * len(lines) + 24 * scale
    background = (231, 231, 231)
    ink = (13, 13, 13)

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=22 * scale, fill=background
    )
    # header: "</>" icon + label
    draw.text((20 * scale, 22 * scale), "</>", font=mono, fill=ink, anchor="lm")
    draw.text((45 * scale, 23 * scale), label, font=header_font, fill=ink, anchor="lm")
    # right icons: wrap-text arrow and copy
    w = 2 * scale
    x = width - 62 * scale
    y = 23 * scale
    draw.line((x - 8 * scale, y, x + 6 * scale, y), fill=ink, width=w)
    draw.line((x + 6 * scale, y, x + 6 * scale, y - 5 * scale), fill=ink, width=w)
    draw.line((x - 8 * scale, y, x - 4 * scale, y - 4 * scale), fill=ink, width=w)
    draw.line((x - 8 * scale, y, x - 4 * scale, y + 4 * scale), fill=ink, width=w)
    draw.line((x + 12 * scale, y - 8 * scale, x + 12 * scale, y + 8 * scale), fill=ink, width=w)
    cx = width - 24 * scale
    draw.rounded_rectangle(
        (cx - 4 * scale, y - 9 * scale, cx + 9 * scale, y + 6 * scale),
        radius=3 * scale, outline=ink, width=w,
    )
    draw.rounded_rectangle(
        (cx - 9 * scale, y - 4 * scale, cx + 4 * scale, y + 10 * scale),
        radius=3 * scale, outline=ink, fill=background, width=w,
    )
    # code text
    top = header_height + 4 * scale
    for number, line in enumerate(lines):
        draw.text((19 * scale, top + number * line_height), line, font=mono, fill=ink)

    image = image.resize((width // scale, height // scale), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_clean_code_block_png(lines):
    """Light-gray rounded code box with a small copy icon (no header label)."""
    if Image is None or ImageDraw is None or ImageFont is None:
        return b""
    mono_paths = (
        r"C:\Windows\Fonts\consola.ttf",
        "consola.ttf",
        "DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "LiberationMono-Regular.ttf",
    )
    scale = 3  # draw at 3x, then downsample for smooth edges
    char_width = 7.7  # Consolas 14 px
    mono = _first_font(mono_paths, 24)
    try:
        em_width = mono.getlength("M") / 24
        mono = _first_font(mono_paths, max(8.0, char_width * scale / em_width))
    except Exception:
        pass
    lines = [line.replace("\t", "    ").rstrip() for line in lines] or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text_width = max((probe.textlength(line, font=mono) for line in lines), default=0)
    width = int(max(766 * scale, text_width + 80 * scale))
    line_height = 20 * scale
    height = 12 * scale * 2 + line_height * len(lines)
    background = (243, 243, 243)
    ink = (13, 13, 13)

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=12 * scale, fill=background
    )
    for number, line in enumerate(lines):
        baseline = 12 * scale + number * line_height + 14 * scale
        draw.text((20 * scale, baseline), line, font=mono, fill=ink, anchor="ls")

    # copy icon: two overlapping rounded squares, top-right
    w = int(1.5 * scale)
    right = width - 17 * scale
    back = (right - 12 * scale, 12 * scale, right, 24 * scale)
    front = (right - 17 * scale, 16 * scale, right - 5 * scale, 28 * scale)
    draw.rounded_rectangle(back, radius=3 * scale, outline=ink, width=w)
    draw.rounded_rectangle(front, radius=3 * scale, outline=ink, fill=background, width=w)

    image = image.resize((width // scale, height // scale), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _add_code_screenshot(document, png_data):
    if not png_data:
        return False
    width = Inches(6)
    if Image is not None:
        try:
            pixel_width = Image.open(io.BytesIO(png_data)).size[0]
            # same scale as the table screenshots (774 px -> 6 in)
            width = Inches(min(6.0, pixel_width * 6.0 / 774))
        except Exception:
            width = Inches(6)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.add_run().add_picture(io.BytesIO(png_data), width=width)
    return True


def _add_table_screenshot(document, rows, screenshot_data=None):
    try:
        png_data = screenshot_data or _render_table_png(rows)
        if png_data and Image is not None:
            image = Image.open(io.BytesIO(png_data)).convert("RGBA")
            width, height = image.size
            padding_left = 3
            padding_right = 3
            padded = Image.new("RGBA", (width + padding_left + padding_right, height), (255, 255, 255, 255))
            padded.paste(image, (padding_left, 0), image)
            buffer = io.BytesIO()
            padded.save(buffer, format="PNG")
            png_data = buffer.getvalue()
    except Exception:
        return False
    if not png_data:
        return False
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run()
    run.add_picture(io.BytesIO(png_data), width=Inches(6))
    return True


# ChatGPT puts the "Plain text" header bar (language label + copy buttons)
# OUTSIDE the <pre>, so climb to the wrapper that holds header + code and mark
# it so the overlay-hiding script leaves it alone.
_CODE_BLOCK_WRAPPER_JS = """
const pre = arguments[0];
const stop = 'p, h1, h2, h3, h4, h5, h6, li, ul, ol, table, blockquote';
let node = pre;
for (let i = 0; i < 6; i++) {
  const parent = node.parentElement;
  if (!parent || parent.matches('[data-message-author-role], .markdown, main, article, body')) break;
  if (parent.querySelectorAll('pre').length > 1) break;
  let foreign = false;
  for (const other of parent.querySelectorAll(stop)) {
    if (!pre.contains(other)) { foreign = true; break; }
  }
  if (foreign) break;
  node = parent;
}
node.setAttribute('data-capture-keep', '1');
return node;
"""


class _TableShot:
    """A table screenshot plus a text signature of the table it came from."""

    __slots__ = ("png", "signature")

    def __init__(self, png, signature=""):
        self.png = png
        self.signature = signature

    def __bool__(self):
        return bool(self.png)


def _table_signature(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _dom_table_signature(driver, table):
    """First-column text of every row of a table on the ChatGPT page."""
    try:
        text = driver.execute_script(
            "return Array.from(arguments[0].querySelectorAll('tr, [role=row]'))"
            ".map(r => r.children.length ? r.children[0].innerText.trim() : '')"
            ".join(' ');",
            table,
        )
    except Exception:
        text = ""
    return _table_signature(text)


def _rows_signature(rows):
    return _table_signature(" ".join(row[0] for row in rows if row))


def _take_table_screenshot(shots, rows):
    """Pick (and remove) the captured screenshot that belongs to this table.

    Tables are matched by their first-column text instead of by position, so a
    table that could not be captured no longer shifts every later screenshot
    or throws all of them away.
    """
    if not shots:
        return None
    if any(not hasattr(shot, "signature") for shot in shots):
        shot = shots.pop(0)  # plain bytes: old positional behaviour
        return getattr(shot, "png", shot)
    import difflib

    wanted = _rows_signature(rows)
    best_index, best_ratio = None, 0.0
    for index, shot in enumerate(shots):
        if not shot.png or not shot.signature or not wanted:
            continue
        ratio = difflib.SequenceMatcher(None, wanted, shot.signature).ratio()
        if ratio > best_ratio:
            best_index, best_ratio = index, ratio
    if best_index is None or best_ratio < 0.92:
        return None
    return shots.pop(best_index).png


_REPLY_CONTAINER_JS = """
const sels = [
  '[data-message-author-role="assistant"]',
  '[data-turn="assistant"]',
  'article[data-testid^="conversation-turn"]',
  '[data-testid^="conversation-turn"]',
  '.markdown',
  '.prose',
  'main'
];
const want = arguments[0];
for (const sel of sels) {
  const els = Array.from(document.querySelectorAll(sel));
  for (let i = els.length - 1; i >= 0; i--) {
    if (els[i].querySelector(want)) return els[i];
  }
}
return document.body;
"""


def _dump_capture_debug(driver, note):
    """Save what Chrome saw, so a failed capture can be diagnosed."""
    try:
        import tempfile

        folder = Path(tempfile.gettempdir()) / "chatgpt_to_word_debug"
        folder.mkdir(parents=True, exist_ok=True)
        info = driver.execute_script(
            "return {title: document.title, url: location.href,"
            " tables: document.querySelectorAll('table,[role=table]').length,"
            " pre: document.querySelectorAll('pre').length,"
            " assistant: document.querySelectorAll('[data-message-author-role=assistant]').length,"
            " text: (document.body.innerText||'').slice(0, 1500)};"
        )
        (folder / "capture_debug.txt").write_text(
            f"{note}\n\n{json.dumps(info, indent=2)}", encoding="utf-8"
        )
        (folder / "capture_debug.html").write_text(
            driver.page_source, encoding="utf-8", errors="replace"
        )
        driver.save_screenshot(str(folder / "capture_debug.png"))
        print(f"[capture] debug files saved to {folder}")
    except Exception as exc:
        print(f"[capture] could not save debug files: {exc}")


def _capture_chatgpt_screenshots(
    url,
    want_tables=True,
    want_code=False,
    cancel_event=None,
    attempts=3,
    expected_tables=None,
):
    """One browser session: returns (table_screenshots, code_screenshots)."""
    best = ([], [])
    best_score = -1
    if webdriver is None or Options is None or By is None or WebDriverWait is None:
        return [], []

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Conversion cancelled.")

    selector = ", ".join(
        part
        for part, wanted in (
            ("table, [role='table']", want_tables),
            ("pre", want_code),
        )
        if wanted
    )
    if not selector:
        return [], []

    for _attempt in range(attempts):
        check_cancel()
        driver = _start_chrome_driver()
        try:
            driver.get(url)
            ready = _wait_for_page_content(
                driver,
                cancel_event=cancel_event,
                content_selector=selector,
            )
            last_message = None
            try:
                last_message = driver.execute_script(_REPLY_CONTAINER_JS, selector)
            except Exception:
                last_message = None
            if last_message is None:
                assistant_messages = driver.find_elements(
                    By.CSS_SELECTOR,
                    '[data-message-author-role="assistant"]',
                )
                last_message = assistant_messages[-1] if assistant_messages else None
            tables = (
                last_message.find_elements(By.CSS_SELECTOR, "table, [role='table']")
                if last_message is not None and want_tables
                else []
            )
            code_blocks = (
                last_message.find_elements(By.CSS_SELECTOR, "pre")
                if last_message is not None and want_code
                else []
            )
            if (
                not ready
                or (want_tables and not tables)
                or (want_code and not code_blocks)
            ):
                _dump_capture_debug(
                    driver,
                    f"attempt {_attempt + 1}: ready={ready}, "
                    f"tables={len(tables)}, code_blocks={len(code_blocks)}",
                )
                continue  # page did not hydrate: retry with a fresh browser

            table_screenshots = []
            for table in tables:
                check_cancel()
                signature = _dom_table_signature(driver, table)
                try:
                    size = table.size
                    if size["width"] < 50 or size["height"] < 30:
                        continue
                    table_screenshots.append(
                        _TableShot(_element_to_png_bytes(driver, table), signature)
                    )
                except RuntimeError:
                    raise
                except Exception:
                    table_screenshots.append(_TableShot(None, signature))

            code_screenshots = []
            code_targets = []
            for block in code_blocks:
                try:
                    code_targets.append(
                        driver.execute_script(_CODE_BLOCK_WRAPPER_JS, block) or block
                    )
                except Exception:
                    code_targets.append(block)
            for target in code_targets:
                check_cancel()
                try:
                    size = target.size
                    if size["width"] < 50 or size["height"] < 15:
                        code_screenshots.append(None)  # keep order aligned
                        continue
                    code_screenshots.append(_element_to_png_bytes(driver, target))
                except RuntimeError:
                    raise
                except Exception:
                    code_screenshots.append(None)

            if want_tables and tables and not any(table_screenshots):
                _dump_capture_debug(
                    driver,
                    f"attempt {_attempt + 1}: found {len(tables)} table element(s) "
                    "but every screenshot came back blank or failed",
                )
            if any(table_screenshots) or any(code_screenshots):
                score = sum(1 for shot in table_screenshots if shot)
                if score > best_score:
                    best, best_score = (table_screenshots, code_screenshots), score
                if not expected_tables or score >= expected_tables:
                    return table_screenshots, code_screenshots
                # fewer tables than the reply text has: the page may not have
                # finished rendering, so try again with a fresh browser
        finally:
            _stop_chrome_driver(driver)
    return best


def _capture_chatgpt_table_screenshots(url, max_tables=None, cancel_event=None, attempts=3):
    tables, _code = _capture_chatgpt_screenshots(
        url,
        want_tables=True,
        want_code=False,
        cancel_event=cancel_event,
        attempts=attempts,
    )
    return tables[:max_tables] if max_tables is not None else tables


def _new_list_number_id(document, style_name="List Number"):
    """Create a fresh numbering instance (restarting at 1) for the style's list."""
    numbering = document.part.numbering_part.numbering_definitions._numbering
    style_num_id = document.styles[style_name].element.pPr.numPr.numId.val
    abstract_id = numbering.num_having_numId(style_num_id).abstractNumId.val
    new_num = numbering.add_num(abstract_id)
    new_num.add_lvlOverride(ilvl=0).add_startOverride(1)
    return new_num.numId


def _apply_list_number_id(paragraph, num_id):
    num_pr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    num_pr.get_or_add_ilvl().val = 0
    num_pr.get_or_add_numId().val = num_id


def _add_response_text(
    document,
    text,
    images=(),
    heading_content=(),
    table_screenshots=(),
    code_screenshots=(),
):
    text = _replace_entity_tags(text)
    text = _normalize_widget_text(text)
    table_screenshots = list(table_screenshots)
    code_screenshots = list(code_screenshots)
    had_table_screenshots = any(table_screenshots)
    images_by_placeholder = {}
    for image in images:
        images_by_placeholder.setdefault(image.placeholder, []).append(image)
    in_code_block = False
    main_heading_seen = False
    main_heading_image_window = False
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^If you want, I can:\s*$", line.strip(), re.IGNORECASE):
            suggestions = [
                candidate.strip()
                for candidate in lines[index + 1 :]
                if candidate.strip()
            ]
            if suggestions and all(
                re.match(r"^(?:[-*+]|[·•▪●○‣◦])\s+", suggestion)
                for suggestion in suggestions
            ):
                lines = lines[:index]
                break

    has_classification_path = any(
        re.match(
            r"^#{1,3}\s+Recommended Classification Path\s*$",
            line.strip(),
            re.IGNORECASE,
        )
        for line in lines
    )
    list_num_id = None  # current numbered-list instance; reset at every heading
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                # Opening fence: screenshot of the plain-text block, if we have one.
                block_end = index + 1
                while block_end < len(lines) and not lines[block_end].strip().startswith("```"):
                    block_end += 1
                code_screenshot = code_screenshots.pop(0) if code_screenshots else None
                if (
                    not code_screenshot
                    and SCREENSHOT_CODE_BLOCKS
                    and FALLBACK_RENDER_CODE_BLOCKS
                ):
                    if CODE_BLOCK_IMAGE_STYLE == "clean":
                        code_screenshot = _render_clean_code_block_png(
                            lines[index + 1 : block_end]
                        )
                    else:
                        code_screenshot = _render_code_block_png(
                            lines[index + 1 : block_end],
                            _code_block_label(stripped[3:]),
                        )
                if code_screenshot and _add_code_screenshot(document, code_screenshot):
                    if not KEEP_CODE_TEXT_AFTER_SCREENSHOT:
                        index = block_end + 1
                        continue
            in_code_block = not in_code_block
            index += 1
            continue
        placeholder_images = images_by_placeholder.get(stripped)
        if placeholder_images:
            paragraph = (
                document.paragraphs[-1]
                if main_heading_image_window
                and document.paragraphs
                and re.match(
                    r"^#?\s*Source:\s*AI Source:",
                    document.paragraphs[-1].text.strip(),
                    re.IGNORECASE,
                )
                else document.add_paragraph()
            )
            for image in placeholder_images:
                paragraph.add_run().add_picture(
                    io.BytesIO(image.data),
                    width=Inches(6),
                )
            index += 1
            continue
        if re.fullmatch(r"<AsyncImage(?:Group)?\b[^>]*?/?>", stripped):
            index += 1
            continue
        if not stripped:
            index += 1
            continue
        if re.fullmatch(
            r"(?:</?(?:box|row|divider|grid-item|grid)\b[^>]*?/?>\s*)+",
            stripped,
            re.IGNORECASE,
        ):
            index += 1
            continue
        if in_code_block:
            paragraph = document.add_paragraph()
            run = paragraph.add_run(line)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            index += 1
            continue

        source_metadata_line = re.match(
            r"^#?\s*Source:\s*AI Source:",
            stripped,
            re.IGNORECASE,
        )
        if main_heading_image_window and not source_metadata_line:
            main_heading_image_window = False

        widget = _WIDGET_TEXT_RE.fullmatch(stripped)
        if widget:
            _add_widget_text(
                document,
                widget.group(1),
                widget.group(2),
                widget.group(3),
            )
            index += 1
            continue
        if re.match(r"^(---+|___+|\*\*\*+)\s*$", stripped):
            index += 1
            continue
        if re.fullmatch(r"<[A-Z][A-Za-z0-9]*(?:\s[^<>]*)?/>", stripped):
            # interactive ChatGPT component (e.g. <LearningViz .../>): it has
            # no Word equivalent, so it must not leak into the document as text
            index += 1
            continue
        if stripped in {r"\[", "$$"}:
            closing = r"\]" if stripped == r"\[" else "$$"
            equation_lines = []
            index += 1
            while index < len(lines) and lines[index].strip() != closing:
                equation_lines.append(lines[index].strip())
                index += 1
            if index < len(lines):
                index += 1
            equation = " ".join(equation_lines)
            paragraph = document.add_paragraph()
            if equation:
                _add_math(paragraph, equation, display=True)
            continue

        if stripped.startswith("|") and index + 1 < len(lines):
            separator = lines[index + 1].strip()
            if re.match(r"^\|?[\s:|-]+\|?$", separator) and "-" in separator:
                rows = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    cells = [
                        cell.strip()
                        for cell in lines[index].strip().strip("|").split("|")
                    ]
                    first_cell = lines[index].strip().strip("|").split("|")[0]
                    if not re.match(r"^\s*:?-+:?\s*$", first_cell):
                        rows.append(cells)
                    index += 1
                if len(rows) > 1:
                    screenshot_data = _take_table_screenshot(table_screenshots, rows)
                    if screenshot_data:
                        _add_table_screenshot(document, rows, screenshot_data)
                    elif had_table_screenshots:
                        # this table was not captured from the page: draw it
                        # from the text so every table still gets its image
                        _add_table_screenshot(document, rows, None)
                    table = document.add_table(
                        rows=len(rows),
                        cols=max(len(row) for row in rows),
                    )
                    table.style = "Normal Table"
                    table.alignment = WD_TABLE_ALIGNMENT.LEFT
                    if len(table.columns) == 4:
                        column_widths = (0.85, 2.31, 0.64, 0.75)
                        table.autofit = False
                        for column, width in zip(table.columns, column_widths):
                            column.width = Inches(width)
                        for row in table.rows:
                            for cell, width in zip(row.cells, column_widths):
                                cell.width = Inches(width)
                    for row_index, cells in enumerate(rows):
                        for column_index, value in enumerate(cells):
                            if row_index == 1 and re.match(r"^\s*:?-+:?\s*$", value):
                                continue
                            value = re.sub(
                                r"^\*\*Basediameter\*\*\(\(([A-Za-z])\)\)$",
                                r"**Base diameter** (\\(\1\\))",
                                value,
                            )
                            cell = table.cell(row_index, column_index)
                            paragraph = cell.paragraphs[0]
                            table_cell_label = cells[0] if cells else None
                            inline_math_cell = (
                                table_cell_label is not None
                                and table_cell_label.strip().casefold()
                                in {"lateral area", "measurement units"}
                            )
                            if (
                                row_index > 0
                                and _is_bare_math_table_cell(value)
                                and not inline_math_cell
                                and not _has_table_math_with_description(value)
                                and not _has_table_math_with_surrounding_text(
                                    value
                                )
                            ):
                                value = (
                                    _strip_redundant_table_symbol_parentheses(
                                        value
                                    )
                                )
                                _add_math(
                                    paragraph,
                                    value,
                                    display=True,
                                    alignment="left",
                                )
                            else:
                                _add_inline_runs(
                                    paragraph,
                                    value,
                                    table_math=True,
                                    table_cell_label=table_cell_label,
                                )
                            if row_index == 0:
                                for run in paragraph.runs:
                                    run.bold = True
                    for row in table.rows:
                        for cell in row.cells:
                            for paragraph in cell.paragraphs:
                                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    table.alignment = WD_TABLE_ALIGNMENT.LEFT
                    continue
                continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        numbered_section_heading = _numbered_section_heading(stripped)
        bullet = re.match(r"^(?:[-*+]|[·•▪●○‣◦])\s+(.+)$", stripped)
        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
        if heading:
            list_num_id = None  # next numbered list restarts at 1
            if len(heading.group(1)) == 1 and not main_heading_seen:
                main_heading_seen = True
                main_heading_image_window = True
            heading_level = (
                _numbered_heading_level(numbered_section_heading)
                or len(heading.group(1))
            )
            paragraph = document.add_heading(level=heading_level)
            if numbered_section_heading:
                heading_text = numbered_section_heading.group(2)
            else:
                heading_text = re.sub(
                    r"^\d+(?:\.\d+)*[.)]?\s+",
                    "",
                    heading.group(2),
                )
            if len(heading.group(1)) == 1 and has_classification_path:
                title_parts = re.split(r"\s+—\s+", heading_text)
                if len(title_parts) >= 3:
                    heading_text = title_parts[-1]
            _add_inline_runs(
                paragraph,
                heading_text,
            )
            if not _next_content_is_subheading(
                lines,
                index,
                heading_level,
            ):
                _add_pasted_text(document, heading_content)
        elif numbered_section_heading:
            list_num_id = None  # next numbered list restarts at 1
            heading_level = _numbered_heading_level(
                numbered_section_heading
            )
            paragraph = document.add_heading(level=heading_level)
            _add_inline_runs(paragraph, numbered_section_heading.group(2))
            if not _next_content_is_subheading(
                lines,
                index,
                heading_level,
            ):
                _add_pasted_text(document, heading_content)
        elif bullet:
            paragraph = document.add_paragraph(style="List Bullet")
            _add_inline_runs(paragraph, bullet.group(1))
        elif numbered:
            # restart under a new heading, or whenever the list itself says "1."
            if list_num_id is None or int(numbered.group(1)) == 1:
                list_num_id = _new_list_number_id(document)
            paragraph = document.add_paragraph(style="List Number")
            _apply_list_number_id(paragraph, list_num_id)
            _add_inline_runs(paragraph, numbered.group(2))
        else:
            if stripped.startswith(r"\]") or stripped == "$$":
                index += 1
                continue
            inline_display = re.fullmatch(r"\\\[(.+?)\\\]", stripped)
            paragraph = document.add_paragraph()
            if inline_display:
                _add_math(paragraph, inline_display.group(1), display=True)
            else:
                _add_inline_runs(paragraph, line)
        index += 1


def _apply_document_format(document):
    for section in document.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    normal = document.styles["Normal"]
    normal.font.name = "Roboto Mono"
    normal.font.size = Pt(12)

    heading_styles = (
        ("Heading 1", 20, 18),
        ("Heading 2", 16, 8),
        ("Heading 3", 14, 8),
        ("Heading 4", 13, 6),
        ("Heading 5", 12, 4),
        ("Heading 6", 11, 4),
    )
    for name, size, space_before in heading_styles:
        style = document.styles[name]
        style.font.name = "Roboto Mono"
        style.font.size = Pt(size)
        style.font.bold = False
        style.font.color.rgb = RGBColor(0x2F, 0x54, 0x96)
        style.paragraph_format.space_before = Pt(space_before)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True


def _build_chrome_options():
    if Options is None:
        return None
    chrome_options = Options()
    chrome_options.page_load_strategy = "eager"
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1600,1200")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-features=UseSkiaRenderer")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument(f"--user-agent={USER_AGENT}")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option(
        "excludeSwitches", ["enable-logging", "enable-automation"]
    )
    return chrome_options


_HIDE_OVERLAYS_JS = """
const target = arguments[0];
const keepScope = !!arguments[1];
let scope = null;
if (target && keepScope) {
  scope = target;
  for (let i = 0; i < 3 && scope.parentElement
       && scope.parentElement !== document.body; i++) scope = scope.parentElement;
}
for (const el of document.querySelectorAll('body *')) {
  const pos = getComputedStyle(el).position;
  if ((pos === 'fixed' || pos === 'sticky')
      && !el.closest('table, pre, [data-capture-keep]')
      && !el.querySelector('table, pre, [data-capture-keep]')
      && !(scope && scope.contains(el))) {
    el.style.setProperty('visibility', 'hidden', 'important');
    el.setAttribute('data-capture-hidden', '1');
  }
}
"""


_RESTORE_HIDDEN_JS = """
for (const el of document.querySelectorAll('[data-capture-hidden]')) {
  el.style.removeProperty('visibility');
  el.removeAttribute('data-capture-hidden');
}
"""


_HIDE_COVERING_JS = """
const target = arguments[0];
const keepScope = !!arguments[1];
let scope = null;
if (keepScope) {
  scope = target;
  for (let i = 0; i < 3 && scope.parentElement
       && scope.parentElement !== document.body; i++) scope = scope.parentElement;
}
const r = target.getBoundingClientRect();
let count = 0;
for (const fy of [0.02, 0.15, 0.3, 0.5, 0.7, 0.85, 0.98]) {
  for (const fx of [0.05, 0.25, 0.5, 0.75, 0.95]) {
    const x = r.left + r.width * fx;
    const y = r.top + r.height * fy;
    if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) continue;
    for (const el of document.elementsFromPoint(x, y)) {
      if (el === target || target.contains(el)) break;
      if (el.contains(target)) continue;
      if (el === document.documentElement || el === document.body) continue;
      if (scope && scope.contains(el)) continue;
      el.style.setProperty('visibility', 'hidden', 'important');
      el.setAttribute('data-capture-hidden', '1');
      count++;
    }
  }
}
return count;
"""


_ROWS_JS = """
const t = arguments[0];
const t0 = t.getBoundingClientRect();
return Array.from(t.querySelectorAll('tr, [role=row]')).map(tr => {
  const r = tr.getBoundingClientRect();
  return {top: Math.round(r.top - t0.top), height: Math.round(r.height),
          text: (tr.innerText || '').trim().length};
});
"""


def _first_row_is_blank(driver, element, png):
    """True when ANY row that has text is empty in the screenshot.

    (Name kept for compatibility.) A covering overlay can hide the header row
    and the first data row, so every row is checked, not only the first.
    """
    if Image is None:
        return False
    try:
        image = Image.open(io.BytesIO(png)).convert("L")
        for info in driver.execute_script(_ROWS_JS, element) or []:
            if not info.get("text") or info["height"] < 8:
                continue
            top = max(0, info["top"])
            if top >= image.height:
                continue
            band = image.crop(
                (0, top, image.width, min(image.height, top + info["height"]))
            )
            low, high = band.getextrema()
            if (high - low) < 8:
                return True
        return False
    except Exception:
        return False


def _png_is_blank(png_bytes):
    if Image is None:
        return False
    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    low, high = image.getextrema()
    return (high - low) < 8


_RECT_JS = """
const r = arguments[0].getBoundingClientRect();
return {x: r.left + window.scrollX, y: r.top + window.scrollY,
        width: r.width, height: r.height, vtop: r.top};
"""


_WAIT_ASSETS_JS = """
document.documentElement.style.setProperty('scroll-behavior', 'auto', 'important');
document.body.style.setProperty('scroll-behavior', 'auto', 'important');
const target = arguments[0];
const imgs = Array.from(document.images).filter(i => {
  if (i.complete) return false;
  if (target.contains(i)) return true;
  // Later images cannot shift or affect this capture target.
  return !(target.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING);
});
return imgs.length;
"""


def _wait_for_stable_layout(driver, element, timeout=6.0):
    """Wait for images before or inside the target and its layout to stabilize.

    A photo above the table that finishes loading after the capture area was
    measured shifts the table, so the screenshot shows part of the photo and
    cuts off the last row.
    """
    deadline = time.time() + timeout
    last = None
    stable = 0
    while time.time() < deadline:
        try:
            pending = driver.execute_script(_WAIT_ASSETS_JS, element)
            rect = driver.execute_script(_RECT_JS, element)
        except Exception:
            return
        key = (
            round(rect["x"]), round(rect["y"]), round(rect["width"]),
            round(rect["height"]), round(rect["vtop"]),
        )
        if not pending and key == last:
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
        last = key
        time.sleep(0.15)


def _edges_have_foreign_content(png_bytes):
    """True when the top or bottom edge strip has dark content.

    A correct table capture has plain background at the very top and bottom.
    Dark pixels there mean the clip is shifted: it shows part of the photo
    above the table, or cuts through the last row's text.
    """
    if Image is None:
        return False
    try:
        image = Image.open(io.BytesIO(png_bytes)).convert("L")
        w, h = image.size
        if h < 12:
            return False
        for box in ((0, 0, w, 3), (0, h - 3, w, h)):
            low, high = image.crop(box).getextrema()
            if (high - low) > 60:
                return True
        return False
    except Exception:
        return False


def _element_to_png_bytes(driver, element, attempts=3):
    best_png = None
    for _attempt in range(attempts):
        # variant 0: hide every fixed/sticky element outside the table;
        # variant 1: same, but keep sticky parts of the table's own wrapper
        #            (ChatGPT can draw the header row as a sticky copy);
        # variant 2: hide nothing and scroll the table clear of the page header.
        try:
            driver.execute_script(_RESTORE_HIDDEN_JS)
            if _attempt < 2:
                driver.execute_script(_HIDE_OVERLAYS_JS, element, _attempt == 1)
        except Exception:
            pass
        height = driver.execute_script(
            "return Math.ceil(arguments[0].getBoundingClientRect().height);",
            element,
        )
        window_height = driver.execute_script("return window.innerHeight;")
        if height + 600 > window_height:
            # Make the viewport taller than the element so nothing is cut off.
            try:
                driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": 1600,
                        "height": int(max(1200, height + 600)),
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
            except Exception:
                driver.set_window_size(1600, height + 400)
            time.sleep(0.4)

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});",
            element,
        )
        if _attempt == 2:
            driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "window.scrollBy(0, r.top - 220);",
                element,
            )
        time.sleep(0.8)
        # Hide whatever is painted on top of the element (sticky headers,
        # login banners, ...), then let the page repaint.
        try:
            if _attempt < 2 and driver.execute_script(
                _HIDE_COVERING_JS, element, _attempt == 1
            ):
                time.sleep(0.3)
        except Exception:
            pass
        _wait_for_stable_layout(driver, element)
        rect = driver.execute_script(_RECT_JS, element)
        clip = {k: rect[k] for k in ("x", "y", "width", "height")}
        shot = driver.execute_cdp_cmd(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
                "clip": {**clip, "scale": 1},
            },
        )
        rect_after = driver.execute_script(_RECT_JS, element)
        if any(abs(rect[k] - rect_after[k]) > 1 for k in rect):
            # The table moved while it was being captured; try again.
            time.sleep(0.5)
            continue
        png = base64.b64decode(shot["data"])
        if not _png_is_blank(png):
            if not _first_row_is_blank(
                driver, element, png
            ) and not _edges_have_foreign_content(png):
                return png
            if best_png is None:
                best_png = png  # defective: rows missing or clip shifted
            continue
        time.sleep(1.0)
    # best_png has missing rows, so it is NOT returned: returning None makes
    # the caller draw the table image from the text, which has every row.
    # Fallbacks: Selenium's own element screenshot, then a full-page clip.
    try:
        png = element.screenshot_as_png
        if (
            png
            and not _png_is_blank(png)
            and not _first_row_is_blank(driver, element, png)
            and not _edges_have_foreign_content(png)
        ):
            return png
    except Exception:
        pass
    try:
        rect = driver.execute_script(
            """
            const r = arguments[0].getBoundingClientRect();
            return {x: r.left + window.scrollX, y: r.top + window.scrollY,
                    width: r.width, height: r.height};
            """,
            element,
        )
        shot = driver.execute_cdp_cmd(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": True,
                "clip": {**rect, "scale": 1},
            },
        )
        png = base64.b64decode(shot["data"])
        if (
            not _png_is_blank(png)
            and not _first_row_is_blank(driver, element, png)
            and not _edges_have_foreign_content(png)
        ):
            return png
    except Exception:
        pass
    return None


def _find_best_capture_target(driver, selectors):
    best = None
    best_area = 0
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                rect = driver.execute_script(
                    "return arguments[0].getBoundingClientRect();",
                    element,
                )
                width = float(rect.get("width", 0) or 0)
                height = float(rect.get("height", 0) or 0)
                area = width * height
                if area > best_area:
                    best = element
                    best_area = area
            except Exception:
                continue
    return best


def _wait_for_page_content(
    driver,
    cancel_event=None,
    timeout=90,
    stable_seconds=1.5,
    content_selector="table, [role='table']",
):
    script = """
    window.scrollTo(0, document.body.scrollHeight);
    return {
        tables: document.querySelectorAll(arguments[0]).length,
        text: (document.body.innerText || "")
    };
    """
    deadline = time.monotonic() + timeout
    last_signature = None
    stable_since = None
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Conversion cancelled.")
        try:
            result = driver.execute_script(script, content_selector)
        except Exception:
            result = {"tables": 0, "text": ""}
        text = result["text"]
        for phrase in _SHARE_BOILERPLATE:
            text = text.replace(phrase, "")
        real_length = len(text.strip())
        has_content = result["tables"] > 0
        signature = (result["tables"], real_length)
        now = time.monotonic()
        if has_content:
            if signature == last_signature:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= stable_seconds:
                    driver.execute_script("window.scrollTo(0, 0);")
                    return True
            else:
                last_signature = signature
                stable_since = None
        time.sleep(0.4)
    return False  # never raise: the docx can still be built without screenshots

def capture_table_screenshot(url, output_path, selector=None):
    if webdriver is None or Options is None or By is None or WebDriverWait is None:
        raise RuntimeError(
            "Selenium is required for table screenshots. Install it with: "
            "python -m pip install selenium"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    candidate_selectors = [
        selector,
        "table",
        "[role='table']",
        ".table",
        ".markdown-table",
        "table[class*='table']",
        "thead",
        "tbody",
        "[data-testid*='table']",
        "main",
        "article",
        "[role='main']",
        "body",
    ]
    candidate_selectors = [item for item in candidate_selectors if item]

    driver = _start_chrome_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            lambda current_driver: current_driver.execute_script(
                "return document.readyState"
            )
            == "complete"
        )
        WebDriverWait(driver, 10).until(
            lambda current_driver: current_driver.find_elements(By.TAG_NAME, "body")
        )
        _wait_for_page_content(driver)

        target = _find_best_capture_target(driver, candidate_selectors)
        if target is None:
            body = driver.find_element(By.TAG_NAME, "body")
            driver.execute_script("arguments[0].scrollTo(0, 0);", body)
            body.screenshot(str(output_path))
            return output_path

        try:
            rect = driver.execute_script(
                "return arguments[0].getBoundingClientRect();",
                target,
            )
            if rect is None or rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
                raise ValueError("Target element has no visible dimensions")
        except Exception:
            body = driver.find_element(By.TAG_NAME, "body")
            body.screenshot(str(output_path))
            return output_path

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )
        target.screenshot(str(output_path))
    finally:
        _stop_chrome_driver(driver)

    return output_path


def save_docx(
    text,
    destination,
    images=(),
    heading_content=(),
    table_screenshots=(),
    code_screenshots=(),
):
    document = Document()
    _add_response_text(
        document,
        text,
        images,
        heading_content,
        table_screenshots=table_screenshots,
        code_screenshots=code_screenshots,
    )
    _apply_document_format(document)
    compatibility = document.settings._element.find(qn("w:compat"))
    compatibility_mode = next(
        (
            setting
            for setting in compatibility.findall(qn("w:compatSetting"))
            if setting.get(qn("w:name")) == "compatibilityMode"
        ),
        None,
    )
    if compatibility_mode is None:
        compatibility_mode = OxmlElement("w:compatSetting")
        compatibility_mode.set(qn("w:name"), "compatibilityMode")
        compatibility_mode.set(
            qn("w:uri"),
            "http://schemas.microsoft.com/office/word",
        )
        compatibility.append(compatibility_mode)
    compatibility_mode.set(qn("w:val"), "15")

    package_buffer = io.BytesIO()
    document.save(package_buffer)
    package_buffer.seek(0)
    finalized_package = io.BytesIO()
    with ZipFile(package_buffer) as package:
        with ZipFile(finalized_package, "w", ZIP_DEFLATED) as finalized:
            for entry in package.infolist():
                data = package.read(entry.filename)
                if entry.filename == "docProps/app.xml":
                    properties = etree.fromstring(data)
                    namespace = (
                        "{http://schemas.openxmlformats.org/officeDocument/"
                        "2006/extended-properties}"
                    )
                    application = properties.find(f"{namespace}Application")
                    version = properties.find(f"{namespace}AppVersion")
                    if application is None or version is None:
                        raise ValueError(
                            "The Word document application metadata is missing."
                        )
                    application.text = "Microsoft Office Word"
                    version.text = "16.0000"
                    data = etree.tostring(
                        properties,
                        xml_declaration=True,
                        encoding="UTF-8",
                        standalone=True,
                    )
                finalized.writestr(entry, data)
    data = finalized_package.getvalue()
    try:
        with open(destination, "wb") as output:
            output.write(data)
        return str(destination)
    except PermissionError:
        # Usually the .docx is still open in Word. Save next to it under a
        # new name instead of losing the whole conversion.
        base = Path(destination)
        for number in range(2, 100):
            alternate = base.with_name(f"{base.stem} ({number}){base.suffix}")
            if alternate.exists():
                continue
            try:
                with open(alternate, "wb") as output:
                    output.write(data)
                return str(alternate)
            except PermissionError:
                continue
        raise PermissionError(
            f"Cannot write to {destination}. Close the file in Word, or choose "
            "a different folder (Desktop may be protected by OneDrive or "
            "Controlled folder access)."
        )


def _notify_windows(title, message):
    """Show a Windows toast notification (best effort, never raises)."""
    if os.name != "nt":
        return

    def worker():
        try:
            import base64 as _b64
            from xml.sax.saxutils import escape

            script = (
                "[Windows.UI.Notifications.ToastNotificationManager,"
                " Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
                "[Windows.Data.Xml.Dom.XmlDocument,"
                " Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
                "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
                "$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\">"
                f"<text>{escape(title).replace(chr(39), chr(39) * 2)}</text>"
                f"<text>{escape(message).replace(chr(39), chr(39) * 2)}</text>"
                "</binding></visual></toast>');"
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
                "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
                "\\WindowsPowerShell\\v1.0\\powershell.exe';"
                "[Windows.UI.Notifications.ToastNotificationManager]"
                "::CreateToastNotifier($id).Show($toast)"
            )
            encoded = _b64.b64encode(script.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-EncodedCommand",
                    encoded,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                timeout=20,
            )
            return
        except Exception:
            pass
        try:  # fallback: balloon from the tray icon, or just a sound
            import winsound

            winsound.MessageBeep()
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


class ChatGPTToDocxApp:
    def __init__(self, root):
        self.root = root
        self.state_path = app_state_path()
        self._hidden = False
        self.console_visible = False
        self.tray_icon = None
        self._tray_started = False
        root.title("ChatGPT to Word")
        root.minsize(1120, 610)
        root.protocol("WM_DELETE_WINDOW", self.exit_app)
        global _CONSOLE_CLOSED_CALLBACK
        _CONSOLE_CLOSED_CALLBACK = self._on_console_closed

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(3, weight=2)

        self._save_job = None
        self._autosave_ready = False
        self._running_jobs = {}
        self._copying_rows = set()
        self._run_total = 0
        self._run_completed = 0
        self._run_items = []
        self._run_statuses = {}
        self._job_started_at = {}
        self._duration_update_job = None
        self._job_editor = None
        self._job_buttons = {}

        jobs_toolbar = ttk.Frame(frame)
        jobs_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(jobs_toolbar, text="Conversion jobs (double-click or type to edit):").pack(
            side="left"
        )
        self.add_job_button = ttk.Button(
            jobs_toolbar, text="Add row", command=self.add_job
        )
        self.add_job_button.pack(side="right")
        self.remove_job_button = ttk.Button(
            jobs_toolbar, text="Remove row(s)", command=self.remove_jobs
        )
        self.remove_job_button.pack(side="right", padx=(0, 6))
        self.browse_destination_button = ttk.Button(
            jobs_toolbar, text="Browse output...", command=self.choose_destination
        )
        self.browse_destination_button.pack(side="right", padx=(0, 6))

        jobs_frame = ttk.Frame(frame)
        jobs_frame.grid(row=1, column=0, sticky="nsew")
        jobs_frame.columnconfigure(0, weight=1)
        jobs_frame.rowconfigure(0, weight=1)
        ttk.Style(root).configure("JobTable.Treeview", rowheight=28)
        self.job_tree = ttk.Treeview(
            jobs_frame,
            columns=(
                "url",
                "destination",
                "copy_destination",
                "status",
                "duration",
                "convert",
                "cancel",
                "copy",
            ),
            show="headings",
            selectmode="extended",
            height=5,
            style="JobTable.Treeview",
        )
        self.job_tree.heading("url", text="ChatGPT share link")
        self.job_tree.heading("destination", text="Save Word file to")
        self.job_tree.heading("copy_destination", text="Destination Word document")
        self.job_tree.heading("status", text="Status")
        self.job_tree.heading("duration", text="Time taken")
        self.job_tree.heading("convert", text="Convert")
        self.job_tree.heading("cancel", text="Cancel")
        self.job_tree.column("url", width=250, minwidth=180, stretch=True)
        self.job_tree.column("destination", width=170, minwidth=140, stretch=True)
        self.job_tree.column("copy_destination", width=180, minwidth=140, stretch=True)
        self.job_tree.column("status", width=100, minwidth=90, stretch=False)
        self.job_tree.column("duration", width=90, minwidth=80, stretch=False)
        self.job_tree.column("convert", width=78, minwidth=78, stretch=False)
        self.job_tree.column("cancel", width=72, minwidth=72, stretch=False)
        self.job_tree.column("copy", width=72, minwidth=72, stretch=False)
        self.job_tree.grid(row=0, column=0, sticky="nsew")
        self.jobs_y_scroll = ttk.Scrollbar(
            jobs_frame, orient="vertical", command=self.job_tree.yview
        )
        self.jobs_y_scroll.grid(row=0, column=1, sticky="ns")
        self.jobs_x_scroll = ttk.Scrollbar(
            jobs_frame, orient="horizontal", command=self.job_tree.xview
        )
        self.jobs_x_scroll.grid(row=1, column=0, sticky="ew")
        self.job_tree.configure(
            yscrollcommand=self._on_job_tree_yview,
            xscrollcommand=self._on_job_tree_xview,
        )
        self.job_tree.bind("<Double-1>", self._edit_job_cell)
        self.job_tree.bind("<KeyPress>", self._type_to_edit_job_cell)
        self.job_tree.bind("<Button-1>", self._remember_job_cell)
        self.job_tree.bind("<Configure>", self._schedule_job_button_layout, add="+")

        pasted_toolbar = ttk.Frame(frame)
        pasted_toolbar.grid(row=2, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(
            pasted_toolbar,
            text="Formatted text after headings (skip headings with subheadings):",
        ).pack(side="left")
        clear_button_frame = ttk.Frame(pasted_toolbar)
        clear_button_frame.pack(side="right")
        ttk.Button(
            clear_button_frame,
            text="Clear",
            command=self.clear_pasted_text,
        ).grid(row=0, column=0, padx=(0, 6))
        self.clear_all_button = ttk.Button(
            clear_button_frame,
            text="Clear all",
            command=self.clear_all_fields,
        )
        self.clear_all_button.grid(row=0, column=1)
        pasted_frame = ttk.Frame(frame)
        pasted_frame.grid(row=3, column=0, sticky="nsew")
        pasted_frame.rowconfigure(0, weight=1)
        pasted_frame.columnconfigure(0, weight=1)
        self.pasted_text = tk.Text(
            pasted_frame,
            width=70,
            height=9,
            wrap="word",
            undo=True,
        )
        self.pasted_text.grid(row=0, column=0, sticky="nsew")
        pasted_scrollbar = ttk.Scrollbar(
            pasted_frame,
            orient="vertical",
            command=self.pasted_text.yview,
        )
        pasted_scrollbar.grid(row=0, column=1, sticky="ns")
        self.pasted_text.configure(yscrollcommand=pasted_scrollbar.set)
        self._preview_formats = {}
        self._formats_by_tag = {}
        self._preview_fonts = []
        self.pasted_text.bind("<Control-v>", self.paste_formatted_text)
        self.pasted_text.bind("<Control-V>", self.paste_formatted_text)
        self.pasted_text.bind("<Shift-Insert>", self.paste_formatted_text)
        self.pasted_text.bind("<<Paste>>", self.paste_formatted_text)
        self.pasted_text.bind("<<Modified>>", self._on_pasted_text_modified)

        copy_destination_frame = ttk.Frame(frame)
        copy_destination_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        copy_destination_frame.columnconfigure(1, weight=1)
        ttk.Label(
            copy_destination_frame,
            text="Default destination Word document (must exist):",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.copy_destination_default_var = tk.StringVar()
        self.copy_destination_default_var.trace_add(
            "write", lambda *_args: self._schedule_save()
        )
        self.copy_destination_default_entry = ttk.Entry(
            copy_destination_frame,
            textvariable=self.copy_destination_default_var,
        )
        self.copy_destination_default_entry.grid(row=0, column=1, sticky="ew")
        self.copy_destination_default_entry.bind(
            "<Return>",
            self._apply_copy_destination_default,
        )
        self.copy_destination_default_entry.bind(
            "<FocusOut>",
            self._apply_copy_destination_default,
        )
        self.browse_copy_destination_button = ttk.Button(
            copy_destination_frame,
            text="Browse...",
            command=self.choose_copy_destination_default,
        )
        self.browse_copy_destination_button.grid(row=0, column=2, padx=(8, 0))

        self.console_button = ttk.Button(
            frame,
            text="Open console",
            command=self.open_console,
        )
        self.console_button.grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.notify_var = tk.BooleanVar(value=True)
        self.notify_var.trace_add("write", lambda *_args: self._schedule_save())
        self.notify_check = ttk.Checkbutton(
            frame,
            text="Notify me in Windows when done",
            variable=self.notify_var,
        )
        self.notify_check.grid(row=8, column=0, sticky="w", pady=(10, 0))
        self.convert_button = ttk.Button(
            frame, text="Convert all rows", command=self.convert
        )
        self.convert_button.grid(row=5, column=0, sticky="e", pady=(10, 0))
        self.cancel_button = ttk.Button(
            frame,
            text="Cancel all",
            command=self.cancel_conversion,
            state="disabled",
        )
        self.cancel_button.grid(row=5, column=0, sticky="e", padx=(0, 100), pady=(10, 0))
        self.progress = ttk.Progressbar(
            frame,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()
        self.status = ttk.Label(frame, text="Only public ChatGPT share links are supported.")
        self.status.grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.add_job()
        self.restore_state()
        self._schedule_job_button_layout()
        try:
            self.pasted_text.edit_modified(False)
        except tk.TclError:
            pass
        self._autosave_ready = True

    def add_job(self):
        default_copy_destination = self._normalize_copy_destination(
            self.copy_destination_default_var.get()
        )
        item = self.job_tree.insert(
            "",
            "end",
            values=("", "", default_copy_destination, "", "", "", "", ""),
        )
        self.job_tree.selection_set(item)
        self.job_tree.focus(item)
        self._schedule_save()
        self.root.after_idle(self._start_job_cell_edit, item, "#1")
        self._schedule_job_button_layout()

    def _normalize_output_path(self, destination):
        destination = destination.strip()
        if not destination:
            return ""
        path = Path(destination)
        if not path.is_absolute():
            path = Path.home() / "Desktop" / path
        if not path.suffix:
            path = path.with_suffix(".docx")
        return str(path)

    def _normalize_copy_destination(self, destination):
        destination = destination.strip()
        if not destination:
            return ""
        path = Path(destination).expanduser()
        if not path.is_absolute():
            path = Path.home() / "Desktop" / path
        if not path.suffix:
            path = path.with_suffix(".docx")
        return str(path)

    def _row_is_busy(self, item):
        return item in self._running_jobs or item in self._copying_rows

    def remove_jobs(self):
        selected = self.job_tree.selection()
        removable = [item for item in selected if not self._row_is_busy(item)]
        running = [item for item in selected if self._row_is_busy(item)]
        if not removable:
            self.status.configure(
                text=(
                    "Rows processing a conversion or copy cannot be removed until they finish."
                    if running
                    else "Select a row to remove."
                )
            )
            return
        for item in removable:
            self.job_tree.delete(item)
            buttons = self._job_buttons.pop(item, {})
            for button in buttons.values():
                button.destroy()
        if not self.job_tree.get_children():
            self.job_tree.insert("", "end", values=("", "", "", "", "", "", "", ""))
        if running:
            self.status.configure(
                text="Removed finished rows. Running rows remain until they finish or are cancelled."
            )
        self._schedule_save()
        self._schedule_job_button_layout()

    def _on_job_tree_yview(self, first, last):
        self.jobs_y_scroll.set(first, last)
        self._schedule_job_button_layout()

    def _on_job_tree_xview(self, first, last):
        self.jobs_x_scroll.set(first, last)
        self._schedule_job_button_layout()

    def _schedule_job_button_layout(self, _event=None):
        try:
            self.root.after_idle(self._position_job_buttons)
        except tk.TclError:
            pass

    def _position_job_buttons(self):
        items = self.job_tree.get_children()
        item_set = set(items)
        for item in tuple(self._job_buttons):
            if item not in item_set:
                for button in self._job_buttons.pop(item).values():
                    button.destroy()
        for item in items:
            buttons = self._job_buttons.get(item)
            if buttons is None:
                buttons = {
                    "convert": ttk.Button(
                        self.job_tree,
                        text="Convert",
                        command=lambda job_id=item: self.convert_job(job_id),
                    ),
                    "cancel": ttk.Button(
                        self.job_tree,
                        text="Cancel",
                        command=lambda job_id=item: self.cancel_job(job_id),
                    ),
                    "copy": ttk.Button(
                        self.job_tree,
                        text="Copy",
                        command=lambda job_id=item: self.copy_job(job_id),
                    ),
                }
                self._job_buttons[item] = buttons
            cancel_event = self._running_jobs.get(item)
            status = self.job_tree.set(item, "status")
            copy_destination = self.job_tree.set(item, "copy_destination").strip()
            buttons["convert"].configure(
                state="disabled" if self._row_is_busy(item) else "normal"
            )
            buttons["cancel"].configure(
                text="Cancel..." if cancel_event and cancel_event.is_set() else "Cancel",
                state=(
                    "normal"
                    if cancel_event is not None and not cancel_event.is_set()
                    else "disabled"
                ),
            )
            buttons["copy"].configure(
                state=(
                    "normal"
                    if status
                    in {
                        "Saved",
                        "Saved with warnings",
                        "Copied",
                        "Copied with warnings",
                        "Copy failed",
                    }
                    and copy_destination
                    and not self._row_is_busy(item)
                    else "disabled"
                )
            )
            for column, button in buttons.items():
                bbox = self.job_tree.bbox(item, column)
                if not bbox:
                    button.place_forget()
                    continue
                x, y, width, height = bbox
                button.place(x=x, y=y, width=width, height=height)

    def _remember_job_cell(self, event):
        column = self.job_tree.identify_column(event.x)
        self._last_job_column = column if column in ("#1", "#2", "#3") else "#1"

    def _edit_job_cell(self, event):
        item = self.job_tree.identify_row(event.y)
        column = self.job_tree.identify_column(event.x)
        if item and not self._row_is_busy(item) and column in ("#1", "#2", "#3"):
            self.job_tree.selection_set(item)
            self.job_tree.focus(item)
            self._last_job_column = column
            self._start_job_cell_edit(item, column)
        return "break"

    def _type_to_edit_job_cell(self, event):
        if not event.char or not event.char.isprintable() or event.state & 0x4:
            return
        selection = self.job_tree.selection()
        if not selection:
            return
        if self._row_is_busy(selection[0]):
            return "break"
        column = getattr(self, "_last_job_column", "#1")
        if column not in ("#1", "#2", "#3"):
            column = "#1"
        self._start_job_cell_edit(selection[0], column, event.char)
        return "break"

    def _start_job_cell_edit(self, item, column, initial_text=None):
        if self._row_is_busy(item) or not self.job_tree.exists(item):
            return
        if self._job_editor is not None:
            self._job_editor.destroy()
        bbox = self.job_tree.bbox(item, column)
        if not bbox:
            return
        x, y, width, height = bbox
        entry = ttk.Entry(self.job_tree)
        entry.place(x=x, y=y, width=width, height=height)
        current = self.job_tree.set(item, column)
        entry.insert(0, current if initial_text is None else initial_text)
        if initial_text is None:
            entry.selection_range(0, tk.END)
        self._job_editor = entry

        def finish(commit=True, move=False):
            if self._job_editor is not entry:
                return
            value = entry.get()
            entry.destroy()
            self._job_editor = None
            if commit and self.job_tree.exists(item):
                if column == "#2":
                    value = self._normalize_output_path(value)
                elif column == "#3":
                    value = self._normalize_copy_destination(value)
                self.job_tree.set(item, column, value)
                self._schedule_save()
                self._schedule_job_button_layout()
            if move:
                self._move_to_next_job_cell(item, column)

        def finish_and_break(_event):
            finish()
            return "break"

        def cancel_and_break(_event):
            finish(commit=False)
            return "break"

        def finish_and_move(_event):
            finish(move=True)
            return "break"

        entry.bind("<Return>", finish_and_break)
        entry.bind("<Escape>", cancel_and_break)
        entry.bind("<FocusOut>", lambda _event: finish())
        entry.bind("<Tab>", finish_and_move)
        entry.focus_set()

    def _move_to_next_job_cell(self, item, column):
        items = list(self.job_tree.get_children())
        if not items:
            return
        columns = ["#1", "#2", "#3"]
        item_index = items.index(item) if item in items else 0
        column_index = columns.index(column)
        if column_index + 1 < len(columns):
            next_item, next_column = items[item_index], columns[column_index + 1]
        else:
            next_index = (item_index + 1) % len(items)
            next_item, next_column = items[next_index], columns[0]
        self.job_tree.selection_set(next_item)
        self.job_tree.focus(next_item)
        self._last_job_column = next_column
        self._start_job_cell_edit(next_item, next_column)

    def _schedule_save(self, delay_ms=400):
        """Autosave shortly after any change so nothing is lost if the program
        is closed any other way than the normal exit (console closed, killed,
        crash, power loss)."""
        if not self._autosave_ready:
            return
        try:
            if self._save_job is not None:
                self.root.after_cancel(self._save_job)
            self._save_job = self.root.after(delay_ms, self._run_scheduled_save)
        except tk.TclError:
            pass

    def _run_scheduled_save(self):
        self._save_job = None
        self.save_state()

    def _on_pasted_text_modified(self, _event=None):
        try:
            if self.pasted_text.edit_modified():
                self.pasted_text.edit_modified(False)
                self._schedule_save()
        except tk.TclError:
            pass

    def save_state(self):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            paragraphs = self._pasted_text_content()
            serialized = []
            for paragraph in paragraphs:
                runs = []
                for run in paragraph.runs:
                    formatted = run.format
                    runs.append(
                        {
                            "text": run.text,
                            "format": {
                                "bold": formatted.bold,
                                "italic": formatted.italic,
                                "underline": formatted.underline,
                                "color": formatted.color,
                                "background": formatted.background,
                                "font_name": formatted.font_name,
                                "font_size": formatted.font_size,
                            },
                        }
                    )
                serialized.append({"runs": runs})
            payload = {
                "jobs": [
                    {
                        "url": values[0],
                        "destination": values[1],
                        "copy_destination": values[2],
                        "status": values[3],
                        "duration": values[4],
                    }
                    for item in self.job_tree.get_children()
                    for values in (self.job_tree.item(item, "values"),)
                ],
                "copy_destination_default": self.copy_destination_default_var.get(),
                "notify": bool(self.notify_var.get()),
                "paragraphs": serialized,
            }
            temporary_path = self.state_path.with_suffix(".tmp")
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False)
            os.replace(temporary_path, self.state_path)
        except OSError:
            pass

    def restore_state(self):
        if not self.state_path.exists():
            return
        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        default_copy_destination = self._normalize_copy_destination(
            str(payload.get("copy_destination_default", ""))
        )
        self.copy_destination_default_var.set(default_copy_destination)
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            jobs = [
                {
                    "url": payload.get("url", ""),
                    "destination": payload.get("destination", ""),
                }
            ]
        paragraphs = payload.get("paragraphs", [])
        self.notify_var.set(bool(payload.get("notify", True)))
        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        for job in jobs:
            if not isinstance(job, dict):
                continue
            status = str(job.get("status", ""))
            if status in {
                "Queued",
                "Fetching",
                "Capturing screenshots",
                "Saving",
                "Cancelling",
            }:
                status = "Cancelled"
            elif status == "Copying":
                status = "Copy failed"
            copy_destination = job.get(
                "copy_destination",
                default_copy_destination,
            )
            self.job_tree.insert(
                "",
                "end",
                values=(
                    str(job.get("url", "")),
                    self._normalize_output_path(str(job.get("destination", ""))),
                    self._normalize_copy_destination(str(copy_destination)),
                    status,
                    str(job.get("duration", "")),
                    "",
                    "",
                    "",
                ),
            )
        if not self.job_tree.get_children():
            self.add_job()
        if default_copy_destination:
            self._apply_copy_destination_default()
        if paragraphs:
            restored = []
            for paragraph in paragraphs:
                runs = []
                for run in paragraph.get("runs", []):
                    format_values = run.get("format", {})
                    runs.append(
                        PastedTextRun(
                            run.get("text", ""),
                            PastedTextFormat(
                                bold=bool(format_values.get("bold", False)),
                                italic=bool(format_values.get("italic", False)),
                                underline=bool(format_values.get("underline", False)),
                                color=format_values.get("color"),
                                background=format_values.get("background"),
                                font_name=format_values.get("font_name"),
                                font_size=format_values.get("font_size"),
                            ),
                        )
                    )
                restored.append(PastedTextParagraph(tuple(runs)))
            if restored:
                self._insert_pasted_paragraphs(tuple(restored))

    def _create_tray_icon(self):
        if pystray is None or os.name != "nt":
            return None
        if self.tray_icon is not None:
            return self.tray_icon
        if Image is None:
            return None
        icon_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon_image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(29, 91, 201, 255))
        draw.text((22, 18), "W", fill=(255, 255, 255, 255))
        tray = pystray.Icon(
            "chatgpt_to_docx",
            icon_image,
            "ChatGPT to Word",
            menu=pystray.Menu(
                pystray.MenuItem("Restore", self.restore_window),
                pystray.MenuItem("Open console", self.open_console),
                pystray.MenuItem("Exit", self.exit_app),
            ),
        )
        self.tray_icon = tray
        return tray

    def _show_tray(self):
        tray = self._create_tray_icon()
        if tray is None or self._tray_started:
            return
        self._tray_started = True
        try:
            tray.run_detached()
        except AttributeError:
            tray.run()

    def hide_window(self):
        self.save_state()
        hide_program_console()
        self.root.withdraw()
        self._hidden = True
        self.console_visible = False
        self._show_tray()
        self.status.configure(text="Window hidden. The app keeps running in the background.")

    def restore_window(self):
        if self._hidden:
            self.root.deiconify()
            self.root.state("normal")
            self.root.focus_force()
            self._hidden = False
            if self.tray_icon is not None:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
                self.tray_icon = None
            self._tray_started = False
            self.status.configure(text="Window restored.")

    def _on_console_closed(self):
        # Called when the user clicks X on the console window.
        self.console_visible = False

    def exit_app(self):
        """Fully quit: stop work, close Chrome, remove tray icon, end the process."""
        self._cancel_running_jobs()
        try:
            self.save_state()
        except Exception:
            pass
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self._tray_started = False
        try:
            hide_program_console()
        except Exception:
            pass
        _force_exit()

    def _cancel_running_jobs(self):
        for item, cancel_event in self._running_jobs.items():
            cancel_event.set()
            if self.job_tree.exists(item):
                self.job_tree.set(item, "status", "Cancelled")
                self._record_job_duration(item)
        for item in self._copying_rows:
            if self.job_tree.exists(item):
                self.job_tree.set(item, "status", "Copy failed")
        self._copying_rows.clear()
        self._stop_duration_updates()
        self._schedule_job_button_layout()

    def _format_elapsed_duration(self, elapsed):
        elapsed = max(0.0, elapsed)
        whole_seconds = int(elapsed)
        if whole_seconds < 60:
            return f"{elapsed:.1f} s"
        hours, remainder = divmod(whole_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours} h {minutes:02} m {seconds:02} s"
        return f"{minutes} m {seconds:02} s"

    def _record_job_duration(self, item):
        started_at = self._job_started_at.pop(item, None)
        if started_at is None or not self.job_tree.exists(item):
            return
        self.job_tree.set(
            item,
            "duration",
            self._format_elapsed_duration(time.monotonic() - started_at),
        )

    def _schedule_duration_updates(self):
        if self._duration_update_job is None and self._running_jobs:
            self._duration_update_job = self.root.after(
                500,
                self._update_running_durations,
            )

    def _update_running_durations(self):
        self._duration_update_job = None
        now = time.monotonic()
        for item in self._running_jobs:
            started_at = self._job_started_at.get(item)
            if started_at is not None and self.job_tree.exists(item):
                self.job_tree.set(
                    item,
                    "duration",
                    self._format_elapsed_duration(now - started_at),
                )
        self._schedule_duration_updates()

    def _stop_duration_updates(self):
        if self._duration_update_job is None:
            return
        try:
            self.root.after_cancel(self._duration_update_job)
        except tk.TclError:
            pass
        self._duration_update_job = None

    def clear_pasted_text(self):
        self.pasted_text.delete("1.0", "end")
        self.pasted_text.focus_set()

    def clear_all_fields(self):
        if self._running_jobs or self._copying_rows:
            return
        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        self.copy_destination_default_var.set("")
        self.add_job()
        self.clear_pasted_text()
        self.status.configure(text="All fields cleared.")

    def _format_tag(self, formatting):
        tag = self._preview_formats.get(formatting)
        if tag is not None:
            return tag
        tag = f"pasted_format_{len(self._preview_formats)}"
        self._preview_formats[formatting] = tag
        self._formats_by_tag[tag] = formatting
        options = {}
        if formatting.color:
            options["foreground"] = f"#{formatting.color}"
        if formatting.background:
            options["background"] = f"#{formatting.background}"
        if (
            formatting.font_name
            or formatting.font_size
            or formatting.bold
            or formatting.italic
            or formatting.underline
        ):
            font = tkfont.Font(
                self.pasted_text,
                family=formatting.font_name or "Segoe UI",
                size=round(formatting.font_size or 10),
                weight="bold" if formatting.bold else "normal",
                slant="italic" if formatting.italic else "roman",
                underline=formatting.underline,
            )
            self._preview_fonts.append(font)
            options["font"] = font
        if options:
            self.pasted_text.tag_configure(tag, **options)
        return tag

    def _insert_pasted_paragraphs(self, paragraphs):
        if not paragraphs:
            return
        selection = self.pasted_text.tag_ranges("sel")
        if selection:
            self.pasted_text.delete(selection[0], selection[1])
        for paragraph_index, paragraph in enumerate(paragraphs):
            for run in paragraph.runs:
                tag = self._format_tag(run.format)
                self.pasted_text.insert("insert", run.text, (tag,))
            if paragraph_index < len(paragraphs) - 1:
                self.pasted_text.insert("insert", "\n")

    def paste_formatted_text(self, _event=None):
        html = _clipboard_html()
        paragraphs = parse_pasted_html(html) if html else ()
        if not paragraphs:
            try:
                plain_text = self.root.clipboard_get()
            except tk.TclError:
                return "break"
            paragraphs = tuple(
                PastedTextParagraph((PastedTextRun(line),))
                for line in plain_text.splitlines()
            )
        self._insert_pasted_paragraphs(paragraphs)
        return "break"

    def _pasted_text_content(self):
        paragraphs = []
        line_count = int(self.pasted_text.index("end-1c").split(".")[0])
        for line_number in range(1, line_count + 1):
            line = self.pasted_text.get(
                f"{line_number}.0",
                f"{line_number}.end",
            )
            runs = []
            for column, character in enumerate(line):
                tag = next(
                    (
                        tag_name
                        for tag_name in self.pasted_text.tag_names(
                            f"{line_number}.{column}"
                        )
                        if tag_name in self._formats_by_tag
                    ),
                    None,
                )
                formatting = (
                    self._formats_by_tag[tag]
                    if tag
                    else PastedTextFormat()
                )
                if runs and runs[-1].format == formatting:
                    previous = runs[-1]
                    runs[-1] = PastedTextRun(
                        previous.text + character,
                        formatting,
                    )
                else:
                    runs.append(PastedTextRun(character, formatting))
            paragraphs.append(PastedTextParagraph(tuple(runs)))
        while paragraphs and not any(
            run.text for run in paragraphs[-1].runs
        ):
            paragraphs.pop()
        return tuple(paragraphs)

    def open_console(self):
        if getattr(self, "console_visible", False):
            if hide_program_console():
                self.console_visible = False
                self.status.configure(text="Console hidden. The app is still running in the GUI.")
            else:
                self.status.configure(text="Console is unavailable in this environment.")
            return
        if show_program_console():
            self.console_visible = True
            self.status.configure(text="Console opened. Errors and progress will print here.")
        else:
            self.status.configure(text="Console is unavailable in this environment.")

    def choose_destination(self):
        selection = self.job_tree.selection()
        if not selection:
            messagebox.showwarning(
                "Select a job",
                "Select a job row before choosing an output file.",
            )
            return
        item = selection[0]
        if self._row_is_busy(item):
            messagebox.showwarning(
                "Job is running",
                "Wait for this row to finish before changing its path.",
            )
            return
        destination = filedialog.asksaveasfilename(
            title="Save Word document",
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
            initialfile=Path(self.job_tree.set(item, "destination")).name
            if self.job_tree.set(item, "destination")
            else "chatgpt-response.docx",
        )
        if destination:
            self.job_tree.set(item, "destination", destination)
            self._schedule_save()

    def _apply_copy_destination_default(self, _event=None):
        destination = self._normalize_copy_destination(
            self.copy_destination_default_var.get()
        )
        if destination:
            self.copy_destination_default_var.set(destination)
            for item in self.job_tree.get_children():
                if (
                    not self.job_tree.set(item, "copy_destination").strip()
                    and not self._row_is_busy(item)
                ):
                    self.job_tree.set(item, "copy_destination", destination)
        self._schedule_job_button_layout()
        self._schedule_save()
        return "break"

    def choose_copy_destination_default(self):
        current = self.copy_destination_default_var.get().strip()
        initial_directory = Path(current).parent if current else Path.home()
        if not initial_directory.is_dir():
            initial_directory = Path.home()
        destination = filedialog.askopenfilename(
            title="Choose existing destination Word document",
            filetypes=[
                ("Word documents", "*.docx;*.doc;*.docm"),
                ("All files", "*.*"),
            ],
            initialdir=str(initial_directory),
        )
        if destination:
            self.copy_destination_default_var.set(destination)
            self._apply_copy_destination_default()

    def copy_job(self, item):
        if self._row_is_busy(item) or not self.job_tree.exists(item):
            return
        if self.job_tree.set(item, "status") not in {
            "Saved",
            "Saved with warnings",
            "Copied",
            "Copied with warnings",
            "Copy failed",
        }:
            messagebox.showwarning(
                "Conversion not finished",
                "Copy is available after this row's conversion finishes.",
            )
            return

        source = Path(self.job_tree.set(item, "destination"))
        raw_destination = self.job_tree.set(item, "copy_destination").strip()
        destination = self._normalize_copy_destination(raw_destination)
        if not destination:
            messagebox.showwarning(
                "Missing destination document",
                "Set the default destination Word document below the formatted text or enter one in this row.",
            )
            return
        self.job_tree.set(item, "copy_destination", destination)
        if not source.is_file():
            self._finish_copy(
                item,
                None,
                FileNotFoundError(f"Converted Word file was not found: {source}"),
                None,
            )
            return
        destination_path = Path(destination)
        if not destination_path.is_file():
            self._finish_copy(
                item,
                destination,
                FileNotFoundError(
                    f"Destination Word document was not found: {destination_path}"
                ),
                None,
            )
            return
        if os.path.abspath(source).lower() == os.path.abspath(destination_path).lower():
            self._finish_copy(
                item,
                destination,
                ValueError("Source and destination must be different documents."),
                None,
            )
            return
        self._copying_rows.add(item)
        self.job_tree.set(item, "status", "Copying")
        self.clear_all_button.configure(state="disabled")
        self.status.configure(text=f"Inserting {source.name} into {destination_path.name}...")
        self._schedule_job_button_layout()
        self._schedule_save()
        worker = threading.Thread(
            target=self._copy_word_document_in_background,
            args=(item, source, destination_path),
            daemon=True,
        )
        worker.start()

    def _copy_word_document_in_background(self, item, source, destination):
        try:
            with _WORD_COPY_LOCK:
                manager_path = (
                    Path(__file__).resolve().parent
                    / "word_document_inserter.py"
                )
                if not manager_path.is_file() and getattr(sys, "frozen", False):
                    executable_directory = Path(sys.executable).resolve().parent
                    candidates = (
                        executable_directory / "word_document_inserter.py",
                        executable_directory.parent
                        / "Code"
                        / "word_document_inserter.py",
                    )
                    manager_path = next(
                        (candidate for candidate in candidates if candidate.is_file()),
                        manager_path,
                    )
                if not manager_path.is_file():
                    raise FileNotFoundError(
                        "Word document insertion engine "
                        "word_document_inserter.py "
                        f"was not found at {manager_path}."
                    )
                spec = importlib.util.spec_from_file_location(
                    "_chatgpt_word_document_inserter",
                    manager_path,
                )
                if spec is None or spec.loader is None:
                    raise ImportError(
                        f"Could not load the Word document insertion engine from {manager_path}."
                    )
                manager_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(manager_module)
                manager = manager_module.WordDocumentInserter()
                numbering_repair_supported = manager.copy_document_paths(
                    str(source),
                    str(destination),
                )
        except ModuleNotFoundError as error:
            if error.name in {"pythoncom", "pywintypes", "win32com"}:
                error = RuntimeError(
                    "Word integration requires pywin32. Install it with "
                    "`python -m pip install pywin32`, then restart the app."
                )
            self.root.after(0, self._finish_copy, item, str(destination), error, None)
        except Exception as error:
            self.root.after(0, self._finish_copy, item, str(destination), error, None)
        else:
            self.root.after(
                0,
                self._finish_copy,
                item,
                str(destination),
                None,
                numbering_repair_supported,
            )

    def _finish_copy(self, item, destination, error, numbering_repair_supported):
        self._copying_rows.discard(item)
        if error is not None:
            self.job_tree.set(item, "status", "Copy failed")
            self.status.configure(text="Word document insertion failed.")
            self._show_copy_dialog(
                "Could not insert Word document",
                "The Word document could not be inserted. Click \"Copy error\" to copy the details:",
                f"{type(error).__name__}: {error}",
                modal=False,
            )
            if self.notify_var.get():
                _notify_windows("Word document insertion failed", str(error)[:180])
        else:
            final_status = (
                "Copied" if numbering_repair_supported else "Copied with warnings"
            )
            self.job_tree.set(item, "status", final_status)
            self.status.configure(
                text=f"Inserted {Path(self.job_tree.set(item, 'destination')).name} "
                f"into {Path(destination).name} and saved."
            )
            if not numbering_repair_supported:
                self._show_copy_dialog(
                    "Numbering may differ",
                    "The document was inserted and saved, but automatic list-numbering repair "
                    "is available only when both documents are .docx or .docm files.",
                    "The destination is a legacy Word document. For reliable numbered-list "
                    "restarts, use a .docx or .docm destination.",
                    modal=False,
                )
            if self.notify_var.get():
                _notify_windows(
                    "Word document inserted",
                    f"Inserted into {Path(destination).name}."
                    if numbering_repair_supported
                    else f"Inserted into {Path(destination).name}; numbering may differ.",
                )
        self._schedule_save()
        self._schedule_job_button_layout()
        if not self._running_jobs and not self._copying_rows:
            self.clear_all_button.configure(state="normal")

    def _show_copy_dialog(self, title, heading, body, copy_text=None, modal=True):
        """Dialog with selectable text and a Copy button (errors and warnings)."""
        copy_text = body if copy_text is None else copy_text
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.minsize(480, 220)

        frame = ttk.Frame(dialog, padding=16)
        frame.grid(sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=heading, wraplength=520).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        box = ttk.Frame(frame)
        box.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 12))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        details = tk.Text(box, width=70, height=12, wrap="word")
        scrollbar = ttk.Scrollbar(box, orient="vertical", command=details.yview)
        details.configure(yscrollcommand=scrollbar.set)
        details.insert("1.0", body)
        details.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        def copy_text_to_clipboard():
            self.root.clipboard_clear()
            self.root.clipboard_append(copy_text)
            self.root.update()
            copy_button.configure(text="Copied!")
            self.status.configure(text="Copied to clipboard.")

        copy_button = ttk.Button(frame, text="Copy error", command=copy_text_to_clipboard)
        copy_button.grid(row=2, column=1, sticky="e", padx=(0, 8))
        ttk.Button(frame, text="Close", command=dialog.destroy).grid(
            row=2, column=2, sticky="e"
        )
        # keep the text selectable (Ctrl+C works) but not editable
        details.bind("<Key>", lambda event: None if event.state & 0x4 else "break")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        if modal:
            dialog.grab_set()
        dialog.focus_set()

    def show_error_dialog(self, error, modal=True):
        import traceback

        error_text = f"{type(error).__name__}: {error}"
        full_text = error_text
        if getattr(error, "__traceback__", None) is not None:
            full_text = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ).strip()
        self._show_copy_dialog(
            "Could not convert link",
            "The conversion failed. Click \"Copy error\" and send it if you need help:",
            full_text,
            modal=modal,
        )

    def show_warning_dialog(self, destination, warnings):
        message = "\n\n".join(warnings)
        self._show_copy_dialog(
            "Saved, but some items are missing",
            f"Word document saved to:\n{destination}",
            message
            + "\n\nThe document was still saved from the reply text, but "
            "without the items listed above. Try converting again, or "
            "re-share the conversation, if you need them.",
            copy_text=f"Saved to: {destination}\n\n{message}",
            modal=False,
        )

    def capture_table_from_url(self):
        url = self.capture_url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a page URL first.")
            return
        destination = filedialog.asksaveasfilename(
            title="Save table screenshot",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            initialfile="table.png",
        )
        if not destination:
            return

        self.convert_button.configure(state="disabled")
        self.status.configure(text="Opening Chrome and capturing the table...")
        self.progress.grid()
        self.progress.start(12)
        worker = threading.Thread(
            target=self._capture_table_in_background,
            args=(url, destination),
            daemon=True,
        )
        worker.start()

    def _capture_table_in_background(self, url, destination):
        try:
            capture_table_screenshot(url, destination)
        except Exception as error:
            self.root.after(0, self._finish_table_capture, None, error)
        else:
            self.root.after(0, self._finish_table_capture, destination, None)

    def _finish_table_capture(self, destination, error):
        self.progress.stop()
        self.progress.grid_remove()
        self.convert_button.configure(state="normal")
        if error is not None:
            self.status.configure(text="Table screenshot failed.")
            self.show_error_dialog(error)
            return
        self.status.configure(text=f"Saved table screenshot: {destination}")
        messagebox.showinfo(
            "Table screenshot saved",
            f"PNG saved to:\n{destination}",
        )

    def _set_progress(self, value, text=None):
        self.progress.configure(value=value)
        if text is not None:
            self.status.configure(text=text)

    def cancel_conversion(self):
        if self._running_jobs:
            for item, cancel_event in self._running_jobs.items():
                cancel_event.set()
                self.job_tree.set(item, "status", "Cancelling")
            self.cancel_button.configure(state="disabled")
            self.status.configure(text="Cancelling conversion...")
            self._schedule_job_button_layout()
            self._schedule_save()

    def cancel_job(self, item):
        cancel_event = self._running_jobs.get(item)
        if cancel_event is None or cancel_event.is_set():
            return
        cancel_event.set()
        self.job_tree.set(item, "status", "Cancelling")
        filename = Path(self.job_tree.set(item, "destination")).name
        self.status.configure(
            text=f"Cancelling {filename or 'selected job'}..."
        )
        self._schedule_job_button_layout()
        self._schedule_save()

    def convert(self):
        jobs = []
        for item in self.job_tree.get_children():
            if self._row_is_busy(item):
                continue
            url = self.job_tree.set(item, "url").strip()
            destination = self._normalize_output_path(
                self.job_tree.set(item, "destination")
            )
            if url:
                jobs.append((item, url, destination))
        if not jobs:
            if not self._running_jobs and not self._copying_rows:
                messagebox.showwarning(
                    "Missing link",
                    "Enter a ChatGPT share link in at least one table row.",
                )
            return
        self._start_jobs(jobs)

    def convert_job(self, item):
        if self._row_is_busy(item) or not self.job_tree.exists(item):
            return
        url = self.job_tree.set(item, "url").strip()
        if not url:
            messagebox.showwarning(
                "Missing link",
                "Enter a ChatGPT share link in this row before converting it.",
            )
            return
        self._start_jobs(
            [
                (
                    item,
                    url,
                    self._normalize_output_path(
                        self.job_tree.set(item, "destination")
                    ),
                )
            ]
        )

    def _start_jobs(self, jobs):
        new_run = not self._running_jobs
        if new_run:
            self._run_total = 0
            self._run_completed = 0
            self._run_items = []
            self._run_statuses = {}
            with _OUTPUT_PATHS_LOCK:
                self._reserved_output_paths = set()

        duplicates = set()
        with _OUTPUT_PATHS_LOCK:
            destination_rows = {}
            for item, _url, destination in jobs:
                if destination:
                    normalized = os.path.normcase(os.path.abspath(destination))
                    destination_rows.setdefault(normalized, []).append(item)
            for destination, items in destination_rows.items():
                if destination in self._reserved_output_paths or len(items) > 1:
                    duplicates.update(items)
            jobs = [job for job in jobs if job[0] not in duplicates]
            for _item, _url, destination in jobs:
                if destination:
                    self._reserved_output_paths.add(
                        os.path.normcase(os.path.abspath(destination))
                    )

        for item in duplicates:
            self.job_tree.set(item, "status", "Duplicate output path")
        if duplicates:
            messagebox.showwarning(
                "Duplicate output paths",
                "Rows with an output path already in use were skipped. "
                "Choose a different output file for each row.",
            )
        if not jobs:
            return

        heading_content = self._pasted_text_content()
        self._run_total += len(jobs)
        self._run_items.extend(item for item, _url, _destination in jobs)
        self.cancel_button.configure(state="normal")
        self.clear_all_button.configure(state="disabled")
        self.progress.configure(
            value=100 * self._run_completed / max(self._run_total, 1)
        )
        self.progress.grid()
        for item, url, destination in jobs:
            cancel_event = threading.Event()
            self._running_jobs[item] = cancel_event
            self._job_started_at[item] = time.monotonic()
            self.job_tree.set(item, "status", "Queued")
            self.job_tree.set(item, "duration", "")
            worker = threading.Thread(
                target=self._convert_in_background,
                args=(
                    item,
                    url,
                    destination,
                    heading_content,
                    cancel_event,
                ),
                daemon=True,
            )
            worker.start()
        self._schedule_duration_updates()
        self.status.configure(
            text=f"Started {len(jobs)} conversion(s); "
            f"{len(self._running_jobs)} running."
        )
        self._schedule_job_button_layout()
        self._schedule_save()

    def _set_job_status(self, item, text):
        if self.job_tree.exists(item):
            self.job_tree.set(item, "status", text)
        active = self._run_total - self._run_completed
        self.status.configure(
            text=f"{text} ({self._run_completed}/{self._run_total} complete; "
            f"{active} active)"
        )

    def _convert_in_background(
        self, item, url, destination, heading_content, cancel_event
    ):
        warnings = []
        try:
            if cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")
            self.root.after(0, self._set_job_status, item, "Fetching")
            skipped_images = []
            text, images = fetch_latest_response_with_images(url, skipped_images)
            if skipped_images:
                warnings.append(
                    f"{len(skipped_images)} image(s) were skipped and are NOT "
                    "in the Word file:\n- " + "\n- ".join(skipped_images)
                )
            if cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")

            table_count = _count_markdown_tables(text)
            code_count = (
                len(_fenced_code_blocks(text))
                if SCREENSHOT_CODE_BLOCKS and CODE_BLOCK_IMAGE_STYLE == "chatgpt"
                else 0
            )
            table_screenshots = []
            code_screenshots = []

            if table_count or code_count:
                self.root.after(
                    0,
                    self._set_job_status,
                    item,
                    "Capturing screenshots",
                )
                capture_error = None
                try:
                    table_screenshots, code_screenshots = _capture_chatgpt_screenshots(
                        url,
                        want_tables=bool(table_count),
                        want_code=bool(code_count),
                        cancel_event=cancel_event,
                        expected_tables=table_count or None,
                    )
                except RuntimeError as screenshot_error:
                    if str(screenshot_error) == "Conversion cancelled.":
                        raise
                    capture_error = screenshot_error
                except Exception as screenshot_error:
                    capture_error = screenshot_error

                if capture_error is not None:
                    warnings.append(
                        "Screenshots failed with an error:\n"
                        f"{type(capture_error).__name__}: {capture_error}"
                    )
                    table_screenshots = []
                    code_screenshots = []
                else:
                    if table_count and not any(table_screenshots):
                        warnings.append(
                            "Could not capture the table screenshots after 3 attempts "
                            "(the ChatGPT page did not finish loading, or "
                            "Selenium/Chrome is not available)."
                        )
                        table_screenshots = []
                    elif table_count and sum(
                        1 for shot in table_screenshots if shot
                    ) < table_count:
                        captured = sum(1 for shot in table_screenshots if shot)
                        warnings.append(
                            f"Captured {captured} of {table_count} table "
                            "screenshot(s) from the page. They were matched to "
                            "their tables by content, and the other "
                            f"{table_count - captured} table image(s) were drawn "
                            "from the text instead."
                        )
                    if code_count and not any(code_screenshots):
                        warnings.append(
                            "Could not capture the plain-text (code block) "
                            "screenshots after 3 attempts; a generated plain-text image "
                            "was used instead."
                        )
                        code_screenshots = []
                    elif code_count and len(code_screenshots) != code_count:
                        warnings.append(
                            f"Captured {len(code_screenshots)} plain-text screenshot(s) "
                            f"but the reply has {code_count} plain-text block(s), so "
                            "a generated plain-text image was used instead."
                        )
                        code_screenshots = []

            if cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")
            self.root.after(0, self._set_job_status, item, "Saving")
            with _OUTPUT_LOCK:
                if not destination:
                    with _OUTPUT_PATHS_LOCK:
                        candidate = Path(default_output_path(text))
                        base = candidate
                        suffix = 2
                        while (
                            os.path.normcase(os.path.abspath(candidate))
                            in self._reserved_output_paths
                            or candidate.exists()
                        ):
                            candidate = base.with_name(
                                f"{base.stem} ({suffix}){base.suffix}"
                            )
                            suffix += 1
                        destination = str(candidate)
                        self._reserved_output_paths.add(
                            os.path.normcase(os.path.abspath(destination))
                        )
                if cancel_event.is_set():
                    raise RuntimeError("Conversion cancelled.")
                destination = save_docx(
                    text,
                    destination,
                    images,
                    heading_content,
                    table_screenshots=table_screenshots,
                    code_screenshots=code_screenshots,
                ) or destination
        except RuntimeError as error:
            if str(error) == "Conversion cancelled.":
                self.root.after(0, self._finish_conversion, item, None, None, True)
            else:
                self.root.after(0, self._finish_conversion, item, None, error, False)
        except Exception as error:
            if cancel_event.is_set():
                self.root.after(0, self._finish_conversion, item, None, None, True)
                return
            self.root.after(0, self._finish_conversion, item, None, error, False)
        else:
            self.root.after(
                0,
                self._finish_conversion,
                item,
                destination,
                None,
                False,
                tuple(warnings),
            )

    def _finish_conversion(
        self, item, destination, error, cancelled=False, warnings=()
    ):
        self._running_jobs.pop(item, None)
        self._run_completed += 1
        self._record_job_duration(item)
        if not self._running_jobs:
            self._stop_duration_updates()
        job_destination = destination or self.job_tree.set(item, "destination")
        filename = Path(job_destination).name if job_destination else "the selected reply"
        if cancelled:
            final_status = "Cancelled"
            self.job_tree.set(item, "status", final_status)
            if self.notify_var.get():
                _notify_windows(
                    "ChatGPT to Word - cancelled",
                    f"Cancelled conversion for {filename}.",
                )
        elif error is not None:
            final_status = "Failed"
            self.job_tree.set(item, "status", final_status)
            self.show_error_dialog(error, modal=False)
            if self.notify_var.get():
                _notify_windows(
                    "ChatGPT to Word - failed",
                    f"Could not convert {filename}: {str(error)[:140]}",
                )
        else:
            final_status = "Saved with warnings" if warnings else "Saved"
            self.job_tree.set(item, "status", final_status)
            self.job_tree.set(item, "destination", destination)
            if warnings:
                self.show_warning_dialog(destination, warnings)
                if self.notify_var.get():
                    _notify_windows(
                        "ChatGPT to Word - saved with warnings",
                        f"{Path(destination).name} was saved with warnings.",
                    )
            elif self.notify_var.get():
                _notify_windows(
                    "ChatGPT to Word - done",
                    f"Saved {Path(destination).name}.",
                )
        if not self.job_tree.set(item, "copy_destination").strip():
            default_copy_destination = self._normalize_copy_destination(
                self.copy_destination_default_var.get()
            )
            if default_copy_destination:
                self.job_tree.set(
                    item, "copy_destination", default_copy_destination
                )
        self._run_statuses[item] = final_status
        self._schedule_save()
        self._schedule_job_button_layout()

        self.progress.configure(
            value=100 * self._run_completed / max(self._run_total, 1)
        )
        if self._running_jobs:
            self.status.configure(
                text=f"{self._run_completed}/{self._run_total} conversion(s) complete; "
                f"{len(self._running_jobs)} still running."
            )
            return

        self.progress.grid_remove()
        self.convert_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.add_job_button.configure(state="normal")
        self.remove_job_button.configure(state="normal")
        self.browse_destination_button.configure(state="normal")
        self.clear_all_button.configure(
            state="disabled" if self._copying_rows else "normal"
        )
        with _OUTPUT_PATHS_LOCK:
            self._reserved_output_paths = set()
        statuses = [self._run_statuses[row] for row in self._run_items]
        failures = statuses.count("Failed")
        cancelled_count = statuses.count("Cancelled")
        warning_count = statuses.count("Saved with warnings")
        if failures:
            self.status.configure(
                text=f"{self._run_total - failures - cancelled_count} saved; "
                f"{failures} failed; {cancelled_count} cancelled."
            )
            return
        if cancelled_count:
            self.status.configure(
                text=f"{self._run_total - cancelled_count} saved; "
                f"{cancelled_count} cancelled."
            )
            return
        if warning_count:
            self.status.configure(
                text=f"Saved {self._run_completed} conversion(s); "
                f"{warning_count} with warnings."
            )
        else:
            self.status.configure(text=f"Saved {self._run_completed} conversion(s).")
def main():
    _bind_children_to_process_lifetime()
    root = tk.Tk()
    ChatGPTToDocxApp(root)
    root.mainloop()
    _force_exit()


if __name__ == "__main__":
    main()