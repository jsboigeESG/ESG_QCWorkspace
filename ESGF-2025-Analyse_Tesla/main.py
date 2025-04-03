# Importer les dépendances nécessaires
from AlgorithmImports import *
import math      
class TeslaAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Configuration de l'algorithme
        self.SetStartDate(2020, 1, 1)  # Date de début
        self.SetEndDate(2023, 1, 1)    # Date de fin
        self.SetCash(100000)           # Capital initial

        # Ajout de l'actif Tesla
        self.ticker = "TSLA"
        self.AddEquity(self.ticker, Resolution.Daily)

        # Initialisation des indicateurs EMA
        self.fast_ema = self.EMA(self.ticker, 10, Resolution.Daily)
        self.slow_ema = self.EMA(self.ticker, 50, Resolution.Daily)

        # Warm-up pour calculer les EMA
        self.SetWarmUp(50)

    def OnData(self, data):
        # Vérifie si les EMA sont prêtes
        if not self.fast_ema.IsReady or not self.slow_ema.IsReady:
            return
        
        # Logique d'achat/vente
        if self.fast_ema.Current.Value > self.slow_ema.Current.Value:
            if not self.Portfolio[self.ticker].Invested:
                self.SetHoldings(self.ticker, 1)
                self.Debug(f"Achat de {self.ticker} à {data[self.ticker].Close}")

        elif self.fast_ema.Current.Value < self.slow_ema.Current.Value:
            if self.Portfolio[self.ticker].Invested:
                self.Liquidate(self.ticker)
                self.Debug(f"Vente de {self.ticker} à {data[self.ticker].Close}")
