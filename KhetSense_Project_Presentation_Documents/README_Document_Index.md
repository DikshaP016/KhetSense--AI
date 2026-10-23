# KhetSense AI — Research Project Presentation Documents Index

**Project Title:** KhetSense AI: AI-Driven Crop Stress Detection and Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing  
**Author:** Diksha Poojary (Roll No. 136) | Master of Computer Applications (MCA)  
**Mentor:** Prof. Anamika Dhawan  
**Academic Year:** 2025–2027  
**Location:** `KhetSense_Project_Presentation_Documents/`  
**Purpose:** Primary technical reference package for preparing the **Research Project PPT** for mentor review, project evaluation, and final viva examination.

---

## 1. Document Inventory & Presentation Guide

This folder contains seven comprehensive, editable Microsoft Word (`.docx`) documents designed to support the creation of your **Research Project PPT** (focused on system implementation, architecture, technology stack, operational workflow, testing evidence, and live demonstration).

| Document Name | File Format | Primary Topic / Purpose | Best Used For PPT Slides |
|---|:---:|---|---|
| **1. KhetSense_Project_Overview.docx** | `.docx` | High-level system summary, agricultural motivation, problem statement, measurable objectives, scope, existing vs. proposed approach, benefits, and current implementation status. | **Slide 1–5:** Title, Problem Statement, Motivation, Aim & Objectives, Key Features. |
| **2. KhetSense_System_Architecture_and_Workflow.docx** | `.docx` | Layered 5-tier architecture, component descriptions, ASCII/flowchart diagrams, 7-stage data flow, external API integrations, and error-handling resilience. | **Slide 6–9:** System Architecture, Subsystems, End-to-End Workflow, Decision Flowchart. |
| **3. KhetSense_Technology_Stack_and_Modules.docx** | `.docx` | Complete technology catalog (16 technologies/APIs) with inputs/outputs/status, and in-depth documentation of all 16 modular subsystems. | **Slide 10–12:** Technology Stack Matrix, Module Architecture, Core Functional Components. |
| **4. KhetSense_Implementation_and_Demo_Guide.docx** | `.docx` | Step-by-step evaluator demonstration script, terminal commands, 5 demo scenarios, expected outputs, troubleshooting, and screenshot capture checklist. | **Slide 13–15:** Live System Demonstration, Example Inputs/Outputs, WhatsApp Cards. |
| **5. KhetSense_Testing_and_Verification_Report.docx** | `.docx` | Complete QA audit, test strategy, test categories, catalog of 10 representative test cases, 401-test execution evidence (100% green), and defect log. | **Slide 16–17:** Quality Assurance, Test Suite Metrics, Test Case Results, Software Correctness. |
| **6. KhetSense_Project_Screenshots_and_Figure_Plan.docx** | `.docx` | Visual evidence plan, screenshot capture guide, recommended diagram placements, formal captions, and how to address unverified items. | **Slide 18–19:** Visual Evidence, Terminal Captures, Evaluation Charts, Captions. |
| **7. KhetSense_Project_Quick_Reference.docx** | `.docx` | Concise master summary, problem/objective bullets, workflow summary, key facts, and the **Top 10 Viva Questions & Answers**. | **Presenter Notes & Viva Prep:** Quick reference cheat-sheet during presentation. |

---

## 2. Recommended Research Project PPT Slide Structure (18–20 Slides)

To deliver an exceptional presentation to your mentor (Prof. Anamika Dhawan) and external evaluators, structure your Research Project PPT as follows:

- **Slide 1: Title Slide**  
  *Project Name, Subtitle, Author (Diksha Poojary, Roll 136), Mentor (Prof. Anamika Dhawan), Degree (MCA), Academic Year (2025–2027).*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 1).

- **Slide 2: Background & Agricultural Motivation**  
  *Smallholder crisis, groundwater depletion, waterlogging risks, reactive irrigation inefficiencies.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 3).

- **Slide 3: Problem Statement (The Triple Divide)**  
  *1. Hardware Capital Cost Barrier ($200–$500/sensor); 2. Literacy & Language Barrier; 3. Spatial Coarseness of District Bulletins.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 4).

- **Slide 4: Project Aim & Core Objectives**  
  *Zero-hardware telemetry, multi-spectral index calculation, Phase 8 primary ML prediction, rainfall safety guardrails, trilingual WhatsApp voice delivery.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 5).

- **Slide 5: Existing Systems vs. KhetSense AI**  
  *Comparative table contrasting In-Situ IoT, Regional Dashboards, General Chatbots, and KhetSense AI.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 9, Table).

- **Slide 6: High-Level System Architecture**  
  *Five functional layers: Farmer Messaging, Webhook & Security, Geospatial Ingestion, Core Intelligence, Multilingual Delivery.*  
  *Reference:* `KhetSense_System_Architecture_and_Workflow.docx` (Section 1, Diagram).

