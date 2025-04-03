from AlgorithmImports import *
import numpy as np

class BinanceFeeModel(FeeModel):
    """Modèle de frais Binance (0,1 %)"""
    def GetOrderFee(self, parameters):
        value = parameters.Security.Price * abs(parameters.Order.AbsoluteQuantity)
        fee = 0.001 * value
        return OrderFee(CashAmount(fee, parameters.Security.QuoteCurrency.Symbol))

class OptimizedCryptoTradingAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration
        self.SetStartDate(2019, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(5000000)

        # Stockage de la valeur initiale (portefeuille total initial)
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue

        # Liste des cryptos (plus diversifiée)
        self.crypto_symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("SOLUSD", Resolution.Daily, Market.GDAX).Symbol
        ]

        # Benchmark basé sur un indice (BTC et ETH comme proxy)
        self.benchmark_symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.GDAX).Symbol,
        ]
        self.SetBenchmark(lambda time: sum(self.Securities[symbol].Price for symbol in self.benchmark_symbols) / len(self.benchmark_symbols))

        # Modèle de frais personnalisé
        for symbol in self.crypto_symbols:
            self.Securities[symbol].SetFeeModel(BinanceFeeModel())

        # Indicateurs pour chaque actif
        self.indicators = {}
        for symbol in self.crypto_symbols:
            self.indicators[symbol] = {
                "short_rsi": self.RSI(symbol, 14, MovingAverageType.Simple, Resolution.Daily),  # RSI courte période (14)
                "long_rsi": self.RSI(symbol, 30, MovingAverageType.Simple, Resolution.Daily),  # RSI longue période (30)
                "bollinger": self.BB(symbol, 20, 2, MovingAverageType.Simple, Resolution.Daily),  # Bandes de Bollinger
                "momentum": self.MOMP(symbol, 60, Resolution.Daily),  # Momentum (60 jours)
                "atr": self.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily)  # ATR
            }

        # Paramètres de gestion des risques
        self.max_risk_per_trade = 0.02  # 2% par trade
        self.trailing_stop_multiplier = 3.0  # Trailing stop dynamique basé sur volatilité
        self.global_drawdown_limit = 0.30  # Limite de drawdown à 30%
        self.trailing_stop_prices = {}
        self.entry_prices = {}
        self.min_order_value = 50000  # Valeur minimale d'une taille de position
        self.total_fees = 0

    def OnData(self, data):
        # Vérification de la limite de drawdown global
        if self.Portfolio.TotalPortfolioValue < (1 - self.global_drawdown_limit) * self.starting_portfolio_value:
            self.Debug("STOP : Limite de drawdown global atteinte.")
            self.Liquidate()
            self.Quit()

        # Parcourir chaque actif
        for symbol in self.crypto_symbols:
            if not data.Bars.ContainsKey(symbol):
                continue

            indicators = self.indicators[symbol]
            price = data[symbol].Close  # Prix actuel
            invested = self.Portfolio[symbol].Invested

            # Vérification des indicateurs prêts
            if not (indicators["short_rsi"].IsReady and indicators["long_rsi"].IsReady 
                    and indicators["bollinger"].IsReady and indicators["momentum"].IsReady
                    and indicators["atr"].IsReady):
                continue

            # Indicateurs
            short_rsi = indicators["short_rsi"].Current.Value
            long_rsi = indicators["long_rsi"].Current.Value
            bollinger_lower = indicators["bollinger"].LowerBand.Current.Value
            bollinger_upper = indicators["bollinger"].UpperBand.Current.Value
            momentum = indicators["momentum"].Current.Value
            atr = indicators["atr"].Current.Value

            # Conditions d'achat
            if not invested and price > bollinger_upper and short_rsi > 50 and momentum > 0:
                allocation = self.Portfolio.TotalPortfolioValue * self.max_risk_per_trade
                risk_per_share = atr * self.trailing_stop_multiplier
                quantity = int(allocation / (risk_per_share * (1 + 0.001)))

                if quantity * price >= self.min_order_value:
                    self.MarketOrder(symbol, quantity)
                    self.trailing_stop_prices[symbol] = price - (atr * self.trailing_stop_multiplier)
                    self.entry_prices[symbol] = price
                    self.Debug(f"Achat : {symbol} à {price:.2f}, quantité : {quantity}")

            # Conditions de vente
            elif invested:
                entry_price = self.entry_prices.get(symbol, price)
                trailing_stop = self.trailing_stop_prices.get(symbol, None)

                # Vente si trailing stop atteint
                if trailing_stop and price < trailing_stop:
                    self.Liquidate(symbol)
                    self.Debug(f"Vente : {symbol} liquidé à {price:.2f} (Trailing Stop)")

                # Sortie des positions si conditions inversées
                elif price < bollinger_lower or short_rsi < 40 or momentum < 0:
                    self.Liquidate(symbol)
                    self.Debug(f"Vente : {symbol} à {price:.2f} (Conditions inverses détectées)")

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            fee = abs(orderEvent.FillQuantity) * orderEvent.FillPrice * 0.001
            self.total_fees += fee
            self.Debug(f"Frais : {fee:.2f} USD")

    def OnEndOfAlgorithm(self):
        net_profit = self.Portfolio.TotalPortfolioValue - self.starting_portfolio_value
        self.Debug(f"Profit Net : {net_profit:.2f} USD")
        self.Debug(f"Frais Totaux : {self.total_fees:.2f} USD")
