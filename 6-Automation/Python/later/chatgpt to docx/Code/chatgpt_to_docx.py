import base64
import ctypes
import io
import json
import os
import re
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
_CONSOLE_CTRL_HANDLER = None


def _install_console_close_handler():
    """Keep the GUI process alive when the user closes the attached console window."""
    global _CONSOLE_CTRL_HANDLER
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32.dll")
    except (AttributeError, OSError):
        return False

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong)
    def _handler(ctrl_type):
        if ctrl_type == 2:  # CTRL_CLOSE_EVENT
            return 1
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


def _image_specs(text, metadata):
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
            group_urls = [
                url for url in image_urls if "purpose=fullsize" in url
            ] or [
                url for url in image_urls if "purpose=inline" in url
            ]
            if not group_urls:
                raise ValueError(
                    "The shared reply contains an image group without "
                    "downloadable ChatGPT images."
                )
            specs.extend((placeholder.group(), url) for url in group_urls)
            continue
        url = next(
            (item for item in image_urls if "purpose=fullsize" in item),
            next(
                (item for item in image_urls if "purpose=inline" in item),
                None,
            ),
        )
        if not url:
            raise ValueError(
                "The shared reply contains an image that ChatGPT did not "
                "provide as a downloadable image."
            )
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


def fetch_latest_response_with_images(url):
    text, metadata = _fetch_response_record(url)
    images = [
        _download_shared_image(placeholder, image_url)
        for placeholder, image_url in _image_specs(text, metadata)
    ]
    return text, images


def fetch_latest_response(url):
    text, _metadata = _fetch_response_record(url)
    return text


def extract_latest_response(html):
    text, _metadata = _latest_response_record(html)
    return _normalize_image_placeholders(_replace_entity_tags(text))


_IMAGE_PLACEHOLDER_RE = re.compile(r"<AsyncImage(?:Group)?\b[^>]*?/?>")
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
    """Collapse each (possibly multi-line) image tag onto its own single line."""
    return _IMAGE_PLACEHOLDER_RE.sub(
        lambda match: "\n" + re.sub(r"\s+", " ", match.group()).strip() + "\n",
        text,
    )


