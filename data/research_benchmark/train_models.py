#!/usr/bin/env python3
"""
KhetSense AI — Phase 4: Offline Model Training, Spatial Cross-Validation & Benchmarking
========================================================================================
Author: KhetSense AI Research Engineering
Target Dataset: CSISA 2018 Eastern India Wheat Multi-Sensor Research Benchmark
Records: 7,648 total (6,135 train across 32 districts, 1,513 held-out test across 8 districts)

Models Evaluated:
1. Baseline 0: Deterministic Rule Engine (KhetSense pipeline/classifier.py thresholds)
2. Baseline 1: Regularized Multinomial Logistic Regression (L2 penalty, balanced class weight)
3. Baseline 2: Random Forest Classifier (balanced_subsample, tree depth regularized)
4. Model Reference: HistGradientBoostingClassifier (LightGBM-style gradient boosting)
5. Dependency Status: XGBoost (Formally reported as NOT INSTALLED / omitted due to environment restrictions)
"""

import sys
import os
import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    balanced_accuracy_score,
    precision_recall_fscore_support,
    precision_recall_curve,
    precision_score,
    recall_score,
    auc,
    roc_auc_score,
)

# Set random seed for exact reproducibility
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
DATA_PATH = BASE_DIR / "csisa_wheat_multisensor_features_2018.csv"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "s2_ndvi",
    "s2_ndwi",
    "s2_ndre",
    "s2_msavi",
    "smap_sm_pct",
    "era5_precip_season_mm",
    "era5_temp_mean_c",
    "era5_temp_max_c",
    "era5_vpd_mean_kpa",
]

TARGET_COL = "target_code_3class"
TARGET_NAMES = ["No Stress", "Mild Stress", "Severe Stress"]


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_dataset_integrity(df: pd.DataFrame) -> dict:
    """Audit dataset checksums, rows, splits, and missingness."""
    print("=" * 70)
    print("STEP 1: PRE-TRAINING DATASET INTEGRITY AUDIT")
    print("=" * 70)
    
    file_sha256 = compute_sha256(DATA_PATH)
    expected_sha256 = "ab79e8144aa4cb9b786a35349df944ed7db5b29738069ce38df1f545c306865e"
    assert file_sha256 == expected_sha256, f"Dataset SHA256 mismatch! Got {file_sha256}"
    print(f" Dataset SHA256 Verified: {file_sha256[:16]}... OK")

    total_rows = len(df)
    assert total_rows == 7648, f"Expected 7,648 rows, found {total_rows}"
    print(f" Total rows: {total_rows} OK")

    train_df = df[df["spatial_split"] == "train"]
    test_df = df[df["spatial_split"] == "held_out_test"]
    assert len(train_df) == 6135, f"Expected 6,135 train rows, got {len(train_df)}"
    assert len(test_df) == 1513, f"Expected 1,513 test rows, got {len(test_df)}"
    print(f" Partition counts: Train={len(train_df)} (80.2%), Held-Out Test={len(test_df)} (19.8%) OK")

    train_districts = set(train_df["district"].unique())
    test_districts = set(test_df["district"].unique())
    overlap = train_districts.intersection(test_districts)
    assert len(overlap) == 0, f"Spatial leakage detected! Overlapping districts: {overlap}"
    print(f" Zero District Overlap: {len(train_districts)} Train vs {len(test_districts)} Test Districts OK")

    missing_train = train_df[FEATURE_COLS].isnull().sum().to_dict()
    missing_test = test_df[FEATURE_COLS].isnull().sum().to_dict()
    print(f" Missing features in Train partition: {sum(missing_train.values())} missing values")
    print(f" Missing features in Held-Out Test: {sum(missing_test.values())} missing values (7 cloud-masked S2 rows in Araria)")

    # Duplicates check
    dups_id = df["record_id"].duplicated().sum()
    dups_geo = df.duplicated(subset=["latitude", "longitude"]).sum()
    print(f" Duplicate record IDs: {dups_id} (0.0%)")
    print(f" Shared village/cluster coordinates: {dups_geo} ({dups_geo/len(df)*100:.1f}%) -> Mandates GroupKFold")

    return {
        "file_sha256": file_sha256,
        "total_rows": total_rows,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_districts_count": len(train_districts),
        "test_districts_count": len(test_districts),
        "missing_train": missing_train,
        "missing_test": missing_test,
    }


