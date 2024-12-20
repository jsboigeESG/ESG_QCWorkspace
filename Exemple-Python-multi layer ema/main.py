from AlgorithmImports import *

class TechnicalIndicatorsAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Définir les paramètres de base pour le backtest
        self.SetStartDate(2020, 1, 1)  # Début du backtest
        self.SetEndDate(2024, 12, 1)    # Fin du backtest
        self.SetCash(100000)           # Montant initial du portefeuille
        
        # Ajouter les paires de cryptomonnaies avec une résolution horaire
        self.symbols = [
            self.AddCrypto("BTCUSD", Resolution.HOUR).Symbol,
            self.AddCrypto("ETHUSD", Resolution.HOUR).Symbol,
            self.AddCrypto("LTCUSD", Resolution.HOUR).Symbol,
            # self.AddCrypto("XRPUSD", Resolution.HOUR).Symbol
        ]

        self.set_benchmark(self.symbols[0])

        # Paramètre optimisable pour le dénominateur de l'allocation
        self.allocation_denominator = self.GetParameter("allocation_denominator", 1)  # Par défaut, équirépartition entre les symboles
        
        
        # Dictionnaire pour stocker les indicateurs pour chaque actif
        self.indicators = {}
        
        for symbol in self.symbols:
            # Associer les indicateurs techniques et les niveaux de prix à chaque actif
            self.indicators[symbol] = {
                # Modèles de chandeliers japonais
                "hammer": self.CandlestickPatterns.Hammer(symbol),
                "hanging_man": self.CandlestickPatterns.HangingMan(symbol),
                "doji": self.CandlestickPatterns.Doji(symbol),
                "spinning_top": self.CandlestickPatterns.SpinningTop(symbol),
                "engulfing": self.CandlestickPatterns.Engulfing(symbol),
                
                # Indicateurs techniques
                "rsi": self.RSI(symbol, 14, MovingAverageType.Wilders, Resolution.HOUR),
                "ema10": self.EMA(symbol, 10, Resolution.HOUR),
                "ema20": self.EMA(symbol, 20, Resolution.HOUR),
                "ema65": self.EMA(symbol, 65, Resolution.HOUR),
                "ema150": self.EMA(symbol, 150, Resolution.HOUR),
                
                # Niveaux de prix pour suivi
                "entry_price": None,
                "stop_price": None
            }
    
    def OnData(self, data):
        for symbol in self.symbols:
            # Vérifier si des données sont disponibles pour l'actif
            if not data.ContainsKey(symbol):
                continue
            
            price = data[symbol].Close  # Prix de clôture actuel
            indicators = self.indicators[symbol]  # Indicateurs associés à l'actif

            # Condition d'achat
            if (indicators["rsi"].Current.Value > 40 and
                indicators["ema10"].Current.Value > indicators["ema20"].Current.Value > indicators["ema65"].Current.Value > indicators["ema150"].Current.Value):
                if not self.Portfolio[symbol].Invested:
                    # Calculer le montant à investir en fonction du dénominateur
                    allocation_fraction = 1 / self.allocation_denominator
                    required_cash = allocation_fraction * self.Portfolio.TotalPortfolioValue 
                    usd_balance = self.Portfolio.CashBook["USD"].Amount
                    # Vérifier si suffisamment d'USD sont disponibles
                    if usd_balance >= required_cash * 0.99:
                        self.SetHoldings(symbol, allocation_fraction)  # Investir selon la fraction
                        indicators["entry_price"] = price
                        indicators["stop_price"] = price * 0.90  # Stop-loss initial à 90% du prix d'achat
                        self.Debug(f"Buy signal triggered for {symbol}. Entry price: {price}")
                    # else:
                    #     self.Debug(f"Insufficient funds to buy {symbol}. Required: {required_cash}, Available: {self.Portfolio.Cash}")

            # Condition de vente
            elif (indicators["rsi"].Current.Value < 50 and
                  (indicators["ema10"].Current.Value < indicators["ema65"].Current.Value or
                   indicators["ema20"].Current.Value < indicators["ema65"].Current.Value)):
                if self.Portfolio[symbol].Invested:
                    self.Liquidate(symbol)  # Vendre toutes les positions pour cet actif
                    indicators["entry_price"] = None
                    indicators["stop_price"] = None
                    self.Debug(f"Sell signal triggered for {symbol}.")

            # (Optionnel) Stop-loss dynamique et objectifs de gains
            if self.Portfolio[symbol].Invested:
                # Mettre à jour le stop-loss pour qu'il suive les prix à la hausse
                indicators["stop_price"] = max(indicators["stop_price"], price * 0.90)
                if price < indicators["stop_price"]:
                    self.Liquidate(symbol)
                    indicators["stop_price"] = None
                    self.Debug(f"Stop-loss triggered for {symbol}.")
                elif price > indicators["entry_price"] * 1.15:  # Exemple de cible de profit à 15%
                    self.Liquidate(symbol)
                    indicators["entry_price"] = None
                    indicators["stop_price"] = None
                    self.Debug(f"Target profit reached for {symbol}.")
