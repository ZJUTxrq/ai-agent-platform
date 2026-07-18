from __future__ import annotations

from fastapi import APIRouter

from .aggregates import router as aggregates_router
from .documents import router as documents_router
from .feature_lists import router as feature_lists_router
from .results import router as results_router

router = APIRouter(prefix="/requirement-review-service")
router.include_router(documents_router)
router.include_router(results_router)
router.include_router(feature_lists_router)
router.include_router(aggregates_router)
