from datetime import date, time, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.permissions import PERMISSIONS_CATALOG, ROLE_ADMIN, ROLE_DEFAULT_PERMISSIONS, ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import hash_password
from app.models.entities import (
    Allergy,
    Appointment,
    ClinicalEncounter,
    ClinicSetting,
    ConsentRecord,
    DentalChartTooth,
    Diagnosis,
    DoctorProfile,
    DoctorSchedule,
    Invoice,
    InvoiceLineItem,
    MedicalHistory,
    Notification,
    PatientProfile,
    Payment,
    Permission,
    Prescription,
    PrescriptionItem,
    Receipt,
    Review,
    Role,
    RolePermission,
    Service,
    StaffProfile,
    ToothFinding,
    TreatmentPlan,
    TreatmentPlanItem,
    TreatmentRecord,
    User,
)


GENUINE_SERVICES = [
    {
        "code": "SRV-001",
        "slug": "dental-consultation",
        "name": "Dental Consultation",
        "category": "Diagnostic & Preventive",
        "tagline": "Personalized Oral Health Evaluation & Care Planning",
        "short_description": "Comprehensive oral health discussion, symptom review, and personalized dental care guidance with Dr. Aisha Salman.",
        "detailed_description": (
            "A thorough initial or follow-up dental consultation at Rumi Dental Care. We listen to your concerns, "
            "review your medical and dental history, evaluate your oral health goals, and outline clear, transparent "
            "treatment options tailored to your needs."
        ),
        "price": Decimal("1500.00"),
        "duration_minutes": 30,
        "icon_name": "stethoscope",
        "display_order": 1,
    },
    {
        "code": "SRV-002",
        "slug": "dental-examinations",
        "name": "Dental Examinations",
        "category": "Diagnostic & Preventive",
        "tagline": "Complete Intra-Oral, Periodontal & Caries Screening",
        "short_description": "Systematic tooth-by-tooth FDI charting, gum health check, and early cavity detection using modern diagnostic instruments.",
        "detailed_description": (
            "Routine and comprehensive dental examinations designed to detect tooth decay, gum inflammation, bite "
            "irregularities, and enamel wear early—saving teeth and preventing painful dental emergencies."
        ),
        "price": Decimal("2000.00"),
        "duration_minutes": 30,
        "icon_name": "clipboard-check",
        "display_order": 2,
    },
    {
        "code": "SRV-003",
        "slug": "dental-x-rays",
        "name": "Dental X-Rays",
        "category": "Diagnostic & Preventive",
        "tagline": "Dental X-rays: Clear Insights, Precise Care.",
        "short_description": "High-clarity digital periapical and bitewing dental radiographs for accurate root, bone, and interproximal diagnosis.",
        "detailed_description": (
            "Digital dental radiography with minimal radiation exposure, providing immediate high-resolution views of "
            "tooth roots, bone levels, impacted teeth, and hidden decay beneath existing restorations."
        ),
        "price": Decimal("1200.00"),
        "duration_minutes": 20,
        "icon_name": "scan",
        "display_order": 3,
    },
    {
        "code": "SRV-004",
        "slug": "teeth-cleaning-scaling-polishing",
        "name": "Teeth Cleaning, Scaling & Polishing",
        "category": "Preventive & Periodontal",
        "tagline": "Promote Oral Health and Prevent Gum Disease",
        "short_description": "Ultrasonic dental scaling and polishing to remove stubborn plaque, tartar (calculus), and surface stains.",
        "detailed_description": (
            "Professional ultrasonic dental scaling and prophylaxis that gently removes hardened calculus and plaque "
            "from tooth surfaces and along the gumline, followed by smooth enamel polishing for healthier gums and fresher breath."
        ),
        "price": Decimal("4500.00"),
        "duration_minutes": 45,
        "icon_name": "sparkles",
        "display_order": 4,
    },
    {
        "code": "SRV-005",
        "slug": "dental-fillings",
        "name": "Dental Fillings",
        "category": "Restorative Dentistry",
        "tagline": "Tooth-Colored Composite & Laser-Assisted Restorations",
        "short_description": "Durable, natural-looking composite and glass ionomer dental fillings to restore decayed or fractured teeth.",
        "detailed_description": (
            "Modern tooth-colored restorative fillings that bond directly to healthy tooth structure, restoring strength, "
            "chewing function, and natural aesthetics while preventing further bacterial progression."
        ),
        "price": Decimal("4000.00"),
        "duration_minutes": 45,
        "icon_name": "shield-check",
        "display_order": 5,
    },
    {
        "code": "SRV-006",
        "slug": "root-canal-treatment",
        "name": "Root Canal Treatment",
        "category": "Endodontics",
        "tagline": "Root Canal: Saving Teeth, Relieving Pain.",
        "short_description": "Painless, modern endodontic therapy to eliminate deep tooth infection, relieve pain, and save your natural tooth.",
        "detailed_description": (
            "Precision root canal treatment using modern rotary endodontics and strict sterilization protocols. We gently "
            "remove infected pulp tissue, disinfect and shape the root canals, and seal them hermetically to preserve your natural tooth."
        ),
        "price": Decimal("12000.00"),
        "duration_minutes": 60,
        "icon_name": "activity",
        "display_order": 6,
    },
    {
        "code": "SRV-007",
        "slug": "tooth-extraction",
        "name": "Tooth Extraction",
        "category": "Oral Surgery",
        "tagline": "Safe, Gentle Simple & Surgical Tooth Extractions",
        "short_description": "Atraumatic simple and wisdom tooth extractions under effective local anesthesia with comprehensive post-op care.",
        "detailed_description": (
            "When a tooth is severely damaged beyond restoration or impacted, our clinic performs gentle extractions under "
            "top-notch sterilization protocols with clear recovery guidance."
        ),
        "price": Decimal("3500.00"),
        "duration_minutes": 45,
        "icon_name": "scissors",
        "display_order": 7,
    },
    {
        "code": "SRV-008",
        "slug": "braces-and-orthodontics",
        "name": "Braces & Orthodontics",
        "category": "Orthodontics",
        "tagline": "Dental Braces: Straighten Smiles, Transform Lives.",
        "short_description": "Comprehensive orthodontic braces and alignment therapies for crowded, crooked, or spaced teeth.",
        "detailed_description": (
            "Orthodontic treatment plans customized for children, teens, and adults to correct tooth crowding, spacing, "
            "and bite alignment—improving both facial harmony and long-term oral hygiene."
        ),
        "price": Decimal("65000.00"),
        "duration_minutes": 60,
        "icon_name": "smile",
        "display_order": 8,
    },
    {
        "code": "SRV-009",
        "slug": "dental-crowns-and-bridges",
        "name": "Dental Crowns & Bridges",
        "category": "Prosthodontics & Restorative",
        "tagline": "Custom Zirconia & Porcelain-Fused Restorations",
        "short_description": "High-strength zirconia and ceramic crowns and fixed bridges to protect treated teeth and replace missing teeth.",
        "detailed_description": (
            "Custom-crafted dental crowns to reinforce root-canal-treated or fractured teeth, and fixed dental bridges "
            "to seamlessly restore missing teeth with natural shade matching."
        ),
        "price": Decimal("15000.00"),
        "duration_minutes": 45,
        "icon_name": "crown",
        "display_order": 9,
    },
    {
        "code": "SRV-010",
        "slug": "dental-implants",
        "name": "Dental Implants",
        "category": "Implantology",
        "tagline": "Dental Implant: Permanent Tooth Replacement.",
        "short_description": "Biocompatible titanium dental implants that restore the look, feel, and chewing strength of natural teeth.",
        "detailed_description": (
            "Advanced dental implant therapy offering a permanent, fixed solution for single or multiple missing teeth "
            "while preserving jawbone integrity and adjacent natural teeth."
        ),
        "price": Decimal("75000.00"),
        "duration_minutes": 60,
        "icon_name": "anchor",
        "display_order": 10,
    },
    {
        "code": "SRV-011",
        "slug": "teeth-whitening",
        "name": "Teeth Whitening",
        "category": "Cosmetic Dentistry",
        "tagline": "Teeth Whitening: Brighten Your Smile!",
        "short_description": "Professional in-office cosmetic teeth whitening to safely lift deep stains and brighten enamel shades.",
        "detailed_description": (
            "Cosmetic Dentistry — Enhancing Beauty, Boosting Confidence. Our professional LED-activated teeth whitening "
            "safely removes coffee, tea, and age-related discoloration for a visibly brighter, radiant smile."
        ),
        "price": Decimal("14000.00"),
        "duration_minutes": 60,
        "icon_name": "sun",
        "display_order": 11,
    },
    {
        "code": "SRV-012",
        "slug": "dentures-and-restorative-dentistry",
        "name": "Dentures & Restorative Dentistry",
        "category": "Prosthodontics & Restorative",
        "tagline": "Comfortable Partial & Complete Prosthetic Solutions",
        "short_description": "Custom-fitted removable partial dentures, flexible dentures, and full arch rehabilitations.",
        "detailed_description": (
            "Well-fitted, natural-looking partial and complete dentures designed for comfort, clear speech, and confident "
            "everyday nutrition."
        ),
        "price": Decimal("28000.00"),
        "duration_minutes": 45,
        "icon_name": "heart-handshake",
        "display_order": 12,
    },
]

