from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.api.requirement_review_service.feature_lists import (  # noqa: E402
    confirm_feature_list,
    create_feature_list,
    get_single_feature_list,
    list_feature_lists,
    patch_feature_list,
    remove_feature_list,
)
from app.db.init_db import create_core_tables  # noqa: E402
from app.schemas.requirement_review_service import (  # noqa: E402
    ConfirmRequirementFeatureListRequest,
    CreateRequirementFeatureListRequest,
    UpdateRequirementFeatureListRequest,
)


def _build_test_request(tmp_path: Path) -> Any:
    db_path = tmp_path / "interaction-data-feature-list.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    create_core_tables(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(db_session_factory=session_factory))
        ),
    )


def _sample_modules() -> list[dict[str, Any]]:
    return [
        {
            "name": "优惠券",
            "description": "优惠券领取与核销",
            "feature_points": [
                {
                    "feature_id": "coupon-claim",
                    "title": "用户领取优惠券",
                    "source_excerpt": "用户可在活动页领取优惠券",
                    "acceptance_criteria": ["每人限领一张"],
                    "constraints": ["库存扣减需幂等"],
                    "priority": "P0",
                    "inferred": False,
                    "open_questions": [],
                }
            ],
        }
    ]


def _create_payload(project_id: str, **overrides: Any) -> CreateRequirementFeatureListRequest:
    values: dict[str, Any] = {
        "project_id": project_id,
        "batch_id": "feature-list:thread-1",
        "thread_id": "thread-1",
        "requirement_text": "优惠券活动需求原文",
        "requirement_summary": "优惠券领取需求",
        "modules": _sample_modules(),
        "open_questions": ["过期券是否可退"],
        "assumptions": ["默认单账号单设备"],
        "raw_result": {"decomposable": True},
    }
    values.update(overrides)
    return CreateRequirementFeatureListRequest(**values)


def test_feature_list_create_confirm_flow(tmp_path: Path) -> None:
    request = _build_test_request(tmp_path)
    project_id = str(uuid.uuid4())

    created = asyncio.run(create_feature_list(request, _create_payload(project_id)))
    assert created["status"] == "draft"
    assert created["version"] == 1

    confirmed = asyncio.run(
        confirm_feature_list(
            request,
            created["id"],
            ConfirmRequirementFeatureListRequest(
                confirmed_by="tester", expected_version=1
            ),
        )
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_by"] == "tester"
    assert confirmed["confirmed_at"] is not None

    fetched = asyncio.run(get_single_feature_list(request, created["id"]))
    assert fetched["status"] == "confirmed"


def test_feature_list_content_edit_bumps_version_and_resets_status(tmp_path: Path) -> None:
    request = _build_test_request(tmp_path)
    project_id = str(uuid.uuid4())

    created = asyncio.run(create_feature_list(request, _create_payload(project_id)))
    asyncio.run(
        confirm_feature_list(
            request, created["id"], ConfirmRequirementFeatureListRequest()
        )
    )

    updated = asyncio.run(
        patch_feature_list(
            request,
            created["id"],
            UpdateRequirementFeatureListRequest(
                requirement_summary="优惠券领取需求（修订）"
            ),
        )
    )
    assert updated["version"] == 2
    assert updated["status"] == "draft"
    assert updated["confirmed_at"] is None
    assert updated["confirmed_by"] is None

    # 非内容字段更新不产生新版本
    touched = asyncio.run(
        patch_feature_list(
            request,
            created["id"],
            UpdateRequirementFeatureListRequest(batch_id="feature-list:thread-2"),
        )
    )
    assert touched["version"] == 2


def test_feature_list_confirm_version_mismatch_rejected(tmp_path: Path) -> None:
    request = _build_test_request(tmp_path)
    project_id = str(uuid.uuid4())

    created = asyncio.run(create_feature_list(request, _create_payload(project_id)))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            confirm_feature_list(
                request,
                created["id"],
                ConfirmRequirementFeatureListRequest(expected_version=99),
            )
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "feature_list_version_mismatch"


def test_feature_list_undecomposable_cannot_confirm(tmp_path: Path) -> None:
    request = _build_test_request(tmp_path)
    project_id = str(uuid.uuid4())

    created = asyncio.run(
        create_feature_list(
            request,
            _create_payload(
                project_id,
                decomposable=False,
                undecomposable_reason="需求原文过于模糊，无法拆解",
                modules=[],
            ),
        )
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            confirm_feature_list(
                request, created["id"], ConfirmRequirementFeatureListRequest()
            )
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "feature_list_not_decomposable"


def test_feature_list_idempotent_create_and_listing(tmp_path: Path) -> None:
    request = _build_test_request(tmp_path)
    project_id = str(uuid.uuid4())

    first = asyncio.run(
        create_feature_list(
            request, _create_payload(project_id, idempotency_key="fl:thread-1")
        )
    )
    second = asyncio.run(
        create_feature_list(
            request, _create_payload(project_id, idempotency_key="fl:thread-1")
        )
    )
    assert first["id"] == second["id"]

    listing = asyncio.run(
        list_feature_lists(
            request,
            project_id=project_id,
            batch_id=None,
            status="draft",
            query="优惠券",
            limit=50,
            offset=0,
        )
    )
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == first["id"]

    removed = asyncio.run(remove_feature_list(request, first["id"]))
    assert removed == {"ok": True}