- **Slide 7: Software Technology Stack**  
  *Visual matrix of Python 3.13, FastAPI, Scikit-Learn, Google Earth Engine, NASA SMAP, Edge-TTS, Supabase/PostgreSQL.*  
  *Reference:* `KhetSense_Technology_Stack_and_Modules.docx` (Section 1, Table).

- **Slide 8: Core Functional Modules**  
  *16 modular subsystems grouped into Ingestion, Feature Processing, ML Decisioning, Guardrails, and Voice Delivery.*  
  *Reference:* `KhetSense_Technology_Stack_and_Modules.docx` (Section 2).

- **Slide 9: End-to-End Operational Decision Workflow**  
  *Decision flowchart: Inbound 'status' -> Sensor check -> Wheat ML inference vs. Cotton rule fallback -> Rainfall guardrail override -> Advisory dispatch.*  
  *Reference:* `KhetSense_System_Architecture_and_Workflow.docx` (Section 4, Flowchart).

- **Slide 10: Multi-Sensor Satellite Feature Engineering**  
  *Mathematical formulation of NDVI, NDWI (Gao 1996), NDRE (Barnes 2000), MSAVI (Qi 1994), and SMAP soil moisture %.*  
  *Reference:* `KhetSense_Technology_Stack_and_Modules.docx` (Modules 4 & 5).

- **Slide 11: Phase 8 Primary ML Decision Architecture**  
  *5-feature live-native Random Forest (Tuned Severe Threshold T = 0.27) as primary authority for wheat; explicit rule fallback for other crops.*  
  *Reference:* `KhetSense_System_Architecture_and_Workflow.docx` (Section 2.F).

- **Slide 12: Two-Tier Rainfall Safety Guardrail Policy**  
  *Tier 1 (5 mm deferral) and Tier 2 (15 mm unconditional halt) preventing crop waterlogging and electricity waste.*  
  *Reference:* `KhetSense_System_Architecture_and_Workflow.docx` (Section 4).

- **Slide 13: Conversational Trilingual Onboarding (WhatsApp)**  
  *Conversational state machine supporting English, Marathi, and Hindi; GPS pin and Google Maps URL resolution; ESA WorldCover screening.*  
  *Reference:* `KhetSense_Implementation_and_Demo_Guide.docx` (Section 4, Scenario 1).

- **Slide 14: Vernacular Neural Voice Synthesis**  
  *Edge-TTS generating natural Marathi (`mr-IN-AarohiNeural`), Hindi (`hi-IN-SwaraNeural`), and English voice notes in Opus OGG format.*  
  *Reference:* `KhetSense_Implementation_and_Demo_Guide.docx` (Section 5).

- **Slide 15: Software Quality Assurance & Test Verification**  
  *401 automated unit/integration tests across 14 test modules passing in 44.33s (100% green build); zero regressions.*  
  *Reference:* `KhetSense_Testing_and_Verification_Report.docx` (Section 4, Table).

- **Slide 16: Key Experimental Findings & Base-Rate Trap**  
  *CSISA benchmark evaluation: Rule baseline superiority (22.89% vs 12.05% recall); HistGradientBoosting base-rate trap (1,274 false alarms).*  
  *Reference:* `KhetSense_Project_Quick_Reference.docx` (Section 6).

- **Slide 17: Live Demonstration Scenarios**  
  *Summary of 5 offline demo scenarios: Registration, Rainfall guardrail, Crop mismatch, Missing sensors, Primary ML advisory.*  
  *Reference:* `KhetSense_Implementation_and_Demo_Guide.docx` (Section 4).

- **Slide 18: Critical Scientific Limitations & Boundaries**  
  *Eastern India wheat domain boundary (not validated for Maharashtra), survey-derived labels, no longitudinal yield trials.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 10) & `KhetSense_Project_Quick_Reference.docx` (Section 8).

- **Slide 19: Future Research & Roadmap**  
  *Maharashtra Vertisol ground-truth field trials, multi-crop model training, multi-temporal LSTM modeling, probability calibration.*  
  *Reference:* `KhetSense_Project_Overview.docx` (Section 10).

- **Slide 20: Conclusion & Acknowledgments**  
  *Final summary, contributions, mentorship acknowledgment (Prof. Anamika Dhawan), and opening for viva Q&A.*  
  *Reference:* `KhetSense_Project_Quick_Reference.docx` (Section 9 - Top 10 Viva Q&As).

---

## 3. How to Use These Files

1. **For Slide Text & Content:** Open `KhetSense_Project_Overview.docx` and `KhetSense_Technology_Stack_and_Modules.docx`. Copy-paste bullet points, tables, and module descriptions directly into PowerPoint.
2. **For Architecture Diagrams:** Open `KhetSense_System_Architecture_and_Workflow.docx`. Use the ASCII diagrams or convert them into colored PowerPoint shapes.
3. **For Screenshots:** Follow `KhetSense_Project_Screenshots_and_Figure_Plan.docx` to capture clean terminal outputs using Windows Snipping Tool (`Win + Shift + S`).
4. **For Viva Defense Preparation:** Read `KhetSense_Project_Quick_Reference.docx` Section 9 to master the Top 10 Viva Questions.