# Genuine testimonials verified directly from https://rumidentalcare.com/ ("Happy Stories")
GENUINE_REVIEWS = [
    {
        "reviewer_display_name": "Uswa Syed",
        "rating": 5,
        "title": "Professional Surgery & Neat, Tidy Clinic",
        "comment": (
            "All thanks goes to my cute Dr 🙂 for such a great surgery thanks for doing your job in such a "
            "professional manner although it was such a tough task for you to deal with my teeth. Also the place "
            "is very neat and tidy 100% recommended from my side."
        ),
        "status": "Approved",
        "source_label": "Verified Clinic Patient (rumidentalcare.com)",
    },
    {
        "reviewer_display_name": "Sherazi Surayya",
        "rating": 5,
        "title": "Successful Family Dental Treatment",
        "comment": (
            "Magical hands of Dr Ayesha largely applauded her services. My mom n daughter got proper successful "
            "treatment overhere, totally recomended, plz visit once in ur life"
        ),
        "status": "Approved",
        "source_label": "Verified Clinic Patient (rumidentalcare.com)",
    },
    {
        "reviewer_display_name": "Haris Muhammad",
        "rating": 5,
        "title": "Hygienic, Professional and Affordable in Lahore",
        "comment": (
            "One of the most hygienic, professional and affordable dental clinics in Lahore, and the best in the are. "
            "Highly recommended"
        ),
        "status": "Approved",
        "source_label": "Verified Clinic Patient (rumidentalcare.com)",
    },
]


