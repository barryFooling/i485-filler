# i485-filler

A Python script that fills USCIS **Form I-485** (Application to Register Permanent Residence or Adjust Status) PDFs from YAML data files, built for refugee resettlement caseworkers and legal aid organizations.

## Features

- Fills all 700+ AcroForm fields in the current USCIS I-485 PDF
- Handles the form's AES encryption and XFA/AcroForm hybrid structure transparently
- Single-applicant and batch modes
- `list-fields` command to inspect field names in any PDF version
- `--flatten` flag to produce read-only output
- YAML templates included for refugee adjustment of status (INA § 209(a))

## Requirements

- Python 3.8+
- [pypdf](https://pypdf.readthedocs.io/) and [PyYAML](https://pyyaml.org/)

```bash
pip install pypdf pyyaml
```

## Setup

Download the blank I-485 from USCIS — this repo does not include it:

```bash
curl -O https://www.uscis.gov/sites/default/files/document/forms/i-485.pdf
mv i-485.pdf blank_i485.pdf
```

## Usage

### Inspect field names

If USCIS releases a new PDF edition, use this to see the exact field names before editing your YAML:

```bash
python fill_i485.py list-fields blank_i485.pdf
```

### Fill a single applicant

1. Copy `applicant_template.yaml` and fill in the applicant's data:

```bash
cp applicant_template.yaml john_doe.yaml
# edit john_doe.yaml
```

2. Run:

```bash
python fill_i485.py fill \
  --input blank_i485.pdf \
  --data john_doe.yaml \
  --output john_doe_i485.pdf
```

### Batch mode

Add each applicant as an entry under the `applicants:` list in `batch_template.yaml`, then run:

```bash
python fill_i485.py fill \
  --input blank_i485.pdf \
  --data batch_template.yaml \
  --batch \
  --outdir ./filled/
```

Output files are named `i485_LASTNAME_N.pdf` in the output directory.

### Flatten (read-only output)

Add `--flatten` to either command to lock all fields after filling:

```bash
python fill_i485.py fill --input blank_i485.pdf --data applicant.yaml \
  --output filled.pdf --flatten
```

## YAML structure

`applicant_template.yaml` is organized by PDF page (matching the form's internal subform numbering) and covers:

| Section | Fields |
|---|---|
| `page1` | Name, A-Number, VOLAG number, date of birth |
| `page2` | Sex, country of birth/citizenship, entry info, I-94 |
| `page3` | Current address, I-94 number, removal proceedings |
| `page3_ssa` | Address history, SSA consent, SSN |
| `page5–7` | Part 2 eligibility — refugee checkbox (`Pt2Line3d_AsyleeRefugeeCB[1]`) and admission date |
| `page8` | Part 3 processing info, Part 4 removal history |
| `page9–12` | Part 5 parents, Part 6 marital status and children |
| `page13` | Part 7 biographic info (ethnicity, race, height, weight, eye/hair color) |
| `page14–17` | Part 8 inadmissibility questions (all Yes/No pairs) |
| `page18–19` | Part 9 public charge / Affidavit of Support |
| `page22–23` | Contact info, applicant signature date, interpreter, preparer |

### Refugee eligibility fields

For INA § 209(a) refugee adjustment, set these in the `refugee_eligibility` section:

```yaml
# Mark as refugee (not asylee)
"form1[0].#subform[6].Pt2Line3d_AsyleeRefugeeCB[0]": false   # Asylee
"form1[0].#subform[6].Pt2Line3d_AsyleeRefugeeCB[1]": true    # Refugee

# Date admitted as refugee (MM/DD/YYYY)
"form1[0].#subform[6].Pt2Line3d_Refugee[0]": "01/15/2024"
```

### Checkboxes and radio buttons

Radio button pairs follow the pattern `FieldName[0]` = Yes/first option, `FieldName[1]` = No/second option. Set one to `true` and the other to `false`:

```yaml
# Example: applicant is not in removal proceedings
"form1[0].#subform[2].Pt1Line13_YN[0]": false   # Yes
"form1[0].#subform[2].Pt1Line13_YN[1]": true    # No
```

### Field name overrides

If your PDF edition uses different field names, add a `field_overrides` section to remap them without touching the script:

```yaml
field_overrides:
  "form1[0].#subform[0].Pt1Line1_FamilyName[0]": "form1[0].#subform[0].Pt1Line1a_FamilyName[0]"
```

## Notes

- **Signatures** must be hand-signed — the script leaves signature fields blank (except the date)
- This form is an **XFA/AcroForm hybrid**. Values are written to the AcroForm layer, which displays correctly in most PDF viewers. If Adobe Reader shows a blank form, print to PDF first to flatten the XFA layer
- Always have a licensed immigration attorney review completed forms before filing
- Field names are verified against USCIS I-485 **edition 09/17/19** — run `list-fields` to confirm compatibility with newer editions

## Files

| File | Purpose |
|---|---|
| `fill_i485.py` | Main script |
| `applicant_template.yaml` | Complete single-applicant template |
| `batch_template.yaml` | Batch template with two example applicants |
| `requirements.txt` | Python dependencies |
