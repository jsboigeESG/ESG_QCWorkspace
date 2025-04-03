from AlgorithmImports import *

class OptimizedSwingTradingCryptoAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Paramètres de l'algorithme
        self.SetStartDate(2019, 1, 1)    # Date de début pour le backtesting
        self.SetEndDate(2024, 12, 31)   # Date de fin pour le backtesting
        self.SetCash(5000000)           # Capital initial
        
        # Définir le modèle de courtage Binance
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        
        # Ajout des cryptos pour le trading
        self.symbols = [
            self.AddCrypto("BTCUSD", Resolution.Daily, Market.Binance).Symbol,
            self.AddCrypto("ETHUSD", Resolution.Daily, Market.Binance).Symbol,
            self.AddCrypto("LTCUSD", Resolution.Daily, Market.Binance).Symbol  # Ajout de Litecoin pour diversification
        ]
        
        # Paramètres optimisables
        self.sma_fast_period = self.GetParameter("sma_fast_period") or 20
        self.sma_slow_period = self.GetParameter("sma_slow_period") or 50
        self.rsi_period = self.GetParameter("rsi_period") or 14
        self.trailing_stop_multiplier = float(self.GetParameter("trailing_stop_multiplier") or 2.0)
        
        # Indicateurs pour chaque crypto
        self.indicators = {}
        for symbol in self.symbols:
            self.indicators[symbol] = {
                "sma_fast": self.SMA(symbol, self.sma_fast_period, Resolution.Daily),
                "sma_slow": self.SMA(symbol, self.sma_slow_period, Resolution.Daily),
                "rsi": self.RSI(symbol, self.rsi_period, MovingAverageType.Wilders, Resolution.Daily),
                "bollinger": self.BB(symbol, 20, 2, MovingAverageType.Simple, Resolution.Daily),
                "macd": self.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily),
                "atr": self.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily),
                "obv": self.OBV(symbol, Resolution.Daily)
            }
        
        # Gestion des risques
        self.max_risk_per_trade = 0.01  # 1% du portefeuille par trade
        self.trailing_stop_prices = {}
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue
        self.daily_returns = []
        self.total_fees = 0
    
    def OnData(self, data):
        for symbol in self.symbols:
            if not data.Bars.ContainsKey(symbol):
                continue
            
            price = data[symbol].Close
            indicators = self.indicators[symbol]
            
            # Vérifiez que tous les indicateurs sont prêts
            if not (indicators["sma_fast"].IsReady and indicators["sma_slow"].IsReady 
                    and indicators["rsi"].IsReady and indicators["bollinger"].IsReady 
                    and indicators["macd"].IsReady and indicators["atr"].IsReady):
                continue
            
            # Récupération des valeurs des indicateurs
            sma_fast = indicators["sma_fast"].Current.Value
            sma_slow = indicators["sma_slow"].Current.Value
            rsi = indicators["rsi"].Current.Value
            bollinger = indicators["bollinger"]
            middle_band = bollinger.MiddleBand.Current.Value
            upper_band = bollinger.UpperBand.Current.Value
            lower_band = bollinger.LowerBand.Current.Value
            macd = indicators["macd"].Current.Value
            signal = indicators["macd"].Signal.Current.Value
            atr = indicators["atr"].Current.Value
            obv = indicators["obv"].Current.Value
            invested = self.Portfolio[symbol].Invested
            
            # Conditions d'achat avec confirmation
            if sma_fast > sma_slow and rsi < 70 and macd > signal and price > middle_band and obv > 0:
                if not invested:
                    # Calcul de la taille de la position basée sur le risque
                    risk_per_share = atr * self.trailing_stop_multiplier
                    allocation = self.Portfolio.TotalPortfolioValue * self.max_risk_per_trade
                    quantity = int(allocation / (risk_per_share * (1 + self.Portfolio[symbol].FeeModel.GetOrderFee(OrderFeeParameters(self, data[symbol])))))
                    self.SetHoldings(symbol, quantity * price / self.Portfolio.TotalPortfolioValue)
                    # Ajouter un trailing stop loss
                    self.trailing_stop_prices[symbol] = price - (atr * self.trailing_stop_multiplier)
            
            # Conditions de vente ou trailing stop
            if invested:
                current_stop_price = self.trailing_stop_prices.get(symbol, None)
                if current_stop_price and price < current_stop_price:
                    self.Liquidate(symbol)
                elif sma_fast < sma_slow or rsi > 70 or price < lower_band:
                    self.Liquidate(symbol)
    
    def OnEndOfAlgorithm(self):
        # Calcul des métriques de performance
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
    
    def OnOrderEvent(self, orderEvent):
        # Enregistrer les frais
        if orderEvent.Status == OrderStatus.Filled:
            fee = abs(orderEvent.FillQuantity) * orderEvent.FillPrice * self.Portfolio[orderEvent.Symbol].FeeModel.GetOrderFee(OrderFeeParameters(self, orderEvent))
            self.total_fees += fee
            self.Debug(f"Frais appliqués: {fee:.2f}")
    
    def OnEndOfDay(self):
        # Calculer les rendements quotidiens
        daily_return = (self.Portfolio.TotalPortfolioValue - self.starting_portfolio_value) / self.starting_portfolio_value
        self.daily_returns.append(daily_return)
        self.starting_portfolio_value = self.Portfolio.TotalPortfolioValue
