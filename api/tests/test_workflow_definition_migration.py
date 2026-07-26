from api.services.workflow_definition_migration import canonicalize_workflow_definition


def test_definition_guard_does_not_rewrite_legacy_aliases() -> None:
    legacy = {
        "steps": [
            {
                "type": "step",
                "targetId": "security-operations",
                "skills": ["playbook-skill"],
            }
        ]
    }

    guarded = canonicalize_workflow_definition(legacy)

    assert guarded is not None
    assert guarded == legacy
    assert guarded is not legacy
    assert guarded["steps"] is not legacy["steps"]


def test_definition_guard_does_not_backfill_missing_node_ids() -> None:
    definition = {
        "steps": [
            {
                "type": "step",
                "executor": {"kind": "agent", "ref": "security-operations"},
            }
        ]
    }

    guarded = canonicalize_workflow_definition(definition)

    assert guarded is not None
    assert guarded == definition
    assert "id" not in guarded["steps"][0]


def test_definition_guard_ignores_non_objects() -> None:
    assert canonicalize_workflow_definition(None) is None
    assert canonicalize_workflow_definition([]) is None
