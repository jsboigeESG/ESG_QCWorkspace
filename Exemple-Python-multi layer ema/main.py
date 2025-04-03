from AlgorithmImports import *

class OptimizedCryptoAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2024, 1, 1)
        self.SetCash(100000)

        # Ajouter les cryptos
        self.symbols = [
            self.AddCrypto("BTCUSD", Resolution.HOUR).Symbol,
            self.AddCrypto("ETHUSD", Resolution.HOUR).Symbol,
            self.AddCrypto("LTCUSD", Resolution.HOUR).Symbol
        ]
        self.SetBenchmark("BTCUSD")
        self.fastPeriod = self.GetParameter("fastPeriod", 10)
        self.slowPeriod = self.GetParameter("slowPeriod", 50)

        # Indicateurs
        self.indicators = {}
        for symbol in self.symbols:
            self.indicators[symbol] = {
                "ema10": self.EMA(symbol, self.fastPeriod, Resolution.HOUR),
                "ema50": self.EMA(symbol, self.slowPeriod, Resolution.HOUR),
                "rsi": self.RSI(symbol, 14, MovingAverageType.Wilders, Resolution.HOUR),
                "bollinger": self.BB(symbol, 20, 2, MovingAverageType.Simple, Resolution.HOUR),
                "entry_price": None,
                "stop_loss": None
            }
        
        # Gestion
        self.max_positions = 3
        self.trailing_stop_pct = 0.92  # Trailing stop à 8%
        self.fixed_stop_pct = 0.85    # Stop-loss absolu à 15%
        self.take_profit_pct = 1.3   # Prise de profit à 30%

    def OnData(self, data):
        active_positions = sum(1 for symbol in self.symbols if self.Portfolio[symbol].Invested)

        for symbol in self.symbols:
            if not data.ContainsKey(symbol):
                continue
            
            price = data[symbol].Close
            indicators = self.indicators[symbol]

            # Condition d'achat
            if (active_positions < self.max_positions and
                indicators["rsi"].Current.Value > 30 and
                indicators["ema10"].Current.Value > indicators["ema50"].Current.Value):
                if not self.Portfolio[symbol].Invested:
                    allocation = 0.7 / self.max_positions  # Allocation augmentée
                    self.SetHoldings(symbol, allocation)
                    indicators["entry_price"] = price
                    indicators["stop_loss"] = price * self.fixed_stop_pct
                    self.Debug(f"Buy signal triggered for {symbol}. Entry price: {price}")

            # Gestion des positions ouvertes
            if self.Portfolio[symbol].Invested:
                # Mise à jour du trailing stop
                trailing_stop = max(indicators["stop_loss"], price * self.trailing_stop_pct)
                indicators["stop_loss"] = trailing_stop

                # Conditions de vente
                if price < trailing_stop:  # Stop-loss
                    self.Liquidate(symbol)
                    indicators["entry_price"] = None
                    indicators["stop_loss"] = None
                    self.Debug(f"Trailing stop-loss triggered for {symbol}. Liquidated at {price}.")
                elif price > indicators["entry_price"] * self.take_profit_pct:  # Prise de profit
                    self.Liquidate(symbol)
                    indicators["entry_price"] = None
                    indicators["stop_loss"] = None
                    self.Debug(f"Take profit triggered for {symbol}. Liquidated at {price}.")
