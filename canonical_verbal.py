"""Canonical verbal seed dataset and safe evidence identity matching."""

import re

import database as db
import evidence_verbal as ev

OUTPUT_RESUME_BULLET = ev.OUTPUT_RESUME_BULLET
OUTPUT_TARGET_TRANSLATION = ev.OUTPUT_TARGET_TRANSLATION
SOURCE_CANONICAL = "canonical_seed"


def normalize_identity_field(value):
    s = re.sub(r"\s+", " ", (value or "").strip())
    s = s.replace("–", "-").replace("—", "-")
    return s.lower()


def evidence_identity_tuple(item):
    return (
        normalize_identity_field(item.get("title")),
        normalize_identity_field(item.get("company")),
        normalize_identity_field(item.get("role_context")),
        normalize_identity_field(item.get("time_period")),
    )


def target_identity_tuple(title, company_project, role_context, time_period):
    return (
        normalize_identity_field(title),
        normalize_identity_field(company_project),
        normalize_identity_field(role_context),
        normalize_identity_field(time_period),
    )


def find_evidence_matches(title, company_project, role_context, time_period):
    """Return evidence items matching the full identity tuple (0, 1, or many)."""
    target = target_identity_tuple(title, company_project, role_context, time_period)
    matches = []
    for item in db.get_evidence_items():
        if evidence_identity_tuple(item) == target:
            matches.append(item)
    return matches


CANONICAL_SEEDS = [
    {
        "identity": {
            "title": "Permission Governance and Access Lifecycle Design",
            "company_project": "miHoYo",
            "role_context": "Live Service Operations / Internal Tools Product Ownership",
            "time_period": "2021–2024",
        },
        "outputs": [
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Designed and operated a role-based access-governance workflow for an internal "
                    "operations platform, establishing approval paths, elevated-access controls, "
                    "new-hire provisioning, permission-change monitoring, and exception handling to "
                    "replace fragmented access processes with a traceable lifecycle."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates ownership of internal access-governance workflows, including "
                    "approval design, lifecycle controls, and internal-user enablement. It transfers "
                    "to Product Operations, Business Systems, and Internal Tools roles, while not "
                    "constituting direct Workday, HRIS, or enterprise IAM ownership."
                ),
            },
            {
                "role_family": "Business Systems",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Designed access-lifecycle workflows for an internal operations platform, covering "
                    "role tiers, accountable-owner approvals, elevated-access controls, onboarding "
                    "provisioning, transfer and offboarding changes, and auditable exception handling."
                ),
            },
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Owned the operating design for internal permission governance, coordinating "
                    "role-based controls, approval paths, lifecycle changes, exception processes, and "
                    "traceability requirements across internal users and tool stakeholders."
                ),
            },
        ],
    },
    {
        "identity": {
            "title": "Internal Tool Platform Product Ownership and Requirements Intake",
            "company_project": "miHoYo",
            "role_context": "Live Service Operations / Internal Tools Product Ownership",
            "time_period": "2021–2024",
        },
        "outputs": [
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Owned centralized discovery, prioritization, and rollout of internal-tool "
                    "improvements across engineering, QA, operations, and marketing, translating "
                    "ambiguous user pain points into scoped workflows, feasible requirements, release "
                    "plans, and adoption documentation."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates internal product-operations ownership across requirements "
                    "discovery, workflow design, constraint-based prioritization, release governance, "
                    "and user enablement. It transfers directly to Product Operations and Internal Tools "
                    "roles without implying sole engineering or software-architecture ownership."
                ),
            },
            {
                "role_family": "Internal Tools",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Led requirements intake and product-definition work for an internal tool "
                    "platform, converting unstructured requests into user scenarios, workflow "
                    "requirements, solution alternatives, staged releases, and documented operating "
                    "processes."
                ),
            },
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Coordinated internal-tool delivery from request intake through rollout, aligning "
                    "cross-functional needs, implementation constraints, release timing, feedback "
                    "collection, and adoption guidance for operational workflows."
                ),
            },
        ],
    },
    {
        "identity": {
            "title": "QA Environment Management and Automated Test Workflow",
            "company_project": "miHoYo",
            "role_context": "Live Service Operations / Internal Tools Product Ownership",
            "time_period": "2021–2024",
        },
        "outputs": [
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Led the design and rollout of a QA environment-management workflow that translated "
                    "ambiguous testing needs into configurable mixed-version environments and automated "
                    "smoke-test checks, reducing manual setup burden and improving test-scenario "
                    "reproducibility."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates user-centered workflow automation: translating operational pain "
                    "points into configurable internal tooling, requirements, validation steps, and "
                    "repeatable processes. It transfers to Product Operations, Internal Tools, QA "
                    "Operations, and Business Systems roles without claiming ownership of test-infrastructure "
                    "architecture."
                ),
            },
            {
                "role_family": "Internal Tools",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Translated QA requirements into an internal private-server management workflow that "
                    "standardized complex environment setup across client, asset, and server-version "
                    "combinations while embedding automated validation into the process."
                ),
            },
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Coordinated the definition and rollout of a configurable QA workflow, aligning user "
                    "scenarios, technical feasibility, environment requirements, and validation checks "
                    "to support reliable testing operations."
                ),
            },
        ],
    },
    {
        "identity": {
            "title": "Platform Integration Governance and End-to-End Validation Improvement",
            "company_project": "ByteDance Games",
            "role_context": "International Publishing Operations / Platform Integration",
            "time_period": "2020–2021",
        },
        "outputs": [
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Improved publishing-platform integration governance after an account-SDK rollout was "
                    "blocked by an undisclosed compliance restriction, coordinating remediation, "
                    "project-notification controls, and end-to-end validation with partner builds and "
                    "internal QA."
                ),
            },
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates cross-system implementation governance, dependency management, "
                    "escalation, acceptance testing, and incident-driven process improvement. It "
                    "transfers to Program, Implementation, Platform Operations, and Partner Operations "
                    "roles without claiming ownership of SDK architecture or compliance policy."
                ),
            },
            {
                "role_family": "Platform Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Coordinated phased publishing-platform integrations across SDKs, account systems, "
                    "payments, compliance, QA, and external development partners using milestone-based "
                    "checklists, acceptance criteria, dependency tracking, and go-live readiness controls."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Strengthened operational rollout controls for publishing-platform integrations by "
                    "aligning partner capacity, test objectives, platform dependencies, compliance "
                    "changes, and end-to-end user-flow validation."
                ),
            },
        ],
    },
    {
        "identity": {
            "title": "Financial Planning, Budget Approval, and Cross-Functional Business Operations",
            "company_project": "ByteDance Games",
            "role_context": "International Publishing Operations",
            "time_period": "2020–2021",
        },
        "outputs": [
            {
                "role_family": "Business Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Supported publishing business-case evaluation through iterative profitability "
                    "forecasting and coordinated budget requests, approval materials, spend tracking, "
                    "and finance reconciliation across user-acquisition, infrastructure, and operational "
                    "expenses."
                ),
            },
            {
                "role_family": "Business Operations",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates business-case support, budget-governance coordination, "
                    "cross-functional approval workflows, and operational finance collaboration. It "
                    "transfers to Business Operations and Program Operations roles, while not constituting "
                    "direct ERP, NetSuite, accounting, or financial-controller ownership."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Coordinated structured review and approval workflows for marketing, infrastructure, "
                    "and operating spend, partnering with finance, legal, procurement, compliance, and "
                    "marketing stakeholders to resolve execution issues."
                ),
            },
            {
                "role_family": "Program / Implementation",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Supported cross-functional operating governance for publishing projects by "
                    "coordinating profitability inputs, budget approvals, spend execution, revenue-share "
                    "reconciliation, and stakeholder issue resolution."
                ),
            },
        ],
    },
    {
        "identity": {
            "title": "B2B Technical Discovery and Custom PCBA Solution Coordination",
            "company_project": "Shenzhen Topband Co., Ltd.",
            "role_context": "Overseas Sales Manager",
            "time_period": "2017–2018",
        },
        "outputs": [
            {
                "role_family": "Customer / Partner Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Conducted early-stage B2B requirements discovery with overseas appliance "
                    "manufacturers, translating custom PCBA needs into internal feasibility checks and "
                    "quotation inputs for design-and-manufacturing solutions."
                ),
            },
            {
                "role_family": "Customer / Partner Operations",
                "output_type": OUTPUT_TARGET_TRANSLATION,
                "generated_text": (
                    "This demonstrates structured customer discovery, technical-commercial communication, "
                    "requirements gathering, internal feasibility coordination, and early opportunity "
                    "qualification. It transfers to Customer Operations, Partner Operations, Solutions "
                    "Operations, and Implementation-adjacent roles without claiming closed enterprise "
                    "sales, procurement-system ownership, or 3PL experience."
                ),
            },
            {
                "role_family": "Business Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Built structured prospect and requirement information for overseas B2B opportunities, "
                    "connecting procurement conversations, technical needs, internal feasibility "
                    "assessment, and commercial follow-up."
                ),
            },
            {
                "role_family": "Product Operations",
                "output_type": OUTPUT_RESUME_BULLET,
                "generated_text": (
                    "Translated external customer needs into structured internal requirements and "
                    "feasibility inputs, supporting early solution definition and cross-functional "
                    "commercial follow-up for custom PCBA opportunities."
                ),
            },
        ],
    },
]


