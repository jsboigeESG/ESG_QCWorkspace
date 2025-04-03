from AlgorithmImports import *

class OptimizedBitcoinTradingAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration de l'algorithme
        self.SetStartDate(2020, 1, 1)  # Début du backtest
        self.SetEndDate(2022, 1, 1)    # Fin du backtest
        self.SetCash(30000)            # Capital initial

        # Ajout du symbole BTCUSD (Bitcoin en USD)
        self.symbol = self.AddCrypto("BTCUSD", Resolution.Hour).Symbol

        # Moyennes mobiles pour les signaux de trading
        self.fast_ma = self.EMA(self.symbol, 10, Resolution.Hour)  # Rapide (10 périodes)
        self.slow_ma = self.EMA(self.symbol, 50, Resolution.Hour)  # Lente (50 périodes)
        self.trend_ma = self.EMA(self.symbol, 200, Resolution.Hour)  # Long-terme (200 périodes)

        # Indicateurs additionnels
        self.atr = self.ATR(self.symbol, 14, MovingAverageType.Simple, Resolution.Hour)  # Volatilité (ATR)
        self.rsi = self.RSI(self.symbol, 14, MovingAverageType.Simple, Resolution.Hour)  # Confirmation (RSI)

        # Gestion des positions
        self.invested = False
        self.trailing_stop_price = None
        self.last_trade_time = None  # Délai entre deux trades
        self.cool_down_period = timedelta(hours=6)  # Période de cool-down (6 heures)

    def OnData(self, data):
        # Vérification que tous les indicateurs sont prêts
        if not (self.fast_ma.IsReady and self.slow_ma.IsReady and self.trend_ma.IsReady and self.atr.IsReady and self.rsi.IsReady):
            return

        # Récupération des valeurs des indicateurs
        fast_value = self.fast_ma.Current.Value
        slow_value = self.slow_ma.Current.Value
        trend_value = self.trend_ma.Current.Value
        rsi_value = self.rsi.Current.Value
        price = self.Securities[self.symbol].Price
        atr_value = self.atr.Current.Value

        # Vérifier le cool-down
        if self.last_trade_time and self.Time - self.last_trade_time < self.cool_down_period:
            return

        # Condition : Long uniquement si le prix est au-dessus de la tendance à long terme
        if price > trend_value:
            # Signal d'achat : Croisement haussier des moyennes mobiles avec confirmation RSI
            if fast_value > slow_value and rsi_value > 55 and not self.invested:
                self.SetHoldings(self.symbol, 1)  # Investir 100% du capital
                self.invested = True
                self.last_trade_time = self.Time

                # Calcul du Stop-Loss dynamique et initialisation du Trailing Stop
                self.trailing_stop_price = price - 2 * atr_value  # Stop-Loss à 2x l'ATR
                self.Debug(f"Achat BTCUSD à {price}, Trailing Stop initial: {self.trailing_stop_price}")

        # Vérification pour la gestion des positions ouvertes
        elif self.invested:
            # Mise à jour du Trailing Stop uniquement si nécessaire
            self.trailing_stop_price = max(self.trailing_stop_price, price - 2 * atr_value)

            # Conditions de liquidation
            if price <= self.trailing_stop_price:
                self.Liquidate(self.symbol)
                self.invested = False
                self.Debug(f"Position fermée BTCUSD à {price} (Trailing Stop atteint)")

            # Signal de vente : Croisement baissier des moyennes mobiles
            elif fast_value < slow_value and rsi_value < 45:
                self.Liquidate(self.symbol)
                self.invested = False
                self.Debug(f"Vente BTCUSD à {price} (Signal baissier)")

        # Condition : Si le prix tombe sous la tendance à long terme, liquider toute position
        elif price < trend_value and self.invested:
            self.Liquidate(self.symbol)
            self.invested = False
            self.Debug(f"Vente forcée BTCUSD à {price} (Prix sous la tendance à long terme)")

