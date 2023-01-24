import datetime
import decimal
import math
from typing import Any

from bot.utils.pnwutils.resources import Resources


__all__ = ('City',)

# thanks to rift (https://github.com/mrvillage/rift)


def mul_bonus(amt, maxi):
    return amt * (1 + (amt - 1) * 0.5 / (maxi - 1)) if amt else 0


class City:
    def __init__(self, data: dict[str, Any], projects: dict[str, bool]):
        self.data = data
        self.projects = projects
        self._population = 0
        self._disease = 0
        self._crime = 0
        self._pollution = 0
        self._commerce = 0
        self._revenue: 'Resources | None' = None

    @property
    def population(self):
        if not self._population:
            age = (datetime.datetime.now(datetime.timezone.utc) -
                   datetime.datetime.fromisoformat(self.data["date"]).replace(tzinfo=datetime.timezone.utc)).days
            self._population = (
                self.data['infrastructure'] * (100 - self.disease)
                - max(10 * self.crime * self.data['infrastructure'] - 25, 0)
            ) * (1 + (math.log(age) if age else 0) / 15)
        return self._population

    @property
    def disease(self) -> float:
        if not self._disease:
            self._disease = (
                (self.data['infrastructure'] / self.data['land']) ** 2 - 0.25
                + self.data['infrastructure'] / 1000
                + self.pollution * 0.05
                - self.data['hospital'] * (2.5 + self.projects['clinical_research_center'])
            )
        if self._disease < 0:
            return 0
        if self._disease > 100:
            return 100
        return self._disease

    @property
    def crime(self) -> float:
        if not self._crime:
            self._crime = (
                ((103 - self.commerce) ** 2 + (self.data['infrastructure'] * 100)) / 111111
                - self.data['police_station'] * (2.5 + self.projects['specialized_police_training_program'])
            )
        if self._crime < 0:
            return 0
        if self._crime > 100:
            return 100
        return self._crime

    @property
    def pollution(self) -> float:
        if not self._pollution:
            green = self.projects['green_technologies']
            self._pollution = (
                self.data['coal_power'] * 8
                + self.data['oil_power'] * 6
                + (self.data['coal_mine'] + self.data['oil_well'] + self.data['lead_mine'] +
                   self.data['iron_mine'] + self.data['bauxite_mine']) * 12
                + self.data['uranium_mine'] * 20
                + self.data['farm'] * 2 * (1 - green * 0.5)
                + (self.data['oil_refinery'] + self.data['munitions_factory']) * 32 * (1 - green * 0.25)
                + (self.data['steel_mill'] + self.data['aluminum_refinery']) * 40 * (1 - green * 0.25)
                + self.data['police_station']
                + self.data['hospital'] * 4
                - self.data['recycling_center'] * (70 + 5 * self.projects['recycling_initiative'])
                - self.data['subway'] * (45 + 25 * green)
                + self.data['shopping_mall'] * 2
                + self.data['stadium'] * 5
            )
        return self._pollution

    @property
    def commerce(self) -> float:
        if not self._commerce:
            self._commerce = (
                self.data['supermarket'] * 3
                + self.data['bank'] * 5
                + self.data['shopping_mall'] * 9
                + self.data['stadium'] * 12
                + self.data['subway'] * 8
                + self.projects['telecommunications_satellite'] * 2
            )
            if not self.projects['telecommunications_satellite']:
                if self.projects['international_trade_center']:
                    self._commerce = 115 if self._commerce >= 115 else self._commerce
                else:
                    self._commerce = 100 if self._commerce >= 100 else self._commerce
        return self._commerce

    def revenue(self, cash_bonus: float):
        """Money production seems off"""
        if not self._revenue:
            self._revenue = Resources(money=(
                (self.commerce / 50 + 1) * 0.725 * self.population * cash_bonus
            ) if self.data['powered'] else 0.725 * self.population)
            self._revenue.money -= (
                self.data['coal_power'] * 1200
                + self.data['oil_power'] * 1800
                + self.data['nuclear_power'] * 10500
                + self.data['wind_power'] * 500
                + self.data['coal_mine'] * 400
                + self.data['oil_well'] * 600
                + (self.data['iron_mine'] + self.data['bauxite_mine']) * 1600
                + self.data['lead_mine'] * 1500
                + self.data['uranium_mine'] * 5000
                + self.data['farm'] * 300
            )
            if self.data['farm']:
                self._revenue.food = (
                    (self.data['land'] / (500 - self.projects['mass_irrigation'] * 100)) * 12
                    * mul_bonus(self.data['farm'], 20)
                )
            self._revenue.food -= self.population / 1000
            # for coal and oil power, assumes that the power plant is needed
            self._revenue.coal = 3 * mul_bonus(self.data['coal_mine'], 10) - 1.2 * self.data['coal_power']
            self._revenue.oil = 3 * mul_bonus(self.data['oil_well'], 10) - 1.2 * self.data['oil_power']
            self._revenue.uranium = (
                    3 * (1 + self.projects['uranium_enrichment_program']) * mul_bonus(self.data['uranium_mine'], 5) -
                    min((self.data['infrastructure'] + 999.99) // 1000, 2 * self.data['nuclear_power']) * 1.2)

            self._revenue.lead = 3 * mul_bonus(self.data['lead_mine'], 10)
            self._revenue.iron = 3 * mul_bonus(self.data['iron_mine'], 10)
            self._revenue.bauxite = 3 * mul_bonus(self.data['bauxite_mine'], 10)
            if self.data['powered']:
                if self.data['oil_refinery']:
                    eff = mul_bonus(self.data['oil_refinery'], 5) * (
                            1 + 0.36 * self.projects['emergency_gasoline_reserve'])
                    self._revenue.oil -= eff * 3
                    self._revenue.gasoline = eff * 6
                if self.data['munitions_factory']:
                    eff = mul_bonus(self.data['munitions_factory'], 5) * (1 + 0.34 * self.projects['arms_stockpile'])
                    self._revenue.lead -= eff * 6
                    self._revenue.munitions = eff * 18
                if self.data['steel_mill']:
                    eff = mul_bonus(self.data['steel_mill'], 5) * (1 + 0.36 * self.projects['iron_works'])
                    self._revenue.coal -= eff * 3
                    self._revenue.iron -= eff * 3
                    self._revenue.steel = eff * 9
                if self.data['aluminum_refinery']:
                    eff = mul_bonus(self.data['aluminum_refinery'], 5) * (1 + 0.36 * self.projects['bauxite_works'])
                    self._revenue.bauxite -= eff * 3
                    self._revenue.aluminum = eff * 9
                self._revenue.money -= (
                    (self.data['oil_refinery'] + self.data['steel_mill']) * 4000
                    + self.data['munitions_factory'] * 3500
                    + self.data['aluminum_refinery'] * 2500
                    + self.data['police_station'] * 750
                    + self.data['hospital'] * 1000
                    + self.data['recycling_center'] * 2500
                    + self.data['subway'] * 3250
                    + self.data['supermarket'] * 600
                    + self.data['bank'] * 1800
                    + self.data['shopping_mall'] * 5400
                    + self.data['stadium'] * 12150
                )
        return self._revenue
