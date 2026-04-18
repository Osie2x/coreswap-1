from .config import CELLULOSE_BASELINE_GWP, CARBON_PRICE_LOW, CARBON_PRICE_HIGH, BUILDING_LIFETIME_YEARS
from .models import FactoryProfile, LCAResult


def compute_insulated_sqft_per_home(profile: FactoryProfile) -> float:
    return profile.avg_home_sqft * profile.wall_assembly_ratio


def compute_annual_emissions_tonnes(gwp_per_sqft: float, insulated_sqft_per_home: float,
                                    annual_units: int) -> float:
    total_kg = gwp_per_sqft * insulated_sqft_per_home * annual_units
    return total_kg / 1000.0


def run_lca(profile: FactoryProfile, current_gwp_per_sqft: float) -> LCAResult:
    insulated_sqft = compute_insulated_sqft_per_home(profile)
    current_tonnes = compute_annual_emissions_tonnes(current_gwp_per_sqft, insulated_sqft, profile.annual_units)
    cellulose_tonnes = compute_annual_emissions_tonnes(CELLULOSE_BASELINE_GWP, insulated_sqft, profile.annual_units)
    annual_benefit = current_tonnes - cellulose_tonnes
    lifetime_benefit = annual_benefit * BUILDING_LIFETIME_YEARS

    return LCAResult(
        profile=profile,
        current_gwp_per_sqft=current_gwp_per_sqft,
        cellulose_gwp_per_sqft=CELLULOSE_BASELINE_GWP,
        insulated_sqft_per_home=insulated_sqft,
        annual_emissions_current_tonnes=round(current_tonnes, 2),
        annual_emissions_cellulose_tonnes=round(cellulose_tonnes, 2),
        annual_switch_benefit_tonnes=round(annual_benefit, 2),
        lifetime_switch_benefit_tonnes=round(lifetime_benefit, 2),
        carbon_credit_value_low_cad=round(annual_benefit * CARBON_PRICE_LOW, 2),
        carbon_credit_value_high_cad=round(annual_benefit * CARBON_PRICE_HIGH, 2),
    )
