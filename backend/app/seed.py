"""
Idempotent seed script: demo accounts, starter note templates, and the ICD-10 embedding
table. Run with `python -m app.seed` after migrations. Safe to re-run.
"""

from app.data.icd10_seed import ICD10_CODES
from app.database import SessionLocal
from app.models.icd10 import Icd10Code
from app.models.template import NoteTemplate
from app.models.user import Role, User
from app.security import hash_password
from app.services.embedding_service import embed_batch

DEMO_PASSWORD = "ChangeMe123!"


def seed_users(db):
    demo_users = [
        ("dr.patel@kyronclinic.demo", "Dr. Ananya Patel", Role.provider),
        ("dr.reyes@kyronclinic.demo", "Dr. Marcus Reyes", Role.provider),
        ("dr.chen@kyronclinic.demo", "Dr. Lily Chen", Role.provider),
        ("admin@kyronclinic.demo", "Sam Whitfield (Admin)", Role.admin),
    ]
    created = {}
    for email, name, role in demo_users:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(email=email, full_name=name, role=role, hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
        created[email] = user
    db.commit()
    return created


def seed_templates(db, admin_user: User):
    starter_templates = [
        (
            "Orthopedic Follow-Up",
            "orthopedic_followup",
            "This is a follow-up visit for an existing orthopedic/musculoskeletal condition. "
            "Emphasize interval change since the last visit (better/worse/unchanged), current "
            "functional status and pain level, physical exam findings localized to the affected "
            "joint or region, and a Plan focused on continuing, escalating, or de-escalating "
            "conservative treatment versus proceeding to imaging, injection, or surgical referral. "
            "Keep tone concise; this provider sees this patient regularly.",
        ),
        (
            "New Patient Evaluation",
            "new_patient_evaluation",
            "This is a comprehensive new-patient visit. Write a fuller Subjective capturing full "
            "history of present illness, relevant past medical/surgical history, and prior "
            "treatments tried. Objective should reflect a complete relevant exam, not just a "
            "focused recheck. Assessment should include differential considerations, not just a "
            "single diagnosis. Plan should establish a full workup and follow-up cadence.",
        ),
        (
            "Urgent Care Visit",
            "urgent_care",
            "This is an urgent/acute visit for a new, unscheduled complaint. Prioritize ruling out "
            "red-flag/emergent presentations first in the Assessment. Keep Subjective and Objective "
            "tightly focused on the acute complaint rather than comprehensive history. Plan should "
            "clearly state return precautions and follow-up timing.",
        ),
        (
            "Post-Operative Follow-Up",
            "post_op_followup",
            "This is a post-surgical follow-up visit. Subjective should capture days/weeks since "
            "surgery, pain trajectory, wound/incision symptoms, and functional milestones (weight "
            "bearing, range of motion) relative to the expected recovery timeline. Objective should "
            "focus on incision appearance, signs of infection, swelling, and surgical-site-specific "
            "exam findings. Assessment should state expected-vs-delayed recovery explicitly. Plan "
            "should address wound care, activity progression, suture/staple removal if applicable, "
            "and the next post-op milestone visit.",
        ),
        (
            "Telehealth Visit",
            "telehealth",
            "This is a virtual/telehealth encounter. There is no hands-on physical exam -- the "
            "Objective section should be limited to what can be assessed visually or verbally over "
            "video (observed range of motion, visible swelling/deformity, patient-reported vital "
            "signs if available) and must not include palpation, auscultation, or any exam maneuver "
            "requiring physical touch. Note explicitly that the exam is limited by the virtual "
            "format. Plan should note whether an in-person visit is needed to complete the workup.",
        ),
        (
            "Physical Therapy Progress Check",
            "pt_progress_check",
            "This is a brief interval visit specifically to check physical therapy progress, not a "
            "full re-evaluation. Subjective should focus narrowly on PT attendance/adherence, "
            "functional gains, and any new pain with specific exercises. Objective should report "
            "only what's changed since the PT program started (ROM, strength grades) rather than a "
            "full exam. Assessment and Plan should be short -- either continue the current program, "
            "adjust specific exercises, or graduate the patient from PT.",
        ),
    ]
    for name, encounter_type, prompt in starter_templates:
        existing = db.query(NoteTemplate).filter(NoteTemplate.encounter_type == encounter_type).one_or_none()
        if existing is None:
            db.add(
                NoteTemplate(
                    name=name,
                    encounter_type=encounter_type,
                    prompt_instructions=prompt,
                    created_by=admin_user.id,
                )
            )
    db.commit()


def seed_icd10(db):
    existing_count = db.query(Icd10Code).count()
    if existing_count >= len(ICD10_CODES):
        print(f"ICD-10 table already seeded ({existing_count} rows), skipping.")
        return

    descriptions = [desc for _, desc in ICD10_CODES]
    embeddings = embed_batch(descriptions)

    for (code, description), embedding in zip(ICD10_CODES, embeddings):
        if db.query(Icd10Code).filter(Icd10Code.code == code).one_or_none() is not None:
            continue
        db.add(Icd10Code(code=code, description=description, embedding=embedding))
    db.commit()
    print(f"Seeded {len(ICD10_CODES)} ICD-10 codes with embeddings.")


def main():
    db = SessionLocal()
    try:
        users = seed_users(db)
        seed_templates(db, users["admin@kyronclinic.demo"])
        seed_icd10(db)
        print("Seed complete. Demo login password for all accounts:", DEMO_PASSWORD)
        for email in users:
            print(" -", email)
    finally:
        db.close()


if __name__ == "__main__":
    main()
