"""
Convert Word files (.docx / .doc) to plain text - GUI version.
Run with no arguments to open the window.
Equations and special symbols are converted to LaTeX:

  * Word equations (OMML)  -> $...$ (inline) or $$...$$ (display)
  * Greek letters, math operators, arrows, set/logic symbols in normal text
    -> inline LaTeX, e.g.  "α ≤ β"  ->  "$\\alpha \\leq \\beta$"
  * Superscript / subscript runs  -> $^{2}$ / $_{i}$
  * Symbol-font characters (Insert > Symbol) -> LaTeX

Usage:
    python doc_to_txt_gui.py                   (opens the window)
    python doc_to_txt_gui.py file.docx         (command line)
    python doc_to_txt.py file.doc out.txt
    python doc_to_txt.py folder_with_docs     (converts every .doc/.docx inside)

Requirements:
    .docx : nothing (standard library only)
    .doc  : LibreOffice installed (any OS)  or  pywin32 + MS Word (Windows).
            The .doc is first converted to .docx, then processed.

Limitations:
    Old-style equation objects (Equation Editor 3.0 / MathType OLE objects) and
    equations pasted as pictures cannot be converted; they are replaced by the
    placeholder [EQUATION OBJECT - not convertible].
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def w(name):
    return f"{{{W}}}{name}"


def m(name):
    return f"{{{M}}}{name}"


def local(el):
    t = el.tag
    return t.rsplit("}", 1)[-1] if isinstance(t, str) else ""


WARNINGS = []

# --------------------------------------------------------------------------
# Symbol tables (Unicode char -> LaTeX command)
# --------------------------------------------------------------------------
GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "varepsilon",
    "ϵ": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta", "ϑ": "vartheta",
    "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "µ": "mu", "ν": "nu",
    "ξ": "xi", "π": "pi", "ϖ": "varpi", "ρ": "rho", "ϱ": "varrho",
    "σ": "sigma", "ς": "varsigma", "τ": "tau", "υ": "upsilon", "φ": "phi",
    "ϕ": "varphi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "∆": "Delta", "Θ": "Theta", "Λ": "Lambda",
    "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma", "Υ": "Upsilon", "Φ": "Phi",
    "Ψ": "Psi", "Ω": "Omega", "Ω": "Omega",
}

OTHER = {
    # operators
    "±": "pm", "∓": "mp", "×": "times", "÷": "div", "·": "cdot", "⋅": "cdot",
    "∙": "cdot", "∘": "circ", "•": "bullet", "⊕": "oplus", "⊖": "ominus",
    "⊗": "otimes", "⊙": "odot", "†": "dagger", "‡": "ddagger", "√": "surd",
    "∗": "ast", "⋆": "star",
    # relations
    "≤": "leq", "≥": "geq", "≠": "neq", "≈": "approx", "≡": "equiv",
    "≅": "cong", "∼": "sim", "≃": "simeq", "∝": "propto", "≪": "ll",
    "≫": "gg", "≺": "prec", "≻": "succ", "⪯": "preceq", "⪰": "succeq",
    "⊥": "perp", "∥": "parallel", "∣": "mid", "≰": "nleq", "≱": "ngeq",
    "≢": "not\\equiv", "≔": "coloneqq", "≐": "doteq", "∽": "backsim",
    # sets
    "∈": "in", "∉": "notin", "∋": "ni", "⊂": "subset", "⊃": "supset",
    "⊆": "subseteq", "⊇": "supseteq", "⊄": "not\\subset", "⊊": "subsetneq",
    "⊋": "supsetneq", "∪": "cup", "∩": "cap", "∅": "emptyset",
    "∖": "setminus", "⊎": "uplus", "⊔": "sqcup", "⊓": "sqcap",
    # logic
    "∀": "forall", "∃": "exists", "∄": "nexists", "¬": "neg", "∧": "wedge",
    "∨": "vee", "⊢": "vdash", "⊨": "models", "⊤": "top", "∴": "therefore",
    "∵": "because",
    # arrows
    "→": "rightarrow", "←": "leftarrow", "↔": "leftrightarrow",
    "⇒": "Rightarrow", "⇐": "Leftarrow", "⇔": "Leftrightarrow",
    "↑": "uparrow", "↓": "downarrow", "⇑": "Uparrow", "⇓": "Downarrow",
    "↦": "mapsto", "⟶": "longrightarrow", "⟵": "longleftarrow",
    "⟹": "Longrightarrow", "⟸": "Longleftarrow", "⟺": "Longleftrightarrow",
    "↗": "nearrow", "↘": "searrow", "↙": "swarrow", "↖": "nwarrow",
    "⇌": "rightleftharpoons", "↪": "hookrightarrow", "↠": "twoheadrightarrow",
    # misc
    "∞": "infty", "∂": "partial", "∇": "nabla", "ℏ": "hbar", "ℓ": "ell",
    "℘": "wp", "ℜ": "Re", "ℑ": "Im", "ℵ": "aleph", "∠": "angle",
    "△": "triangle", "∎": "blacksquare", "□": "square", "…": "ldots",
    "⋯": "cdots", "⋮": "vdots", "⋱": "ddots",
    # big operators
    "∑": "sum", "∏": "prod", "∐": "coprod", "∫": "int", "∬": "iint",
    "∭": "iiint", "∮": "oint", "⋃": "bigcup", "⋂": "bigcap", "⋁": "bigvee",
    "⋀": "bigwedge",
    # delimiters
    "⟨": "langle", "⟩": "rangle", "〈": "langle", "〉": "rangle",
    "⌈": "lceil", "⌉": "rceil", "⌊": "lfloor", "⌋": "rfloor",
}

SYMBOLS = {k: "\\" + v for k, v in {**GREEK, **OTHER}.items()}
SYMBOLS.update({
    "′": "'", "″": "''", "‖": "\\|", "°": "^{\\circ}", "∕": "/", "⁄": "/",
    "ℝ": "\\mathbb{R}", "ℕ": "\\mathbb{N}", "ℤ": "\\mathbb{Z}",
    "ℚ": "\\mathbb{Q}", "ℂ": "\\mathbb{C}", "ℙ": "\\mathbb{P}",
    "ℍ": "\\mathbb{H}", "ℎ": "h",
    "¼": "\\frac{1}{4}", "½": "\\frac{1}{2}", "¾": "\\frac{3}{4}",
    "⅓": "\\frac{1}{3}", "⅔": "\\frac{2}{3}",
    "ⁿ": "^{n}", "⁺": "^{+}", "⁻": "^{-}",
})
for i, ch in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹"):
    SYMBOLS[ch] = "^{%d}" % i
for i, ch in enumerate("₀₁₂₃₄₅₆₇₈₉"):
    SYMBOLS[ch] = "_{%d}" % i

ASCII_FIX = {"−": "-", "∕": "/", "⁄": "/", "∶": ":"}   # no $...$ needed
PLAIN_KEEP = {"…", "•", "′", "″"}                       # leave alone in prose
MATH_ESC = {"%": "\\%", "#": "\\#", "$": "\\$", "_": "\\_", "{": "\\{",
            "}": "\\}", "\\": "\\backslash "}
TEXT_ESC = {"%": "\\%", "#": "\\#", "$": "\\$", "_": "\\_", "{": "\\{",
            "}": "\\}", "&": "\\&", "~": "\\~{}", "^": "\\^{}",
            "\\": "\\textbackslash{}"}


def _cmd(s):
    """Add a trailing space after a bare \\command so it can't glue to letters."""
    return s + " " if s[-1:].isalpha() else s


