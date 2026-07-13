# registry/router 为零框架依赖模块,这里用文件路径加载以绕开
# requirement_review_agent 包 __init__ 对 graph(deepagents)的重依赖,
# 使本文件可在无 langchain 的环境中独立运行。
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "capability_skills" / "registry.py"
)
_SHIPPED_CAPABILITIES_ROOT = (
    Path(__file__).resolve().parents[1] / "skills" / "capabilities"
)


def _load_registry_module():
    spec = importlib.util.spec_from_file_location(
        "capability_registry_standalone", _MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reg = _load_registry_module()


def _manifest(name: str, **overrides) -> dict:
    data = {
        "name": name,
        "version": "0.1.0",
        "category": "general",
        "description": "test capability skill",
        "triggers": {"keywords": ["接口"]},
        "prompt": {"file": "SKILL.md"},
        "scoring": {"dimension": "testability"},
    }
    data.update(overrides)
    return data


def _write_skill(
    root: Path,
    name: str,
    manifest: dict | None,
    *,
    skill_md: str | None = "# test skill\n\n检查清单",
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    if manifest is not None:
        (directory / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
        )
    if skill_md is not None:
        (directory / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return directory


def test_load_valid_registry_and_defaults(tmp_path):
    _write_skill(tmp_path, "api-review", _manifest("api-review"))
    registry = reg.load_capability_registry(tmp_path)

    assert registry.errors == []
    assert len(registry.skills) == 1
    manifest = registry.skills[0]
    assert manifest.name == "api-review"
    assert manifest.enabled is True
    assert manifest.inject_stage == reg.DEFAULT_INJECT_STAGE
    assert manifest.triggers.priority == reg.DEFAULT_TRIGGER_PRIORITY
    assert manifest.scoring_max_findings == reg.DEFAULT_MAX_FINDINGS
    assert manifest.handler is None
    assert manifest.prompt_virtual_path == "/skills/capabilities/api-review/SKILL.md"


def test_missing_capabilities_root_returns_empty(tmp_path):
    registry = reg.load_capability_registry(tmp_path / "nope")
    assert registry.skills == []
    assert registry.errors == []


def test_name_mismatch_rejected(tmp_path):
    _write_skill(tmp_path, "dir-a", _manifest("other-name"))
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("must match directory name" in error for error in registry.errors)


def test_missing_manifest_rejected(tmp_path):
    _write_skill(tmp_path, "no-manifest", None)
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("missing manifest.yaml" in error for error in registry.errors)


def test_missing_prompt_file_rejected(tmp_path):
    _write_skill(tmp_path, "no-prompt", _manifest("no-prompt"), skill_md=None)
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("does not exist" in error for error in registry.errors)


def test_empty_prompt_file_rejected(tmp_path):
    _write_skill(tmp_path, "empty-prompt", _manifest("empty-prompt"), skill_md="  \n")
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("is empty" in error for error in registry.errors)


def test_invalid_version_rejected(tmp_path):
    _write_skill(tmp_path, "bad-version", _manifest("bad-version", version="v1"))
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("semver" in error for error in registry.errors)


def test_invalid_category_rejected(tmp_path):
    _write_skill(tmp_path, "bad-cat", _manifest("bad-cat", category="unknown"))
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("category" in error for error in registry.errors)


def test_invalid_scoring_dimension_rejected(tmp_path):
    _write_skill(
        tmp_path,
        "bad-dim",
        _manifest("bad-dim", scoring={"dimension": "not_a_dimension"}),
    )
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("scoring.dimension" in error for error in registry.errors)


def test_invalid_inject_stage_rejected(tmp_path):
    _write_skill(
        tmp_path,
        "bad-stage",
        _manifest("bad-stage", prompt={"file": "SKILL.md", "inject_stage": "nope"}),
    )
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("inject_stage" in error for error in registry.errors)


def test_handler_module_missing_rejected(tmp_path):
    _write_skill(
        tmp_path,
        "bad-handler",
        _manifest("bad-handler", handler={"module": "handler.py"}),
    )
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("handler module" in error for error in registry.errors)


def test_invalid_yaml_rejected_without_crash(tmp_path):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "manifest.yaml").write_text("a: [unclosed", encoding="utf-8")
    (directory / "SKILL.md").write_text("# x", encoding="utf-8")
    registry = reg.load_capability_registry(tmp_path)
    assert registry.skills == []
    assert any("invalid yaml" in error for error in registry.errors)


def test_bad_skill_does_not_block_good_skill(tmp_path):
    _write_skill(tmp_path, "good-one", _manifest("good-one"))
    _write_skill(tmp_path, "bad-one", _manifest("bad-one", category="nope"))
    registry = reg.load_capability_registry(tmp_path)
    assert [manifest.name for manifest in registry.skills] == ["good-one"]
    assert len(registry.errors) == 1


def test_unknown_fields_warn_but_load(tmp_path):
    _write_skill(
        tmp_path, "extra-field", _manifest("extra-field", future_field="x")
    )
    registry = reg.load_capability_registry(tmp_path)
    assert len(registry.skills) == 1
    assert any("unknown manifest fields" in warning for warning in registry.warnings)


def test_requires_tools_filtering(tmp_path):
    _write_skill(
        tmp_path,
        "needs-kb",
        _manifest("needs-kb", requires_tools=["query_project_knowledge"]),
    )
    without_tools = reg.load_capability_registry(
        tmp_path, available_tool_names=set()
    )
    assert without_tools.skills == []
    assert any("required tools unavailable" in error for error in without_tools.errors)

    with_tools = reg.load_capability_registry(
        tmp_path, available_tool_names={"query_project_knowledge"}
    )
    assert len(with_tools.skills) == 1


def test_agent_compatibility_filtering(tmp_path):
    _write_skill(
        tmp_path,
        "other-agent",
        _manifest("other-agent", compatibility={"agents": ["test_case_agent_v2"]}),
    )
    registry = reg.load_capability_registry(
        tmp_path, agent_name="requirement_review_agent"
    )
    assert registry.skills == []
    assert any("not compatible" in error for error in registry.errors)


def test_disabled_skill_loaded_but_not_routed(tmp_path):
    _write_skill(tmp_path, "off-skill", _manifest("off-skill", enabled=False))
    registry = reg.load_capability_registry(tmp_path)
    assert len(registry.skills) == 1
    assert registry.enabled_skills == []
    assert reg.route_capability_skills("涉及接口的需求", registry) == []


def test_router_keyword_match_case_insensitive(tmp_path):
    _write_skill(
        tmp_path,
        "api-review",
        _manifest("api-review", triggers={"keywords": ["API", "接口"]}),
    )
    registry = reg.load_capability_registry(tmp_path)

    assert [
        manifest.name
        for manifest in reg.route_capability_skills("新增 api 上传能力", registry)
    ] == ["api-review"]
    assert [
        manifest.name
        for manifest in reg.route_capability_skills("这个接口要改", registry)
    ] == ["api-review"]
    assert reg.route_capability_skills("纯业务描述", registry) == []


def test_router_always_selected_without_text(tmp_path):
    _write_skill(
        tmp_path,
        "always-on",
        _manifest("always-on", triggers={"always": True}),
    )
    registry = reg.load_capability_registry(tmp_path)
    assert [
        manifest.name for manifest in reg.route_capability_skills(None, registry)
    ] == ["always-on"]
    assert [
        manifest.name for manifest in reg.route_capability_skills("", registry)
    ] == ["always-on"]


def test_router_priority_ordering(tmp_path):
    _write_skill(
        tmp_path,
        "later-skill",
        _manifest("later-skill", triggers={"keywords": ["接口"], "priority": 50}),
    )
    _write_skill(
        tmp_path,
        "first-skill",
        _manifest("first-skill", triggers={"keywords": ["接口"], "priority": 10}),
    )
    registry = reg.load_capability_registry(tmp_path)
    selected = reg.route_capability_skills("接口需求", registry)
    assert [manifest.name for manifest in selected] == ["first-skill", "later-skill"]


def test_build_capability_skills_prompt_lists_enabled_only(tmp_path):
    _write_skill(tmp_path, "on-skill", _manifest("on-skill"))
    _write_skill(tmp_path, "off-skill", _manifest("off-skill", enabled=False))
    registry = reg.load_capability_registry(tmp_path)
    prompt = reg.build_capability_skills_prompt(registry)
    assert "`on-skill`" in prompt
    assert "off-skill" not in prompt
    assert "requirement-quality-scoring" in prompt


def test_build_capability_skills_prompt_empty_registry(tmp_path):
    registry = reg.load_capability_registry(tmp_path)
    assert reg.build_capability_skills_prompt(registry) == ""


def test_shipped_capabilities_load_without_errors():
    """随代码交付的 capabilities 目录必须始终通过契约校验。"""
    registry = reg.load_capability_registry(
        _SHIPPED_CAPABILITIES_ROOT,
        available_tool_names={
            "query_project_knowledge",
            "list_project_knowledge_documents",
            "get_project_knowledge_document_status",
            "persist_requirement_review_result",
        },
        agent_name="requirement_review_agent",
    )
    assert registry.errors == []
    assert registry.warnings == []
    names = {manifest.name for manifest in registry.skills}
    assert names == {
        "api-review",
        "security-review",
        "business-flow-review",
        "quote-verify",
    }

    quote_verify = registry.get("quote-verify")
    assert quote_verify.triggers.always is True
    assert quote_verify.handler is not None
    assert quote_verify.handler.tools == ("verify_quote",)
    assert quote_verify.inject_stage == "requirement-quality-scoring"

    # 安全类需求应同时命中 security-review(关键词)与 quote-verify(always)
    selected = reg.route_capability_skills("登录鉴权接口的需求评审", registry)
    selected_names = [manifest.name for manifest in selected]
    assert "security-review" in selected_names
    assert "api-review" in selected_names
    assert "quote-verify" in selected_names
    # quote-verify priority=1 应排最前
    assert selected_names[0] == "quote-verify"
