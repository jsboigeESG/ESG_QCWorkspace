from AlgorithmImports import *
from datetime import timedelta

class BinanceFeeModel(FeeModel):
    """Modèle de frais personnalisé (Binance, frais de 0,1 %)"""
    def GetOrderFee(self, parameters):
        value = parameters.Security.Price * abs(parameters.Order.AbsoluteQuantity)
        fee = 0.001 * value  # 0.1 % fee
        return OrderFee(CashAmount(fee, parameters.Security.QuoteCurrency.Symbol))


class OptimizedSwingTradingCryptoAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Configuration du backtest
        self.SetStartDate(2019, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(5000000)
        
        # Liste des cryptomonnaies suivies
        self.crypto_symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("SOLUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ADAUSD", Resolution.Daily, Market.GDAX).Symbol
        ]

        # Appliquer le modèle de frais Binance
        for symbol in self.crypto_symbols:
            self.Securities[symbol].SetFeeModel(BinanceFeeModel())

        # Initialisation des indicateurs pour chaque crypto
        self.indicators = {}
        for symbol in self.crypto_symbols:
            self.indicators[symbol] = {
                "ema_fast": self.EMA(symbol, 15, Resolution.Daily),  # EMA rapide sur 15 jours
                "ema_slow": self.EMA(symbol, 50, Resolution.Daily),  # EMA lente sur 50 jours
                "rsi": self.RSI(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "macd": self.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily),
                "atr": self.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),  # Volatilité (ATR)
            }

        # Paramètres de gestion des risques
        self.trailing_stop_multiplier = 2.0
        self.max_risk_per_trade = 0.02  # Maximum 2% de risque par trade
        self.trailing_stop_prices = {}  # Trailing stop par crypto
        self.entry_prices = {}  # Prix d'entrée par crypto
        self.min_order_value = 50000  # Ignorer les ordres inférieurs à 50 000 USD
        self.total_fees = 0  # Suivi des frais de trading
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue

    def OnData(self, data):
        for symbol in self.crypto_symbols:
            if not data.Bars.ContainsKey(symbol):
                continue

            indicators = self.indicators[symbol]
            price = data[symbol].Close
            invested = self.Portfolio[symbol].Invested

            # Vérifiez que tous les indicateurs sont prêts
            if not (indicators["ema_fast"].IsReady and indicators["ema_slow"].IsReady 
                    and indicators["rsi"].IsReady and indicators["macd"].IsReady 
                    and indicators["atr"].IsReady):
                continue

            # Récupérez les valeurs actuelles des indicateurs
            ema_fast = indicators["ema_fast"].Current.Value
            ema_slow = indicators["ema_slow"].Current.Value
            rsi = indicators["rsi"].Current.Value
            macd = indicators["macd"].Current.Value
            macd_signal = indicators["macd"].Signal.Current.Value
            atr = indicators["atr"].Current.Value

            # **Filtrage des marchés avec faible volatilité**
            atr_relative = atr / price
            if atr_relative < 0.03:  # Ignorer les marchés consolidés ou plats
                continue

            # **Conditions d'achat**
            if not invested and ema_fast > ema_slow and macd > macd_signal and rsi < 70:
                # Calculez le risque par position
                allocation = self.Portfolio.TotalPortfolioValue * self.max_risk_per_trade
                risk_per_share = atr * self.trailing_stop_multiplier
                quantity = int(allocation / (risk_per_share * (1 + 0.001)))  # Inclut 0.1% de frais
                if quantity * price >= self.min_order_value:  # Vérifie la taille minimale
                    self.SetHoldings(symbol, quantity * price / self.Portfolio.TotalPortfolioValue)
                    self.trailing_stop_prices[symbol] = price - (atr * self.trailing_stop_multiplier)
                    self.entry_prices[symbol] = price
                    self.Debug(f"Achat : {symbol} à {price:.2f}, quantité : {quantity}")

            # **Conditions de vente**
            if invested:
                entry_price = self.entry_prices.get(symbol, price)
                trailing_stop = self.trailing_stop_prices.get(symbol, None)
                gain = price - entry_price

                # Ajustement des trailing stops après un gain significatif (> 5x ATR)
                if gain > 5 * atr and trailing_stop is not None:
                    new_trailing_stop = price - (1.5 * atr)
                    # Ajuster seulement si le mouvement est significatif (0.5% du prix)
                    if abs(new_trailing_stop - trailing_stop) > (0.005 * price):
                        self.trailing_stop_prices[symbol] = new_trailing_stop
                        self.Debug(f"Trailing Stop ajusté pour {symbol} à {self.trailing_stop_prices[symbol]:.2f}")

                # Liquidation si trailing stop atteint ou critères baissiers remplis
                if trailing_stop and price < trailing_stop:
                    self.Liquidate(symbol)
                    self.Debug(f"Vente : {symbol} liquidé à {price:.2f} - Trailing Stop atteint")
                elif ema_fast < ema_slow or rsi > 85:
                    self.Liquidate(symbol)
                    self.Debug(f"Vente : {symbol} à {price:.2f} - Critères de sortie détectés")

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            # Calculer les frais sur les ordres exécutés
            fee = abs(orderEvent.FillQuantity) * orderEvent.FillPrice * 0.001  # 0.1% de frais Binance
            self.total_fees += fee
            self.Debug(f"Frais appliqués pour une transaction : {fee:.2f}")

    def OnEndOfAlgorithm(self):
        # Résumé final des performances et des frais
        net_profit = self.Portfolio.TotalPortfolioValue - self.starting_portfolio_value
        self.Debug(f"Performance finale : {self.Portfolio.TotalPortfolioValue:.2f}")
        self.Debug(f"Net Profit : {net_profit:.2f}")
        self.Debug(f"Total des frais : {self.total_fees:.2f}")