def math_alnum(c):
    """Mathematical alphanumeric block (U+1D400..) -> \\mathbb{R}, \\mathcal{F}, ..."""
    if not 0x1D400 <= ord(c) <= 0x1D7FF:
        return None
    name = unicodedata.name(c, "")
    base = unicodedata.normalize("NFKC", c)
    greek = SYMBOLS.get(base)
    if "DOUBLE-STRUCK" in name:
        return "\\mathbb{%s}" % base
    if "SCRIPT" in name:
        return "\\mathcal{%s}" % base
    if "FRAKTUR" in name:
        return "\\mathfrak{%s}" % base
    if "MONOSPACE" in name:
        return "\\mathtt{%s}" % base
    if "SANS-SERIF" in name:
        return "\\mathsf{%s}" % base
    if "BOLD" in name and "ITALIC" not in name:
        return "\\boldsymbol{%s}" % greek if greek else "\\mathbf{%s}" % base
    return greek if greek else base


def symbol_latex(c):
    """LaTeX for one character, or None if it is an ordinary character."""
    if c in SYMBOLS:
        return SYMBOLS[c]
    return math_alnum(c)


def math_text(s):
    """Text inside an equation -> LaTeX."""
    out = []
    for c in s:
        if c in ASCII_FIX:
            out.append(ASCII_FIX[c])
            continue
        t = symbol_latex(c)
        out.append(_cmd(t) if t is not None else MATH_ESC.get(c, c))
    return "".join(out)


