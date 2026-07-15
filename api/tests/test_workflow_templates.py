from api.services.workflow_compiler import validate_and_normalize_definition
from api.services.workflow_templates import get_workflow_template, list_workflow_templates


def test_templates_are_non_empty_and_unique():
    items = list_workflow_templates()
    assert len(items) >= 3
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids))


def test_each_template_definition_validates():
    for item in list_workflow_templates():
        normalized = validate_and_normalize_definition(item["definition"])
        assert normalized["steps"]


def test_get_template():
    assert get_workflow_template("ir-triage") is not None
    assert get_workflow_template("missing") is None
