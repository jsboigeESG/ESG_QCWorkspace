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

        # Ajout des cryptos
        self.crypto_symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("SOLUSD", Resolution.Daily, Market.GDAX).Symbol,
            self.AddCrypto("ADAUSD", Resolution.Daily, Market.GDAX).Symbol
        ]

        # Appliquer le modèle de frais Binance à chaque crypto
        for symbol in self.crypto_symbols:
            self.Securities[symbol].SetFeeModel(BinanceFeeModel())

        # Indicateurs & Consolidateurs pour SMA Hebdomadaire
        self.indicators = {}
        self.weekly_sma = {}
        for symbol in self.crypto_symbols:
            self.indicators[symbol] = {
                "ema_fast": self.EMA(symbol, 15, Resolution.Daily),  # EMA rapide : 15 jours
                "ema_slow": self.EMA(symbol, 40, Resolution.Daily),  # EMA lente : 40 jours
                "rsi": self.RSI(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "macd": self.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily),
                "atr": self.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "obv": self.OBV(symbol, Resolution.Daily)
            }

            # Configuration du SMA Hebdomadaire via un TradeBarConsolidator
            consolidator = TradeBarConsolidator(timedelta(days=7))
            sma_weekly = SimpleMovingAverage(50)  # SMA hebdo sur 50 périodes
            self.RegisterIndicator(symbol, sma_weekly, consolidator)
            self.SubscriptionManager.AddConsolidator(symbol, consolidator)

            # Sauvegarde de l'indicateur
            self.weekly_sma[symbol] = sma_weekly

        # Paramètres dynamiques
        self.trailing_stop_multiplier = 2.0
        self.max_risk_per_trade = 0.015  # 1.5% maximum par position
        self.trailing_stop_prices = {}
        self.entry_prices = {}
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
            if not (indicators["ema_fast"].IsReady and indicators["ema_slow"].IsReady and indicators["rsi"].IsReady 
                    and indicators["macd"].IsReady and indicators["atr"].IsReady and self.weekly_sma[symbol].IsReady):
                continue

            # Récupération des valeurs des indicateurs
            ema_fast = indicators["ema_fast"].Current.Value
            ema_slow = indicators["ema_slow"].Current.Value
            rsi = indicators["rsi"].Current.Value
            macd = indicators["macd"].Current.Value
            macd_signal = indicators["macd"].Signal.Current.Value
            atr = indicators["atr"].Current.Value
            obv = indicators["obv"].Current.Value
            invested = self.Portfolio[symbol].Invested

            # Filtre de marché haussier basé sur le régime du marché
            if not self.MarketBullish(symbol):
                continue

            # Conditions d'achat optimisées
            if (ema_fast > ema_slow and macd > macd_signal and (macd - macd_signal > 0.01)
                and rsi < 85 and obv > 0):  # RSI plus souple, divergence MACD plus réactive
                if not invested:
                    # Taille de position basée sur le régime du marché
                    allocation = self.Portfolio.TotalPortfolioValue * (0.02 if self.MarketBullish(symbol) else self.max_risk_per_trade)
                    risk_per_share = max(atr * self.trailing_stop_multiplier, 0.02 * price)  # Minimum risk per share
                    quantity = int(allocation / (risk_per_share * (1 + 0.001)))  # Inclut les frais
                    if quantity * price < 100:
                        continue  # Ingorez les ordres trop petits
                    self.SetHoldings(symbol, quantity * price / self.Portfolio.TotalPortfolioValue)
                    self.trailing_stop_prices[symbol] = price - (atr * self.trailing_stop_multiplier)
                    self.entry_prices[symbol] = price  # Stocker le prix d'entrée

            # Conditions de vente avec trailing stop amélioré et prise de profits
            if invested:
                current_stop_price = self.trailing_stop_prices.get(symbol, None)
                entry_price = self.entry_prices.get(symbol, price)
                if current_stop_price:
                    # Ajuster le trailing stop après des gains significatifs
                    gain = price - entry_price
                    if gain > 5 * atr:  # Resserrez après 5 ATR
                        self.trailing_stop_prices[symbol] = price - (1.5 * atr)

                    # Prendre des profits après un gain significatif
                    take_profit_price = entry_price + 6 * atr
                    if price >= take_profit_price:
                        self.Liquidate(symbol)
                        self.Debug(f"Take Profit effectué pour {symbol}.")

                # Liquidation si trailing stop atteint ou si conditions de sortie
                if current_stop_price and price < current_stop_price:
                    self.Liquidate(symbol)
                elif ema_fast < ema_slow or rsi > 85:  # Critères de sortie
                    self.Liquidate(symbol)

    def OnOrderEvent(self, orderEvent):
        # Enregistrer les frais des ordres exécutés
        if orderEvent.Status == OrderStatus.Filled:
            fee = abs(orderEvent.FillQuantity) * orderEvent.FillPrice * 0.001  # Frais Binance : 0,1%
            self.total_fees += fee
            self.Debug(f"Frais appliqués: {fee:.2f}")

    def OnEndOfDay(self):
        # Calculer les rendements quotidiens
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
