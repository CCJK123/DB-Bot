from typing import Final

from .resources import Resources

base_url: Final[str] = 'https://politicsandwar.com/'
base_api_url: Final[str] = 'https://api.politicsandwar.com/graphql'
market_res: Final[tuple[str, ...]] = Resources.all_res[1:]
market_res_title: Final[tuple[str, ...]] = tuple(res.title() for res in market_res)

project_costs = {
    'advanced_urban_planning': Resources(uranium=10000, aluminum=40000, steel=20000, munitions=20000, food=2_500_000),
    'advanced_engineering_corps': Resources(uranium=1000, munitions=10000, gasoline=10000, money=50_000_000),
    'arable_land_agency': Resources(coal=1500, lead=1500, money=3_000_000),
    'arms_stockpile': Resources(aluminum=125, steel=125, money=4_000_000),
    'bauxite_works': Resources(steel=750, gasoline=1500, money=5_000_000),
    'center_for_civil_engineering': Resources(oil=1000, iron=1000, bauxite=1000, money=3_000_000),
    'clinical_research_center': Resources(food=100_000, money=10_000_000),
    'emergency_gasoline_reserve': Resources(aluminum=125, steel=125, money=4_000_000),
    'green_technologies': Resources(iron=10000, steel=10000, aluminum=10000, food=250_000),
    'government_support_agency': Resources(food=200_000, aluminum=10000, money=20_000_000),
    'central_intelligence_agency': Resources(steel=500, gasoline=500, money=5_000_000),
    'international_trade_center': Resources(aluminum=2500, steel=2500, gasoline=5000, money=45_000_000),
    'iron_dome': Resources(aluminum=500, steel=1250, gasoline=500, money=6_000_000),
    'iron_works': Resources(aluminum=750, gasoline=1500, money=5_000_000),
    'mass_irrigation': Resources(aluminum=500, steel=500, money=3_000_000),
    'metropolitan_planning': Resources(aluminum=60000, steel=40000, uranium=30000,
                                       lead=15000, iron=15000, bauxite=15000, oil=10000, coal=10000),
    'missile_launch_pad': Resources(steel=1000, gasoline=350, money=8_000_000),
    'nuclear_research_facility': Resources(steel=5000, gasoline=7500, money=50_000_000),
    'pirate_economy': Resources(aluminum=10000, munitions=10000, gasoline=10000, steel=10000, money=25_000_000),
    'propaganda_bureau': Resources(aluminum=1500, money=15_000_000),
    'recycling_initiative': Resources(food=100_000, money=10_000_000),
    'research_and_development_center': Resources(uranium=1000, aluminum=5000, food=100_000, money=50_000_000),
    'resource_production_center': Resources(food=1000, money=500_000),
    'space_program': Resources(uranium=20000, oil=20000, iron=10000,
                               gasoline=5000, steel=1000, aluminum=1000, money=40_000_000),
    'specialized_police_training_program': Resources(food=100_000, money=10_000_000),
    'spy_satellite': Resources(oil=10000, iron=10000, lead=10000, bauxite=10000, uranium=10000, money=20_000_000),
    'telecommunications_satellite': Resources(uranium=10000, iron=10000, oil=10000, aluminum=10000, money=300_000_000),
    'uranium_enrichment_program': Resources(aluminum=1000, gasoline=1000, uranium=500, money=21_000_000),
    'urban_planning': Resources(coal=10000, oil=10000, aluminum=20000, munitions=10000, gasoline=10000, food=1_000_000),
    'vital_defense_system': Resources(aluminum=3000, steel=6500, gasoline=5000, money=40_000_000)
}
