from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import RoleEnum, User
from schemas import LoginRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = [role.value for role in RoleEnum]
MANAGER_ROLES = ("manager_l1", "manager_l2", "hr_admin")

# Public registration can only ever create this role.
# Higher roles must be assigned by an HR admin.
DEFAULT_ROLE = "employee"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Public sign-up. Always creates an employee, whatever role is sent."""
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter(User.employee_id == user.employee_id).first():
        raise HTTPException(status_code=400, detail="Employee ID already registered")

    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id).first()
        if not manager or manager.role not in MANAGER_ROLES:
            raise HTTPException(status_code=400, detail="manager_id must be the id of an existing manager")

    new_user = User(
        employee_id=user.employee_id,
        full_name=user.full_name,
        email=user.email,
        password=hash_password(user.password),
        role=DEFAULT_ROLE,  # never trust the role from the request
        department_id=user.department_id,
        manager_id=user.manager_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """JSON login used by the React frontend."""
    user = authenticate(db, request.email, request.password)
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/token", response_model=TokenResponse)
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Form login used by the Authorize button on /docs (username = email)."""
    user = authenticate(db, form_data.username, form_data.password)
    access_token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}