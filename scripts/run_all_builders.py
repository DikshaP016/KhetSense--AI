#!/usr/bin/env python3
"""
Master runner script that executes all 7 builders sequentially to generate
the complete presentation documentation package.
"""

import sys
import time
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_doc1_overview import build_doc1
from build_doc2_architecture import build_doc2
from build_doc3_techstack import build_doc3
from build_doc4_demoguide import build_doc4
from build_doc5_testing import build_doc5
from build_doc6_screenshots import build_doc6
from build_doc7_quickref import build_doc7

def main():
    print("=" * 75)
    print("KHETSENSE AI — GENERATING ALL 7 RESEARCH PROJECT PPT SUPPORTING DOCUMENTS")
    print("=" * 75)
    start_time = time.time()

    print("\n[1/7] Generating KhetSense_Project_Overview.docx...")
    build_doc1()

    print("\n[2/7] Generating KhetSense_System_Architecture_and_Workflow.docx...")
    build_doc2()

    print("\n[3/7] Generating KhetSense_Technology_Stack_and_Modules.docx...")
    build_doc3()

    print("\n[4/7] Generating KhetSense_Implementation_and_Demo_Guide.docx...")
    build_doc4()

    print("\n[5/7] Generating KhetSense_Testing_and_Verification_Report.docx...")
    build_doc5()

    print("\n[6/7] Generating KhetSense_Project_Screenshots_and_Figure_Plan.docx...")
    build_doc6()

    print("\n[7/7] Generating KhetSense_Project_Quick_Reference.docx...")
    build_doc7()

    duration = time.time() - start_time
    print("\n" + "=" * 75)
    print(f"SUCCESS: All 7 documents generated in {duration:.2f} seconds!")
    print("=" * 75)

if __name__ == "__main__":
    main()
