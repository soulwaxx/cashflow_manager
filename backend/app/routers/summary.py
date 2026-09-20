from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.reporting import MAX_REPORTING_YEAR, MIN_REPORTING_YEAR
from app.services.summary import monthly_summary, year_monthly_summaries

router = APIRouter(prefix="/summary", tags=["summary"])

@router.get("/{year}")
def year_summary(
    year: Annotated[int, Path(ge=MIN_REPORTING_YEAR, le=MAX_REPORTING_YEAR)],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return year_monthly_summaries(current_user.id, year, db)


@router.get("/{year}/{month}")
def month_summary(
    year: Annotated[int, Path(ge=MIN_REPORTING_YEAR, le=MAX_REPORTING_YEAR)],
    month: Annotated[int, Path(ge=1, le=12)],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return monthly_summary(current_user.id, year, month, db)
