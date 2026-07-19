"""Built-in security workflow templates for Studio."""

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
                        "skills": ["cve-intel-skill"],
                        "position": {"x": 80, "y": 80},
                    },
                    {
                        "id": "severity",
                        "type": "condition",
                        "name": "Critical?",
                        "evaluator": {"cel": 'input.contains("critical") || input.contains("CRITICAL")'},
                        "steps": [
                            {
                                "id": "contain",
                                "type": "step",
                                "name": "Contain",
                                "executor": {"kind": "agent", "ref": "security-operations"},
                                "instructions": "Propose containment steps for critical severity.",
                                "skills": ["hitl-containment-skill"],
                                "requires_confirmation": True,
                                "confirmation_message": "Approve containment actions for this incident?",
                                "position": {"x": 420, "y": 40},
                            }
                        ],
                        "else": [
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
                                        "confirmation_message": "Proceed with this critical workflow action?",
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

        {
            "id": "deep-research-review",
            "name": "Deep research review",
            "description": (
                "Agno-style research pipeline: scope → parallel research+analysis → "
                "structured memo (auditable steps)."
            ),
            "category": "research",
            "tags": ["research", "analysis", "parallel", "deep-research"],
            "definition": {
                "name": "Deep research review",
                "description": (
                    "Deterministic deep-research shape: clarify mandate, parallel "
                    "investigation, synthesize an auditable memo."
                ),
                "steps": [
                    {
                        "id": "scope",
                        "type": "step",
                        "name": "Scope & plan",
                        "executor": {"kind": "agent", "ref": "deep-research"},
                        "instructions": (
                            "Clarify the research mandate from the user input: subject, "
                            "time range, decision use. List 3–7 sub-questions and the "
                            "evidence types you will need. Do not write the final memo yet."
                        ),
                        "position": {"x": 60, "y": 120},
                    },
                    {
                        "id": "investigate",
                        "type": "parallel",
                        "name": "Parallel investigation",
                        "position": {"x": 300, "y": 120},
                        "steps": [
                            {
                                "id": "research_arm",
                                "type": "step",
                                "name": "Sources & findings",
                                "executor": {"kind": "agent", "ref": "deep-research"},
                                "instructions": (
                                    "Investigate using available tools (website/search/knowledge). "
                                    "Return key findings with source titles and URLs where possible. "
                                    "Separate facts from inference."
                                ),
                                "position": {"x": 520, "y": 40},
                            },
                            {
                                "id": "analysis_arm",
                                "type": "step",
                                "name": "Numbers & checks",
                                "executor": {"kind": "agent", "ref": "data-analysis"},
                                "instructions": (
                                    "From the same user topic and any numbers in context, "
                                    "compute or sanity-check quantitative claims. "
                                    "Show formulas or tool results; do not invent stats."
                                ),
                                "position": {"x": 520, "y": 220},
                            },
                        ],
                    },
                    {
                        "id": "memo",
                        "type": "step",
                        "name": "Research memo",
                        "executor": {"kind": "agent", "ref": "deep-research"},
                        "instructions": (
                            "Synthesize prior steps into an auditable Markdown memo: "
                            "Executive summary (with confidence), Key findings (with evidence), "
                            "Detailed analysis, Risks/unknowns, Recommended actions, References. "
                            "No unsupported hard facts."
                        ),
                        "position": {"x": 780, "y": 120},
                    },
                ],
            },
        },
        {
            "id": "csv-quick-analysis",
            "name": "CSV quick analysis",
            "description": "Data-agent path: profile table → metrics → short readout.",
            "category": "analysis",
            "tags": ["data", "csv", "analysis"],
            "definition": {
                "name": "CSV quick analysis",
                "description": "Profile uploaded or pasted tabular data and report metrics.",
                "steps": [
                    {
                        "id": "profile",
                        "type": "step",
                        "name": "Profile data",
                        "executor": {"kind": "agent", "ref": "data-analysis"},
                        "instructions": (
                            "Inspect available files/tables (list files/CSV in sandbox if present). "
                            "Report row count estimate, columns, dtypes, missingness, and outliers. "
                            "Ask at most 2 clarifying questions only if data is missing."
                        ),
                        "position": {"x": 80, "y": 100},
                    },
                    {
                        "id": "metrics",
                        "type": "step",
                        "name": "Key metrics",
                        "executor": {"kind": "agent", "ref": "data-analysis"},
                        "instructions": (
                            "Compute the most decision-relevant metrics for the user question "
                            "using calculator/Python/CSV tools. Cite formulas or code steps. "
                            "Do not invent numbers."
                        ),
                        "position": {"x": 360, "y": 100},
                    },
                    {
                        "id": "readout",
                        "type": "step",
                        "name": "Readout",
                        "executor": {"kind": "agent", "ref": "data-analysis"},
                        "instructions": (
                            "Write a concise Markdown readout: summary → findings → "
                            "method/limitations → next steps. Include chart suggestions in text only."
                        ),
                        "position": {"x": 640, "y": 100},
                    },
                ],
            },
        },
    ]
