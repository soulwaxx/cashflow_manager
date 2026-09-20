from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.reporting import YearMonthRange
from app.services.analytics import category_spending, transfer_spending

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _reporting_range(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> YearMonthRange:
    try:
        return YearMonthRange.model_validate({"from": from_, "to": to})
    except ValueError as error:
        raise HTTPException(422, "Invalid reporting range") from error


@router.get("/categories")
def analytics_categories(
    reporting_range: YearMonthRange = Depends(_reporting_range),
    category_ids: Optional[str] = Query(None),
    payment_method_ids: Optional[str] = Query(None),
    direction: str = Query("all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat_ids = category_ids.split(",") if category_ids else None
    pm_ids = payment_method_ids.split(",") if payment_method_ids else None
    return category_spending(
        current_user.id,
        reporting_range.from_,
        reporting_range.to,
        db,
        cat_ids,
        pm_ids,
        direction,
    )


@router.get("/transfers")
def analytics_transfers(
    reporting_range: YearMonthRange = Depends(_reporting_range),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return transfer_spending(current_user.id, reporting_range.from_, reporting_range.to, db)