def plain_text(s, esc=False):
    """Ordinary prose: only special symbols get wrapped in $...$."""
    out, buf = [], []

    def flush():
        if buf:
            out.append("$" + "".join(buf).strip() + "$")
            buf.clear()

    def is_sym(ch):
        return ch not in ASCII_FIX and ch not in PLAIN_KEEP and symbol_latex(ch) is not None

    for i, c in enumerate(s):
        if c in ASCII_FIX:
            flush(); out.append(ASCII_FIX[c])
        elif c in PLAIN_KEEP:
            flush(); out.append(c)
        elif c == " " and buf and i + 1 < len(s) and is_sym(s[i + 1]):
            if not buf[-1].endswith(" "):
                buf.append(" ")      # "α ≤ β" stays one $...$ group
        else:
            t = symbol_latex(c)
            if t is not None:
                buf.append(_cmd(t))
            else:
                flush(); out.append(TEXT_ESC.get(c, c) if esc else c)
    flush()
    return "".join(out)


# Word "Symbol" font (Insert > Symbol) code points -> Unicode
SYMBOL_FONT = {}
for a, b in zip("abcdefghijklmnopqrstuvwxyz",
                "αβχδεφγηιϕκλμνοπθρστυϖωξψζ"):
    SYMBOL_FONT[ord(a)] = b
for a, b in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                "ABXΔEΦΓHIϑKΛMNOΠΘPΣTΥςΩΞΨZ"):
    SYMBOL_FONT[ord(a)] = b
SYMBOL_FONT.update({
    0xA3: "≤", 0xB3: "≥", 0xB9: "≠", 0xBB: "≈", 0xBA: "≡", 0xB1: "±",
    0xB4: "×", 0xB8: "÷", 0xB7: "•", 0xA5: "∞", 0xB6: "∂", 0xD1: "∇",
    0xB0: "°", 0xAE: "→", 0xAC: "←", 0xAB: "↔", 0xAD: "↑", 0xAF: "↓",
    0xDE: "⇒", 0xDC: "⇐", 0xDB: "⇔", 0xD6: "√", 0xE5: "∑", 0xD5: "∏",
    0xF2: "∫", 0xCE: "∈", 0xCF: "∉", 0xCC: "⊂", 0xC9: "⊃", 0xCD: "⊆",
    0xCA: "⊇", 0xC8: "∪", 0xC7: "∩", 0xC6: "∅", 0xD9: "∧", 0xDA: "∨",
    0xD8: "¬", 0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2D: "−", 0x40: "≅",
    0x5E: "⊥", 0x7E: "∼", 0xB5: "∝", 0xA2: "′", 0xB2: "″", 0xBC: "…",
    0xD0: "∠", 0xC5: "⊕", 0xC4: "⊗", 0xD7: "⋅", 0xC0: "ℵ",
})


def sym_element_char(el):
    font = (el.get(w("font")) or "").lower()
    try:
        code = int(el.get(w("char")), 16)
    except (TypeError, ValueError):
        return "?"
    if code >= 0xF000:
        code -= 0xF000
    if "symbol" in font:
        return SYMBOL_FONT.get(code, "?")
    return chr(code)


