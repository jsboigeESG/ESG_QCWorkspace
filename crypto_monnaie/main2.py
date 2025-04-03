# **Import des bibliothèques**
from AlgorithmImports import *

class CryptoMovingAverageCrossAlgorithm(QCAlgorithm): 
    def Initialize(self):
        # **Configuration Initiale**
        self.SetStartDate(2021, 1, 1)  # Date de début
        self.SetEndDate(2023, 1, 1)    # Date de fin
        self.SetCash(100000)           # Capital initial
        self.SetAccountCurrency("USDT")  # Définir la devise du compte en USDT

        # **Configuration de Binance et des Cryptomonnaies**
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        self.btc_symbol = self.AddCrypto("BTCUSDT", Resolution.Hour, Market.Binance).Symbol

        # **Indicateurs des Moyennes Mobiles**
        self.ma5 = self.SMA(self.btc_symbol, 5, Resolution.Hour)   # Moyenne mobile à 5 périodes
        self.ma10 = self.SMA(self.btc_symbol, 10, Resolution.Hour) # Moyenne mobile à 10 périodes
        
        # **Benchmark**
        self.SetBenchmark(self.btc_symbol)

        # **Suivi des positions**
        self.current_position = None  # Variable pour stocker l'état actuel (achat ou vente)

    def OnData(self, data):
        # Vérifier si tous les indicateurs sont prêts
        if not self.ma5.IsReady or not self.ma10.IsReady:
            return

        # Obtenir les valeurs actuelles de MA5 et MA10
        ma5_value = self.ma5.Current.Value
        ma10_value = self.ma10.Current.Value
        price = data[self.btc_symbol].Price  # Prix actuel du Bitcoin

        # **Logique d'achat**
        if self.current_position != "long" and ma5_value > ma10_value:
            self.SetHoldings(self.btc_symbol, 1.0)  # Allouer 100% du capital au Bitcoin
            self.current_position = "long"         # Marquer la position comme "long"
            self.Debug(f"Achat BTCUSDT à {price} ; MA5: {ma5_value}, MA10: {ma10_value}")

        # **Logique de vente**
        elif self.current_position != "short" and ma5_value < ma10_value:
            self.Liquidate(self.btc_symbol)        # Vendre toutes les positions
            self.current_position = "short"       # Marquer la position comme "short"
            self.Debug(f"Vente BTCUSDT à {price} ; MA5: {ma5_value}, MA10: {ma10_value}")