def _clean_inline_text(text):
    text = _replace_entity_tags(text)
    text = _IMAGE_PLACEHOLDER_RE.sub("", text)
    text = re.sub(
        r"</?(?:box|row|divider)\b[^>]*?/?>",
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


def _merge_nary_bodies(nodes):
    merged = []
    index = 0
    while index < len(nodes):
        node = nodes[index]
        merged.append(node)
        if (
            node.tag.endswith("}nary")
            and node.find("{http://schemas.openxmlformats.org/officeDocument/2006/math}e") is None
            and index + 1 < len(nodes)
        ):
            body = _math_element("e")
            _append_script_content(body, nodes[index + 1])
            node.append(body)
            index += 2
            continue
        index += 1
    return merged


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
        "cdot": "·",
        "cdots": "⋯",
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
        "perp": "⊥",
        "vert": "|",
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

    def __init__(self, expression):
        self.tokens = re.findall(
            r"\\[A-Za-z]+|\\.|[A-Za-z]+|\d+(?:\.\d+)?|"
            r"\s+|.",
            expression,
        )
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

    def _fraction_argument(self):
        while self.position < len(self.tokens) and self.tokens[self.position].isspace():
            self.position += 1
        if self.position < len(self.tokens):
            token = self.tokens[self.position]
            if re.fullmatch(r"\d{2,}", token):
                self.tokens[self.position] = token[1:]
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
            if command in {"left", "right"}:
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
            if command in {"text", "mathrm"}:
                return self._group(preserve_whitespace=command == "text")
            if command in {"sum", "prod", "int"}:
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
            if command in self.COMMANDS:
                return _math_run(self.COMMANDS[command])
            return _math_run(command)
        return _math_run(token)

    def _sequence(self, closing=None, preserve_whitespace=False):
        nodes = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token == closing:
                break
            if token.isspace() and not preserve_whitespace:
                self.position += 1
                continue
            if token in {"^", "_"} and nodes:
                self.position += 1
                script = self._group()
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
                r"</?(?:box|row|divider)\b[^>]*?/?>",
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
        r"(\\\(.+?\\\)|\\\[.+?\\\]|\$.+?\$|\*\*.+?\*\*|__.+?__|"
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


def _capture_chatgpt_screenshots(
    url,
    want_tables=True,
    want_code=False,
    cancel_event=None,
    attempts=3,
):
    """One browser session: returns (table_screenshots, code_screenshots)."""
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
        driver = webdriver.Chrome(options=_build_chrome_options())
        try:
            driver.get(url)
            ready = _wait_for_page_content(
                driver,
                cancel_event=cancel_event,
                content_selector=selector,
            )
            assistant_messages = driver.find_elements(
                By.CSS_SELECTOR,
                '[data-message-author-role="assistant"]',
            )
            last_message = assistant_messages[-1] if assistant_messages else None
            tables = (
                last_message.find_elements(By.CSS_SELECTOR, "table")
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
                continue  # page did not hydrate: retry with a fresh browser

            table_screenshots = []
            for table in tables:
                check_cancel()
                try:
                    size = table.size
                    if size["width"] < 50 or size["height"] < 30:
                        continue
                    table_screenshots.append(_element_to_png_bytes(driver, table))
                except RuntimeError:
                    raise
                except Exception:
                    table_screenshots.append(None)

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

            if any(table_screenshots) or any(code_screenshots):
                return table_screenshots, code_screenshots
        finally:
            driver.quit()
    return [], []


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
    table_screenshots = list(table_screenshots)
    code_screenshots = list(code_screenshots)
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
        if re.fullmatch(r"</?(?:box|row|divider)\b[^>]*?/?>", stripped, re.IGNORECASE):
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

        if re.match(r"^(---+|___+|\*\*\*+)\s*$", stripped):
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
                    screenshot_data = table_screenshots.pop(0) if table_screenshots else None
                    if screenshot_data:
                        _add_table_screenshot(document, rows, screenshot_data)
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
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1600,1200")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-features=UseSkiaRenderer")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return chrome_options


_HIDE_OVERLAYS_JS = """
for (const el of document.querySelectorAll('body *')) {
  const pos = getComputedStyle(el).position;
  if ((pos === 'fixed' || pos === 'sticky')
      && !el.closest('table, pre, [data-capture-keep]')
      && !el.querySelector('table, pre, [data-capture-keep]')) {
    el.style.setProperty('visibility', 'hidden', 'important');
  }
}
"""


def _png_is_blank(png_bytes):
    if Image is None:
        return False
    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    low, high = image.getextrema()
    return (high - low) < 8


def _element_to_png_bytes(driver, element, attempts=3):
    driver.execute_script(_HIDE_OVERLAYS_JS)
    for _attempt in range(attempts):
        height = driver.execute_script(
            "return Math.ceil(arguments[0].getBoundingClientRect().height);",
            element,
        )
        window_height = driver.execute_script("return window.innerHeight;")
        if height + 200 > window_height:
            driver.set_window_size(1600, height + 400)

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            element,
        )
        time.sleep(0.8)
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
                "fromSurface": True,
                "captureBeyondViewport": False,
                "clip": {**rect, "scale": 1},
            },
        )
        png = base64.b64decode(shot["data"])
        if not _png_is_blank(png):
            return png
        time.sleep(1.0)
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
    stable_seconds=3.0,
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

    driver = webdriver.Chrome(options=_build_chrome_options())
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
        driver.quit()

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
    with open(destination, "wb") as output:
        output.write(finalized_package.getvalue())


