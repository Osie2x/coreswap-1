from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

Province = Literal["ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "PE", "NL", "YT", "NT", "NU"]
InsulationType = Literal["spray_foam_hfc", "spray_foam_hfo", "fiberglass", "mineral_wool", "cellulose"]


class FactoryProfile(BaseModel):
    company_name: str
    province: Province
    annual_units: int = Field(ge=1, le=100000)
    avg_home_sqft: int = Field(ge=400, le=10000)
    current_insulation: InsulationType
    wall_assembly_ratio: float = Field(default=1.6, ge=1.0, le=3.0)


class ExtractedEPDData(BaseModel):
    product_name: str
    manufacturer: str
    declared_unit: str
    gwp_kg_co2e_per_sqft: float
    reference_standard: Optional[str] = None
    validity_year: Optional[int] = None
    extraction_confidence: Literal["high", "medium", "low"]
    extraction_notes: str


class ValidationResult(BaseModel):
    passed: bool
    insulation_type_inferred: InsulationType
    expected_range: tuple[float, float]
    flagged_reason: Optional[str] = None


class LCAResult(BaseModel):
    profile: FactoryProfile
    current_gwp_per_sqft: float
    cellulose_gwp_per_sqft: float
    insulated_sqft_per_home: float
    annual_emissions_current_tonnes: float
    annual_emissions_cellulose_tonnes: float
    annual_switch_benefit_tonnes: float
    lifetime_switch_benefit_tonnes: float
    carbon_credit_value_low_cad: float
    carbon_credit_value_high_cad: float


class ReportRecord(BaseModel):
    id: Optional[int] = None
    created_at: datetime
    profile: FactoryProfile
    lca: LCAResult
    narrative_summary: str
    pdf_path: str