# --------------------------------------------------------------------------
# OMML (Word equation) -> LaTeX
# --------------------------------------------------------------------------
FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "coth", "log", "ln", "lg", "exp", "lim", "liminf",
    "limsup", "max", "min", "sup", "inf", "det", "dim", "ker", "gcd", "deg",
    "arg", "hom", "Pr",
}
LIMIT_FUNCS = {"lim", "liminf", "limsup", "max", "min", "sup", "inf", "Pr", "det", "gcd"}

DELIM = {
    "(": "(", ")": ")", "[": "[", "]": "]", "{": "\\{", "}": "\\}", "|": "|",
    "‖": "\\|", "⟨": "\\langle", "⟩": "\\rangle", "〈": "\\langle",
    "〉": "\\rangle", "⌈": "\\lceil", "⌉": "\\rceil", "⌊": "\\lfloor",
    "⌋": "\\rfloor", "": ".", "/": "/", "\\": "\\backslash",
}
ACC = {
    "\u0302": "hat", "^": "hat", "\u030c": "check", "ˇ": "check",
    "\u0303": "tilde", "~": "tilde", "˜": "tilde", "\u0301": "acute",
    "´": "acute", "\u0300": "grave", "`": "grave", "\u0307": "dot",
    "˙": "dot", "\u0308": "ddot", "¨": "ddot", "\u0304": "bar", "¯": "bar",
    "\u20d7": "vec", "→": "vec", "\u0306": "breve", "˘": "breve",
    "\u20db": "dddot",
}


def chr_prop(pr, name, default):
    """Value of <m:name m:val="..."/> inside a property element."""
    if pr is None:
        return default
    c = pr.find(m(name))
    if c is None:
        return default
    v = c.get(m("val"))
    return "" if v is None else v


def flag(pr, name):
    if pr is None:
        return False
    c = pr.find(m(name))
    if c is None:
        return False
    v = c.get(m("val"))
    return v is None or v.lower() not in ("0", "false", "off")


def raw_text(el):
    return "".join(t.text or "" for t in el.iter(m("t")))


def kids(el):
    return "".join(conv(c) for c in el if isinstance(c.tag, str))


def sub(el, name):
    c = el.find(m(name))
    return kids(c) if c is not None else ""


def conv(el):
    n = local(el)
    h = HANDLERS.get(n)
    if h:
        return h(el)
    if n.endswith("Pr"):
        return ""
    return kids(el)


def h_r(el):
    text = "".join(t.text or "" for t in el.findall(m("t")))
    text += "".join(t.text or "" for t in el.findall(w("t")))
    if not text:
        return ""
    pr = el.find(m("rPr"))
    if flag(pr, "nor"):
        return "\\text{" + plain_text(text, esc=True) + "}"
    sty = chr_prop(pr, "sty", "i")
    if sty == "p" and re.fullmatch(r"[A-Za-z0-9 ]+", text):
        return "\\mathrm{" + text.replace(" ", "\\ ") + "}"
    body = math_text(text)
    if sty == "b":
        return "\\mathbf{" + body + "}"
    if sty == "bi":
        return "\\boldsymbol{" + body + "}"
    return body


def h_f(el):
    typ = chr_prop(el.find(m("fPr")), "type", "bar")
    num, den = sub(el, "num"), sub(el, "den")
    if typ in ("lin", "skw"):
        return "{%s}/{%s}" % (num, den)
    if typ == "noBar":
        return "\\binom{%s}{%s}" % (num, den)
    return "\\frac{%s}{%s}" % (num, den)


def h_ssup(el):
    return "{%s}^{%s}" % (sub(el, "e"), sub(el, "sup"))


def h_ssub(el):
    return "{%s}_{%s}" % (sub(el, "e"), sub(el, "sub"))


def h_ssubsup(el):
    return "{%s}_{%s}^{%s}" % (sub(el, "e"), sub(el, "sub"), sub(el, "sup"))


