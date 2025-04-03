# region imports
from AlgorithmImports import *
#endregion

class TrailingStopRiskManagementModel(RiskManagementModel):
    """
    Modèle de gestion du risque basé sur un Trailing Stop.
    Par défaut : stop à 8% pour laisser plus de marge en Hourly.
    """

    def __init__(self, stop_loss_percentage=0.08):
        """
        stop_loss_percentage: fraction du prix moyen en dessous (LONG) ou au-dessus (SHORT)
        de laquelle on liquide la position.
        """
        self.stop_loss_percentage = stop_loss_percentage

    def ManageRisk(self, algorithm, targets):
        """
        Parcourt le portefeuille et renvoie des cibles (PortfolioTarget)
        pour liquider les positions qui ont atteint le stop.
        """
        risk_adjusted_targets = []

        for kvp in algorithm.Portfolio:
            symbol = kvp.Key
            security = kvp.Value

            if security.Invested:
                # Calcul du stop
                if security.IsLong:
                    stop_price = security.AveragePrice * (1 - self.stop_loss_percentage)
                    if security.Price < stop_price:
                        algorithm.Log(f"[Risk] Liquidating LONG {symbol} at {security.Price:.2f}, Stop={stop_price:.2f}")
                        risk_adjusted_targets.append(PortfolioTarget(symbol, 0))

                if security.IsShort:
                    stop_price = security.AveragePrice * (1 + self.stop_loss_percentage)
                    if security.Price > stop_price:
                        algorithm.Log(f"[Risk] Liquidating SHORT {symbol} at {security.Price:.2f}, Stop={stop_price:.2f}")
                        risk_adjusted_targets.append(PortfolioTarget(symbol, 0))

        return risk_adjusted_targets

