#!/usr/bin/env python3
"""
I-485 PDF Form Filler for Refugees
===================================
Fills USCIS I-485 (Application to Register Permanent Residence or Adjust Status)
PDF form fields from a YAML configuration file.

Works with the current USCIS PDF (AES-encrypted, XFA/AcroForm hybrid, PDF 1.7).

Usage:
  # Inspect field names in the blank PDF:
  python fill_i485.py list-fields blank_i485.pdf

  # Fill a single applicant:
  python fill_i485.py fill --input blank_i485.pdf --data applicant.yaml --output filled.pdf

  # Batch mode (YAML has an 'applicants:' list):
  python fill_i485.py fill --input blank_i485.pdf --data batch.yaml --batch --outdir ./filled/

  # Flatten (read-only) output:
  python fill_i485.py fill --input blank_i485.pdf --data applicant.yaml --output out.pdf --flatten
"""

import argparse
import sys
import yaml
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject, create_string_object
except ImportError:
    sys.exit("Missing dependency: run  pip install pypdf pyyaml")


# ---------------------------------------------------------------------------
# AcroForm tree traversal
# ---------------------------------------------------------------------------

def _iter_acroform_fields(node_ref, parent_name=""):
    """
    Recursively yield (full_name, indirect_ref, field_obj) for every
    terminal field in the AcroForm hierarchy.
    """
    node = node_ref.get_object() if hasattr(node_ref, "get_object") else node_ref

    t_raw = node.get("/T")
    if t_raw is not None:
        seg = str(t_raw)
        full_name = f"{parent_name}.{seg}" if parent_name else seg
    else:
        full_name = parent_name

    has_ft = node.get("/FT") is not None

    kids = node.get("/Kids")
    if kids:
        # Intermediate node — recurse
        for kid_ref in kids:
            yield from _iter_acroform_fields(kid_ref, full_name)
    elif has_ft:
        # Terminal field
        yield full_name, node_ref, node


def collect_all_fields(writer):
    """Return {full_name: (ref, field_obj)} for every writable field."""
    root = writer._root_object
    if "/AcroForm" not in root:
        return {}
    acroform = root["/AcroForm"].get_object()
    top_fields = acroform.get("/Fields", [])
    result = {}
    for top_ref in top_fields:
        for full_name, ref, obj in _iter_acroform_fields(top_ref):
            result[full_name] = (ref, obj)
    return result


# ---------------------------------------------------------------------------
# Field value encoding
# ---------------------------------------------------------------------------

def encode_value(value, field_obj):
    """Convert a Python value to the correct pypdf generic type."""
    ft = str(field_obj.get("/FT", "")).strip("/")

    if ft == "Btn":
        # Checkbox or radio button
        if isinstance(value, bool):
            pdf_val = NameObject("/Yes") if value else NameObject("/Off")
        else:
            # Allow explicit "/Yes", "/Off", "Yes", "Off" strings
            s = str(value).strip("/")
            pdf_val = NameObject(f"/{s}")
        return pdf_val, pdf_val   # (/V, /AS)

    # Text field or dropdown
    return create_string_object(str(value)), None


# ---------------------------------------------------------------------------
# Core fill logic
# ---------------------------------------------------------------------------

def fill_pdf(pdf_path: str, field_map: dict, output_path: str, flatten: bool = False):
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        res = reader.decrypt("")
        if not res:
            sys.exit("Could not decrypt PDF. Non-empty owner password required.")

    writer = PdfWriter()
    writer.append(reader)

    # Enable appearance regeneration
    root = writer._root_object
    if "/AcroForm" in root:
        acroform = root["/AcroForm"].get_object()
        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})

    all_fields = collect_all_fields(writer)
    unmatched = set(field_map.keys())
    filled = 0

    for full_name, (ref, field_obj) in all_fields.items():
        if full_name not in field_map:
            continue
        unmatched.discard(full_name)

        v, ap_state = encode_value(field_map[full_name], field_obj)
        update = {NameObject("/V"): v}
        if ap_state is not None:
            update[NameObject("/AS")] = ap_state
        if flatten:
            # Set read-only flag bit 1
            ff = int(str(field_obj.get("/Ff", 0))) | 1
            update[NameObject("/Ff")] = NameObject(str(ff))
        field_obj.update(update)
        filled += 1

    if unmatched:
        print(f"  [warn] {len(unmatched)} YAML field(s) not found in PDF:")
        for name in sorted(unmatched)[:20]:
            print(f"         • {name}")
        if len(unmatched) > 20:
            print(f"         … and {len(unmatched) - 20} more")

    print(f"  [ok]  Filled {filled} field(s) → {output_path}")
    with open(output_path, "wb") as f:
        writer.write(f)


