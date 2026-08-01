"""Shared validation helpers for normalized permit records."""

SCHEMA_VERSION = "1.0"

REQUIRED_FIELDS = (
    "schema_version",
    "record_id",
    "source_id",
    "permit_number",
    "project",
    "county",
    "state",
    "source",
    "source_url",
    "contractors",
)


class PermitValidationError(ValueError):
    """Raised when an adapter emits a malformed normalized permit."""


def validate_project(project):
    missing = [field for field in REQUIRED_FIELDS if field not in project]
    if missing:
        raise PermitValidationError(
            "normalized permit is missing fields: " + ", ".join(missing)
        )

    if project["schema_version"] != SCHEMA_VERSION:
        raise PermitValidationError("unsupported normalized permit schema version")
    if not project["record_id"] or ":" not in project["record_id"]:
        raise PermitValidationError("record_id must be source-qualified")
    if not isinstance(project["contractors"], list):
        raise PermitValidationError("contractors must be a list")

    for contractor in project["contractors"]:
        if not isinstance(contractor, dict):
            raise PermitValidationError("each contractor must be an object")
        for field in ("name", "role", "source", "source_field"):
            if not contractor.get(field):
                raise PermitValidationError(
                    f"contractor is missing provenance field: {field}"
                )

    return project