def seed_canonical_verbal_outputs(dry_run=False):
    """Idempotent seed. Returns report dict."""
    import role_family_vocab as rfv

    report = {
        "inserted": [],
        "skipped_idempotent": [],
        "skipped_user_protected": [],
        "skipped_missing": [],
        "skipped_ambiguous": [],
    }
    for block in CANONICAL_SEEDS:
        ident = block["identity"]
        matches = find_evidence_matches(
            ident["title"], ident["company_project"],
            ident["role_context"], ident["time_period"],
        )
        if len(matches) == 0:
            report["skipped_missing"].append(ident["title"])
            continue
        if len(matches) > 1:
            report["skipped_ambiguous"].append({
                "title": ident["title"],
                "ids": [m["id"] for m in matches],
            })
            continue
        evidence_id = matches[0]["id"]
        for out in block["outputs"]:
            rf = rfv.ensure_role_family(out["role_family"])
            rf_norm = rfv.normalize_role_family_key(rf)
            action, reason = db.canonical_seed_decision(
                evidence_id, out["output_type"], rf_norm, out["generated_text"],
            )
            if action == "insert":
                if not dry_run:
                    db.insert_verbal_output(
                        evidence_id,
                        out["output_type"],
                        out["generated_text"],
                        role_family=rf,
                        role_family_normalized=rf_norm,
                        user_approved=1,
                        is_preferred=1,
                        source=SOURCE_CANONICAL,
                    )
                report["inserted"].append({
                    "evidence_id": evidence_id,
                    "title": ident["title"],
                    "role_family": rf,
                    "output_type": out["output_type"],
                })
            elif action == "skip_idempotent":
                report["skipped_idempotent"].append({
                    "evidence_id": evidence_id,
                    "role_family": rf,
                    "output_type": out["output_type"],
                })
            elif action == "skip_protected":
                report["skipped_user_protected"].append({
                    "evidence_id": evidence_id,
                    "role_family": rf,
                    "output_type": out["output_type"],
                    "reason": reason,
                })
    return report