class ChatGPTToDocxApp:
    def __init__(self, root):
        self.root = root
        self.state_path = app_state_path()
        self._hidden = False
        self.console_visible = False
        self.tray_icon = None
        self._tray_started = False
        root.title("ChatGPT to Word")
        root.minsize(680, 500)
        root.protocol("WM_DELETE_WINDOW", self.hide_window)

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="ChatGPT share link:").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 12)
        )
        self.url_entry = ttk.Entry(frame, width=58)
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=(0, 12))

        ttk.Label(frame, text="Save Word file to:").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 12)
        )
        self.destination_entry = ttk.Entry(frame)
        self.destination_entry.grid(row=1, column=1, sticky="ew", pady=(0, 12))
        ttk.Button(frame, text="Browse...", command=self.choose_destination).grid(
            row=1, column=2, padx=(8, 0), pady=(0, 12)
        )

        ttk.Label(
            frame,
            text="Formatted text after headings (skip headings with subheadings):",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))
        clear_button_frame = ttk.Frame(frame)
        clear_button_frame.grid(row=2, column=2, sticky="e", pady=(8, 4))
        ttk.Button(
            clear_button_frame,
            text="Clear",
            command=self.clear_pasted_text,
        ).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(
            clear_button_frame,
            text="Clear all",
            command=self.clear_all_fields,
        ).grid(row=0, column=1)
        pasted_frame = ttk.Frame(frame)
        pasted_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
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

        self.console_button = ttk.Button(
            frame,
            text="Open console",
            command=self.open_console,
        )
        self.console_button.grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.convert_button = ttk.Button(
            frame, text="Convert latest reply", command=self.convert
        )
        self.convert_button.grid(row=4, column=1, sticky="e", pady=(10, 0))
        self.cancel_button = ttk.Button(
            frame,
            text="Cancel",
            command=self.cancel_conversion,
            state="disabled",
        )
        self.cancel_button.grid(row=4, column=2, sticky="e", pady=(10, 0))
        self.progress = ttk.Progressbar(
            frame,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()
        self.status = ttk.Label(frame, text="Only public ChatGPT share links are supported.")
        self.status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._cancel_event = threading.Event()
        self.restore_state()

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
                "url": self.url_entry.get().strip(),
                "destination": self.destination_entry.get().strip(),
                "paragraphs": serialized,
            }
            with self.state_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False)
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
        url = payload.get("url", "")
        destination = payload.get("destination", "")
        paragraphs = payload.get("paragraphs", [])
        if url:
            self.url_entry.insert(0, url)
        if destination:
            self.destination_entry.insert(0, destination)
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

    def exit_app(self):
        self.save_state()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self._tray_started = False
        self.root.destroy()

    def clear_pasted_text(self):
        self.pasted_text.delete("1.0", "end")
        self.pasted_text.focus_set()

    def clear_all_fields(self):
        self.url_entry.delete(0, tk.END)
        self.destination_entry.delete(0, tk.END)
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
        destination = filedialog.asksaveasfilename(
            title="Save Word document",
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
            initialfile="chatgpt-response.docx",
        )
        if destination:
            self.destination_entry.delete(0, tk.END)
            self.destination_entry.insert(0, destination)

    def show_error_dialog(self, error):
        error_text = f"{type(error).__name__}: {error}"
        dialog = tk.Toplevel(self.root)
        dialog.title("Could not convert link")
        dialog.transient(self.root)
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=16)
        frame.grid(sticky="nsew")
        ttk.Label(
            frame,
            text="The conversion failed. Copy the error below if you need help:",
            wraplength=420,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        details = tk.Text(frame, width=58, height=5, wrap="word")
        details.insert("1.0", error_text)
        details.configure(state="disabled")
        details.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        def copy_error():
            self.root.clipboard_clear()
            self.root.clipboard_append(error_text)
            self.root.update()
            dialog.destroy()
            self.status.configure(text="Error copied to clipboard.")

        ttk.Button(frame, text="Copy error", command=copy_error).grid(
            row=2, column=0, sticky="e", padx=(0, 8)
        )
        ttk.Button(frame, text="Close", command=dialog.destroy).grid(
            row=2, column=1, sticky="e"
        )
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.grab_set()
        dialog.focus_set()

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
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status.configure(text="Cancelling conversion...")

    def convert(self):
        if self._cancel_event.is_set():
            self._cancel_event.clear()
        url = self.url_entry.get().strip()
        destination = self.destination_entry.get().strip()
        heading_content = self._pasted_text_content()

        self.convert_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._set_progress(0, "Fetching the latest reply...")
        self.progress.grid()
        worker = threading.Thread(
            target=self._convert_in_background,
            args=(url, destination, heading_content),
            daemon=True,
        )
        worker.start()

    def _convert_in_background(self, url, destination, heading_content):
        warnings = []
        try:
            if self._cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")
            self.root.after(0, self._set_progress, 10, "Fetching the latest reply...")
            text, images = fetch_latest_response_with_images(url)
            if self._cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")

            table_pattern = r"^\s*\|.+\|\s*$\n^\s*\|?[\s:|-]+\|?\s*$"
            table_count = len(
                re.findall(
                    table_pattern,
                    _text_without_code_blocks(text),
                    re.MULTILINE,
                )
            )
            code_count = (
                len(_fenced_code_blocks(text)) if SCREENSHOT_CODE_BLOCKS else 0
            )
            table_screenshots = []
            code_screenshots = []

            if table_count or code_count:
                self.root.after(
                    0,
                    self._set_progress,
                    40,
                    "Capturing table / plain-text screenshots...",
                )
                capture_error = None
                try:
                    table_screenshots, code_screenshots = _capture_chatgpt_screenshots(
                        url,
                        want_tables=bool(table_count),
                        want_code=bool(code_count),
                        cancel_event=self._cancel_event,
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
                    elif table_count and len(table_screenshots) != table_count:
                        warnings.append(
                            f"Captured {len(table_screenshots)} table screenshot(s) "
                            f"but the reply has {table_count} table(s), so the "
                            "screenshots were skipped."
                        )
                        table_screenshots = []
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

            if self._cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")
            self.root.after(0, self._set_progress, 75, "Saving Word document...")
            if not destination:
                destination = str(default_output_path(text))
            if self._cancel_event.is_set():
                raise RuntimeError("Conversion cancelled.")
            save_docx(
                text,
                destination,
                images,
                heading_content,
                table_screenshots=table_screenshots,
                code_screenshots=code_screenshots,
            )
        except RuntimeError as error:
            if str(error) == "Conversion cancelled.":
                self.root.after(0, self._finish_conversion, None, None, True)
            else:
                self.root.after(0, self._finish_conversion, None, error, False)
        except Exception as error:
            if self._cancel_event.is_set():
                self.root.after(0, self._finish_conversion, None, None, True)
                return
            self.root.after(0, self._finish_conversion, None, error, False)
        else:
            self.root.after(
                0,
                self._finish_conversion,
                destination,
                None,
                False,
                tuple(warnings),
            )

    def _finish_conversion(self, destination, error, cancelled=False, warnings=()):
        self.progress.configure(value=100)
        self.progress.grid_remove()
        self.convert_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._cancel_event.clear()
        if cancelled:
            self.status.configure(text="Conversion cancelled.")
            return
        if error is not None:
            self.status.configure(text="Conversion failed.")
            self.show_error_dialog(error)
            return

        if not self.destination_entry.get().strip():
            self.destination_entry.insert(0, destination)

        if warnings:
            self.status.configure(text=f"Saved with warnings: {destination}")
            messagebox.showwarning(
                "Saved, but some screenshots are missing",
                "Word document saved to:\n"
                f"{destination}\n\n"
                + "\n\n".join(warnings)
                + "\n\nThe content was still built from the text, but without "
                "the missing screenshot images. Try converting again if you need them.",
            )
        else:
            self.status.configure(text=f"Saved: {destination}")
            messagebox.showinfo(
                "Conversion complete",
                f"Word document saved to:\n{destination}",
            )

def main():
    root = tk.Tk()
    ChatGPTToDocxApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()