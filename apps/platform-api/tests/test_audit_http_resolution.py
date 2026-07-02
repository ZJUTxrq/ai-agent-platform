from __future__ import annotations

import unittest

from app.modules.audit.application import AuditHttpRequest, resolve_http_audit
from app.modules.audit.domain import AuditPlane, AuditResult


class AuditHttpResolutionTest(unittest.TestCase):
    def test_announcement_feed_resolution_uses_project_scope(self) -> None:
        resolved = resolve_http_audit(
            request=AuditHttpRequest(
                method="GET",
                path="/api/announcements/feed",
                query_params={"project_id": "project-1"},
                query_string="project_id=project-1",
                state_project_id=None,
                client_ip="127.0.0.1",
                user_agent="pytest",
                response_content_length="123",
            ),
            response_payload=None,
            actor_user_id="user-1",
            status_code=200,
            result=AuditResult.SUCCESS,
        )

        self.assertEqual(resolved.plane, AuditPlane.CONTROL_PLANE)
        self.assertEqual(resolved.action, "announcement.feed.read")
        self.assertEqual(resolved.target_type, "announcement_feed")
        self.assertEqual(resolved.target_id, "project-1")
        self.assertEqual(resolved.project_id, "project-1")
        self.assertEqual(resolved.metadata["route_kind"], "control_plane")

    def test_runtime_thread_create_resolution_uses_response_payload_target(self) -> None:
        resolved = resolve_http_audit(
            request=AuditHttpRequest(
                method="POST",
                path="/api/langgraph/threads",
                query_params={},
                query_string=None,
                state_project_id="project-2",
                client_ip="127.0.0.1",
                user_agent="pytest",
                response_content_length="64",
            ),
            response_payload={"thread_id": "thread-9"},
            actor_user_id="user-1",
            status_code=201,
            result=AuditResult.SUCCESS,
        )

        self.assertEqual(resolved.plane, AuditPlane.RUNTIME_GATEWAY)
        self.assertEqual(resolved.action, "runtime.thread.item.created")
        self.assertEqual(resolved.target_type, "thread")
        self.assertEqual(resolved.target_id, "thread-9")
        self.assertEqual(resolved.project_id, "project-2")
        self.assertEqual(resolved.metadata["response_size"], 64)

    def test_unknown_route_uses_stable_route_template_for_target_id(self) -> None:
        resolved = resolve_http_audit(
            request=AuditHttpRequest(
                method="GET",
                path="/api/projects/da40d59f-030d-42e4-b61d-f759ddc559f8/testcase/cases",
                route_path="/api/projects/{project_id}/testcase/cases",
                query_params={},
                query_string=None,
                state_project_id=None,
                client_ip="127.0.0.1",
                user_agent="pytest",
                response_content_length="32",
            ),
            response_payload=None,
            actor_user_id="user-1",
            status_code=200,
            result=AuditResult.SUCCESS,
        )

        self.assertEqual(resolved.action, "system.route.requested")
        self.assertEqual(resolved.target_type, "route")
        self.assertEqual(resolved.target_id, "/api/projects/{project_id}/testcase/cases")
        self.assertLessEqual(len(resolved.target_id or ""), 64)

    def test_unknown_route_without_template_compresses_long_identifiers(self) -> None:
        resolved = resolve_http_audit(
            request=AuditHttpRequest(
                method="GET",
                path="/api/projects/da40d59f-030d-42e4-b61d-f759ddc559f8/requirement-review/results/requirement-review:019ed0f2-3a44-70b2-a345-f55d76ca35e7",
                query_params={},
                query_string=None,
                state_project_id=None,
                client_ip="127.0.0.1",
                user_agent="pytest",
                response_content_length="32",
            ),
            response_payload=None,
            actor_user_id="user-1",
            status_code=200,
            result=AuditResult.SUCCESS,
        )

        self.assertEqual(resolved.action, "system.route.requested")
        self.assertEqual(resolved.target_type, "route")
        self.assertIsNotNone(resolved.target_id)
        self.assertLessEqual(len(resolved.target_id or ""), 64)
        self.assertIn("{id}", resolved.target_id or "")


if __name__ == "__main__":
    unittest.main()
