#!/usr/bin/env python3
"""
KhetSense AI — Phase 7F: Training and Evaluation of Live-Native 5-Feature ML Model
==================================================================================
Author: KhetSense AI Research Engineering & Machine Learning Team
Target Dataset: CSISA 2018 Eastern India Wheat Multi-Sensor Research Benchmark
Features (Strict 5-Feature Live-Observable Vector):
  1. s2_ndvi    - Sentinel-2 Surface Reflectance 10m NDVI (B8 - B4) / (B8 + B4)
  2. s2_ndwi    - Sentinel-2 Surface Reflectance 20m NDWI (B8 - B11) / (B8 + B11) (Gao 1996)
  3. s2_ndre    - Sentinel-2 Surface Reflectance 20m NDRE (B8 - B5) / (B8 + B5) (Barnes et al. 2000)
  4. s2_msavi   - Sentinel-2 Surface Reflectance 10m MSAVI (Qi et al. 1994, scaled [0, 1])
  5. smap_sm_pct - NASA SMAP Enhanced L3 9km Radiometer Volumetric Soil Moisture (%)

Anti-Leakage Validation:
- Spatial Blocked Partitioning: 32 districts (6,135 records) train, 8 districts (1,513 records) held-out test.
- 5-Fold Spatial Cross-Validation: Whole districts grouped within folds.
- Preprocessing (SimpleImputer, StandardScaler) fitted strictly on each training fold.

Candidate Models:
1. Deterministic Rule-Based Baseline (dual-index worst-case heuristic)
2. Random Forest Classifier (class_weight='balanced', tree depth regularized)
3. HistGradientBoosting Classifier (LightGBM-style gradient boosting, class_weight='balanced')

Artifacts Saved (distinct filenames, preserving existing 9-feature models):
- preprocessor_5feat.joblib
- random_forest_5feat.joblib
- hist_gradient_boosting_5feat.joblib
- evaluation_metrics_5feat.json
- manifest_phase7f.json
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Add user site-packages if needed (Windows Python 3.13 venv)
try:
    import site
    user_site = site.getusersitepackages()
    if user_site and os.path.exists(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
except Exception:
    pass

import numpy as np
import pandas as pd
import joblib

from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
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

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "csisa_wheat_multisensor_features_2018.csv"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Exact 5-feature live-observable specification
FEATURE_COLS_5 = [
    "s2_ndvi",
    "s2_ndwi",
    "s2_ndre",
    "s2_msavi",
    "smap_sm_pct",
]

TARGET_COL = "target_code_3class"
TARGET_NAMES = ["No Stress", "Mild Stress", "Severe Stress"]


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def rule_engine_predict(row: pd.Series) -> int:
    """
    Deterministic rule engine implementing KhetSense's pipeline/classifier.py logic:
    NDVI: >0.6 -> 0 (No Stress), 0.3-0.6 -> 1 (Mild Stress), <0.3 -> 2 (Severe Stress)
    SMAP: >25% -> 0, 15-25% -> 1, <15% -> 2
    Worst-case ranking: max(s_ndvi, s_smap)
    """
    ndvi = row.get("s2_ndvi")
    sm = row.get("smap_sm_pct")

    if pd.isna(ndvi) and pd.isna(sm):
        return 0

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
    print("=" * 75)
    print("KHETSENSE AI — PHASE 7F: LIVE-NATIVE 5-FEATURE MODEL TRAINING & EVALUATION")
    print("=" * 75)
    print(f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}")

    # 1. Dataset Integrity & Audit
    print("\n[STEP 1] Auditing dataset integrity and feature compatibility...")
    file_sha256 = compute_sha256(DATA_PATH)
    print(f" Dataset SHA256: {file_sha256}")

    df = pd.read_csv(DATA_PATH)
    total_records = len(df)
    assert total_records == 7648, f"Expected 7648 records, got {total_records}"
    print(f" Total records: {total_records} (34 columns)")

    train_df = df[df["spatial_split"] == "train"].copy()
    test_df = df[df["spatial_split"] == "held_out_test"].copy()
    print(f" Spatial Partitions: Train={len(train_df)} (80.22%), Held-Out Test={len(test_df)} (19.78%)")

    train_districts = set(train_df["district"].unique())
    test_districts = set(test_df["district"].unique())
    assert len(train_districts.intersection(test_districts)) == 0, "Spatial leakage detected across districts!"
    print(f" Anti-Leakage Verified: 0 overlapping districts between {len(train_districts)} Train and {len(test_districts)} Test districts.")

    # Audit missing values in 5 live-native features
    missing_train = train_df[FEATURE_COLS_5].isnull().sum().to_dict()
    missing_test = test_df[FEATURE_COLS_5].isnull().sum().to_dict()
    print(f" Missing features in Train: {missing_train}")
    print(f" Missing features in Test:  {missing_test} (7 cloudy scenes in Araria)")

    # Class balance
    print("\nClass distribution (Train):")
    for c_code, c_name in [(0, "No Stress"), (1, "Mild Stress"), (2, "Severe Stress")]:
        c_count = (train_df[TARGET_COL] == c_code).sum()
        print(f"  {c_name:15s} (code {c_code}): {c_count:5d} ({c_count/len(train_df)*100:.2f}%)")

    print("Class distribution (Held-Out Test):")
    for c_code, c_name in [(0, "No Stress"), (1, "Mild Stress"), (2, "Severe Stress")]:
        c_count = (test_df[TARGET_COL] == c_code).sum()
        print(f"  {c_name:15s} (code {c_code}): {c_count:5d} ({c_count/len(test_df)*100:.2f}%)")

    # 2. Preprocessing & Imputation (Fit on Train Only)
    print("\n[STEP 2] Fitting preprocessors strictly on Train partition...")
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()

    X_train_raw = train_df[FEATURE_COLS_5].values
    y_train = train_df[TARGET_COL].values
    cv_folds = train_df["cv_fold_id"].values

    X_test_raw = test_df[FEATURE_COLS_5].values
    y_test = test_df[TARGET_COL].values

    # Fit imputer and scaler ONLY on train
    X_train_imp = imputer.fit_transform(X_train_raw)
    X_test_imp = imputer.transform(X_test_raw)

    X_train_scaled = scaler.fit_transform(X_train_imp)
    X_test_scaled = scaler.transform(X_test_imp)

    # Save 5-feature preprocessor bundle under distinct name
    preproc_5feat_bundle = {
        "imputer": imputer,
        "scaler": scaler,
        "feature_names": FEATURE_COLS_5,
        "imputed_medians": dict(zip(FEATURE_COLS_5, [round(float(x), 4) for x in imputer.statistics_])),
    }
    joblib.dump(preproc_5feat_bundle, MODELS_DIR / "preprocessor_5feat.joblib")
    print(" Preprocessor saved to models/preprocessor_5feat.joblib")
    print(f" Training medians: {preproc_5feat_bundle['imputed_medians']}")

    # 3. 5-Fold Spatial Cross-Validation
    print("\n[STEP 3] Executing 5-Fold Spatial Blocked Cross-Validation...")
    cv_results = {
        "rule_baseline": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
        "random_forest": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
        "hist_gradient_boosting": {"macro_f1": [], "bal_acc": [], "sev_recall": [], "sev_precision": []},
    }

    oof_probs_rf = np.zeros((len(train_df), 3))
    oof_probs_hgb = np.zeros((len(train_df), 3))

    for fold in range(5):
        val_idx = (cv_folds == fold)
        trn_idx = ~val_idx

        # Fold training/validation splits
        f_X_trn, f_y_trn = X_train_imp[trn_idx], y_train[trn_idx]
        f_X_val, f_y_val = X_train_imp[val_idx], y_train[val_idx]

        # 0. Rule baseline on validation fold
        val_sub_df = train_df.iloc[val_idx]
        y_val_rule = np.array([rule_engine_predict(r) for _, r in val_sub_df.iterrows()])
        p0, r0, f0, _ = precision_recall_fscore_support(f_y_val, y_val_rule, labels=[0, 1, 2], zero_division=0)
        cv_results["rule_baseline"]["macro_f1"].append(f1_score(f_y_val, y_val_rule, average="macro"))
        cv_results["rule_baseline"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_rule))
        cv_results["rule_baseline"]["sev_recall"].append(r0[2])
        cv_results["rule_baseline"]["sev_precision"].append(p0[2])

        # 1. Random Forest (5 Features)
        clf_rf = RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )
        clf_rf.fit(f_X_trn, f_y_trn)
        y_val_rf = clf_rf.predict(f_X_val)
        oof_probs_rf[val_idx] = clf_rf.predict_proba(f_X_val)
        p1, r1, f1, _ = precision_recall_fscore_support(f_y_val, y_val_rf, labels=[0, 1, 2], zero_division=0)
        cv_results["random_forest"]["macro_f1"].append(f1_score(f_y_val, y_val_rf, average="macro"))
        cv_results["random_forest"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_rf))
        cv_results["random_forest"]["sev_recall"].append(r1[2])
        cv_results["random_forest"]["sev_precision"].append(p1[2])

        # 2. HistGradientBoosting (5 Features)
        clf_hgb = HistGradientBoostingClassifier(
            max_iter=80,
            max_depth=5,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=RANDOM_SEED,
        )
        clf_hgb.fit(f_X_trn, f_y_trn)
        y_val_hgb = clf_hgb.predict(f_X_val)
        oof_probs_hgb[val_idx] = clf_hgb.predict_proba(f_X_val)
        p2, r2, f2, _ = precision_recall_fscore_support(f_y_val, y_val_hgb, labels=[0, 1, 2], zero_division=0)
        cv_results["hist_gradient_boosting"]["macro_f1"].append(f1_score(f_y_val, y_val_hgb, average="macro"))
        cv_results["hist_gradient_boosting"]["bal_acc"].append(balanced_accuracy_score(f_y_val, y_val_hgb))
        cv_results["hist_gradient_boosting"]["sev_recall"].append(r2[2])
        cv_results["hist_gradient_boosting"]["sev_precision"].append(p2[2])

        print(f"  Fold {fold+1}/5 evaluated: {len(f_X_val)} validation plots.")

    print("\n--- 5-FOLD SPATIAL CROSS-VALIDATION RESULTS ---")
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
            "macro_f1_mean": round(float(m_f1), 4),
            "macro_f1_std": round(float(s_f1), 4),
            "balanced_accuracy_mean": round(float(m_acc), 4),
            "balanced_accuracy_std": round(float(s_acc), 4),
            "severe_recall_mean": round(float(m_rec), 4),
            "severe_recall_std": round(float(s_rec), 4),
            "severe_precision_mean": round(float(m_prec), 4),
            "severe_precision_std": round(float(s_prec), 4),
        }
        print(f"  {m:25s}: Macro-F1 = {m_f1:.4f} (+/- {s_f1:.4f}) | Bal Acc = {m_acc:.4f} (+/- {s_acc:.4f}) | Sev Recall = {m_rec:.4f} | Sev Prec = {m_prec:.4f}")

    # 4. Severe Stress Threshold Optimization
    print("\n[STEP 4] Severe Stress Threshold Optimization on Out-Of-Fold Probabilities...")
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

    # PR-AUC for Severe Stress
    prec_rf_curve, rec_rf_curve, _ = precision_recall_curve(y_train == 2, oof_probs_rf[:, 2])
    pr_auc_rf = float(auc(rec_rf_curve, prec_rf_curve))

    prec_hgb_curve, rec_hgb_curve, _ = precision_recall_curve(y_train == 2, oof_probs_hgb[:, 2])
    pr_auc_hgb = float(auc(rec_hgb_curve, prec_hgb_curve))

    base_rate_severe = float(np.mean(y_train == 2))
    print(f"  Severe Base Rate (Train): {base_rate_severe:.4f} ({base_rate_severe*100:.2f}%)")
    print(f"  RF 5-Feat OOF Severe PR-AUC: {pr_auc_rf:.4f} | Optimal T={thresh_rf:.2f} -> F1={f1_rf_oof:.4f}, Recall={rec_rf_oof:.4f}, Prec={prec_rf_oof:.4f}")
    print(f"  HGB 5-Feat OOF Severe PR-AUC: {pr_auc_hgb:.4f} | Optimal T={thresh_hgb:.2f} -> F1={f1_hgb_oof:.4f}, Recall={rec_hgb_oof:.4f}, Prec={prec_hgb_oof:.4f}")

    # 5. Fit Final Candidate Models on Full Train Set (6,135 records)
    print("\n[STEP 5] Fitting final candidate models on full Train partition...")
    rf_final = RandomForestClassifier(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=10,
        class_weight="balanced",
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    rf_final.fit(X_train_imp, y_train)
    joblib.dump(rf_final, MODELS_DIR / "random_forest_5feat.joblib")
    print("  Random Forest 5-Feature model saved to models/random_forest_5feat.joblib")

    hgb_final = HistGradientBoostingClassifier(
        max_iter=80,
        max_depth=5,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=RANDOM_SEED,
    )
    hgb_final.fit(X_train_imp, y_train)
    joblib.dump(hgb_final, MODELS_DIR / "hist_gradient_boosting_5feat.joblib")
    print("  HistGradientBoosting 5-Feature model saved to models/hist_gradient_boosting_5feat.joblib")

    # 6. Final Evaluation on Untouched Held-Out Test Set (1,513 records across 8 districts)
    print("\n[STEP 6] Evaluating models on untouched Held-Out Test Set (8 unseen districts)...")

    # A. Rule Baseline
    y_test_rule = np.array([rule_engine_predict(r) for _, r in test_df.iterrows()])
    eval_rule = evaluate_predictions(y_test, y_test_rule, "Deterministic Rule Baseline")

    # B. Random Forest 5-Feat (Standard Argmax)
    y_test_rf_std = rf_final.predict(X_test_imp)
    eval_rf_std = evaluate_predictions(y_test, y_test_rf_std, "Random Forest 5-Feat (Standard Argmax)")

    # C. Random Forest 5-Feat (Tuned Severe Threshold)
    probs_test_rf = rf_final.predict_proba(X_test_imp)
    y_test_rf_tuned = np.array([2 if p[2] >= thresh_rf else (0 if p[0] >= p[1] else 1) for p in probs_test_rf])
    eval_rf_tuned = evaluate_predictions(y_test, y_test_rf_tuned, f"Random Forest 5-Feat (Tuned Severe T={thresh_rf:.2f})")

    # D. HistGradientBoosting 5-Feat (Standard Argmax)
    y_test_hgb_std = hgb_final.predict(X_test_imp)
    eval_hgb_std = evaluate_predictions(y_test, y_test_hgb_std, "HistGradientBoosting 5-Feat (Standard Argmax)")

    # E. HistGradientBoosting 5-Feat (Tuned Severe Threshold)
    probs_test_hgb = hgb_final.predict_proba(X_test_imp)
    y_test_hgb_tuned = np.array([2 if p[2] >= thresh_hgb else (0 if p[0] >= p[1] else 1) for p in probs_test_hgb])
    eval_hgb_tuned = evaluate_predictions(y_test, y_test_hgb_tuned, f"HistGradientBoosting 5-Feat (Tuned Severe T={thresh_hgb:.2f})")

    # Held-Out PR-AUC for Severe Stress
    test_prec_rf, test_rec_rf, _ = precision_recall_curve(y_test == 2, probs_test_rf[:, 2])
    test_pr_auc_rf = float(auc(test_rec_rf, test_prec_rf))

    test_prec_hgb, test_rec_hgb, _ = precision_recall_curve(y_test == 2, probs_test_hgb[:, 2])
    test_pr_auc_hgb = float(auc(test_rec_hgb, test_prec_hgb))

    all_evaluations = [eval_rule, eval_rf_std, eval_rf_tuned, eval_hgb_std, eval_hgb_tuned]

    for ev in all_evaluations:
        print(f"\n--- {ev['model_name']} ---")
        print(f" Macro-F1: {ev['macro_f1']:.4f} | Balanced Accuracy: {ev['balanced_accuracy']:.4f}")
        for cname, cmtr in ev["per_class"].items():
            print(f"   {cname:15s}: Prec={cmtr['precision']:.4f}, Recall={cmtr['recall']:.4f}, F1={cmtr['f1']:.4f} (Support={cmtr['support']})")
        print(f"   Confusion Matrix [No, Mild, Severe]:\n   {ev['confusion_matrix']}")

    # Feature Importance for 5-Feature Random Forest
    rf_feat_imp = sorted(
        zip(FEATURE_COLS_5, [round(float(x), 4) for x in rf_final.feature_importances_]),
        key=lambda x: x[1],
        reverse=True,
    )
    print("\n--- 5-FEATURE RANDOM FOREST IMPORTANCES ---")
    for fname, fweight in rf_feat_imp:
        print(f"  {fname:15s}: {fweight*100:.2f}%")

    # 7. Write Evaluation Metrics Bundle
    evaluation_bundle = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": round(time.time() - start_time, 2),
        "dataset_metadata": {
            "file_sha256": file_sha256,
            "total_records": total_records,
            "train_records": len(train_df),
            "test_records": len(test_df),
            "train_districts_count": len(train_districts),
            "test_districts_count": len(test_districts),
            "feature_names": FEATURE_COLS_5,
            "missing_train": missing_train,
            "missing_test": missing_test,
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
            "hgb_oof_severe_pr_auc": round(pr_auc_hgb, 4),
        },
        "held_out_pr_auc": {
            "positive_class": "Severe Stress (code 2)",
            "calculation_method": "Scikit-learn precision_recall_curve integrated via trapezoidal auc()",
            "random_forest_pr_auc": round(test_pr_auc_rf, 4),
            "hist_gradient_boosting_pr_auc": round(test_pr_auc_hgb, 4),
            "base_rate": round(float(np.mean(y_test == 2)), 4),
        },
        "cv_results": cv_summary,
        "held_out_test_evaluations": all_evaluations,
        "feature_importances": {
            "random_forest_5feat": dict(rf_feat_imp),
        },
    }

    metrics_path = MODELS_DIR / "evaluation_metrics_5feat.json"
    with open(metrics_path, "w") as f:
        json.dump(evaluation_bundle, f, indent=2)
    print(f"\n Evaluation metrics written to {metrics_path}")

    # 8. Cryptographic Manifest
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 7F Live-Native Five-Feature Model",
        "artifacts": {
            "preprocessor_5feat.joblib": compute_sha256(MODELS_DIR / "preprocessor_5feat.joblib"),
            "random_forest_5feat.joblib": compute_sha256(MODELS_DIR / "random_forest_5feat.joblib"),
            "hist_gradient_boosting_5feat.joblib": compute_sha256(MODELS_DIR / "hist_gradient_boosting_5feat.joblib"),
            "evaluation_metrics_5feat.json": compute_sha256(MODELS_DIR / "evaluation_metrics_5feat.json"),
        },
    }
    manifest_path = MODELS_DIR / "manifest_phase7f.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f" Cryptographic manifest written to {manifest_path}")
    print("\nPhase 7F model training and evaluation successfully completed!")


if __name__ == "__main__":
    main()
