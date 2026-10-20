from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.models.entities import DentalChartTooth, ToothFinding


# FDI Two-Digit Tooth Numbering System (Permanent & Primary Dentition)
PERMANENT_TEETH_FDI: List[Dict[str, str]] = [
    # Upper Right (Quadrant 1) — displayed right-to-left (18 to 11)
    {"fdi": "18", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Third Molar (Wisdom)"},
    {"fdi": "17", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Second Molar"},
    {"fdi": "16", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right First Molar"},
    {"fdi": "15", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Second Premolar"},
    {"fdi": "14", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right First Premolar"},
    {"fdi": "13", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Canine"},
    {"fdi": "12", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Lateral Incisor"},
    {"fdi": "11", "arch": "Upper", "quadrant": "Q1 (Upper Right)", "name": "Upper Right Central Incisor"},
    # Upper Left (Quadrant 2) — displayed left-to-right (21 to 28)
    {"fdi": "21", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Central Incisor"},
    {"fdi": "22", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Lateral Incisor"},
    {"fdi": "23", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Canine"},
    {"fdi": "24", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left First Premolar"},
    {"fdi": "25", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Second Premolar"},
    {"fdi": "26", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left First Molar"},
    {"fdi": "27", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Second Molar"},
    {"fdi": "28", "arch": "Upper", "quadrant": "Q2 (Upper Left)", "name": "Upper Left Third Molar (Wisdom)"},
    # Lower Right (Quadrant 4) — displayed right-to-left (48 to 41)
    {"fdi": "48", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Third Molar (Wisdom)"},
    {"fdi": "47", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Second Molar"},
    {"fdi": "46", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right First Molar"},
    {"fdi": "45", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Second Premolar"},
    {"fdi": "44", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right First Premolar"},
    {"fdi": "43", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Canine"},
    {"fdi": "42", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Lateral Incisor"},
    {"fdi": "41", "arch": "Lower", "quadrant": "Q4 (Lower Right)", "name": "Lower Right Central Incisor"},
    # Lower Left (Quadrant 3) — displayed left-to-right (31 to 38)
    {"fdi": "31", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Central Incisor"},
    {"fdi": "32", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Lateral Incisor"},
    {"fdi": "33", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Canine"},
    {"fdi": "34", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left First Premolar"},
    {"fdi": "35", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Second Premolar"},
    {"fdi": "36", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left First Molar"},
    {"fdi": "37", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Second Molar"},
    {"fdi": "38", "arch": "Lower", "quadrant": "Q3 (Lower Left)", "name": "Lower Left Third Molar (Wisdom)"},
]

PRIMARY_TEETH_FDI: List[Dict[str, str]] = [
    # Upper Right Primary (Quadrant 5: 55 to 51)
    {"fdi": "55", "arch": "Upper Primary", "quadrant": "Q5 (Upper Right Primary)", "name": "Primary Upper Right Second Molar"},
    {"fdi": "54", "arch": "Upper Primary", "quadrant": "Q5 (Upper Right Primary)", "name": "Primary Upper Right First Molar"},
    {"fdi": "53", "arch": "Upper Primary", "quadrant": "Q5 (Upper Right Primary)", "name": "Primary Upper Right Canine"},
    {"fdi": "52", "arch": "Upper Primary", "quadrant": "Q5 (Upper Right Primary)", "name": "Primary Upper Right Lateral Incisor"},
    {"fdi": "51", "arch": "Upper Primary", "quadrant": "Q5 (Upper Right Primary)", "name": "Primary Upper Right Central Incisor"},
    # Upper Left Primary (Quadrant 6: 61 to 65)
    {"fdi": "61", "arch": "Upper Primary", "quadrant": "Q6 (Upper Left Primary)", "name": "Primary Upper Left Central Incisor"},
    {"fdi": "62", "arch": "Upper Primary", "quadrant": "Q6 (Upper Left Primary)", "name": "Primary Upper Left Lateral Incisor"},
    {"fdi": "63", "arch": "Upper Primary", "quadrant": "Q6 (Upper Left Primary)", "name": "Primary Upper Left Canine"},
    {"fdi": "64", "arch": "Upper Primary", "quadrant": "Q6 (Upper Left Primary)", "name": "Primary Upper Left First Molar"},
    {"fdi": "65", "arch": "Upper Primary", "quadrant": "Q6 (Upper Left Primary)", "name": "Primary Upper Left Second Molar"},
    # Lower Right Primary (Quadrant 8: 85 to 81)
    {"fdi": "85", "arch": "Lower Primary", "quadrant": "Q8 (Lower Right Primary)", "name": "Primary Lower Right Second Molar"},
    {"fdi": "84", "arch": "Lower Primary", "quadrant": "Q8 (Lower Right Primary)", "name": "Primary Lower Right First Molar"},
    {"fdi": "83", "arch": "Lower Primary", "quadrant": "Q8 (Lower Right Primary)", "name": "Primary Lower Right Canine"},
    {"fdi": "82", "arch": "Lower Primary", "quadrant": "Q8 (Lower Right Primary)", "name": "Primary Lower Right Lateral Incisor"},
    {"fdi": "81", "arch": "Lower Primary", "quadrant": "Q8 (Lower Right Primary)", "name": "Primary Lower Right Central Incisor"},
    # Lower Left Primary (Quadrant 7: 71 to 75)
    {"fdi": "71", "arch": "Lower Primary", "quadrant": "Q7 (Lower Left Primary)", "name": "Primary Lower Left Central Incisor"},
    {"fdi": "72", "arch": "Lower Primary", "quadrant": "Q7 (Lower Left Primary)", "name": "Primary Lower Left Lateral Incisor"},
    {"fdi": "73", "arch": "Lower Primary", "quadrant": "Q7 (Lower Left Primary)", "name": "Primary Lower Left Canine"},
    {"fdi": "74", "arch": "Lower Primary", "quadrant": "Q7 (Lower Left Primary)", "name": "Primary Lower Left First Molar"},
    {"fdi": "75", "arch": "Lower Primary", "quadrant": "Q7 (Lower Left Primary)", "name": "Primary Lower Left Second Molar"},
]

ALL_FDI_MAP: Dict[str, Dict[str, str]] = {
    t["fdi"]: {**t, "dentition_type": "Permanent"} for t in PERMANENT_TEETH_FDI
}
for t in PRIMARY_TEETH_FDI:
    ALL_FDI_MAP[t["fdi"]] = {**t, "dentition_type": "Primary"}

ALLOWED_TOOTH_CONDITIONS = {
    "Sound",
    "Caries",
    "Filled",
    "Crown",
    "RootCanalTreated",
    "Missing",
    "ExtractionIndicated",
    "Implant",
    "BridgePontic",
    "Fractured",
    "Sealant",
}


def get_patient_dental_chart(db: Session, patient_id: int) -> Dict[str, Any]:
    """Return full FDI permanent & primary dental chart merged with persisted findings for the patient."""
    persisted_rows = (
        db.query(DentalChartTooth)
        .filter(DentalChartTooth.patient_id == patient_id)
        .all()
    )
    by_fdi = {row.tooth_fdi: row for row in persisted_rows}

    findings = (
        db.query(ToothFinding)
        .filter(ToothFinding.patient_id == patient_id)
        .order_by(ToothFinding.recorded_at.desc())
        .all()
    )

    def _build_list(catalog: List[Dict[str, str]], dentition: str) -> List[Dict[str, Any]]:
        result = []
        for meta in catalog:
            fdi = meta["fdi"]
            row = by_fdi.get(fdi)
            result.append(
                {
                    "tooth_fdi": fdi,
                    "tooth_name": meta["name"],
                    "arch": meta["arch"],
                    "quadrant": meta["quadrant"],
                    "dentition_type": dentition,
                    "condition_status": row.condition_status if row else "Sound",
                    "surfaces": row.surfaces if row else None,
                    "mobility_grade": row.mobility_grade if row else None,
                    "clinical_notes": row.clinical_notes if row else None,
                    "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
                }
            )
        return result

    return {
        "patient_id": patient_id,
        "notation_system": "FDI Two-Digit Notation",
        "disclaimer": (
            "This visual odontogram displays documented clinical observations only and does not replace "
            "a professional in-person dental examination."
        ),
        "permanent_teeth": _build_list(PERMANENT_TEETH_FDI, "Permanent"),
        "primary_teeth": _build_list(PRIMARY_TEETH_FDI, "Primary"),
        "findings_history": [
            {
                "id": f.id,
                "tooth_fdi": f.tooth_fdi,
                "condition_status": f.condition_status,
                "surfaces": f.surfaces,
                "finding_notes": f.finding_notes,
                "treatment_recommended": f.treatment_recommended,
                "doctor_id": f.doctor_id,
                "recorded_at": f.recorded_at.isoformat() if f.recorded_at else None,
            }
            for f in findings
        ],
    }
