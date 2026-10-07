from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401  (registers the shared and leave tables)
import po_models  # noqa: F401  (registers the purchase order tables)
from database import Base, engine
from routers import admin, auth, leave_balance, outflows, purchase_orders, requests, users

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="University ERP API",
    description="Leave requests, purchase orders and shared workflow services",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(requests.router)
app.include_router(leave_balance.router)
app.include_router(purchase_orders.router)
app.include_router(admin.router)
app.include_router(outflows.router)


@app.get("/")
def root():
    return {"message": "University ERP API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}

from fastapi.staticfiles import StaticFiles
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")