import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, or_, text)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")      # .env: mysql+pymysql://user:password@localhost:3306/hospital_db
SECRET_KEY = os.getenv("SECRET_KEY")          # .env: koi lambi random string
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "2"))
if not (DATABASE_URL and SECRET_KEY):
    raise RuntimeError("DATABASE_URL aur SECRET_KEY .env file me set karo")

# database nahi bana ho to khud bana do
_url = make_url(DATABASE_URL)
with create_engine(_url.set(database=None)).connect() as c:
    c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{_url.database}`"))
    c.commit()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
app = FastAPI(title="Hospital Management System")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ==================== Models ====================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    password = Column(String(255))
    role = Column(String(50))
    is_active = Column(Boolean, default=True)


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    description = Column(Text)
    head = Column(String(100))
    phone = Column(String(20))


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    phone = Column(String(20))
    address = Column(Text)
    blood_group = Column(String(10))
    date_of_birth = Column(String(20))
    gender = Column(String(10))
    emergency_contact = Column(String(100))
    user = relationship("User")


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    specialization = Column(String(100))
    qualification = Column(String(200))
    experience = Column(Integer)
    phone = Column(String(20))
    consultation_fee = Column(Float)
    user = relationship("User")
    department = relationship("Department")


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    appointment_date = Column(DateTime)
    status = Column(String(50))
    reason = Column(Text)
    patient = relationship("Patient")
    doctor = relationship("Doctor")


class MedicalRecord(Base):
    __tablename__ = "medical_records"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    diagnosis = Column(Text)
    symptoms = Column(Text)
    treatment = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    patient = relationship("Patient")
    doctor = relationship("Doctor")


class Medicine(Base):
    __tablename__ = "medicines"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    manufacturer = Column(String(100))
    price = Column(Float)
    stock = Column(Integer)
    expiry_date = Column(String(20))


class Bed(Base):
    __tablename__ = "beds"
    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    room_number = Column(String(50))
    bed_number = Column(String(50))
    status = Column(String(50), default="available")
    patient_admitted = Column(String(100))
    department = relationship("Department")


Base.metadata.create_all(bind=engine)


# ==================== Request Schemas ====================

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    date_of_birth: date

    @field_validator("username")
    @classmethod
    def v_username(cls, v):
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return v

    @field_validator("password")
    @classmethod
    def v_password(cls, v):
        if not 8 <= len(v.encode()) <= 72:
            raise ValueError("Password must be 8 to 72 characters long")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def v_dob(cls, v):
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class UserLogin(BaseModel):
    username: str
    password: str
    role: str


class PatientCreate(BaseModel):
    user_id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: str
    address: str
    blood_group: str
    date_of_birth: str
    gender: str = ""
    emergency_contact: str = ""

    @field_validator("date_of_birth")
    @classmethod
    def v_dob(cls, v):
        try:
            dob = date.fromisoformat(v.strip())
        except ValueError:
            raise ValueError("Date of birth should be YYYY-MM-DD")
        if not date.today().replace(year=date.today().year - 120) < dob <= date.today():
            raise ValueError("Date of birth is not valid")
        return dob.isoformat()

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v):
        digits = v.replace("+", "").replace("-", "").replace(" ", "")
        if not digits.isdigit() or not 10 <= len(digits) <= 13:
            raise ValueError("Enter a valid phone number (10-13 digits)")
        return v.strip()


class DoctorCreate(BaseModel):
    name: str
    email: EmailStr
    department: str
    specialization: str
    qualification: str
    experience: int
    phone: str
    consultation_fee: float


class DepartmentCreate(BaseModel):
    name: str
    description: str
    head: str
    phone: str


class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    reason: str

    @field_validator("appointment_date")
    @classmethod
    def v_date(cls, v):
        if v.tzinfo:
            v = v.astimezone().replace(tzinfo=None)
        now = datetime.now()
        if v < now:
            raise ValueError("Appointment date/time cannot be in the past")
        if v > now + timedelta(days=365):
            raise ValueError("Appointment cannot be more than 1 year ahead")
        return v


class MedicalRecordCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    diagnosis: str
    symptoms: str
    treatment: str


class BedCreate(BaseModel):
    department_id: int
    room_number: str
    bed_number: str


class MedicineCreate(BaseModel):
    name: str
    manufacturer: str
    price: float
    stock: int
    expiry_date: date


# ==================== Helpers ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), hashed.encode())
    except ValueError:
        return False


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    try:
        payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session has expired, please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return user


def require_roles(*roles):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission to perform this action")
        return user
    return checker


def own_id(db: Session, user: User) -> int:
    """logged-in patient/doctor ki apni patient_id / doctor_id (nahi mili to -1)."""
    model = Patient if user.role == "patient" else Doctor
    row = db.query(model).filter(model.user_id == user.id).first()
    return row.id if row else -1


def make_profile(db: Session, user: User, dob: Optional[date] = None):
    """patient/doctor user ke liye khaali profile row, taaki patient_id/doctor_id hamesha mile."""
    if user.role == "patient" and own_id(db, user) == -1:
        db.add(Patient(user_id=user.id, phone="", address="", blood_group="",
                       date_of_birth=dob.isoformat() if dob else "", gender="", emergency_contact=""))
    elif user.role == "doctor" and own_id(db, user) == -1:
        db.add(Doctor(user_id=user.id, specialization="General", qualification="",
                      experience=0, phone="", consultation_fee=0))


def new_user(db: Session, name: str, email: str, role: str, password: str) -> User:
    """admin ke dwara doctor/patient ke liye login account."""
    name = name.strip()
    if len(name) < 3:
        raise HTTPException(400, "Name must be at least 3 characters long")
    if db.query(User).filter(or_(User.username == name, User.email == email.lower())).first():
        raise HTTPException(400, "Username or email already exists")
    u = User(username=name, email=email.lower(), password=hash_password(password), role=role)
    db.add(u)
    db.flush()
    return u


def save(db: Session, obj):
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def uname(x):
    return x.user.username if x and x.user else ""


# ---- frontend ko bheje jane wale dict ----
def patient_out(p):
    return {"id": p.id, "name": uname(p), "email": p.user.email if p.user else "", "phone": p.phone or "",
            "address": p.address or "", "blood_group": p.blood_group or "", "date_of_birth": p.date_of_birth or ""}


def doctor_out(d):
    return {"id": d.id, "name": uname(d), "specialization": d.specialization or "",
            "qualification": d.qualification or "", "experience": d.experience or 0,
            "phone": d.phone or "", "fee": d.consultation_fee or 0,
            "department": d.department.name if d.department else ""}


def appointment_out(a):
    return {"id": a.id, "patient_id": a.patient_id, "doctor_id": a.doctor_id,
            "patient_name": uname(a.patient), "doctor_name": uname(a.doctor),
            "appointment_date": a.appointment_date.isoformat(), "status": a.status, "reason": a.reason}


def record_out(r):
    return {"id": r.id, "patient_name": uname(r.patient), "doctor_name": uname(r.doctor),
            "diagnosis": r.diagnosis, "symptoms": r.symptoms, "treatment": r.treatment,
            "created_at": r.created_at.isoformat() if r.created_at else ""}


def bed_out(b):
    return {"id": b.id, "room_number": b.room_number, "bed_number": b.bed_number,
            "department": b.department.name if b.department else "",
            "status": b.status, "patient_admitted": b.patient_admitted}


def medicine_out(m):
    return {"id": m.id, "name": m.name, "manufacturer": m.manufacturer, "price": m.price,
            "stock": m.stock, "expiry_date": m.expiry_date}


def dept_out(d):
    return {"id": d.id, "name": d.name, "description": d.description, "head": d.head, "phone": d.phone}


# ==================== Startup & Home ====================

@app.on_event("startup")
def startup_tasks():
    db = SessionLocal()
    try:
        u, e, p = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_EMAIL"), os.getenv("ADMIN_PASSWORD")
        if u and e and p and not db.query(User).filter(User.username == u).first():
            db.add(User(username=u, email=e.lower(), password=hash_password(p), role="admin"))
            db.commit()
        for user in db.query(User).filter(User.role.in_(["patient", "doctor"])).all():
            make_profile(db, user)
        db.commit()
    finally:
        db.close()


@app.get("/")
def home():
    return FileResponse("templates/index.html")


# ==================== Auth ====================

@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(or_(User.username == data.username, User.email == data.email.lower())).first():
        raise HTTPException(400, "Username or email already registered")
    user = User(username=data.username, email=data.email.lower(),
                password=hash_password(data.password), role="patient")   # hamesha patient
    db.add(user)
    db.flush()
    make_profile(db, user, data.date_of_birth)
    db.commit()
    return {"message": "Registered successfully"}


@app.post("/api/auth/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    ident = data.username.strip()
    user = db.query(User).filter(or_(User.username == ident, User.email == ident.lower())).first()
    if not user:
        raise HTTPException(404, "You are not registered. Please register first.")
    if not verify_password(data.password, user.password):
        raise HTTPException(401, "Invalid password")
    if user.role != data.role:
        raise HTTPException(403, f"You are not registered as a '{data.role}'")
    if not user.is_active:
        raise HTTPException(403, "Account is inactive. Please contact admin.")
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    token = jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "username": user.username, "role": user.role}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


# ==================== Patients ====================

@app.post("/api/patients")
def create_patient(patient: PatientCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "patient"))):
    data = patient.model_dump()
    name, email = data.pop("name"), data.pop("email")
    if user.role == "patient":          # register par khaali profile ban chuki hai, usi ko bhar do
        data["user_id"] = user.id
        existing = db.query(Patient).filter(Patient.user_id == user.id).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            db.commit()
            return patient_out(existing)
    elif not data.get("user_id"):
        if not (name and email):
            raise HTTPException(400, "Name and email required")
        data["user_id"] = new_user(db, name, email, "patient", "Patient@123").id
    return patient_out(save(db, Patient(**data)))


@app.get("/api/patients")
def get_patients(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor", "patient"))):
    q = db.query(Patient)
    if user.role == "patient":
        q = q.filter(Patient.user_id == user.id)       # patient ko sirf apna data
    return [patient_out(p) for p in q.all()]


# ==================== Doctors & Departments ====================

@app.post("/api/doctors")
def create_doctor(doc: DoctorCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    dept = db.query(Department).filter(Department.name == doc.department).first()
    if not dept:
        raise HTTPException(400, "Department not found, add the department first")
    u = new_user(db, doc.name, doc.email, "doctor", "Doctor@123")
    return doctor_out(save(db, Doctor(
        user_id=u.id, department_id=dept.id, specialization=doc.specialization,
        qualification=doc.qualification, experience=doc.experience, phone=doc.phone,
        consultation_fee=doc.consultation_fee)))


@app.get("/api/doctors")
def get_doctors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [doctor_out(d) for d in db.query(Doctor).all()]


@app.post("/api/departments")
def create_department(dept: DepartmentCreate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin"))):
    if db.query(Department).filter(Department.name == dept.name).first():
        raise HTTPException(400, "Department already exists")
    return dept_out(save(db, Department(**dept.model_dump())))


@app.get("/api/departments")
def get_departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [dept_out(d) for d in db.query(Department).all()]


# ==================== Appointments ====================

@app.post("/api/appointments")
def create_appointment(a: AppointmentCreate, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("admin", "patient"))):
    if user.role == "patient" and a.patient_id != own_id(db, user):
        raise HTTPException(403, "You can only create appointments for yourself")
    if not db.get(Patient, a.patient_id):
        raise HTTPException(404, "Patient not found")
    if not db.get(Doctor, a.doctor_id):
        raise HTTPException(404, "Doctor not found")
    return appointment_out(save(db, Appointment(**a.model_dump(), status="scheduled")))


@app.get("/api/appointments")
def get_appointments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Appointment)
    if user.role == "patient":
        q = q.filter(Appointment.patient_id == own_id(db, user))
    elif user.role == "doctor":
        q = q.filter(Appointment.doctor_id == own_id(db, user))
    return [appointment_out(a) for a in q.all()]


# ==================== Medical Records ====================

@app.post("/api/medical-records")
def create_record(r: MedicalRecordCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "doctor"))):
    return record_out(save(db, MedicalRecord(**r.model_dump())))


@app.get("/api/medical-records")
def get_records(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(MedicalRecord)
    if user.role == "patient":
        q = q.filter(MedicalRecord.patient_id == own_id(db, user))
    return [record_out(r) for r in q.all()]


# ==================== Beds ====================

@app.post("/api/beds")
def create_bed(bed: BedCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return bed_out(save(db, Bed(**bed.model_dump())))


@app.get("/api/beds")
def get_beds(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    return [bed_out(b) for b in db.query(Bed).all()]


@app.put("/api/beds/{bed_id}/status")
def toggle_bed(bed_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    bed = db.get(Bed, bed_id)
    if not bed:
        raise HTTPException(404, "Bed not found")
    bed.status = "occupied" if bed.status == "available" else "available"
    db.commit()
    return bed_out(bed)


# ==================== Medicines & Dashboard ====================

@app.post("/api/medicines")
def create_medicine(m: MedicineCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    if db.query(Medicine).filter(Medicine.name == m.name).first():
        raise HTTPException(400, "Medicine already exists")
    return medicine_out(save(db, Medicine(**{**m.model_dump(), "expiry_date": m.expiry_date.isoformat()})))


@app.get("/api/medicines")
def get_medicines(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    return [medicine_out(m) for m in db.query(Medicine).all()]


@app.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "doctor"))):
    return {"total_patients": db.query(Patient).count(), "total_doctors": db.query(Doctor).count(),
            "total_appointments": db.query(Appointment).count(),
            "available_beds": db.query(Bed).filter(Bed.status == "available").count()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)