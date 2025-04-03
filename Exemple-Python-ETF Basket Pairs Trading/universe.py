#region imports
from AlgorithmImports import *
#endregion

class SectorETFUniverseSelectionModel(ETFConstituentsUniverseSelectionModel):
    """
    Exemple de UniverseSelectionModel qui se base sur les constituants
    d'un ETF (ici IYM, iShares U.S. Basic Materials ETF).
    On récupère, par ordre décroissant de poids, les 10 plus gros composants.

    Cette approche permet de cibler un ensemble d'actions
    potentiellement corrélées (même secteur).

    NOTE: La résolution passera en Hourly via UniverseSettings dans main.py.
    """

    def __init__(self, universe_settings: UniverseSettings = None) -> None:
        # Exemple : on utilise l'ETF "IYM" pour les materials.
        symbol = Symbol.Create("IYM", SecurityType.Equity, Market.USA)

        super().__init__(symbol, universe_settings, self.etf_constituents_filter)

    def etf_constituents_filter(self, constituents: List[ETFConstituentData]) -> List[Symbol]:
        # Récupère les 10 plus gros constituants (par Weight) pour limiter la dilution
        selected = sorted(
            [c for c in constituents if c.Weight],
            key=lambda c: c.Weight,
            reverse=True
        )
        return [c.Symbol for c in selected[:10]]

