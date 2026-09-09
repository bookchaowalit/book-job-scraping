#!/usr/bin/env python3
"""Deterministic contract-first qualification for collected job listings.

The candidate already has a full-time role in Thailand. This policy therefore
prefers flexible engagements that can legally and practically coexist with the
current role. It classifies discovery evidence as PASS, VERIFY, or REJECT; it
does not infer permission to submit an application.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from .job_role_relevance import evidence_tags
except ImportError:  # Direct script execution keeps scripts/ on sys.path.
    from job_role_relevance import evidence_tags


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "config" / "job_targeting.yaml"

PASS = "PASS"
VERIFY = "VERIFY"
REJECT = "REJECT"
APPROVED = "APPROVED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"

# Bridge opportunities can build a credible path into paid work, but they are
# not interchangeable with an ordinary contract.  Unpaid work is always
# review-only; paid bridge programs may pass only after the same location,
# hours, and engagement-boundary checks as a contract have been satisfied.
BRIDGE_EMPLOYMENT_TYPES = (
    "Contract-to-hire",
    "Paid trial",
    "Apprenticeship",
    "Fellowship",
    "Internship",
    "Volunteer",
)
UNPAID_BRIDGE_TYPES = {"Internship", "Volunteer"}
PAID_BRIDGE_TYPES = {"Contract-to-hire", "Paid trial", "Apprenticeship", "Fellowship"}

POLICY_FIELDS = (
    "search_lane",
    "visa_sponsorship",
    "qualification_status",
    "policy_version",
    "employment_type",
    "work_arrangement",
    "thailand_eligibility",
    "concurrent_employment",
    "engagement_boundary",
    "application_readiness",
    "qualification_reasons",
)
HUMAN_VERIFICATION_FIELDS = (
    "verified_role_requirements",
    "verified_destination_country",
    "verified_destination_eligibility",
    "verified_career_transition",
    "verified_employment_terms",
    "verification_source_url",
    "verified_at",
    "verified_employment_type",
    "verified_work_arrangement",
    "verified_thailand_eligibility",
    "verified_concurrent_employment",
    "verified_engagement_boundary",
    "verified_bridge_compensation",
    "verified_scope_duration",
    "verified_mentor",
    "verified_conversion_path",
    "verification_notes",
)
SOURCE_EVIDENCE_FIELDS = (
    "description",
    "search_lane",
    "visa_sponsorship",
    "location",
    "salary",
    "source",
    "keyword",
    "posted",
    "tags",
    "scraped_at",
    "score",
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_clean(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{_clean(key)} {_clean(item)}" for key, item in value.items())
    return re.sub(r"\s+", " ", str(value)).strip()


@lru_cache(maxsize=4)
def load_policy(path: str | None = None) -> dict[str, Any]:
    policy_path = Path(path).resolve() if path else DEFAULT_POLICY_PATH
    with policy_path.open(encoding="utf-8") as handle:
        policy = yaml.safe_load(handle) or {}
    if not policy.get("policy_version"):
        raise ValueError(f"job targeting policy has no policy_version: {policy_path}")
    return policy


def _search_text(job: dict[str, Any], description: str = "") -> str:
    fields = (
        "title",
        "company",
        "location",
        "job_type",
        "employment_type",
        "notes",
        "note",
        "description",
        "requirements",
        "source",
    )
    return " ".join(_clean(job.get(field)) for field in fields) + " " + evidence_tags(job) + " " + _clean(description)


def _source_key(job: dict[str, Any]) -> str:
    return _clean(job.get("source") or job.get("provider") or job.get("board")).lower()


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def classify_employment(job: dict[str, Any], text: str, policy: dict[str, Any]) -> tuple[str, bool]:
    """Return (employment_type, full_time_commitment_signal)."""
    lower = text.lower()
    verified = _clean(job.get("verified_employment_type"))
    bridge_types = set(policy.get("bridge_opportunities", {}).get("employment_types", BRIDGE_EMPLOYMENT_TYPES))
    allowed_types = set(policy.get("target", {}).get("accepted_employment_types", [])) | bridge_types | {"Full-time", "Unknown"}
    canonical_types = {item.lower(): item for item in allowed_types}
    if verified.lower() in canonical_types:
        employment_type = canonical_types[verified.lower()]
        return employment_type, employment_type == "Full-time"
    full_time = _has(r"\bfull[\s-]?time\b|\bpermanent\b|\bregular employee\b", lower)
    # "smart contract" describes a technology, not an engagement.
    contract_text = re.sub(r"\bsmart contracts?\b", "", lower)

    # Check bridge-to-hire signals before the broader contract/freelance
    # patterns so "contract-to-hire" is not flattened to just "Contract".
    if _has(r"\bcontract[\s-]?to[\s-]?hire\b|\btemp(?:orary)?[\s-]?to[\s-]?hire\b|\bconvert(?:ed|s|ing)?\s+to\s+full[\s-]?time\b", lower):
        return "Contract-to-hire", full_time
    if _has(r"\bpaid[\s-]?(?:trial|test|assessment)\b|\btrial\s+(?:project|engagement)\b.*\bpaid\b", lower):
        return "Paid trial", full_time
    if _has(r"\bapprenticeship\b|\bapprentice\b", lower):
        return "Apprenticeship", full_time
    if _has(r"\bfellowship\b|\bfellow\b", lower):
        return "Fellowship", full_time
    if _has(r"\bintern(?:ship)?\b", lower):
        return "Internship", full_time
    if _has(r"\bvolunteer(?:ing)?\b|\bunpaid\s+(?:open[\s-]?source|developer|software|engineering)\b", lower):
        return "Volunteer", full_time

    if _has(r"\bfreelanc(?:e|er|ing)\b|\bindependent (?:professional|consultant)\b", lower):
        return "Freelance", full_time
    if _has(r"\bfractional\b", lower):
        return "Fractional", full_time
    if _has(r"\bpart[\s-]?time\b", lower):
        return "Part-time", full_time
    if _has(r"\bfixed[\s-]?term\b", lower):
        return "Fixed-term", full_time
    if _has(r"\bproject[\s-]?based\b|\bper[\s-]?project\b", lower):
        return "Project-based", full_time
    if _has(r"\bretainer\b", lower):
        return "Retainer", full_time
    if _has(
        r"\bindependent contractor\b|\bcontractor\b|\bcontract(?: role| position| basis| work| job| engagement)?\b|\b1099\b|\bc2c\b|\bb2b contract\b|\btemporary\b|\btemp role\b",
        contract_text,
    ):
        return "Contract", full_time

    source = _source_key(job)
    freelance_sources = [str(item).lower() for item in policy.get("freelance_sources", [])]
    if any(token in source for token in freelance_sources):
        return "Freelance", full_time
    if full_time:
        return "Full-time", True
    return "Unknown", False


def classify_work_arrangement(job: dict[str, Any], text: str, policy: dict[str, Any]) -> str:
    verified = _clean(job.get("verified_work_arrangement"))
    arrangements = {item.lower(): item for item in ("Remote", "Marketplace", "Hybrid", "Onsite", "Unknown")}
    if verified.lower() in arrangements:
        return arrangements[verified.lower()]
    lower = text.lower()
    location = _clean(job.get("location")).lower()
    location_remote = _has(r"\bremote\b|\bhome[\s-]based\b", location)
    if location_remote and not _has(r"\bhybrid\b|\bon[\s-]?site\b", location):
        # Occasional in-person company events do not define the workplace.
        conflict = _has(r"\b(?:role|position|job)\s+(?:is\s+)?(?:fully\s+)?(?:on[\s-]?site|hybrid)\b|\b(?:required|must)\s+(?:to\s+)?(?:work|be)\s+(?:on[\s-]?site|in (?:the )?office)\b", lower)
        return "Unknown" if conflict else "Remote"
    if _has(r"\bhybrid\b(?!\s+(?:cloud|infrastructure|architecture|systems|environments|deployments))|\bpartially remote\b", lower):
        return "Hybrid"
    if _has(r"\bon[\s-]?site\b|\bin[\s-]?person\b|\boffice[\s-]?based\b|\brelocation required\b", lower):
        return "Onsite"
    if _has(r"\bremote\b|\bhome[\s-]based\b|\bwork from (?:home|anywhere)\b|\bworldwide\b|\banywhere\b", lower):
        return "Remote"
    source = _source_key(job)
    freelance_sources = [str(item).lower() for item in policy.get("freelance_sources", [])]
    if any(token in source for token in freelance_sources):
        return "Marketplace"
    return "Unknown"


def classify_thailand_eligibility(job: dict[str, Any], text: str) -> str:
    verified = _clean(job.get("verified_thailand_eligibility")).upper()
    if verified in {"YES", "LIKELY", "NO", "VERIFY"}:
        return verified
    location = _clean(job.get("location") or job.get("locations") or job.get("job_location"))
    lower_location = location.lower()
    lower_text = text.lower()

    if _has(r"(?:not available|not eligible|excluding|except|exclude(?:s|d)?)\s+(?:in\s+)?thailand|thailand\s+(?:not eligible|excluded)", lower_text):
        return "NO"
    if _has(r"\bthailand\b|\bbangkok\b|ประเทศไทย|กรุงเทพ", lower_location):
        return "YES"
    if _has(r"\bworldwide\b|\banywhere\b|\bglobal(?:ly)?\b|\bapac\b|\basia\b|\basean\b", lower_location):
        return "LIKELY"
    if not lower_location or lower_location in {"remote", "remote only", "work from home", "wfh"}:
        return "VERIFY"

    if _has(r"\btaiwan\b|\btaipei\b|\bkorea\b|\bseoul\b|\bhong kong\b", lower_location):
        return "NO"
    restricted_region = _has(
        r"\b(?:us|usa|u\.s\.|united states|ca|canada|eu|europe|emea|latam|gb|united kingdom|uk|de|germany|nl|netherlands|au|australia|nz|new zealand|sg|singapore|jp|japan|in|india|ph|philippines|br|brazil|mx|mexico|pl|poland|il|israel|ar|argentina|ua|ukraine|es|spain|fr|france|pt|portugal|it|italy|ie|ireland|americas?|north america|south america|toronto|vancouver|london|berlin|munich|amsterdam|sydney|melbourne|tokyo|chennai|kathmandu)\b",
        lower_location,
    )
    if restricted_region:
        return "NO"
    return "VERIFY"


def classify_concurrent_employment(job: dict[str, Any], text: str, full_time_commitment: bool) -> str:
    verified = _clean(job.get("verified_concurrent_employment")).upper()
    if verified in {"COMPATIBLE", "PROHIBITED", "OVERLAP_RISK", "VERIFY"}:
        return verified
    lower = text.lower()
    if _has(
        r"\bexclusive(?:ly| engagement)?\b|\bno (?:other|outside) (?:job|work|employment)\b|\bmoonlighting (?:is )?(?:prohibited|not allowed)\b|\bmust not (?:work|engage) (?:for|with) (?:another|other)\b",
        lower,
    ):
        return "PROHIBITED"
    if full_time_commitment or _has(r"\b(?:35|36|37|38|39|40)\+?\s*(?:hours?|hrs?)\s*(?:per|a)\s*week\b", lower):
        return "OVERLAP_RISK"
    if _has(r"\basynchronous\b|\basync(?:-first)?\b|\bflexible hours\b|\bset your own (?:hours|schedule)\b", lower):
        return "COMPATIBLE"
    if not full_time_commitment and _has(
        r"\bfreelanc(?:e|er|ing)\b|\bfractional\b|\bproject[\s-]?based\b|\bper[\s-]?project\b|\bretainer\b",
        lower,
    ):
        return "COMPATIBLE"
    return "VERIFY"


def classify_engagement_boundary(job: dict[str, Any], text: str) -> str:
    verified = _clean(job.get("verified_engagement_boundary")).upper()
    if verified in {"CONTRACTOR", "EMPLOYMENT_REVIEW", "THAI_EMPLOYEE", "VERIFY"}:
        return verified
    lower = text.lower()
    if _has(r"ประกันสังคม|thai social security|social security fund", lower):
        return "THAI_EMPLOYEE"
    if _has(r"\bemployer of record\b|\bemployee of record\b|\beor\b|\bpayroll employee\b", lower):
        return "EMPLOYMENT_REVIEW"
    if _has(r"\bfreelanc(?:e|er)\b|\bindependent contractor\b|\b1099\b|\bb2b\b|\bc2c\b", lower):
        return "CONTRACTOR"
    return "VERIFY"


def sponsorship_signal(text: str) -> str:
    """A question or search keyword is not evidence of sponsorship."""
    if _has(r"\b(?:no|without)\s+visa\s+(?:support|assistance)|\b(?:do not|does not|cannot|can't|unable to|don't|will not|won't)\s+(?:provide|offer)\s+visa\s+(?:support|assistance)", text):
        return "NO"
    if _has(r"\b(?:no|without)\s+(?:visa\s+)?sponsorship\b|\b(?:cannot|can't|unable to|do not|don't|will not|won't)\s+(?:provide\s+|offer\s+)?sponsor|\bsponsorship\s+(?:is\s+)?not\s+(?:available|provided|offered)", text):
        return "NO"
    if _has(r"\b(?:provide[sd]?|offer[sed]*|includes?)\s+(?:\w+\s+){0,3}visa\s+sponsor|\bvisa\s+sponsor(?:ship)?\s*(?:\+|and|is available|available|provided)|\bvisa\s+(?:support|assistance)\b", text):
        return "SIGNAL"
    return "VERIFY"


def career_lane(job: dict[str, Any], text: str, employment: str, arrangement: str, policy: dict) -> str:
    if not policy.get("career_lanes", {}).get("enabled"):
        return "remote_contract"
    requested = _clean(job.get("search_lane"))
    if requested in {"remote_contract", "remote_career", "relocation"}:
        return requested
    # Do not use keyword/source labels; only actual listing evidence.
    denied_relocation = _has(r"\b(?:no|without)\s+relocation|\b(?:do not|cannot|can't|don't|will not|won't)\s+(?:provide|offer)[^.!?\n]{0,100}\brelocation", text)
    if sponsorship_signal(text) == "SIGNAL" or (not denied_relocation and _has(r"\brelocation\s+(?:required|support|assistance|package)\b", text)):
        return "relocation"
    if employment == "Full-time" and arrangement == "Remote":
        return "remote_career"
    return "remote_contract"


def qualify_career(job: dict, lane: str, text: str, employment: str, arrangement: str,
                   thailand: str, policy: dict) -> tuple[str, list[str]]:
    reasons = []
    if lane == "remote_career":
        if arrangement in {"Onsite", "Hybrid"} or thailand == "NO":
            return REJECT, ["not_thailand_remote_eligible"]
        if arrangement != "Remote":
            reasons.append("verify_remote_work_arrangement")
        if _clean(job.get("verified_thailand_eligibility")).upper() != "YES":
            reasons.append("verify_thailand_employment_path")
    else:
        destination = _clean(job.get("verified_destination_eligibility")).upper()
        if not _clean(job.get("verified_destination_country")):
            reasons.append("verify_destination_country")
        if destination == "NO":
            return REJECT, ["destination_work_authorization_unavailable"]
        if destination != "YES":
            reasons.append("verify_destination_work_authorization_and_visa")
        if sponsorship_signal(text) == "NO" and destination != "YES":
            reasons.append("sponsorship_unavailable_verify_existing_work_rights")
        if not _clean(job.get("location")):
            reasons.append("verify_destination_location")
    if employment == "Unknown":
        reasons.append("verify_employment_type")
    if _clean(job.get("verified_role_requirements")).upper() != "YES":
        reasons.append("verify_required_skills_experience_and_languages")
    if _clean(job.get("verified_career_transition")).upper() != "YES":
        reasons.append("verify_notice_period_and_career_transition")
    if _clean(job.get("verified_employment_terms")).upper() != "YES":
        reasons.append("verify_compensation_hours_and_employment_terms")
    evidence = urlsplit(_clean(job.get("verification_source_url")))
    if evidence.scheme != "https" or not evidence.hostname or not _clean(job.get("verification_notes")):
        reasons.append("require_source_backed_verification_notes")
    try:
        age = (date.today() - date.fromisoformat(_clean(job.get("verified_at")))).days
        fresh = 0 <= age <= policy.get("career_lanes", {}).get("verification_max_age_days", 7)
    except ValueError:
        fresh = False
    if not fresh:
        reasons.append("refresh_listing_and_eligibility_verification")
    if reasons and employment == "Full-time":
        reasons.append("foreign_full_time_requires_review")
    return (VERIFY, reasons) if reasons else (PASS, ["verified_career_change_opportunity"])


def qualify_job(
    job: dict[str, Any],
    description: str = "",
    *,
    policy_path: str | None = None,
) -> dict[str, str]:
    """Classify one listing without mutating it."""
    policy = load_policy(policy_path)
    text = _search_text(job, description)
    employment_type, full_time_commitment = classify_employment(job, text, policy)
    work_arrangement = classify_work_arrangement(job, text, policy)
    thailand_eligibility = classify_thailand_eligibility(job, text)
    concurrent_employment = classify_concurrent_employment(job, text, full_time_commitment)
    engagement_boundary = classify_engagement_boundary(job, text)
    lane = career_lane(job, text, employment_type, work_arrangement, policy)
    source = _source_key(job)
    local_sources = [str(item).lower() for item in policy.get("thai_local_sources", [])]
    local_source = any(token in source for token in local_sources)
    accepted = employment_type in set(policy.get("target", {}).get("accepted_employment_types", []))
    bridge_policy = policy.get("bridge_opportunities", {})
    bridge_types = set(bridge_policy.get("employment_types", BRIDGE_EMPLOYMENT_TYPES))
    unpaid_bridge_types = set(bridge_policy.get("unpaid_review_only", UNPAID_BRIDGE_TYPES))
    paid_bridge_types = bridge_types - unpaid_bridge_types
    bridge_type = employment_type in bridge_types
    lower_text = text.lower()
    verified_compensation = _clean(job.get("verified_bridge_compensation")).upper()
    verified_scope = _clean(job.get("verified_scope_duration")).upper()
    verified_mentor = _clean(job.get("verified_mentor")).upper()
    verified_conversion = _clean(job.get("verified_conversion_path")).upper()
    compensation_signal = verified_compensation in {"YES", "LIKELY"} or _has(
        r"\bpaid\b|\bstipend\b|\bsalary\b|\bhourly\b|\brate\b|\bcompensation\b|[$€£฿]\s*\d",
        lower_text,
    )
    unpaid_signal = _has(r"\bunpaid\b|\bno (?:pay|salary|stipend|compensation)\b", lower_text)
    scope_signal = verified_scope in {"YES", "LIKELY"} or _has(
        r"\b(?:fixed|defined|scoped|milestone|deliverable)\b|\b\d+\s*(?:days?|weeks?|months?)\b",
        lower_text,
    )
    mentor_signal = verified_mentor in {"YES", "LIKELY"} or _has(
        r"\bmentor(?:ing)?\b|\bsupervis(?:or|ed|ion)\b|\bmaintainer\b",
        lower_text,
    )
    conversion_signal = verified_conversion in {"YES", "LIKELY"} or _has(
        r"\bcontract[\s-]?to[\s-]?hire\b|\b(?:path|option|opportunity|eligible)\s+to\s+(?:convert|become|join|transition|hire)\b|\bpotential(?:ly)?\s+(?:full[\s-]?time|hire|employment)\b|\bhire(?:d)?\s+after\b",
        lower_text,
    )
    fee_signal = _has(
        r"\b(?:upfront|application|registration|participation|enrol(?:l)?ment)\s+fee\b|\bpay\s+(?:to|for)\s+(?:apply|participate|join|access)\b|\bincome[\s-]?share\s+agreement\b|\btuition(?:\s+fee)?\b",
        lower_text,
    )
    fee_denial_signal = _has(
        r"\b(?:no|without|zero|free|waived)\s+(?:upfront|application|registration|participation|enrol(?:l)?ment)\s+fee\b|\b(?:no|without|zero|free|waived)\s+tuition(?:\s+fee)?\b|\b(?:upfront|application|registration|participation|enrol(?:l)?ment)\s+fee\s+(?:is|are)\s+(?:free|waived|zero|none)\b|\btuition(?:\s+fee)?\s+(?:is|are)\s+(?:free|waived|zero|none)\b|\b(?:tuition|(?:upfront|application|registration|participation|enrol(?:l)?ment)\s+fee)[-\s]?free\b",
        lower_text,
    )
    bridge_fee_signal = fee_signal and not fee_denial_signal
    exploitative_unpaid_signal = _has(
        r"\bunpaid\b.*\b(?:full[\s-]?time|ongoing|indefinite|unlimited|production|support|on[\s-]?call)\b|\b(?:full[\s-]?time|ongoing|indefinite|unlimited)\b.*\bunpaid\b",
        lower_text,
    )

    reasons: list[str] = []
    status = VERIFY

    if work_arrangement in {"Hybrid", "Onsite"}:
        reasons.append("onsite_or_hybrid_conflicts_with_current_role")
    if thailand_eligibility == "NO":
        reasons.append("thailand_not_in_eligible_region")
    if concurrent_employment == "PROHIBITED":
        reasons.append("outside_employment_prohibited")
    if engagement_boundary == "THAI_EMPLOYEE":
        reasons.append("thai_employee_or_social_security_signal")
    if employment_type == "Full-time" and (local_source or thailand_eligibility == "YES"):
        reasons.append("thai_full_time_not_targeted")
    if employment_type == "Unknown" and local_source:
        reasons.append("thai_listing_without_flexible_engagement_evidence")

    if reasons:
        status = REJECT
    elif bridge_type:
        # Bridge opportunities never bypass human review.  Unpaid volunteer /
        # internship work can be worthwhile for portfolio and references, but
        # it is not evidence of a job offer and must not be auto-prepared.
        if bridge_fee_signal or exploitative_unpaid_signal:
            status = REJECT
            if bridge_fee_signal:
                reasons.append("upfront_fee_or_income_share_not_accepted")
            if exploitative_unpaid_signal:
                reasons.append("unpaid_indefinite_or_production_work_not_accepted")
        else:
            status = VERIFY
            if employment_type in unpaid_bridge_types or unpaid_signal or not compensation_signal:
                reasons.append("unpaid_or_unverified_bridge_compensation")
            if not scope_signal or not mentor_signal:
                reasons.append("verify_scope_duration_and_mentor")
            if employment_type == "Contract-to-hire" and not conversion_signal:
                reasons.append("verify_conversion_timeline_and_terms")
            elif employment_type in {"Apprenticeship", "Fellowship"} and not conversion_signal:
                reasons.append("verify_conversion_or_reference_path")
            if employment_type in unpaid_bridge_types:
                reasons.append("unpaid_bridge_review_only_no_guaranteed_hire")
            # A paid bridge can be promoted only when a reviewer has supplied
            # every critical fact and the engagement is contractor-compatible.
            if (
                employment_type in paid_bridge_types
                and compensation_signal
                and scope_signal
                and mentor_signal
                and conversion_signal
                and thailand_eligibility in {"YES", "LIKELY"}
                and work_arrangement in {"Remote", "Marketplace"}
                and concurrent_employment == "COMPATIBLE"
                and engagement_boundary == "CONTRACTOR"
            ):
                status = PASS
                reasons = ["paid_bridge_with_verified_scope_and_conversion_path"]
    elif accepted:
        if thailand_eligibility not in {"YES", "LIKELY"}:
            reasons.append("verify_thailand_eligibility")
        if work_arrangement == "Unknown":
            reasons.append("verify_remote_work_arrangement")
        if full_time_commitment or concurrent_employment == "OVERLAP_RISK":
            reasons.append("verify_hours_do_not_overlap_current_role")
        elif concurrent_employment != "COMPATIBLE":
            reasons.append("verify_concurrent_employment_compatibility")
        if engagement_boundary == "EMPLOYMENT_REVIEW":
            reasons.append("verify_eor_or_payroll_terms")
        elif engagement_boundary != "CONTRACTOR":
            reasons.append("verify_contractor_or_payroll_terms")
        status = VERIFY if reasons else PASS
        if status == PASS:
            reasons.append("flexible_engagement_and_thailand_eligible")
    elif employment_type == "Full-time":
        status = VERIFY
        reasons.extend(("foreign_full_time_requires_review", "verify_hours_exclusivity_and_employer_terms"))
    else:
        status = VERIFY
        reasons.extend(("employment_type_not_explicit", "verify_contract_or_freelance_terms"))

    # A career change does not require permission to hold two jobs concurrently.
    # Bridge lanes retain their stricter compensation/scope checks above.
    if lane != "remote_contract" and not bridge_type:
        if local_source or (employment_type == "Full-time" and thailand_eligibility == "YES"
                            and engagement_boundary == "THAI_EMPLOYEE"):
            status, reasons = REJECT, ["thai_full_time_not_targeted"]
        else:
            status, reasons = qualify_career(job, lane, text, employment_type,
                                            work_arrangement, thailand_eligibility, policy)

    requested_readiness = _clean(job.get("application_readiness")).upper()
    if status == REJECT:
        application_readiness = BLOCKED
    elif status == PASS and requested_readiness == APPROVED:
        application_readiness = APPROVED
    else:
        application_readiness = REVIEW_REQUIRED

    return {
        "search_lane": lane,
        "visa_sponsorship": sponsorship_signal(text),
        "policy_version": str(policy["policy_version"]),
        "qualification_status": status,
        "employment_type": employment_type,
        "work_arrangement": work_arrangement,
        "thailand_eligibility": thailand_eligibility,
        "concurrent_employment": concurrent_employment,
        "engagement_boundary": engagement_boundary,
        "application_readiness": application_readiness,
        "qualification_reasons": ";".join(dict.fromkeys(reasons)),
    }


def is_qualified_for_preparation(job: dict[str, Any]) -> bool:
    if job.get("search_lane") in {"remote_career", "relocation"}:
        return qualify_job(job)["qualification_status"] == PASS
    return _clean(job.get("qualification_status")).upper() == PASS


def is_approved_for_submission(job: dict[str, Any]) -> bool:
    return is_qualified_for_preparation(job) and _clean(job.get("application_readiness")).upper() == APPROVED