def h_spre(el):
    return "{}_{%s}^{%s}{%s}" % (sub(el, "sub"), sub(el, "sup"), sub(el, "e"))


def h_rad(el):
    deg = sub(el, "deg").strip()
    hide = flag(el.find(m("radPr")), "degHide")
    if deg and not hide:
        return "\\sqrt[%s]{%s}" % (deg, sub(el, "e"))
    return "\\sqrt{%s}" % sub(el, "e")


def h_nary(el):
    pr = el.find(m("naryPr"))
    ch = chr_prop(pr, "chr", "∫")
    op = SYMBOLS.get(ch, ch) or "\\int"
    lo = "" if flag(pr, "subHide") else sub(el, "sub").strip()
    hi = "" if flag(pr, "supHide") else sub(el, "sup").strip()
    s = op
    if lo:
        s += "_{%s}" % lo
    if hi:
        s += "^{%s}" % hi
    return s + " " + sub(el, "e")


def h_d(el):
    pr = el.find(m("dPr"))
    b = chr_prop(pr, "begChr", "(")
    e_ = chr_prop(pr, "endChr", ")")
    beg, end = DELIM.get(b, b), DELIM.get(e_, e_)
    sep = chr_prop(pr, "sepChr", "|")
    parts = [kids(e) for e in el.findall(m("e"))]
    if sep in ("|", "‖"):
        joiner = " \\middle%s " % DELIM[sep]
    else:
        joiner = " %s " % math_text(sep)
    return "\\left%s %s \\right%s" % (beg, joiner.join(parts), end)


def h_func(el):
    fn = el.find(m("fName"))
    name = raw_text(fn).strip() if fn is not None else ""
    if name in FUNCS:
        head = "\\" + name
    elif name.isalpha():
        head = "\\operatorname{%s}" % name
    else:
        head = sub(el, "fName")
    return head + " " + sub(el, "e")


def h_acc(el):
    ch = chr_prop(el.find(m("accPr")), "chr", "\u0302")
    cmd = ACC.get(ch, "hat")
    e = sub(el, "e")
    if cmd in ("hat", "tilde") and len(e.strip()) > 2:
        cmd = "wide" + cmd
    return "\\%s{%s}" % (cmd, e)


def h_bar(el):
    pos = chr_prop(el.find(m("barPr")), "pos", "top")
    return ("\\underline{%s}" if pos == "bot" else "\\overline{%s}") % sub(el, "e")


def h_limlow(el):
    e = el.find(m("e"))
    name = raw_text(e).strip() if e is not None else ""
    lim = sub(el, "lim")
    if name in LIMIT_FUNCS:
        return "\\%s_{%s}" % (name, lim)
    return "\\underset{%s}{%s}" % (lim, sub(el, "e"))


def h_limupp(el):
    return "\\overset{%s}{%s}" % (sub(el, "lim"), sub(el, "e"))


def h_groupchr(el):
    pr = el.find(m("groupChrPr"))
    ch = chr_prop(pr, "chr", "⏟")
    pos = chr_prop(pr, "pos", "bot")
    over = ch == "⏞" or pos == "top"
    return ("\\overbrace{%s}" if over else "\\underbrace{%s}") % sub(el, "e")


def h_matrix(el):
    rows = []
    for mr in el.findall(m("mr")):
        rows.append(" & ".join(kids(e) for e in mr.findall(m("e"))))
    return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"


def h_eqarr(el):
    rows = [kids(e) for e in el.findall(m("e"))]
    return "\\begin{aligned} " + " \\\\ ".join(rows) + " \\end{aligned}"


def h_borderbox(el):
    return "\\boxed{%s}" % sub(el, "e")


HANDLERS = {
    "r": h_r, "f": h_f, "sSup": h_ssup, "sSub": h_ssub, "sSubSup": h_ssubsup,
    "sPre": h_spre, "rad": h_rad, "nary": h_nary, "d": h_d, "func": h_func,
    "acc": h_acc, "bar": h_bar, "limLow": h_limlow, "limUpp": h_limupp,
    "groupChr": h_groupchr, "m": h_matrix, "eqArr": h_eqarr,
    "borderBox": h_borderbox,
}