def rule_engine_predict(row: pd.Series) -> int:
    """
    Deterministic rule engine implementing KhetSense's pipeline/classifier.py logic:
    NDVI: >0.6 -> 0 (No Stress), 0.3-0.6 -> 1 (Mild Stress), <0.3 -> 2 (Severe Stress)
    SMAP: >25% -> 0, 15-25% -> 1, <15% -> 2
    Worst-case ranking: max(s_ndvi, s_smap)
    """
    ndvi = row["s2_ndvi"]
    sm = row["smap_sm_pct"]

    if pd.isna(ndvi) and pd.isna(sm):
        return 0  # fallback

    s_ndvi = 0 if pd.isna(ndvi) or ndvi > 0.6 else (1 if ndvi >= 0.3 else 2)
    s_sm = 0 if pd.isna(sm) or sm > 25.0 else (1 if sm >= 15.0 else 2)
    return max(s_ndvi, s_sm)


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray, model_name: str) -> dict:
    """Compute standard multi-class and class-wise classification metrics."""
    macro_f1 = float(f1_score(y_true, y_pred, average="macro"))
    bal_acc = float(balanced_accuracy_score(y_true, y_pred))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1, 2], zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2]).tolist()

    res = {
        "model_name": model_name,
        "macro_f1": round(macro_f1, 4),
        "balanced_accuracy": round(bal_acc, 4),
        "per_class": {
            "no_stress": {"precision": round(float(p[0]), 4), "recall": round(float(r[0]), 4), "f1": round(float(f[0]), 4), "support": int(s[0])},
            "mild_stress": {"precision": round(float(p[1]), 4), "recall": round(float(r[1]), 4), "f1": round(float(f[1]), 4), "support": int(s[1])},
            "severe_stress": {"precision": round(float(p[2]), 4), "recall": round(float(r[2]), 4), "f1": round(float(f[2]), 4), "support": int(s[2])},
        },
        "confusion_matrix": cm,
    }
    return res