# ---------------------------------------------------------------------------
# list-fields sub-command
# ---------------------------------------------------------------------------

def list_fields(pdf_path: str):
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        reader.decrypt("")

    writer = PdfWriter()
    writer.append(reader)
    all_fields = collect_all_fields(writer)

    if not all_fields:
        print("No AcroForm fields found.")
        print("The PDF may be XFA-only. Try printing to PDF or re-saving from Acrobat.")
        return

    # Skip barcode fields
    printable = {
        name: obj for name, (_, obj) in all_fields.items()
        if "PDF417" not in name and "BarCode" not in name
    }

    col = max(len(n) for n in printable) if printable else 60
    print(f"{'FIELD NAME':<{col}}  {'TYPE':<6}  CURRENT VALUE / OPTIONS")
    print("-" * (col + 50))

    for name, obj in sorted(printable.items()):
        ft = str(obj.get("/FT", "")).strip("/")
        val = str(obj.get("/V", "")).strip("()")
        extra = ""
        opts = obj.get("/Opt")
        if opts:
            flat = []
            for o in list(opts)[:6]:
                if isinstance(o, list):
                    flat.append(str(o[0]))
                else:
                    flat.append(str(o))
            extra = "  opts:[" + ", ".join(flat) + ("…" if len(opts) > 6 else "") + "]"
        print(f"{name:<{col}}  {ft:<6}  {val}{extra}")

    print(f"\nTotal input fields (excl. barcodes): {len(printable)}")
    print("\nTo fill the form, copy field names into your YAML data file.")


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_field_map(data: dict) -> dict:
    """
    Flatten YAML sections into {pdf_field_name: value}.
    Supports a 'field_overrides' key to remap logical → actual PDF names.
    """
    overrides = data.get("field_overrides", {})
    field_map = {}
    for section, content in data.items():
        if section in ("field_overrides", "applicants", "_meta"):
            continue
        if isinstance(content, dict):
            field_map.update(content)
    for logical, pdf_name in overrides.items():
        if logical in field_map:
            field_map[pdf_name] = field_map.pop(logical)
    return field_map


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Fill USCIS I-485 PDFs from YAML data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command")

    lf = sub.add_parser("list-fields", help="List all form fields in a PDF")
    lf.add_argument("pdf", help="Path to blank I-485 PDF")

    fi = sub.add_parser("fill", help="Fill the form from YAML data")
    fi.add_argument("--input", "-i", required=True, help="Blank I-485 PDF")
    fi.add_argument("--data", "-d", required=True, help="YAML data file")
    fi.add_argument("--output", "-o", help="Output path (single applicant)")
    fi.add_argument("--batch", action="store_true",
                    help="Batch mode: YAML has top-level 'applicants' list")
    fi.add_argument("--outdir", default="./filled",
                    help="Output directory for batch mode (default: ./filled)")
    fi.add_argument("--flatten", action="store_true",
                    help="Make all fields read-only in output")
    return p.parse_args()


def main():
    args = parse_args()

    if args.command == "list-fields":
        list_fields(args.pdf)

    elif args.command == "fill":
        data = load_yaml(args.data)

        if args.batch:
            applicants = data.get("applicants")
            if not applicants:
                sys.exit("Batch mode requires an 'applicants:' list in the YAML.")
            outdir = Path(args.outdir)
            outdir.mkdir(parents=True, exist_ok=True)
            for i, applicant in enumerate(applicants, 1):
                fm = build_field_map(applicant)
                last = fm.get(
                    "form1[0].#subform[0].Pt1Line1_FamilyName[0]",
                    f"applicant{i}"
                )
                out = outdir / f"i485_{last}_{i}.pdf"
                print(f"Applicant {i}: {last}")
                fill_pdf(args.input, fm, str(out), args.flatten)
        else:
            if not args.output:
                sys.exit("--output is required for single-applicant mode.")
            fm = build_field_map(data)
            print(f"Filling {len(fm)} configured field(s)…")
            fill_pdf(args.input, fm, args.output, args.flatten)

    else:
        import subprocess
        subprocess.run([sys.executable, __file__, "--help"])


if __name__ == "__main__":
    main()
