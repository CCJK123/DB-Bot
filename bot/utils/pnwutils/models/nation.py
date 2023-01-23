from typing import Any

from .city import City
from .. import Resources


class Nation:
    def __init__(self, data: dict[str, Any]):
        open_markets = data['domestic_policy'] == 'OPEN_MARKETS'
        self.data = data
        self.cities = [City(city_data, data, open_markets) for city_data in data['cities']]
        self._population = 0
        self._revenue: 'Resources | None' = None

    def population(self):
        if not self._population:
            self._population = sum(city.population for city in self.cities)
        return self._population

    def revenue(self):
        """It does not take into account the turn bonus, and does not include spies if they are not accessible"""
        if not self._revenue:
            print(f'calculating revenue for {self.data["nation_name"]}')
            self._revenue = Resources()
            spies = self.data['spies'] if self.data['spies'] else 0
            self._revenue.money -= (
                    0.0025 * self.data['soldiers']
                    + 75 * self.data['tanks']
                    + 750 * self.data['aircraft']
                    + 5062.5 * self.data['ships']
                    + 2400 * spies
                    + 31500 * self.data['missiles']
                    + 52500 * self.data['nukes']
            ) if self.data['wars'] else (
                    0.00376 * self.data['soldiers']
                    + 50 * self.data['tanks']
                    + 500 * self.data['aircraft']
                    + 3375 * self.data['ships']
                    + 2400 * spies
                    + 21000 * self.data['missiles']
                    + 35000 * self.data['nukes']
            )
            self._revenue.food -= self.data['soldiers'] / (500 if self.data['wars'] else 750)
            if self.data['domestic_policy'] == 'IMPERIALISM':
                self._revenue *= 0.95 - 0.025 * self.data['government_support_agency']
            print('expenses: ', self._revenue)
            self._revenue = sum((city.revenue() for city in self.cities), self._revenue)
            print(self._revenue)
        return self._revenue
