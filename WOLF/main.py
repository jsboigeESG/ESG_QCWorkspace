from AlgorithmImports import *

class RiskAverseMomentumStrategy(QCAlgorithm):
    def Initialize(self):
        # Paramètres backtest
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2024, 12, 1)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        # Universe crypto
        self.cryptoSymbols = ["BTCUSDT", "ETHUSDT", "LTCUSDT"]
        self.symbols = []
        for ticker in self.cryptoSymbols:
            symbolObj = self.AddCrypto(ticker, Resolution.Hour)
            self.symbols.append(symbolObj.Symbol)
        
        # Benchmark
        self.SetBenchmark("BTCUSDT")

        # BTC en daily pour filtre macro (EMA et RSI)
        self.btcDaily = self.AddCrypto("BTCUSDT", Resolution.Daily).Symbol
        self.dailyEma200 = self.EMA(self.btcDaily, 200, Resolution.Daily)
        self.dailyRsiBtc = self.RSI(self.btcDaily, 14, MovingAverageType.Wilders, Resolution.Daily)
        self.SetWarmUp(200, Resolution.Daily)
        
        # Indicateurs sur chaque actif (Hourly)
        # On rajoute un petit "rateOfChange" daily pour scoring
        self.indicators = {}
        for sym in self.symbols:
            rsi = self.RSI(sym, 14, MovingAverageType.Wilders, Resolution.Hour)
            atr = self.ATR(sym, 14, MovingAverageType.Wilders, Resolution.Hour)
            macd = self.MACD(sym, 12, 26, 9, MovingAverageType.Wilders, Resolution.Hour)
            boll = self.BB(sym, 20, 2, MovingAverageType.Wilders, Resolution.Hour)
            
            # Indicateur "momentum" daily, par exemple un RateOfChange(14)
            # Note: On peut faire plus sophistiqué (regression slope, etc.)
            dailySymbol = self.AddCrypto(sym.Value, Resolution.Daily).Symbol
            rocDaily = self.ROC(dailySymbol, 14, Resolution.Daily)

            self.indicators[sym] = {
                "rsi": rsi,
                "atr": atr,
                "macd": macd,
                "bollinger": boll,
                "rocDaily": rocDaily,
                "stop_price": None,
                "max_price": None,
                "entry_price": None,
                "partial_exit_done": False
            }
        
        # Paramètres gestion risque
        self.riskPerc = 0.01               # 1% du capital risqué par trade
        self.trailingMultiplier = 1.5      # Trailing stop plus serré
        self.minHoldingPeriod = 48         # En heures
        self.maxPortfolioDD = -0.25        # Stop global à -25%
        
        # Prise de profit partielle plus rapide
        self.partialExitAtrMultiple = 2.0
        self.partialExitFraction = 0.5
        
        # Limitation de positions simultanées
        self.maxConcurrentPositions = 2
        
        # Tracking du moment d'ouverture
        self.positionsOpened = {}

        # Équity initiale pour calcul du drawdown
        self.initialPortfolioValue = self.Portfolio.TotalPortfolioValue

    def OnData(self, data):
        if self.IsWarmingUp:
            return
        
        # Vérification drawdown global
        if (self.Portfolio.TotalPortfolioValue / self.initialPortfolioValue - 1) < self.maxPortfolioDD:
            self.Liquidate()
            return
        
        # Filtre marché global sur BTC Daily : EMA200 + RSI(14) > 55
        btcDailyPrice = self.Securities[self.btcDaily].Close
        isBullMarket = btcDailyPrice > self.dailyEma200.Current.Value
        if not isBullMarket or self.dailyRsiBtc.Current.Value < 55:
            # Sort en cas de marché baissier
            for sym in self.symbols:
                if self.Portfolio[sym].Invested:
                    self.Liquidate(sym)
                    self.resetPositionData(sym)
            return
        
        # --- SÉLECTION DES MEILLEURES OPPORTUNITÉS ---
        # On calcule un score de momentum daily (rocDaily)
        # On prendra les 2 cryptos avec le meilleur ROC daily > 0
        scoring = []
        for sym in self.symbols:
            if self.indicators[sym]["rocDaily"].IsReady:
                score = self.indicators[sym]["rocDaily"].Current.Value
                scoring.append((sym, score))
        
        # On filtre cryptos avec un ROC>0 (momentum positif) puis on range par score décroissant
        scoringPositive = [(sym, sc) for (sym, sc) in scoring if sc > 0]
        scoringPositive.sort(key=lambda x: x[1], reverse=True)
        
        # On ne garde que les N=2 meilleurs
        bestSymbols = [x[0] for x in scoringPositive[:self.maxConcurrentPositions]]
        
        # --- PRISE DE POSITION SI SIGNAL ---
        # On ne prend des positions que sur ces "bestSymbols"
        currentOpenPositions = sum(1 for sym in self.symbols if self.Portfolio[sym].Invested)
        
        for sym in bestSymbols:
            # Si on a déjà un certain nombre de positions ouvertes, on vérifie qu'on peut en ajouter
            if currentOpenPositions >= self.maxConcurrentPositions:
                break
            
            # Vérif si data dispo
            if not data.ContainsKey(sym):
                continue
            
            ind = self.indicators[sym]
            if not all([ind["rsi"].IsReady, ind["macd"].IsReady, ind["bollinger"].IsReady, ind["atr"].IsReady]):
                continue
            
            price = self.Securities[sym].Price
            macd_hist = ind["macd"].Current.Value - ind["macd"].Signal.Current.Value
            
            # Condition d'entrée (un peu plus stricte)
            # RSI>50, MACD haussier, prix au-dessus Bollinger sup.
            if (ind["rsi"].Current.Value > 50 and
                macd_hist > 0 and
                price > ind["bollinger"].UpperBand.Current.Value):
                
                # Sauf si déjà investi
                if not self.Portfolio[sym].Invested:
                    # Position sizing plus défensif
                    atr_val = ind["atr"].Current.Value
                    stop_dist = self.trailingMultiplier * atr_val
                    capital = self.Portfolio.TotalPortfolioValue
                    capital_risk = capital * self.riskPerc
                    
                    quantity = capital_risk / stop_dist
                    ratio = (quantity * price) / capital
                    self.SetHoldings(sym, ratio)
                    
                    # Initialiser les valeurs de suivi
                    ind["stop_price"] = price - stop_dist
                    ind["max_price"] = price
                    ind["entry_price"] = price
                    ind["partial_exit_done"] = False
                    self.positionsOpened[sym] = self.Time
                    currentOpenPositions += 1
        
        # --- GESTION DES POSITIONS EXISTANTES (Stops + Sortie partielle) ---
        for sym in self.symbols:
            if self.Portfolio[sym].Invested and data.ContainsKey(sym):
                ind = self.indicators[sym]
                price = data[sym].Close
                
                # Met à jour le plus haut
                if ind["max_price"] is None or price > ind["max_price"]:
                    ind["max_price"] = price
                
                # Trailing stop dynamique
                atr_val = ind["atr"].Current.Value
                new_stop = ind["max_price"] - self.trailingMultiplier * atr_val
                if new_stop > ind["stop_price"]:
                    ind["stop_price"] = new_stop
                
                # Durée de détention (heures)
                holding_hours = (self.Time - self.positionsOpened[sym]).total_seconds() / 3600
                
                # Sortie partielle si on atteint +2 ATR
                if not ind["partial_exit_done"]:
                    if price >= ind["entry_price"] + self.partialExitAtrMultiple * atr_val:
                        halfQty = 0.5 * self.Portfolio[sym].Quantity
                        self.MarketOrder(sym, -halfQty)
                        ind["partial_exit_done"] = True
                
                # Stop standard (si on a dépassé la période min)
                if holding_hours >= self.minHoldingPeriod:
                    if price < ind["stop_price"]:
                        self.Liquidate(sym)
                        self.resetPositionData(sym)

    def resetPositionData(self, sym):
        """ Nettoie les variables quand on sort d'une position. """
        ind = self.indicators[sym]
        ind["stop_price"] = None
        ind["max_price"] = None
        ind["entry_price"] = None
        ind["partial_exit_done"] = False
        if sym in self.positionsOpened:
            del self.positionsOpened[sym]
