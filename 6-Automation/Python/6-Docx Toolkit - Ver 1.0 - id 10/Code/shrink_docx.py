#!/usr/bin/env python3
"""Reduce a DOCX's size by resizing and recompressing embedded images."""

import argparse
import io
import sys
import threading
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageOps


def optimize_image(data, extension, max_dimension, quality):
    with Image.open(io.BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original)
        if max(image.size) > max_dimension:
            image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )

        output = io.BytesIO()
        if extension in (".jpg", ".jpeg"):
            options = {
                "format": "JPEG",
                "quality": quality,
                "optimize": True,
                "progressive": True,
            }
            if image.info.get("icc_profile"):
                options["icc_profile"] = image.info["icc_profile"]
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(output, **options)
        else:
            image.save(output, format="PNG", optimize=True)

        candidate = output.getvalue()
        return candidate if len(candidate) < len(data) else data


def optimize_docx(source, output=None, max_dimension=1200, quality=75):
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Input file does not exist: {}".format(source))
    if source.suffix.lower() != ".docx":
        raise ValueError("Input must be a .docx file")
    if max_dimension < 1:
        raise ValueError("Maximum image dimension must be greater than zero")
    if not 1 <= quality <= 95:
        raise ValueError("JPEG quality must be between 1 and 95")

    output = Path(output).expanduser().resolve() if output else source.with_name(
        source.stem + ".optimized.docx"
    )
    if source == output:
        raise ValueError("Output must be different from the input")
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_output = None
    try:
        with zipfile.ZipFile(str(source), "r") as original:
            if any(name.startswith("_xmlsignatures/") for name in original.namelist()):
                raise ValueError(
                    "The DOCX contains digital signatures; changing it would invalidate them"
                )

            with tempfile.NamedTemporaryFile(
                prefix=output.stem + ".", suffix=".tmp", dir=str(output.parent), delete=False
            ) as temp_file:
                temporary_output = Path(temp_file.name)

            image_count = 0
            resized_count = 0
            saved_bytes = 0
            with zipfile.ZipFile(
                str(temporary_output), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as result:
                result.comment = original.comment
                for info in original.infolist():
                    data = original.read(info)
                    extension = Path(info.filename).suffix.lower()
                    if info.filename.startswith("word/media/") and extension in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                    ):
                        image_count += 1
                        with Image.open(io.BytesIO(data)) as image:
                            was_oversized = max(image.size) > max_dimension
                        optimized = optimize_image(data, extension, max_dimension, quality)
                        if was_oversized and optimized != data:
                            resized_count += 1
                        saved_bytes += len(data) - len(optimized)
                        data = optimized

                    copied_info = zipfile.ZipInfo(info.filename, info.date_time)
                    copied_info.comment = info.comment
                    copied_info.extra = info.extra
                    copied_info.internal_attr = info.internal_attr
                    copied_info.external_attr = info.external_attr
                    copied_info.create_system = info.create_system
                    copied_info.compress_type = zipfile.ZIP_DEFLATED
                    result.writestr(
                        copied_info,
                        data,
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9,
                    )

        with zipfile.ZipFile(str(temporary_output), "r") as check:
            bad_file = check.testzip()
            if bad_file:
                raise RuntimeError("Output archive failed integrity check at {}".format(bad_file))

        temporary_output.replace(output)
        old_size = source.stat().st_size
        new_size = output.stat().st_size
        return {
            "output": output,
            "image_count": image_count,
            "resized_count": resized_count,
            "saved_bytes": saved_bytes,
            "old_size": old_size,
            "new_size": new_size,
        }
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError):
        if temporary_output and temporary_output.exists():
            temporary_output.unlink()
        raise


def optimize_docx_folder(source_folder, output_folder, max_dimension=1200, quality=75):
    source_folder = Path(source_folder).expanduser().resolve()
    if not source_folder.is_dir():
        raise ValueError("Input folder does not exist: {}".format(source_folder))

    sources = sorted(
        (
            path
            for path in source_folder.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".docx"
            and not path.name.startswith("~$")
            and not path.name.lower().endswith(".optimized.docx")
        ),
        key=lambda path: path.name.casefold(),
    )
    if not sources:
        raise ValueError("The selected folder does not contain any DOCX files")

    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    for source in sources:
        destination = output_folder / (source.stem + ".optimized.docx")
        try:
            results.append(optimize_docx(source, destination, max_dimension, quality))
        except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
            failures.append((source, error))

    return results, failures


