from enum import StrEnum


class AssigneeId(StrEnum):
    AARTI = "u_aarti"
    ROHIT = "u_rohit"
    MEERA = "u_meera"
    KARAN = "u_karan"
    DIVYA = "u_divya"
    TRIAGE = "u_triage"


class Category(StrEnum):
    ENTERPRISE_RFP = "enterprise_rfp"
    SMB_ENQUIRY = "smb_enquiry"
    MARKETING = "marketing"
    ALLIANCES = "alliances"
    FINANCE = "finance"
    TRIAGE = "triage"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Operation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"
    NOOP = "noop"


class Actionability(StrEnum):
    ACTIONABLE = "actionable"
    NON_ACTIONABLE = "non_actionable"
    AMBIGUOUS = "ambiguous"


class SkipReason(StrEnum):
    OUT_OF_OFFICE = "out_of_office"
    NEWSLETTER = "newsletter"
    VENDOR_SPAM = "vendor_spam"
    AUTOMATED_BOUNCE = "automated_bounce"


ASSIGNEE_CATEGORY = {
    AssigneeId.AARTI: Category.ENTERPRISE_RFP,
    AssigneeId.ROHIT: Category.SMB_ENQUIRY,
    AssigneeId.MEERA: Category.MARKETING,
    AssigneeId.KARAN: Category.ALLIANCES,
    AssigneeId.DIVYA: Category.FINANCE,
    AssigneeId.TRIAGE: Category.TRIAGE,
}
