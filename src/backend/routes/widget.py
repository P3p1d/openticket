from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.database import get_db
from src.backend.routes.admin import get_branding

router = APIRouter(prefix="/api/widget", tags=["widget"])

@router.get("/config")
def get_widget_config(db: Session = Depends(get_db)):
    return get_branding(db)