def omml_to_latex(el):
    s = kids(el)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# WordprocessingML (document body) -> text
# --------------------------------------------------------------------------
def has_equation_object(run):
    for node in run.iter():
        if local(node) == "OLEObject":
            prog = (node.get("ProgID") or "").lower()
            if "equation" in prog or "mathtype" in prog:
                return True
    return False


def run_text(r):
    parts = []
    for c in r:
        n = local(c)
        if n == "t":
            parts.append(c.text or "")
        elif n == "tab":
            parts.append("\t")
        elif n in ("br", "cr"):
            parts.append("\n")
        elif n == "noBreakHyphen":
            parts.append("-")
        elif n == "sym":
            parts.append(sym_element_char(c))
        elif n in ("object", "pict") and has_equation_object(c):
            WARNINGS.append("equation object")
            parts.append("[EQUATION OBJECT - not convertible]")
    text = "".join(parts)
    if not text:
        return ""
    rpr = r.find(w("rPr"))
    va = rpr.find(w("vertAlign")) if rpr is not None else None
    va = va.get(w("val")) if va is not None else None
    if va in ("superscript", "subscript") and text.strip():
        mark = "^" if va == "superscript" else "_"
        return "$%s{%s}$" % (mark, math_text(text))
    return plain_text(text)


PASS_THROUGH = {"hyperlink", "ins", "smartTag", "sdt", "sdtContent",
                "fldSimple", "moveTo", "customXml"}


def paragraph_text(p):
    out = []

    def walk(parent):
        for c in parent:
            if not isinstance(c.tag, str):
                continue
            n = local(c)
            if c.tag == w("r"):
                out.append(run_text(c))
            elif c.tag == m("oMathPara"):
                for om in c.findall(m("oMath")):
                    out.append("\n$$ " + omml_to_latex(om) + " $$\n")
            elif c.tag == m("oMath"):
                out.append("$" + omml_to_latex(c) + "$")
            elif n in PASS_THROUGH:
                walk(c)

    walk(p)
    return "".join(out).strip("\n")


def table_lines(tbl):
    for tr in tbl.findall(w("tr")):
        cells = []
        for tc in tr.findall(w("tc")):
            txt = " ".join(paragraph_text(p).strip().replace("\n", " ")
                           for p in tc.findall(w("p")))
            cells.append(txt.strip())
        yield "\t".join(cells)


def body_lines(parent):
    for el in parent:
        if not isinstance(el.tag, str):
            continue
        n = local(el)
        if n == "p":
            yield paragraph_text(el)
        elif n == "tbl":
            yield from table_lines(el)
        elif n in ("sdt", "sdtContent"):
            yield from body_lines(el)


def docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(w("body"))
    return "\n".join(body_lines(body))


