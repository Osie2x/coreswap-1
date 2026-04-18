from .config import PLAUSIBLE_GWP_RANGES
from .models import ExtractedEPDData, InsulationType, ValidationResult


def validate_extraction(extracted: ExtractedEPDData, declared_type: InsulationType) -> ValidationResult:
    low, high = PLAUSIBLE_GWP_RANGES[declared_type]
    value = extracted.gwp_kg_co2e_per_sqft

    if low <= value <= high:
        return ValidationResult(
            passed=True,
            insulation_type_inferred=declared_type,
            expected_range=(low, high),
        )

    for candidate_type, (clow, chigh) in PLAUSIBLE_GWP_RANGES.items():
        if clow <= value <= chigh:
            return ValidationResult(
                passed=False,
                insulation_type_inferred=candidate_type,
                expected_range=(low, high),
                flagged_reason=(
                    f"Extracted GWP of {value} kg CO2e/sq ft falls outside the expected "
                    f"range [{low}, {high}] for {declared_type}. It matches the range for "
                    f"{candidate_type}. Verify the EPD type or manually override."
                ),
            )

    return ValidationResult(
        passed=False,
        insulation_type_inferred=declared_type,
        expected_range=(low, high),
        flagged_reason=(
            f"Extracted GWP of {value} kg CO2e/sq ft is implausible for any standard "
            f"insulation type. Re-check the EPD — possible unit error, wrong document, "
            f"or LLM hallucination."
        ),
    )