def ensure_roles_and_permissions(db: Session) -> dict[str, Role]:
    role_meta = {
        ROLE_PATIENT: ("Patient", "Registered clinic patient with personal portal access"),
        ROLE_DOCTOR: ("Doctor / Dental Surgeon", "Authorized clinician managing encounters, charts, and treatments"),
        ROLE_ADMIN: ("Administrator", "Authorized clinic administrator managing operations, staff, and billing"),
    }
    roles_by_name: dict[str, Role] = {}
    for r_name, (disp, desc) in role_meta.items():
        role = db.query(Role).filter(Role.name == r_name).first()
        if not role:
            role = Role(name=r_name, display_name=disp, description=desc)
            db.add(role)
            db.flush()
        roles_by_name[r_name] = role

    perms_by_code: dict[str, Permission] = {}
    for code, desc in PERMISSIONS_CATALOG.items():
        perm = db.query(Permission).filter(Permission.code == code).first()
        if not perm:
            perm = Permission(code=code, description=desc)
            db.add(perm)
            db.flush()
        perms_by_code[code] = perm

    for r_name, perm_codes in ROLE_DEFAULT_PERMISSIONS.items():
        role = roles_by_name[r_name]
        for code in perm_codes:
            perm = perms_by_code[code]
            exists = (
                db.query(RolePermission)
                .filter(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
                .first()
            )
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()
    return roles_by_name


def ensure_clinic_settings_and_catalog(db: Session) -> ClinicSetting:
    setting = db.query(ClinicSetting).first()
    if not setting:
        setting = ClinicSetting()
        db.add(setting)
        db.flush()

    for s_data in GENUINE_SERVICES:
        existing = db.query(Service).filter(Service.code == s_data["code"]).first()
        if not existing:
            db.add(Service(**s_data, is_published=True, is_bookable=True))
    db.flush()

    if db.query(Review).count() == 0:
        for rev in GENUINE_REVIEWS:
            db.add(Review(**rev, consent_to_publish=True))
        db.flush()

    return setting


def provision_admin_account(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    phone: str = "+92 310 2468080",
    can_view_clinical_details: bool = True,
) -> User:
    roles = ensure_roles_and_permissions(db)
    admin_role = roles[ROLE_ADMIN]
    email_norm = email.strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    if user:
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.role_id = admin_role.id
        user.is_active = True
        user.is_email_verified = True
        user.token_version += 1
    else:
        user = User(
            email=email_norm,
            phone=phone,
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=admin_role.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        db.flush()

    if not user.staff_profile:
        staff_count = db.query(StaffProfile).count() + 1
        db.add(
            StaffProfile(
                user_id=user.id,
                staff_code=f"STF-{staff_count:04d}",
                full_name=full_name,
                designation="Senior Clinic Administrator",
                department="Administration & Operations",
                can_view_clinical_details=can_view_clinical_details,
                is_active=True,
            )
        )
    db.commit()
    db.refresh(user)
    return user


def seed_initial_data(db: Session, include_demo_records: bool = True) -> None:
    """
    Idempotently initializes roles, permissions, genuine Rumi Dental Care settings,
    the 12 dental services, genuine approved testimonials, and Dr. Aisha Salman's profile/schedule.
    When include_demo_records=True in development, also provisions synthetic test patients and clinical records.
    """
    roles = ensure_roles_and_permissions(db)
    ensure_clinic_settings_and_catalog(db)

    # Ensure Lead Dentist: Dr. Aisha Salman
    dr_email = "dr.aisha@rumidentalcare.com"
    dr_user = db.query(User).filter(User.email == dr_email).first()
    if not dr_user:
        dr_user = User(
            email=dr_email,
            phone="+92 310 2468080",
            full_name="Dr. Aisha Salman",
            password_hash=hash_password("Doctor@Rumi2026!"),
            role_id=roles[ROLE_DOCTOR].id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(dr_user)
        db.flush()

    dr_profile = db.query(DoctorProfile).filter(DoctorProfile.user_id == dr_user.id).first()
    if not dr_profile:
        dr_profile = DoctorProfile(
            user_id=dr_user.id,
            doctor_code="DOC-0001",
            full_name="Dr. Aisha Salman",
            title="Lead Dental Surgeon",
            specialization="General, Cosmetic, Restorative & Endodontic Dentistry",
            qualification="BDS (Clinical Dental Practice — Configurable in Admin Settings)",
            license_number="PMC-RDC-001",
            bio=(
                "Lead Dental Surgeon at Rumi Dental Care in Johar Town, Lahore. Dedicated to providing "
                "personalized, hygienic, and comprehensive dental treatments including dental implants, "
                "painless root canals, cosmetic dentistry, teeth whitening, and orthodontics under strict "
                "sterilization protocols."
            ),
            consultation_fee=Decimal("1500.00"),
            slot_duration_minutes=30,
            is_active=True,
            is_public=True,
        )
        db.add(dr_profile)
        db.flush()

        # Verified opening hours from rumidentalcare.com: Mon-Sat 04:00 PM - 10:00 PM, Sun Closed
        for day_idx in range(7):
            is_open = day_idx < 6  # 0=Mon..5=Sat open, 6=Sun closed
            db.add(
                DoctorSchedule(
                    doctor_id=dr_profile.id,
                    day_of_week=day_idx,
                    start_time=time(16, 0),
                    end_time=time(22, 0),
                    slot_duration_minutes=30,
                    is_available=is_open,
                )
            )
        db.flush()

    if include_demo_records and settings.APP_ENV.lower() in {"development", "test", "local"}:
        # Ensure development Administrator account (can also be provisioned/rotated via `python -m app.cli create-admin`)
        admin_email = "admin@rumidentalcare.com"
        if not db.query(User).filter(User.email == admin_email).first():
            provision_admin_account(
                db=db,
                email=admin_email,
                full_name="Rumi Clinic Administrator",
                password="Admin@Rumi2026!",
                phone="+92 310 2468080",
                can_view_clinical_details=True,
            )

        # Synthetic Patient A: Ayesha Tariq
        p1_email = "ayesha.patient@example.com"
        if not db.query(User).filter(User.email == p1_email).first():
            u1 = User(
                email=p1_email,
                phone="+92 300 1112233",
                full_name="Ayesha Tariq",
                password_hash=hash_password("Patient@Rumi2026!"),
                role_id=roles[ROLE_PATIENT].id,
                is_active=True,
                is_email_verified=True,
            )
            db.add(u1)
            db.flush()

            p1 = PatientProfile(
                user_id=u1.id,
                patient_number="RDC-2026-00001",
                full_name="Ayesha Tariq",
                email=p1_email,
                phone="+92 300 1112233",
                date_of_birth=date(1995, 5, 14),
                gender="Female",
                blood_group="B+",
                address="House 42, Block B, Johar Town",
                city="Lahore",
                emergency_contact_name="Tariq Mehmood",
                emergency_contact_phone="+92 300 9998877",
                primary_doctor_id=dr_profile.id,
            )
            db.add(p1)
            db.flush()

            db.add(
                ConsentRecord(
                    patient_id=p1.id,
                    user_id=u1.id,
                    consent_type="PrivacyPolicy",
                    consent_version="v1.0",
                    is_accepted=True,
                    notes="Accepted during registration",
                )
            )
            db.add(
                MedicalHistory(
                    patient_id=p1.id,
                    systemic_conditions="No chronic systemic illness reported",
                    current_medications="None",
                    previous_surgeries="None",
                    bleeding_disorders=False,
                    diabetes=False,
                    hypertension=False,
                    heart_condition=False,
                    dental_anxiety_level="Mild",
                    previous_dental_history="Routine scaling 1 year ago",
                    last_dental_visit_date=date.today() - timedelta(days=180),
                    updated_by_id=dr_user.id,
                )
            )
            db.add(
                Allergy(
                    patient_id=p1.id,
                    allergen="Penicillin",
                    reaction="Mild skin rash",
                    severity="Moderate",
                    recorded_by_id=dr_user.id,
                )
            )

            srv_rct = db.query(Service).filter(Service.slug == "root-canal-treatment").first()
            srv_consult = db.query(Service).filter(Service.slug == "dental-consultation").first()

            # Completed past appointment + upcoming confirmed appointment
            past_apt = Appointment(
                appointment_number="APT-2026-00001",
                patient_id=p1.id,
                doctor_id=dr_profile.id,
                service_id=srv_rct.id if srv_rct else None,
                appointment_date=date.today() - timedelta(days=7),
                start_time=time(17, 0),
                end_time=time(18, 0),
                status="Completed",
                reason_for_visit="Sensitivity and throbbing pain in lower right first molar (#46)",
                follow_up_recommended_date=date.today() + timedelta(days=14),
                created_by_user_id=u1.id,
            )
            upcoming_apt = Appointment(
                appointment_number="APT-2026-00002",
                patient_id=p1.id,
                doctor_id=dr_profile.id,
                service_id=srv_consult.id if srv_consult else None,
                appointment_date=date.today() + timedelta(days=2),
                start_time=time(18, 0),
                end_time=time(18, 30),
                status="Confirmed",
                reason_for_visit="Post-endodontic crown preparation follow-up for Tooth #46",
                created_by_user_id=u1.id,
            )
            db.add_all([past_apt, upcoming_apt])
            db.flush()

            enc = ClinicalEncounter(
                encounter_number="ENC-2026-00001",
                patient_id=p1.id,
                doctor_id=dr_profile.id,
                appointment_id=past_apt.id,
                visit_date=date.today() - timedelta(days=7),
                presenting_complaint="Spontaneous lingering pain on hot/cold stimuli in lower right molar region.",
                history_of_present_illness="Pain started 4 days ago, disturbing sleep.",
                medical_history_summary="Healthy adult female; Penicillin allergy noted.",
                allergies_summary="Allergic to Penicillin (use macrolide/clindamycin alternative if antibiotic indicated).",
                examination_findings="Deep distal caries on FDI Tooth #46 tender to vertical percussion.",
                extra_oral_findings="Symmetrical facial profile, no submandibular lymphadenopathy.",
                intra_oral_findings="Fair oral hygiene; deep carious lesion on #46.",
                tooth_specific_findings="Tooth #46: Symptomatic irreversible pulpitis.",
                diagnosis_summary="Symptomatic Irreversible Pulpitis with Apical Periodontitis — FDI Tooth #46",
                treatment_performed="Single-visit rotary endodontic canal preparation and obturation completed under rubber dam isolation.",
                treatment_plan_notes="Recommend Zirconia Crown on Tooth #46 after 2 weeks.",
                follow_up_instructions="Avoid chewing hard foods on the right side until crown placement.",
                next_recommended_visit_date=date.today() + timedelta(days=14),
                status="Finalized",
                created_by_id=dr_user.id,
                finalized_by_id=dr_user.id,
            )
            db.add(enc)
            db.flush()

            db.add(
                Diagnosis(
                    encounter_id=enc.id,
                    patient_id=p1.id,
                    doctor_id=dr_profile.id,
                    tooth_fdi="46",
                    diagnosis_code="K04.0",
                    diagnosis_title="Symptomatic Irreversible Pulpitis (Tooth #46)",
                    severity="High",
                    clinical_notes="Confirmed via thermal test and periapical radiograph.",
                    status="Active",
                )
            )

            chart_tooth = DentalChartTooth(
                patient_id=p1.id,
                tooth_fdi="46",
                dentition_type="Permanent",
                tooth_name="Lower Right First Molar",
                condition_status="RootCanalTreated",
                surfaces="DO",
                clinical_notes="Rotary RCT completed; awaiting full-coverage zirconia crown.",
                updated_by_doctor_id=dr_profile.id,
            )
            db.add(chart_tooth)
            db.flush()

            db.add(
                ToothFinding(
                    chart_tooth_id=chart_tooth.id,
                    patient_id=p1.id,
                    encounter_id=enc.id,
                    doctor_id=dr_profile.id,
                    tooth_fdi="46",
                    condition_status="RootCanalTreated",
                    surfaces="DO",
                    finding_notes="Obturated mesial and distal canals; composite core buildup placed.",
                    treatment_recommended="Zirconia Crown (#46)",
                )
            )

            plan = TreatmentPlan(
                plan_number="TP-2026-00001",
                patient_id=p1.id,
                doctor_id=dr_profile.id,
                encounter_id=enc.id,
                title="Endodontic & Prosthodontic Rehabilitation — Tooth #46",
                clinical_summary="Root canal therapy followed by custom zirconia crown.",
                status="InProgress",
                total_estimated_cost=Decimal("27000.00"),
            )
            db.add(plan)
            db.flush()

            tp_item1 = TreatmentPlanItem(
                treatment_plan_id=plan.id,
                service_id=srv_rct.id if srv_rct else None,
                tooth_fdi="46",
                procedure_name="Root Canal Treatment (Tooth #46)",
                estimated_cost=Decimal("12000.00"),
                priority="High",
                status="Completed",
            )
            tp_item2 = TreatmentPlanItem(
                treatment_plan_id=plan.id,
                tooth_fdi="46",
                procedure_name="Zirconia Dental Crown (Tooth #46)",
                estimated_cost=Decimal("15000.00"),
                priority="Standard",
                status="Planned",
                scheduled_date=date.today() + timedelta(days=14),
            )
            db.add_all([tp_item1, tp_item2])
            db.flush()

            db.add(
                TreatmentRecord(
                    record_number="TR-2026-00001",
                    patient_id=p1.id,
                    doctor_id=dr_profile.id,
                    appointment_id=past_apt.id,
                    encounter_id=enc.id,
                    treatment_plan_item_id=tp_item1.id,
                    service_id=srv_rct.id if srv_rct else None,
                    tooth_fdi="46",
                    surface="DO",
                    procedure_name="Root Canal Treatment",
                    clinical_description="Rotary instrumentation, NaOCl irrigation, gutta-percha obturation with bioceramic sealer.",
                    materials_used="ProTaper Gold, AH Plus / Bioceramic Sealer, Composite Core",
                    post_op_instructions="Take prescribed analgesic as directed; return for crown preparation.",
                    follow_up_recommended=date.today() + timedelta(days=14),
                    performed_date=date.today() - timedelta(days=7),
                )
            )

            rx = Prescription(
                prescription_number="RX-2026-00001",
                patient_id=p1.id,
                doctor_id=dr_profile.id,
                encounter_id=enc.id,
                appointment_id=past_apt.id,
                issue_date=date.today() - timedelta(days=7),
                diagnosis_notes="Post-endodontic analgesia & infection prophylaxis (Penicillin-allergic patient)",
                general_instructions="Take medications after meals with a full glass of water.",
            )
            db.add(rx)
            db.flush()
            db.add_all(
                [
                    PrescriptionItem(
                        prescription_id=rx.id,
                        medication_name="Ibuprofen",
                        strength="400 mg",
                        dosage="1 Tablet",
                        route="Oral",
                        frequency="Every 8 hours (TID)",
                        duration="3 Days",
                        quantity="9 Tablets",
                        instructions="Take after meals for post-procedure comfort.",
                    ),
                    PrescriptionItem(
                        prescription_id=rx.id,
                        medication_name="Azithromycin",
                        strength="500 mg",
                        dosage="1 Capsule",
                        route="Oral",
                        frequency="Once Daily (OD)",
                        duration="3 Days",
                        quantity="3 Capsules",
                        instructions="Selected due to documented Penicillin allergy.",
                    ),
                ]
            )

            inv = Invoice(
                invoice_number="INV-2026-00001",
                patient_id=p1.id,
                appointment_id=past_apt.id,
                encounter_id=enc.id,
                document_kind="Invoice",
                issue_date=date.today() - timedelta(days=7),
                due_date=date.today() + timedelta(days=7),
                currency="PKR",
                subtotal=Decimal("13200.00"),
                discount_amount=Decimal("1200.00"),
                discount_reason="Patient care courtesy discount",
                tax_amount=Decimal("0.00"),
                total_amount=Decimal("12000.00"),
                amount_paid=Decimal("8000.00"),
                balance_due=Decimal("4000.00"),
                status="PartiallyPaid",
                notes="Partial payment received in clinic; remaining PKR 4,000 due at crown visit.",
                created_by_user_id=dr_user.id,
            )
            db.add(inv)
            db.flush()

            db.add_all(
                [
                    InvoiceLineItem(
                        invoice_id=inv.id,
                        service_id=srv_rct.id if srv_rct else None,
                        tooth_fdi="46",
                        description="Root Canal Treatment — Lower Right First Molar (#46)",
                        quantity=1,
                        unit_price=Decimal("12000.00"),
                        line_total=Decimal("12000.00"),
                    ),
                    InvoiceLineItem(
                        invoice_id=inv.id,
                        tooth_fdi="46",
                        description="Digital Periapical Dental X-Ray",
                        quantity=1,
                        unit_price=Decimal("1200.00"),
                        line_total=Decimal("1200.00"),
                    ),
                ]
            )
            db.flush()

            pay = Payment(
                payment_number="PAY-2026-00001",
                invoice_id=inv.id,
                patient_id=p1.id,
                amount=Decimal("8000.00"),
                currency="PKR",
                payment_method="Cash",
                reference_number="CASH-DESK-001",
                status="Recorded",
                received_by_user_id=dr_user.id,
                notes="Initial payment recorded at reception.",
            )
            db.add(pay)
            db.flush()

            db.add(
                Receipt(
                    receipt_number="RCP-2026-00001",
                    payment_id=pay.id,
                    invoice_id=inv.id,
                    patient_id=p1.id,
                    amount_received=Decimal("8000.00"),
                    currency="PKR",
                    payment_method="Cash",
                    issued_by_user_id=dr_user.id,
                    notes="Official payment receipt for partial payment against INV-2026-00001.",
                )
            )

            db.add(
                Notification(
                    user_id=u1.id,
                    title="Appointment Confirmed",
                    message="Your follow-up appointment with Dr. Aisha Salman is confirmed.",
                    notification_type="Appointment",
                    related_entity_type="appointment",
                    related_entity_id=upcoming_apt.id,
                )
            )

        # Synthetic Patient B: Bilal Khan (for immediate isolation verification)
        p2_email = "bilal.patient@example.com"
        if not db.query(User).filter(User.email == p2_email).first():
            u2 = User(
                email=p2_email,
                phone="+92 321 4445566",
                full_name="Bilal Ahmed Khan",
                password_hash=hash_password("Patient@Rumi2026!"),
                role_id=roles[ROLE_PATIENT].id,
                is_active=True,
                is_email_verified=True,
            )
            db.add(u2)
            db.flush()

            p2 = PatientProfile(
                user_id=u2.id,
                patient_number="RDC-2026-00002",
                full_name="Bilal Ahmed Khan",
                email=p2_email,
                phone="+92 321 4445566",
                date_of_birth=date(1988, 11, 20),
                gender="Male",
                blood_group="O+",
                address="Street 9, Phase 2, Johar Town",
                city="Lahore",
                primary_doctor_id=dr_profile.id,
            )
            db.add(p2)
            db.flush()

            srv_scaling = db.query(Service).filter(Service.slug == "teeth-cleaning-scaling-polishing").first()
            apt2 = Appointment(
                appointment_number="APT-2026-00003",
                patient_id=p2.id,
                doctor_id=dr_profile.id,
                service_id=srv_scaling.id if srv_scaling else None,
                appointment_date=date.today(),
                start_time=time(19, 0),
                end_time=time(19, 45),
                status="Confirmed",
                reason_for_visit="Routine ultrasonic scaling and polishing",
                created_by_user_id=u2.id,
            )
            db.add(apt2)
            db.flush()

        # Additional Demo Patient C: Amna Khan (amna.khan@example.com)
        p3_email = "amna.khan@example.com"
        if not db.query(User).filter(User.email == p3_email).first():
            u3 = User(
                email=p3_email,
                phone="+92 302 5556677",
                full_name="Amna Khan",
                password_hash=hash_password("Patient@Rumi2026!"),
                role_id=roles[ROLE_PATIENT].id,
                is_active=True,
                is_email_verified=True,
            )
            db.add(u3)
            db.flush()

            p3 = PatientProfile(
                user_id=u3.id,
                patient_number="RDC-2026-00101",
                full_name="Amna Khan",
                email=p3_email,
                phone="+92 302 5556677",
                date_of_birth=date(1996, 8, 22),
                gender="Female",
                blood_group="A+",
                address="Block C, RECHS, Johar Town",
                city="Lahore",
                emergency_contact_name="Salman Khan",
                emergency_contact_phone="+92 302 1119988",
                primary_doctor_id=dr_profile.id,
            )
            db.add(p3)
            db.flush()

            db.add(
                MedicalHistory(
                    patient_id=p3.id,
                    systemic_conditions="No chronic systemic conditions",
                    current_medications="None",
                    dental_anxiety_level="Low",
                    previous_dental_history="Composite filling 6 months ago",
                    updated_by_id=dr_user.id,
                )
            )
            srv_fill = db.query(Service).filter(Service.slug == "dental-fillings").first()
            apt3 = Appointment(
                appointment_number="APT-2026-00101",
                patient_id=p3.id,
                doctor_id=dr_profile.id,
                service_id=srv_fill.id if srv_fill else None,
                appointment_date=date.today() + timedelta(days=3),
                start_time=time(17, 30),
                end_time=time(18, 15),
                status="Confirmed",
                reason_for_visit="Tooth-colored composite restoration and dental checkup",
                created_by_user_id=u3.id,
            )
            db.add(apt3)
            db.flush()

            enc3 = ClinicalEncounter(
                encounter_number="ENC-2026-00101",
                patient_id=p3.id,
                doctor_id=dr_profile.id,
                appointment_id=apt3.id,
                visit_date=date.today() - timedelta(days=5),
                presenting_complaint="Mild sensitivity to cold on upper left premolar (#25).",
                examination_findings="Class II mesio-occlusal caries on FDI Tooth #25.",
                diagnosis_summary="Reversible Pulpitis — FDI Tooth #25",
                treatment_performed="Composite resin restoration completed on Tooth #25.",
                follow_up_instructions="Review at upcoming checkup.",
                next_recommended_visit_date=date.today() + timedelta(days=3),
                status="Finalized",
                created_by_id=dr_user.id,
                finalized_by_id=dr_user.id,
            )
            db.add(enc3)
            db.flush()

            db.add(
                DentalChartTooth(
                    patient_id=p3.id,
                    tooth_fdi="25",
                    dentition_type="Permanent",
                    tooth_name="Upper Left Second Premolar",
                    condition_status="Filled",
                    surfaces="MO",
                    clinical_notes="Composite restoration placed.",
                    updated_by_doctor_id=dr_profile.id,
                )
            )

        # Additional Demo Patient D: Usman Ali (usman.ali@example.com)
        p4_email = "usman.ali@example.com"
        if not db.query(User).filter(User.email == p4_email).first():
            u4 = User(
                email=p4_email,
                phone="+92 333 7778899",
                full_name="Usman Ali",
                password_hash=hash_password("Patient@Rumi2026!"),
                role_id=roles[ROLE_PATIENT].id,
                is_active=True,
                is_email_verified=True,
            )
            db.add(u4)
            db.flush()

            p4 = PatientProfile(
                user_id=u4.id,
                patient_number="RDC-2026-00102",
                full_name="Usman Ali",
                email=p4_email,
                phone="+92 333 7778899",
                date_of_birth=date(1991, 3, 10),
                gender="Male",
                blood_group="O+",
                address="Block F, Johar Town",
                city="Lahore",
                primary_doctor_id=dr_profile.id,
            )
            db.add(p4)
            db.flush()

            db.add(
                MedicalHistory(
                    patient_id=p4.id,
                    systemic_conditions="None reported",
                    updated_by_id=dr_user.id,
                )
            )

    db.commit()
