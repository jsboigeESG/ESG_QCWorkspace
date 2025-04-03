# Import des bibliothèques
from AlgorithmImports import *

class CryptoBollingerBandsAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2021, 1, 1)  # Date de début
        self.SetEndDate(2023, 1, 1)    # Date de fin
        self.SetAccountCurrency("USDT") # Indication de la devise
        self.SetCash(100000)           # Capital initial

        # Configuration de Binance et des cryptomonnaies
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        self.btc_symbol = self.AddCrypto("BTCUSDT", Resolution.Hour, Market.Binance).Symbol

        # Indicateur des Bandes de Bollinger
        self.bollinger_period = 20
        self.bollinger_std_dev = 2
        self.bollinger = self.BB(self.btc_symbol, self.bollinger_period, self.bollinger_std_dev, MovingAverageType.Simple, Resolution.Hour)

        # Benchmark sur le Bitcoin
        self.SetBenchmark(self.btc_symbol)

        # Variables pour suivre les positions
        self.current_position = None

    def OnData(self, data):
        if not self.bollinger.IsReady:
            return

        price = data[self.btc_symbol].Price
        upper_band = self.bollinger.UpperBand.Current.Value
        middle_band = self.bollinger.MiddleBand.Current.Value
        lower_band = self.bollinger.LowerBand.Current.Value

        # Logiciel d'achat et de vente basé sur les bandes de Bollinger
        if self.current_position != "long" and price < lower_band:
            self.SetHoldings(self.btc_symbol, 1.0)  # Allouer 100% du capital au Bitcoin
            self.current_position = "long"
            self.Debug(f"#BTCUSD acheté à {price}")

        elif self.current_position != "short" and price > upper_band:
            self.Liquidate(self.btc_symbol)        # Vendre toutes les positions
            self.current_position = "short"
            self.Debug(f"#BTCUSD vendu à {price}")

        elif middle_band - price < 10 and self.current_position == "long":
            self.Liquidate(self.btc_symbol)
            self.current_position = None
            self.Debug(f"Position liquidé à {price}")


