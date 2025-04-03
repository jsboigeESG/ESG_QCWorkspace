# Import des bibliothèques
from AlgorithmImports import *

class CryptoMovingAverageCrossAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration Initiale
        self.SetStartDate(2020, 1, 1)  # Date de début
        self.SetEndDate(2024, 1, 1)    # Date de fin
        self.SetAccountCurrency("USDT") # Définir la devise du compte en USDT
        self.SetCash(100000)           # Capital initial

        # Configuration de Binance et des Cryptomonnaies
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        self.btc_symbol = self.AddCrypto("BTCUSDT", Resolution.Daily, Market.Binance).Symbol

        # Indicateurs des Moyennes Mobiles
        self.ma5 = self.SMA(self.btc_symbol, 5, Resolution.Daily)  # Moyenne mobile à 5 jours
        self.ma20 = self.SMA(self.btc_symbol, 20, Resolution.Daily) # Moyenne mobile à 20 jours
        
        # Benchmark
        self.SetBenchmark(self.btc_symbol)

        # Suivi des positions
        self.current_position = None  # Variable pour stocker l'état actuel (achat ou vente)

    def OnData(self, data):
        # Vérifier si tous les indicateurs sont prêts
        if not self.ma5.IsReady or not self.ma20.IsReady:
            return

        # Obtenir les valeurs actuelles de MA5 et MA20
        ma5_value = self.ma5.Current.Value
        ma20_value = self.ma20.Current.Value
        price = data[self.btc_symbol].Price  # Prix actuel du Bitcoin

        # Logique d'achat
        if self.current_position != "long" and ma5_value > ma20_value:
            self.SetHoldings(self.btc_symbol, 1.0)  # Allouer 100% du capital au Bitcoin
            self.current_position = "long"  # Marquer la position comme "long"
            self.Debug(f"Achat BTCUSDT à {price} ; MA5: {ma5_value}, MA20: {ma20_value}")

        # Logique de vente
        elif self.current_position != "short" and ma5_value < ma20_value:
            self.Liquidate(self.btc_symbol)  # Vendre toutes les positions
            self.current_position = "short"  # Marquer la position comme "short"
            self.Debug(f"Vente BTCUSDT à {price} ; MA5: {ma5_value}, MA20: {ma20_value}")
