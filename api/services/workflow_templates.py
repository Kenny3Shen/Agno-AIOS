"""Built-in security workflow templates for Studio (PR9)."""

from __future__ import annotations

from typing import Any


def list_workflow_templates() -> list[dict[str, Any]]:
    """Return copy-ready draft definitions (not persisted until Save)."""
    return [
        {
            "id": "ir-triage",
            "name": "Incident triage (IR)",
            "description": "Classify severity, branch critical path, optional human confirm before contain.",
            "category": "incident_response",
            "tags": ["security", "ir", "condition", "hitl"],
            "definition": {
                "name": "Incident triage",
                "description": "Security IR: analyze → branch by severity → confirm contain",
                "steps": [
                    {
                        "id": "triage",
                        "type": "step",
                        "name": "Triage alert",
                        "executor": {"kind": "agent", "ref": "security-operations"},
                        "instructions": (
                            "Summarize the alert, list IOCs, and state severity as one of: "
                            "critical, high, medium, low. Put severity token in the reply."
                        ),
                        "skills": ["playbook-skill", "cve-intel-skill"],
                        "position": {"x": 80, "y": 80},
                    },
                    {
                        "id": "severity",
                        "type": "condition",
                        "name": "Critical?",
                        "evaluator": {"cel": 'input.contains("critical") || input.contains("CRITICAL")'},
                        "then_steps": [
                            {
                                "id": "contain",
                                "type": "step",
                                "name": "Contain",
                                "executor": {"kind": "agent", "ref": "security-operations"},
                                "instructions": "Propose containment steps for critical severity.",
                                "skills": ["hitl-containment-skill", "playbook-skill"],
                                "requires_confirmation": True,
                                "confirmation_message": "Approve containment actions for this incident?",
                                "position": {"x": 420, "y": 40},
                            }
                        ],
                        "else_steps": [
                            {
                                "id": "report",
                                "type": "step",
                                "name": "Report",
                                "executor": {"kind": "agent", "ref": "safe-fallback"},
                                "instructions": "Write a short non-critical incident note.",
                                "position": {"x": 420, "y": 200},
                            }
                        ],
                        "position": {"x": 280, "y": 80},
                    },
                ],
            },
        },
        {
            "id": "alert-fanout",
            "name": "Alert fan-out",
            "description": "Parallel CVE + asset checks, then synthesize.",
            "category": "detection",
            "tags": ["security", "parallel", "cve"],
            "definition": {
                "name": "Alert fan-out",
                "description": "Parallel enrichment then summary",
                "steps": [
                    {
                        "id": "fanout",
                        "type": "parallel",
                        "name": "Enrich",
                        "position": {"x": 80, "y": 100},
                        "steps": [
                            {
                                "id": "cve",
                                "type": "step",
                                "name": "CVE context",
                                "skills": ["cve-intel-skill"],
                                "executor": {"kind": "agent", "ref": "security-operations"},
                                "instructions": "Map any CVEs or product versions mentioned in the alert.",
                                "position": {"x": 320, "y": 40},
                            },
                            {
                                "id": "asset",
                                "type": "step",
                                "name": "Asset impact",
                                "skills": ["intranet-ip-skill"],
                                "executor": {"kind": "agent", "ref": "safe-fallback"},
                                "instructions": "Infer likely affected assets and blast radius.",
                                "position": {"x": 320, "y": 180},
                            },
                        ],
                    },
                    {
                        "id": "synthesize",
                        "type": "step",
                        "name": "Synthesize",
                        "executor": {"kind": "agent", "ref": "security-operations"},
                        "instructions": "Merge parallel findings into a single operator brief.",
                        "position": {"x": 560, "y": 100},
                    },
                ],
            },
        },
        {
            "id": "asset-patrol",
            "name": "Asset patrol loop",
            "description": "Loop probe until DONE or max iterations; good for health checks.",
            "category": "ops",
            "tags": ["security", "loop", "ops"],
            "definition": {
                "name": "Asset patrol",
                "description": "Retry probe until completion signal",
                "steps": [
                    {
                        "id": "patrol",
                        "type": "loop",
                        "name": "Patrol",
                        "max_iterations": 3,
                        "end_condition": {"cel": 'last_step_content.contains("DONE")'},
                        "position": {"x": 100, "y": 80},
                        "steps": [
                            {
                                "id": "probe",
                                "type": "step",
                                "name": "Probe",
                                "executor": {"kind": "agent", "ref": "safe-fallback"},
                                "instructions": (
                                    "Check asset health from the input. "
                                    "If healthy or finished, include the token DONE in your reply."
                                ),
                                "position": {"x": 340, "y": 80},
                            }
                        ],
                    }
                ],
            },
        },
        {
            "id": "severity-router",
            "name": "Severity router",
            "description": "Router CEL picks path_a / path_b / path_c by severity keyword.",
            "category": "routing",
            "tags": ["security", "router"],
            "definition": {
                "name": "Severity router",
                "description": "Route by severity token in input",
                "steps": [
                    {
                        "id": "classify",
                        "type": "step",
                        "name": "Classify",
                        "executor": {"kind": "agent", "ref": "security-operations"},
                        "instructions": "Echo severity as critical, high, or other.",
                        "position": {"x": 60, "y": 120},
                    },
                    {
                        "id": "route",
                        "type": "router",
                        "name": "Route",
                        "selector": {
                            "cel": (
                                'input.contains("critical") ? "path_a" : '
                                '(input.contains("high") ? "path_b" : "path_c")'
                            )
                        },
                        "position": {"x": 280, "y": 120},
                        "choices": [
                            {
                                "id": "path_a",
                                "name": "path_a",
                                "steps": [
                                    {
                                        "id": "crit_act",
                                        "type": "step",
                                        "name": "Critical action",
                                        "executor": {"kind": "agent", "ref": "security-operations"},
                                        "requires_confirmation": True,
                                        "confirmation_message": "Proceed with critical playbook?",
                                        "position": {"x": 520, "y": 20},
                                    }
                                ],
                            },
                            {
                                "id": "path_b",
                                "name": "path_b",
                                "steps": [
                                    {
                                        "id": "high_act",
                                        "type": "step",
                                        "name": "High priority",
                                        "executor": {"kind": "agent", "ref": "security-operations"},
                                        "position": {"x": 520, "y": 140},
                                    }
                                ],
                            },
                            {
                                "id": "path_c",
                                "name": "path_c",
                                "steps": [
                                    {
                                        "id": "low_act",
                                        "type": "step",
                                        "name": "Standard queue",
                                        "executor": {"kind": "agent", "ref": "safe-fallback"},
                                        "position": {"x": 520, "y": 260},
                                    }
                                ],
                            },
                        ],
                    },
                ],
            },
        },
    ]


def get_workflow_template(template_id: str) -> dict[str, Any] | None:
    tid = (template_id or "").strip()
    for item in list_workflow_templates():
        if item["id"] == tid:
            return item
    return None