# --------------------------------------------------------------------------
# .doc -> .docx, then reuse the docx path
# --------------------------------------------------------------------------
def doc_to_docx(path: Path, outdir: Path) -> Path:
    out = outdir / (path.stem + ".docx")

    candidates = [shutil.which("soffice"), shutil.which("libreoffice"),
                  r"C:\Program Files\LibreOffice\program\soffice.exe",
                  r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]
    soffice = next((c for c in candidates if c and Path(c).exists()), None)
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "docx",
                        "--outdir", str(outdir), str(path)],
                       check=True, capture_output=True)
        if out.exists():
            return out

    try:
        import win32com.client  # type: ignore
    except ImportError:
        raise RuntimeError("Can't read .doc: install LibreOffice, or "
                           "pywin32 + MS Word (Windows).")
    try:
        import pythoncom  # type: ignore
        pythoncom.CoInitialize()
    except ImportError:
        pass
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        d = word.Documents.Open(str(path.resolve()))
        d.SaveAs2(str(out), FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
        d.Close()
    finally:
        word.Quit()
    return out


def convert(src: Path, dst: Path | None = None) -> Path:
    ext = src.suffix.lower()
    if ext == ".docx":
        text = docx_to_text(src)
    elif ext == ".doc":
        with tempfile.TemporaryDirectory() as td:
            text = docx_to_text(doc_to_docx(src, Path(td)))
    else:
        raise ValueError(f"Unsupported file type: {src}")
    dst = dst or src.with_suffix(".txt")
    dst.write_text(text, encoding="utf-8")
    return dst


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = Path(sys.argv[1])
    if src.is_dir():
        for f in sorted(src.iterdir()):
            if f.suffix.lower() in (".doc", ".docx") and not f.name.startswith("~$"):
                print("Saved:", convert(f))
    else:
        dst = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        print("Saved:", convert(src, dst))

    if WARNINGS:
        print(f"Warning: {len(WARNINGS)} old-style equation object(s) could not "
              "be converted (marked in the text).", file=sys.stderr)


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def worker(files, out_dir, q):
    """Runs in a background thread so the window never freezes."""
    try:
        import pythoncom  # type: ignore  (needed for Word COM in a thread)
        pythoncom.CoInitialize()
    except Exception:
        pass
    WARNINGS.clear()
    for i, f in enumerate(files, 1):
        try:
            dst = Path(out_dir) / (f.stem + ".txt") if out_dir else None
            q.put(("ok", i, f, convert(f, dst)))
        except Exception as e:  # keep going with the other files
            q.put(("err", i, f, str(e)))
    q.put(("done", len(WARNINGS)))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Word to Text  (equations → LaTeX)")
        self.geometry("860x640")
        self.minsize(700, 520)

        self.files = []          # list[Path]
        self.results = {}        # source Path -> output Path
        self.q = queue.Queue()
        self.running = False
        self.same_folder = tk.BooleanVar(value=True)
        self.out_dir = tk.StringVar()
        self.status = tk.StringVar(value="Add .doc / .docx files to begin.")

        self._build()

    # ---- layout ----------------------------------------------------------
    def _build(self):
        pad = {"padx": 10, "pady": 4}

        # file list
        top = ttk.LabelFrame(self, text="Files to convert")
        top.pack(fill="x", **pad)
        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=6, pady=(6, 2))
        self.b_add = ttk.Button(btns, text="Add files…", command=self.add_files)
        self.b_folder = ttk.Button(btns, text="Add folder…", command=self.add_folder)
        self.b_remove = ttk.Button(btns, text="Remove selected", command=self.remove_selected)
        self.b_clear = ttk.Button(btns, text="Clear", command=self.clear)
        for b in (self.b_add, self.b_folder, self.b_remove, self.b_clear):
            b.pack(side="left", padx=(0, 6))

        lf = ttk.Frame(top)
        lf.pack(fill="x", padx=6, pady=(2, 6))
        self.listbox = tk.Listbox(lf, height=6, selectmode="extended",
                                  activestyle="none")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        # output location
        out = ttk.LabelFrame(self, text="Save .txt files")
        out.pack(fill="x", **pad)
        ttk.Radiobutton(out, text="Next to each original file",
                        variable=self.same_folder, value=True,
                        command=self._toggle_out).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(out, text="In this folder:",
                        variable=self.same_folder, value=False,
                        command=self._toggle_out).grid(row=1, column=0, sticky="w", padx=6, pady=2)
        self.e_out = ttk.Entry(out, textvariable=self.out_dir, state="disabled")
        self.e_out.grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        self.b_out = ttk.Button(out, text="Browse…", command=self.pick_out, state="disabled")
        self.b_out.grid(row=1, column=2, padx=6, pady=2)
        out.columnconfigure(1, weight=1)

        # convert + progress
        run = ttk.Frame(self)
        run.pack(fill="x", **pad)
        self.b_convert = ttk.Button(run, text="Convert", command=self.start)
        self.b_convert.pack(side="left")
        self.progress = ttk.Progressbar(run, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        # log + preview
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, **pad)
        self.log = self._textbox(self.nb)
        self.preview = self._textbox(self.nb)
        self.nb.add(self.log.master, text="Log")
        self.nb.add(self.preview.master, text="Preview (select a converted file)")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        ttk.Button(bottom, text="Copy preview", command=self.copy_preview).pack(side="right")

    def _textbox(self, parent):
        frame = ttk.Frame(parent)
        txt = tk.Text(frame, wrap="word", state="disabled", font=("Consolas", 10))
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return txt

    # ---- helpers ---------------------------------------------------------
    def _set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _toggle_out(self):
        st = "disabled" if self.same_folder.get() else "normal"
        self.e_out.configure(state=st)
        self.b_out.configure(state=st)

    def _set_busy(self, busy):
        self.running = busy
        st = "disabled" if busy else "normal"
        for b in (self.b_add, self.b_folder, self.b_remove, self.b_clear, self.b_convert):
            b.configure(state=st)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for f in self.files:
            mark = "✓ " if f in self.results else "   "
            self.listbox.insert("end", mark + str(f))

    def _add(self, paths):
        for p in map(Path, paths):
            if (p.suffix.lower() in (".doc", ".docx") and not p.name.startswith("~$")
                    and p not in self.files):
                self.files.append(p)
        self._refresh_list()
        self.status.set(f"{len(self.files)} file(s) ready.")

    # ---- actions ---------------------------------------------------------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose Word files",
            filetypes=[("Word documents", "*.doc *.docx"), ("All files", "*.*")])
        self._add(paths)

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder with Word files")
        if d:
            self._add(sorted(Path(d).iterdir()))

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            f = self.files.pop(i)
            self.results.pop(f, None)
        self._refresh_list()
        self.status.set(f"{len(self.files)} file(s) ready.")

    def clear(self):
        self.files.clear()
        self.results.clear()
        self._refresh_list()
        self._set_text(self.preview, "")
        self.status.set("Add .doc / .docx files to begin.")

    def pick_out(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.out_dir.set(d)

    def on_select(self, _event=None):
        sel = self.listbox.curselection()
        if len(sel) != 1:
            return
        out = self.results.get(self.files[sel[0]])
        if out and Path(out).exists():
            self._set_text(self.preview, Path(out).read_text(encoding="utf-8"))
            self.nb.select(1)

    def copy_preview(self):
        text = self.preview.get("1.0", "end-1c")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status.set("Preview copied to clipboard.")

    def start(self):
        if not self.files:
            messagebox.showinfo("Nothing to convert", "Add some .doc or .docx files first.")
            return
        out_dir = None
        if not self.same_folder.get():
            out_dir = self.out_dir.get().strip()
            if not out_dir:
                messagebox.showinfo("Output folder", "Choose an output folder first.")
                return
            Path(out_dir).mkdir(parents=True, exist_ok=True)

        self.results.clear()
        self._refresh_list()
        self._set_text(self.log, "")
        self.progress.configure(maximum=len(self.files), value=0)
        self._set_busy(True)
        self.status.set("Converting…")
        self.nb.select(0)
        threading.Thread(target=worker, args=(list(self.files), out_dir, self.q),
                         daemon=True).start()
        self.after(100, self.poll)

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "ok":
                    _, i, src, dst = msg
                    self.results[src] = dst
                    self.progress.configure(value=i)
                    self._log(f"OK     {src.name}  →  {dst}")
                elif msg[0] == "err":
                    _, i, src, err = msg
                    self.progress.configure(value=i)
                    self._log(f"FAILED {src.name}: {err}")
                elif msg[0] == "done":
                    n_warn = msg[1]
                    ok = len(self.results)
                    self._log(f"\nFinished: {ok} of {len(self.files)} converted.")
                    if n_warn:
                        self._log(f"Note: {n_warn} old-style equation object(s) could not "
                                  "be converted (marked in the text).")
                    self.status.set(f"Done — {ok} of {len(self.files)} converted.")
                    self._set_busy(False)
                    self._refresh_list()
        except queue.Empty:
            pass
        if self.running:
            self.after(100, self.poll)


if __name__ == "__main__":
    if len(sys.argv) > 1:      # command line still works:  python doc_to_txt.py file.docx
        main()
    else:
        App().mainloop()