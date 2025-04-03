from AlgorithmImports import *
from datetime import timedelta

class BinanceFeeModel(FeeModel):
    """Modèle de frais personnalisé pour Binance avec des frais de 0,1%."""
    def GetOrderFee(self, parameters):
        value = parameters.Security.Price * abs(parameters.Order.AbsoluteQuantity)
        fee = 0.001 * value  # 0.1% fee
        return OrderFee(CashAmount(fee, parameters.Security.QuoteCurrency.Symbol))

class OptimizedSwingTradingCryptoAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Configuration du Backtest
        self.SetStartDate(2019, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(5000000)

        # Ajout de multiples cryptomonnaies
        self.crypto_symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("SOLUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ADAUSD", Resolution.Daily, Market.GDAX).Symbol
        ]

        # Appliquer le modèle de frais Binance à chaque crypto
        for symbol in self.crypto_symbols:
            self.Securities[symbol].SetFeeModel(BinanceFeeModel())

        # Benchmarks & Indicateurs
        self.SetBenchmark("BTCUSD")
        self.indicators = {}
        self.weekly_sma = {}  # Pour stocker les SMA hebdomadaires

        for symbol in self.crypto_symbols:
            # Création des indicateurs
            self.indicators[symbol] = {
                "sma_fast": self.SMA(symbol, 20, Resolution.Daily),
                "sma_slow": self.SMA(symbol, 50, Resolution.Daily),
                "rsi": self.RSI(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "macd": self.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily),
                "atr": self.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "obv": self.OBV(symbol, Resolution.Daily)
            }

            # Configuration du SMA Hebdomadaire via un TradeBarConsolidator
            consolidator = TradeBarConsolidator(timedelta(days=7))
            sma_weekly = SimpleMovingAverage(50)  # SMA hebdomadaire sur 50 périodes
            self.RegisterIndicator(symbol, sma_weekly, consolidator)
            self.SubscriptionManager.AddConsolidator(symbol, consolidator)

            # Sauvegarde de l'indicateur
            self.weekly_sma[symbol] = sma_weekly

        # Paramètres dynamiques
        self.trailing_stop_multiplier = 2.0
        self.max_risk_per_trade = 0.015  # Augmenté légèrement (1.5%) pour profiter des tendances haussières.
        self.trailing_stop_prices = {}
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue
        self.daily_returns = []
        self.total_fees = 0

    def MarketBullish(self, symbol):
        """Détermine si le marché est dans une tendance haussière."""
        if not self.weekly_sma[symbol].IsReady:
            return False
        return self.Securities[symbol].Price > self.weekly_sma[symbol].Current.Value

    def OnData(self, data):
        for symbol in self.crypto_symbols:
            # Vérifiez que les données sont disponibles
            if not data.Bars.ContainsKey(symbol):
                continue

            price = data[symbol].Close
            indicators = self.indicators[symbol]

            # Vérifiez que tous les indicateurs sont prêts
            if not (indicators["sma_fast"].IsReady and indicators["sma_slow"].IsReady and indicators["rsi"].IsReady 
                    and indicators["macd"].IsReady and indicators["atr"].IsReady and self.weekly_sma[symbol].IsReady):
                continue

            # Récupération des valeurs des indicateurs
            sma_fast = indicators["sma_fast"].Current.Value
            sma_slow = indicators["sma_slow"].Current.Value
            rsi = indicators["rsi"].Current.Value
            macd = indicators["macd"].Current.Value
            macd_signal = indicators["macd"].Signal.Current.Value
            atr = indicators["atr"].Current.Value
            obv = indicators["obv"].Current.Value
            invested = self.Portfolio[symbol].Invested

            # Filtre du marché haussier
            if not self.MarketBullish(symbol):
                continue  # Ignorez les trades dans les marchés baissiers.

            # Conditions d'achat
            if sma_fast > sma_slow and macd > macd_signal and rsi < 80 and obv > 0:
                if not invested:
                    # Taille de position basée sur le risque
                    risk_per_share = atr * self.trailing_stop_multiplier
                    allocation = self.Portfolio.TotalPortfolioValue * self.max_risk_per_trade
                    quantity = int(allocation / (risk_per_share * (1 + 0.001)))  # Inclut les frais de Binance
                    self.SetHoldings(symbol, quantity * price / self.Portfolio.TotalPortfolioValue)
                    self.trailing_stop_prices[symbol] = price - (atr * self.trailing_stop_multiplier)

            # Conditions de vente
            if invested:
                current_stop_price = self.trailing_stop_prices.get(symbol, None)
                if current_stop_price and price < current_stop_price:
                    self.Liquidate(symbol)  # Trailing stop atteint
                elif sma_fast < sma_slow or rsi > 85:  # Conditions de sortie
                    self.Liquidate(symbol)

    def OnOrderEvent(self, orderEvent):
        # Suivi des frais appliqués
        if orderEvent.Status == OrderStatus.Filled:
            fee = abs(orderEvent.FillQuantity) * orderEvent.FillPrice * 0.001  # Frais Binance : 0,1%
            self.total_fees += fee
            self.Debug(f"Frais appliqués: {fee:.2f}")

    def OnEndOfDay(self):
        # Calculez les rendements quotidiens
        daily_return = (self.Portfolio.TotalPortfolioValue - self.starting_portfolio_value) / self.starting_portfolio_value
        self.daily_returns.append(daily_return)
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue

    def OnEndOfAlgorithm(self):
        # Analyse de la performance finale
        portfolio_returns = self.Portfolio.TotalPortfolioValue / self.starting_portfolio_value - 1

        # Calcul du ratio de Sharpe
        if len(self.daily_returns) > 1:
            average_return = sum(self.daily_returns) / len(self.daily_returns)
            std_dev = (sum([(r - average_return) ** 2 for r in self.daily_returns]) / (len(self.daily_returns) - 1)) ** 0.5
            sharpe_ratio = (average_return / std_dev) * (252 ** 0.5) if std_dev != 0 else 0
        else:
            sharpe_ratio = 0

        self.Debug(f"Performance du portefeuille: {portfolio_returns:.2%}")
        self.Debug(f"Sharpe Ratio: {sharpe_ratio:.2f}")
        self.Debug(f"Total des frais appliqués: {self.total_fees:.2f}")
        self.Debug("Fin du backtesting.")