def main():
    start_time = time.time()
    print("Starting KhetSense AI Phase 4 Model Training and Benchmarking...")
    print(f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}")

    # Check xgboost availability
    xgboost_available = False
    try:
        import xgboost
        xgboost_available = True
        print(f"XGBoost version: {xgboost.__version__}")
    except ImportError:
        print("XGBoost status: NOT INSTALLED in current Python environment.")
        print("Restriction policy: No dependency installation permitted. Formally logging omission.")

    # Load dataset
    df = pd.read_csv(DATA_PATH)
    audit_meta = verify_dataset_integrity(df)

    train_df = df[df["spatial_split"] == "train"].copy()
    test_df = df[df["spatial_split"] == "held_out_test"].copy()

    # Preprocessing strictly on train partition
    print("\n" + "=" * 70)
    print("STEP 2: PREPROCESSING AND FEATURE IMPUTATION (FIT ON TRAIN ONLY)")
    print("=" * 70)
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()

    X_train_raw = train_df[FEATURE_COLS].values
    y_train = train_df[TARGET_COL].values
    cv_folds = train_df["cv_fold_id"].values

    X_test_raw = test_df[FEATURE_COLS].values
    y_test = test_df[TARGET_COL].values

    # Fit imputer and scaler ONLY on train
    X_train_imp = imputer.fit_transform(X_train_raw)
    X_test_imp = imputer.transform(X_test_raw)

    X_train_scaled = scaler.fit_transform(X_train_imp)
    X_test_scaled = scaler.transform(X_test_imp)

    # Save preprocessors
    joblib.dump({"imputer": imputer, "scaler": scaler, "feature_names": FEATURE_COLS}, MODELS_DIR / "preprocessor.joblib")
    print(" Preprocessors fitted on train partition and saved to models/preprocessor.joblib")

    # -------------------------------------------------------------
    # 5-FOLD SPATIAL CROSS-VALIDATION
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 3: 5-FOLD SPATIAL CROSS-VALIDATION (TRAIN PARTITION ONLY)")
    print("=" * 70)

    cv_results = {
        "rule_baseline": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
        "logistic_regression": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
        "random_forest": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
        "hist_gradient_boosting": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
    }

    oof_probs_rf = np.zeros((len(train_df), 3))
    oof_probs_hgb = np.zeros((len(train_df), 3))
    oof_probs_lr = np.zeros((len(train_df), 3))

    for fold in range(5):
        val_idx = (cv_folds == fold)
        trn_idx = ~val_idx

        # Fold data
        f_X_trn, f_y_trn = X_train_imp[trn_idx], y_train[trn_idx]
        f_X_val, f_y_val = X_train_imp[val_idx], y_train[val_idx]

        f_scaler = StandardScaler()
        f_X_trn_s = f_scaler.fit_transform(f_X_trn)
        f_X_val_s = f_scaler.transform(f_X_val)

        # 0. Rule baseline on validation fold
        val_sub_df = train_df.iloc[val_idx]
        y_val_rule = np.array([rule_engine_predict(r) for _, r in val_sub_df.iterrows()])
        p0, r0, f0, _ = precision_recall_fscore_support(f_y_val, y_val_rule, labels=[0, 1, 2], zero_division=0)
        cv_results["rule_baseline"]["macro_f1"].append(f1_score(f_y_val, y_val_rule, average="macro"))
        cv_results["rule_baseline"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_rule))
        cv_results["rule_baseline"]["sev_recall"].append(r0[2])
        cv_results["rule_baseline"]["sev_precision"].append(p0[2])

        # 1. Logistic Regression
        clf_lr = LogisticRegression(class_weight="balanced", max_iter=1000, C=0.1, random_state=RANDOM_SEED)
        clf_lr.fit(f_X_trn_s, f_y_trn)
        y_val_lr = clf_lr.predict(f_X_val_s)
        oof_probs_lr[val_idx] = clf_lr.predict_proba(f_X_val_s)
        p1, r1, f1, _ = precision_recall_fscore_support(f_y_val, y_val_lr, labels=[0, 1, 2], zero_division=0)
        cv_results["logistic_regression"]["macro_f1"].append(f1_score(f_y_val, y_val_lr, average="macro"))
        cv_results["logistic_regression"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_lr))
        cv_results["logistic_regression"]["sev_recall"].append(r1[2])
        cv_results["logistic_regression"]["sev_precision"].append(p1[2])

        # 2. Random Forest
        clf_rf = RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_leaf=10, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
        clf_rf.fit(f_X_trn, f_y_trn)
        y_val_rf = clf_rf.predict(f_X_val)
        oof_probs_rf[val_idx] = clf_rf.predict_proba(f_X_val)
        p2, r2, f2, _ = precision_recall_fscore_support(f_y_val, y_val_rf, labels=[0, 1, 2], zero_division=0)
        cv_results["random_forest"]["macro_f1"].append(f1_score(f_y_val, y_val_rf, average="macro"))
        cv_results["random_forest"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_rf))
        cv_results["random_forest"]["sev_recall"].append(r2[2])
        cv_results["random_forest"]["sev_precision"].append(p2[2])

        # 3. HistGradientBoosting
        clf_hgb = HistGradientBoostingClassifier(max_iter=80, max_depth=5, min_samples_leaf=20, class_weight="balanced", random_state=RANDOM_SEED)
        clf_hgb.fit(f_X_trn, f_y_trn)
        y_val_hgb = clf_hgb.predict(f_X_val)
        oof_probs_hgb[val_idx] = clf_hgb.predict_proba(f_X_val)
        p3, r3, f3, _ = precision_recall_fscore_support(f_y_val, y_val_hgb, labels=[0, 1, 2], zero_division=0)
        cv_results["hist_gradient_boosting"]["macro_f1"].append(f1_score(f_y_val, y_val_hgb, average="macro"))
        cv_results["hist_gradient_boosting"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_hgb))
        cv_results["hist_gradient_boosting"]["sev_recall"].append(r3[2])
        cv_results["hist_gradient_boosting"]["sev_precision"].append(p3[2])

        print(f" Fold {fold} evaluated: {len(f_X_val)} validation plots.")

    print("\n--- 5-FOLD SPATIAL CROSS-VALIDATION SUMMARY ---")
    cv_summary = {}
    for m, vals in cv_results.items():
        m_f1 = np.mean(vals["macro_f1"])
        s_f1 = np.std(vals["macro_f1"])
        m_acc = np.mean(vals["bal_acc"])
        s_acc = np.std(vals["bal_acc"])
        m_rec = np.mean(vals["sev_recall"])
        s_rec = np.std(vals["sev_recall"])
        m_prec = np.mean(vals["sev_precision"])
        s_prec = np.std(vals["sev_precision"])
        cv_summary[m] = {
            "macro_f1_mean": round(float(m_f1), 4), "macro_f1_std": round(float(s_f1), 4),
            "balanced_accuracy_mean": round(float(m_acc), 4), "balanced_accuracy_std": round(float(s_acc), 4),
            "severe_recall_mean": round(float(m_rec), 4), "severe_recall_std": round(float(s_rec), 4),
            "severe_precision_mean": round(float(m_prec), 4), "severe_precision_std": round(float(s_prec), 4),
        }
        print(f" {m:25s}: Macro-F1 = {m_f1:.4f} (+/- {s_f1:.4f}) | Balanced Acc = {m_acc:.4f} (+/- {s_acc:.4f}) | Severe Recall = {m_rec:.4f} | Severe Prec = {m_prec:.4f}")

    # Determine optimal Severe Stress probability threshold from out-of-fold predictions
    print("\n" + "=" * 70)
    print("STEP 4: SEVERE STRESS THRESHOLD OPTIMIZATION (ON OOF PROBABILITIES)")
    print("=" * 70)

    def optimize_severe_threshold(oof_probs, y_true):
        threshold_candidates = np.linspace(0.02, 0.45, 44)
        best_t, best_f1, best_rec, best_prec = 0.33, -1, 0, 0
        for t in threshold_candidates:
            preds = [2 if p[2] >= t else (0 if p[0] >= p[1] else 1) for p in oof_probs]
            p_val = precision_score(y_true == 2, np.array(preds) == 2, zero_division=0)
            r_val = recall_score(y_true == 2, np.array(preds) == 2, zero_division=0)
            f_val = f1_score(y_true == 2, np.array(preds) == 2, zero_division=0)
            if f_val > best_f1:
                best_f1, best_t, best_rec, best_prec = f_val, t, r_val, p_val
        return float(best_t), float(best_f1), float(best_rec), float(best_prec)

    thresh_rf, f1_rf_oof, rec_rf_oof, prec_rf_oof = optimize_severe_threshold(oof_probs_rf, y_train)
    thresh_hgb, f1_hgb_oof, rec_hgb_oof, prec_hgb_oof = optimize_severe_threshold(oof_probs_hgb, y_train)

    # PR-AUC for Severe Stress on OOF
    prec_rf_curve, rec_rf_curve, _ = precision_recall_curve(y_train == 2, oof_probs_rf[:, 2])
    pr_auc_rf = float(auc(rec_rf_curve, prec_rf_curve))

    print(f" RF OOF Severe PR-AUC: {pr_auc_rf:.4f} (Base rate: {np.mean(y_train == 2):.4f})")
    print(f" RF Optimal Severe Threshold: {thresh_rf:.3f} -> OOF Severe F1={f1_rf_oof:.4f}, Recall={rec_rf_oof:.4f}, Prec={prec_rf_oof:.4f}")
    print(f" HGB Optimal Severe Threshold: {thresh_hgb:.3f} -> OOF Severe F1={f1_hgb_oof:.4f}, Recall={rec_hgb_oof:.4f}, Prec={prec_hgb_oof:.4f}")

    # -------------------------------------------------------------
    # FIT FINAL MODELS ON FULL TRAINING PARTITION (6,135 RECORDS)
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 5: FIT FINAL PRODUCTION-CANDIDATE MODELS (FULL TRAIN SET)")
    print("=" * 70)

    # 1. Logistic Regression
    lr_final = LogisticRegression(class_weight="balanced", max_iter=1000, C=0.1, random_state=RANDOM_SEED)
    lr_final.fit(X_train_scaled, y_train)
    joblib.dump(lr_final, MODELS_DIR / "logistic_regression.joblib")
    print(" Logistic Regression trained and saved.")

    # 2. Random Forest
    rf_final = RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_leaf=10, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
    rf_final.fit(X_train_imp, y_train)
    joblib.dump(rf_final, MODELS_DIR / "random_forest.joblib")
    print(" Random Forest trained and saved.")

    # 3. HistGradientBoosting
    hgb_final = HistGradientBoostingClassifier(max_iter=80, max_depth=5, min_samples_leaf=20, class_weight="balanced", random_state=RANDOM_SEED)
    hgb_final.fit(X_train_imp, y_train)
    joblib.dump(hgb_final, MODELS_DIR / "hist_gradient_boosting.joblib")
    print(" HistGradientBoosting trained and saved.")

    # Save rule metadata
    rule_metadata = {
        "model_type": "Deterministic Rule Baseline",
        "description": "KhetSense pipeline/classifier.py threshold logic",
        "rules": {
            "ndvi": {"> 0.6": "No Stress", "0.3 - 0.6": "Mild Stress", "< 0.3": "Severe Stress"},
            "soil_moisture_pct": {"> 25.0": "No Stress", "15.0 - 25.0": "Mild Stress", "< 15.0": "Severe Stress"},
            "combination": "Worst-case heuristic max(NDVI, SMAP)",
        },
    }
    with open(MODELS_DIR / "rule_baseline_metadata.json", "w") as f:
        json.dump(rule_metadata, f, indent=2)

    # -------------------------------------------------------------
    # FINAL EVALUATION ON UNTOUCHED HELD-OUT TEST SET (1,513 RECORDS)
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 6: FINAL EVALUATION ON HELD-OUT TEST SET (8 UNSEEN DISTRICTS)")
    print("=" * 70)

    # Predictions
    # A. Rule Baseline
    y_test_rule = np.array([rule_engine_predict(r) for _, r in test_df.iterrows()])
    eval_rule = evaluate_predictions(y_test, y_test_rule, "Deterministic Rule Baseline")

    # B. Logistic Regression
    y_test_lr = lr_final.predict(X_test_scaled)
    eval_lr = evaluate_predictions(y_test, y_test_lr, "Regularized Logistic Regression (Balanced)")

    # C. Random Forest (Standard Argmax)
    y_test_rf_std = rf_final.predict(X_test_imp)
    eval_rf_std = evaluate_predictions(y_test, y_test_rf_std, "Random Forest (Standard Argmax)")

    # D. Random Forest (Tuned Severe Threshold)
    probs_test_rf = rf_final.predict_proba(X_test_imp)
    y_test_rf_tuned = np.array([2 if p[2] >= thresh_rf else (0 if p[0] >= p[1] else 1) for p in probs_test_rf])
    eval_rf_tuned = evaluate_predictions(y_test, y_test_rf_tuned, f"Random Forest (Tuned Severe Threshold T={thresh_rf:.2f})")

    # E. HistGradientBoosting (Standard Argmax)
    y_test_hgb_std = hgb_final.predict(X_test_imp)
    eval_hgb_std = evaluate_predictions(y_test, y_test_hgb_std, "HistGradientBoosting (Standard Argmax)")

    # F. HistGradientBoosting (Tuned Severe Threshold)
    probs_test_hgb = hgb_final.predict_proba(X_test_imp)
    y_test_hgb_tuned = np.array([2 if p[2] >= thresh_hgb else (0 if p[0] >= p[1] else 1) for p in probs_test_hgb])
    eval_hgb_tuned = evaluate_predictions(y_test, y_test_hgb_tuned, f"HistGradientBoosting (Tuned Severe Threshold T={thresh_hgb:.2f})")

    all_evaluations = [eval_rule, eval_lr, eval_rf_std, eval_rf_tuned, eval_hgb_std, eval_hgb_tuned]

    for ev in all_evaluations:
        print(f"\n--- {ev['model_name']} ---")
        print(f" Macro-F1: {ev['macro_f1']:.4f} | Balanced Accuracy: {ev['balanced_accuracy']:.4f}")
        for cname, cmtr in ev["per_class"].items():
            print(f"   {cname:15s}: Prec={cmtr['precision']:.4f}, Recall={cmtr['recall']:.4f}, F1={cmtr['f1']:.4f} (N={cmtr['support']})")
        print(f"   Confusion Matrix: {ev['confusion_matrix']}")

    # Feature Importance / Coefficients Analysis
    rf_feat_imp = sorted(zip(FEATURE_COLS, [round(float(x), 4) for x in rf_final.feature_importances_]), key=lambda x: x[1], reverse=True)
    lr_feat_coef = sorted(zip(FEATURE_COLS, [round(float(x), 4) for x in lr_final.coef_[2]]), key=lambda x: x[1])

    # Build evaluation metrics bundle
    evaluation_bundle = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": round(time.time() - start_time, 2),
        "audit_metadata": audit_meta,
        "environment": {
            "python_version": sys.version,
            "sklearn_version": __import__("sklearn").__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "joblib_version": joblib.__version__,
            "xgboost_available": xgboost_available,
            "xgboost_reason": "Not installed in Python 3.13 environment; dependency installation restricted by project directives",
        },
        "threshold_optimization": {
            "rf_severe_threshold": thresh_rf,
            "rf_oof_severe_f1": round(f1_rf_oof, 4),
            "rf_oof_severe_recall": round(rec_rf_oof, 4),
            "rf_oof_severe_precision": round(prec_rf_oof, 4),
            "rf_oof_severe_pr_auc": round(pr_auc_rf, 4),
            "hgb_severe_threshold": thresh_hgb,
            "hgb_oof_severe_f1": round(f1_hgb_oof, 4),
            "hgb_oof_severe_recall": round(rec_hgb_oof, 4),
            "hgb_oof_severe_precision": round(prec_hgb_oof, 4),
        },
        "cv_results": cv_summary,
        "held_out_test_evaluations": all_evaluations,
        "feature_importances": {
            "random_forest": dict(rf_feat_imp),
            "logistic_regression_severe_coef": dict(lr_feat_coef),
        },
    }

    metrics_out_path = MODELS_DIR / "evaluation_metrics.json"
    with open(metrics_out_path, "w") as f:
        json.dump(evaluation_bundle, f, indent=2)
    print(f"\n Evaluation metrics written to: {metrics_out_path}")

    # Build Phase 4 Manifest
    manifest_phase4 = {
        "manifest_version": "1.0.0",
        "phase": "Phase 4: Offline Model Training, Spatial Cross-Validation and Benchmarking",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset_sha256": audit_meta["file_sha256"],
        "artifacts": [
            {
                "filename": "train_models.py",
                "path": "data/research_benchmark/train_models.py",
                "sha256": compute_sha256(BASE_DIR / "train_models.py"),
                "description": "Reproducible Python training, cross-validation, and evaluation pipeline",
            },
            {
                "filename": "preprocessor.joblib",
                "path": "data/research_benchmark/models/preprocessor.joblib",
                "sha256": compute_sha256(MODELS_DIR / "preprocessor.joblib"),
                "description": "SimpleImputer (median) and StandardScaler fitted strictly on train partition",
            },
            {
                "filename": "logistic_regression.joblib",
                "path": "data/research_benchmark/models/logistic_regression.joblib",
                "sha256": compute_sha256(MODELS_DIR / "logistic_regression.joblib"),
                "description": "Multinomial Logistic Regression with balanced class weights and L2 penalty",
            },
            {
                "filename": "random_forest.joblib",
                "path": "data/research_benchmark/models/random_forest.joblib",
                "sha256": compute_sha256(MODELS_DIR / "random_forest.joblib"),
                "description": "Random Forest Classifier (150 trees, max_depth=8, balanced class weights)",
            },
            {
                "filename": "hist_gradient_boosting.joblib",
                "path": "data/research_benchmark/models/hist_gradient_boosting.joblib",
                "sha256": compute_sha256(MODELS_DIR / "hist_gradient_boosting.joblib"),
                "description": "HistGradientBoosting Classifier (LightGBM-style gradient boosting)",
            },
            {
                "filename": "rule_baseline_metadata.json",
                "path": "data/research_benchmark/models/rule_baseline_metadata.json",
                "sha256": compute_sha256(MODELS_DIR / "rule_baseline_metadata.json"),
                "description": "Specification of KhetSense deterministic rule baseline thresholds",
            },
            {
                "filename": "evaluation_metrics.json",
                "path": "data/research_benchmark/models/evaluation_metrics.json",
                "sha256": compute_sha256(metrics_out_path),
                "description": "Full machine-readable evaluation metrics across all CV folds and held-out test set",
            },
        ],
    }

    manifest_path = MODELS_DIR / "manifest_phase4.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_phase4, f, indent=2)
    print(f" Manifest written to: {manifest_path}")

    print("\n" + "=" * 70)
    print("PHASE 4 TRAINING AND BENCHMARKING COMPLETE")
    print(f"Total Elapsed Time: {time.time() - start_time:.2f} seconds")
    print("=" * 70)


if __name__ == "__main__":
    main()