def run_gui(parent=None, initial_path=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    root.title("DOCX Image Shrinker")
    root.resizable(True, True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    if parent is not None:
        root.transient(parent)
        root.grab_set()

    input_path = tk.StringVar()
    output_path = tk.StringVar()
    if initial_path is not None:
        initial_source = Path(initial_path).expanduser()
        input_path.set(str(initial_source))
        if initial_source.is_dir():
            output_path.set(str(initial_source / "optimized"))
        else:
            output_path.set(
                str(initial_source.with_name(initial_source.stem + ".optimized.docx"))
            )
    max_dimension = tk.StringVar(value="1200")
    quality = tk.StringVar(value="75")
    status = tk.StringVar(value="Choose a DOCX file or folder to get started.")

    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="Word document or folder:").grid(
        row=0, column=0, sticky="w", pady=5
    )
    ttk.Entry(frame, textvariable=input_path, width=48).grid(
        row=0, column=1, sticky="ew", padx=8, pady=5
    )

    def choose_file():
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose a Word document",
            filetypes=(("Word documents", "*.docx"), ("All files", "*.*")),
        )
        if selected:
            input_path.set(selected)
            source = Path(selected)
            output_path.set(str(source.with_name(source.stem + ".optimized.docx")))

    def choose_folder():
        selected = filedialog.askdirectory(
            parent=root,
            title="Choose a folder containing Word documents",
        )
        if selected:
            input_path.set(selected)
            output_path.set(str(Path(selected) / "optimized"))

    ttk.Button(frame, text="Choose File...", command=choose_file).grid(
        row=0, column=2, padx=(0, 4), pady=5
    )
    ttk.Button(frame, text="Choose Folder...", command=choose_folder).grid(
        row=0, column=3, pady=5
    )

    ttk.Label(frame, text="Save optimized file(s) to:").grid(
        row=1, column=0, sticky="w", pady=5
    )
    ttk.Entry(frame, textvariable=output_path, width=48).grid(
        row=1, column=1, sticky="ew", padx=8, pady=5
    )

    def choose_output():
        source_text = input_path.get().strip()
        source = Path(source_text) if source_text else None
        if source is not None and source.is_dir():
            selected = filedialog.askdirectory(
                parent=root,
                title="Choose a folder for optimized documents",
                initialdir=str(source),
            )
            if selected:
                output_path.set(selected)
            return

        suggested = output_path.get() or "optimized.docx"
        selected = filedialog.asksaveasfilename(
            parent=root,
            title="Save optimized document",
            initialfile=Path(suggested).name,
            defaultextension=".docx",
            filetypes=(("Word documents", "*.docx"),),
        )
        if selected:
            output_path.set(selected)

    ttk.Button(frame, text="Browse...", command=choose_output).grid(
        row=1, column=2, pady=5
    )

    settings = ttk.Frame(frame)
    settings.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 5))
    ttk.Label(settings, text="Max image dimension (px):").grid(row=0, column=0, sticky="w")
    ttk.Entry(settings, textvariable=max_dimension, width=8).grid(
        row=0, column=1, padx=(8, 24)
    )
    ttk.Label(settings, text="JPEG quality (1-95):").grid(row=0, column=2, sticky="w")
    ttk.Entry(settings, textvariable=quality, width=8).grid(row=0, column=3, padx=8)

    progress = ttk.Progressbar(frame, mode="indeterminate", length=420)
    progress.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 4))
    ttk.Label(frame, textvariable=status).grid(
        row=4, column=0, columnspan=4, sticky="w", pady=(2, 8)
    )

    compress_button = ttk.Button(frame, text="Reduce file size")
    compress_button.grid(row=5, column=0, columnspan=4, pady=(2, 0))

    def finish(results, failures, error):
        progress.stop()
        compress_button.configure(state="normal")
        if error:
            status.set("Could not optimize the selected documents.")
            messagebox.showerror("Optimization failed", str(error), parent=root)
            return

        if not results:
            details = "\n".join(
                "{}: {}".format(source, failure)
                for source, failure in failures
            )
            status.set("Could not optimize any documents.")
            messagebox.showerror(
                "Optimization failed",
                details or "No documents were optimized.",
                parent=root,
            )
            return

        old_size = sum(result["old_size"] for result in results)
        new_size = sum(result["new_size"] for result in results)
        percent = (old_size - new_size) * 100.0 / old_size if old_size else 0
        status.set("Finished: {:.1f}% smaller".format(percent))
        summary = (
            "Optimized documents: {}\n"
            "Size: {:.2f} MB -> {:.2f} MB\n"
            "Images resized: {} of {}".format(
                len(results),
                old_size / 1048576,
                new_size / 1048576,
                sum(result["resized_count"] for result in results),
                sum(result["image_count"] for result in results),
            )
        )
        if len(results) == 1:
            summary = "Saved to:\n{}\n\n{}".format(results[0]["output"], summary)
        else:
            summary = "Saved to:\n{}\n\n{}".format(output_path.get(), summary)

        if failures:
            status.set(
                "Finished with errors: {} of {} documents failed.".format(
                    len(failures), len(results) + len(failures)
                )
            )
            details = "\n".join(
                "{}: {}".format(source, failure)
                for source, failure in failures
            )
            messagebox.showwarning(
                "Optimization partially complete",
                "{}\n\nFailed documents:\n{}".format(summary, details),
                parent=root,
            )
        else:
            messagebox.showinfo("Optimization complete", summary, parent=root)

    def start_optimization():
        try:
            dimension = int(max_dimension.get())
            jpeg_quality = int(quality.get())
        except ValueError:
            messagebox.showerror(
                "Invalid settings",
                "Maximum dimension and JPEG quality must be whole numbers.",
                parent=root,
            )
            return

        source = input_path.get().strip()
        destination = output_path.get().strip()
        if not source or not destination:
            messagebox.showerror(
                "Missing file",
                "Choose both an input document and an output location.",
                parent=root,
            )
            return

        compress_button.configure(state="disabled")
        progress.start(12)
        status.set("Resizing and compressing images...")

        def work():
            try:
                source_path = Path(source)
                if source_path.is_dir():
                    results, failures = optimize_docx_folder(
                        source_path, destination, dimension, jpeg_quality
                    )
                else:
                    results = [
                        optimize_docx(source, destination, dimension, jpeg_quality)
                    ]
                    failures = []
            except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
                root.after(0, finish, [], [], error)
            else:
                root.after(0, finish, results, failures, None)

        threading.Thread(target=work, daemon=True).start()

    compress_button.configure(command=start_optimization)
    if parent is None:
        root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reduce a DOCX file's size by resizing and recompressing its images."
    )
    parser.add_argument("input", type=Path, nargs="?", help="source .docx file")
    parser.add_argument(
        "-o", "--output", type=Path, help="output file (default: <input>.optimized.docx)"
    )
    parser.add_argument(
        "--max-dimension",
        type=int,
        default=1200,
        help="maximum image width or height in pixels (default: 1200)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=75,
        help="JPEG quality from 1 to 95 (default: 75)",
    )
    args = parser.parse_args(argv)
    if args.input is None:
        run_gui()
        return 0

    if args.max_dimension < 1:
        parser.error("--max-dimension must be greater than zero")
    if not 1 <= args.quality <= 95:
        parser.error("--quality must be between 1 and 95")

    try:
        result = optimize_docx(args.input, args.output, args.max_dimension, args.quality)
        print("Created: {}".format(result["output"]))
        print("Images checked: {}".format(result["image_count"]))
        print("Images resized: {}".format(result["resized_count"]))
        print("Image bytes saved: {}".format(result["saved_bytes"]))
        old_size = result["old_size"]
        new_size = result["new_size"]
        if new_size < old_size:
            change = "{:.1f}% smaller".format((old_size - new_size) * 100.0 / old_size)
        elif new_size > old_size:
            change = "{:.1f}% larger".format((new_size - old_size) * 100.0 / old_size)
        else:
            change = "no size change"
        print("DOCX size: {} -> {} bytes ({})".format(old_size, new_size, change))
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
