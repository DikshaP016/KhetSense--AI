#!/usr/bin/env python3
"""
KhetSense AI — Research Project Presentation Documents Generator
Generates all 7 formal, editable .docx documents for the Research Project PPT.
"""

import os
import sys
from pathlib import Path
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

# Paths
ROOT_DIR = Path(r"C:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project")
KHETSENSE_DIR = ROOT_DIR / "khetsense"
OUTPUT_DIRS = [
    ROOT_DIR / "KhetSense_Project_Presentation_Documents",
    KHETSENSE_DIR / "KhetSense_Project_Presentation_Documents",
]

for d in OUTPUT_DIRS:
    d.mkdir(parents=True, exist_ok=True)

# Colors
COLOR_PRIMARY = RGBColor(27, 54, 93)     # #1B365D Navy
COLOR_SECONDARY = RGBColor(75, 107, 148) # #4B6B94 Steel Blue
COLOR_TEXT = RGBColor(34, 34, 34)        # #222222 Charcoal
COLOR_MUTED = RGBColor(100, 100, 100)    # Gray
COLOR_GREEN = RGBColor(46, 125, 50)      # Green
COLOR_RED = RGBColor(198, 40, 40)        # Red

HEX_PRIMARY = "1B365D"
HEX_SECONDARY = "4B6B94"
HEX_LIGHT_BG = "F4F6F9"
HEX_BORDER = "CCCCCC"
HEX_GREEN_BG = "E8F5E9"
HEX_RED_BG = "FFEBEE"


def set_cell_background(cell, fill_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def apply_table_styles(table, col_widths=None):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(table.rows):
        is_header = (i == 0)
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        if is_header:
            trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

        for j, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_margins(cell, top=120, bottom=120, left=150, right=150)
            if is_header:
                set_cell_background(cell, HEX_PRIMARY)
                for p in cell.paragraphs:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    for run in p.runs:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                        run.font.size = Pt(9.5)
            else:
                if i % 2 == 1:
                    set_cell_background(cell, "FFFFFF")
                else:
                    set_cell_background(cell, HEX_LIGHT_BG)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(9.0)
                        run.font.color.rgb = COLOR_TEXT

            # Borders
            tcPr = cell._tc.get_or_add_tcPr()
            tcBorders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER}"/>'
                f'<w:left w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER}"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER}"/>'
                f'<w:right w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER}"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(tcBorders)

    if col_widths:
        for row in table.rows:
            for j, w in enumerate(col_widths):
                if j < len(row.cells):
                    row.cells[j].width = Inches(w)


def add_callout(doc, text, title="NOTE / IMPORTANT NOTICE", border_hex="1B365D", bg_hex="F4F6F9"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_hex)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=180)
    
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_t = p.add_run(f"[{title}]\n")
    run_t.bold = True
    run_t.font.size = Pt(10)
    run_t.font.color.rgb = COLOR_PRIMARY
    
    run_b = p.add_run(text)
    run_b.font.size = Pt(9.5)
    run_b.font.color.rgb = COLOR_TEXT
    
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def create_base_doc(doc_title, doc_subtitle):
    doc = Document()
    
    # Page Setup - Margins 1 inch
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
        # Header
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run(f"KhetSense AI — Research Project Documentation | {doc_title}")
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = COLOR_MUTED
        
        # Footer
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        frun = fp.add_run("MCA Research Capstone Project | Academic Year 2025–2027 | Internal Documentation")
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = COLOR_MUTED
        
    # Styles Setup
    styles = doc.styles
    normal_style = styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = COLOR_TEXT
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.space_after = Pt(6)
    
    # Document Title Block
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_title = title_p.add_run(doc_title)
    run_title.font.size = Pt(22)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY
    
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(16)
    run_sub = sub_p.add_run(doc_subtitle)
    run_sub.font.size = Pt(12)
    run_sub.font.italic = True
    run_sub.font.color.rgb = COLOR_SECONDARY
    
    # Metadata Block
    meta_tbl = doc.add_table(rows=2, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_tbl.cell(0, 0).text = "Project Name: KhetSense AI"
    meta_tbl.cell(0, 1).text = "Author: Diksha Poojary (Roll No. 136)"
    meta_tbl.cell(1, 0).text = "Mentor: Prof. Anamika Dhawan"
    meta_tbl.cell(1, 1).text = "Degree: Master of Computer Applications (MCA)"
    for r in meta_tbl.rows:
        for c in r.cells:
            set_cell_background(c, HEX_LIGHT_BG)
            set_cell_margins(c, top=60, bottom=60, left=100, right=100)
            for p in c.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9.0)
                    run.font.bold = True
                    run.font.color.rgb = COLOR_PRIMARY
    
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    return doc


def add_heading_1(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(16)
    h.paragraph_format.space_after = Pt(6)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.size = Pt(15)
    run.font.bold = True
    run.font.color.rgb = COLOR_PRIMARY
    return h


def add_heading_2(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.size = Pt(12.5)
    run.font.bold = True
    run.font.color.rgb = COLOR_SECONDARY
    return h


def add_heading_3(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(8)
    h.paragraph_format.space_after = Pt(2)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(text)
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = COLOR_TEXT
    return h


def add_bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.bold = True
        r_pre.font.color.rgb = COLOR_PRIMARY
    p.add_run(text)
    return p


def save_doc_to_destinations(doc, filename):
    for out_dir in OUTPUT_DIRS:
        target = out_dir / filename
        doc.save(target)
        print(f"Saved: {target}")


print("Script template loaded successfully.")
