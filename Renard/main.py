from AlgorithmImports import *

class BtcEmaCrossDaily1Algorithm(QCAlgorithm):
    """
    Algorithme amélioré pour BTCUSDT, avec croisements EMA, RSI, gestion des risques, Stop-Loss et Take-Profit.
    """
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2024, 11, 27)
        self.SetAccountCurrency("USDT")
        self.SetCash(600000)
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)

        # Ajout de l'actif BTCUSDT
        self._btcUsdSymbol = self.AddCrypto("BTCUSDT", Resolution.Daily, Market.Binance).Symbol

        # Indicateurs EMA
        self.FastPeriod = 10
        self.SlowPeriod = 30
        self._fastEma = self.EMA(self._btcUsdSymbol, self.FastPeriod, Resolution.Daily)
        self._slowEma = self.EMA(self._btcUsdSymbol, self.SlowPeriod, Resolution.Daily)

        # RSI pour filtrer les signaux
        self.rsi = self.RSI(self._btcUsdSymbol, 14, MovingAverageType.Simple, Resolution.Daily)

        # ATR pour vérifier la volatilité
        self.atr = self.ATR(self._btcUsdSymbol, 14, Resolution.Daily)

        # Période de chauffe
        self.SetWarmUp(timedelta(days=max(self.FastPeriod, self.SlowPeriod)))

        # Marges et niveaux de RSI
        self.buy_margin = 1.002
        self.sell_margin = 0.998
        self.rsi_upper = 70
        self.rsi_lower = 30

        # Initialisation des graphiques
        self.InitializeCharts()

    def OnData(self, data):
        if self.IsWarmingUp or self._btcUsdSymbol not in data:
            return

        # Récupération des indicateurs
        fastEmaValue = self._fastEma.Current.Value
        slowEmaValue = self._slowEma.Current.Value
        price = self.Securities[self._btcUsdSymbol].Price
        rsiValue = self.rsi.Current.Value
        atr_value = self.atr.Current.Value

        self.Debug(f"[LOG] RSI: {rsiValue}, FAST EMA: {fastEmaValue}, SLOW EMA: {slowEmaValue}, ATR: {atr_value}, PRICE: {price}")

        # Conditions d'achat
        if not self.Portfolio.Invested and fastEmaValue > slowEmaValue * self.buy_margin \
                and self.rsi_lower < rsiValue < self.rsi_upper and atr_value > 200:
            allocation = 1 #0.5 if rsiValue < 50 else 0.3  # Dynamique
            self.SetHoldings(self._btcUsdSymbol, allocation)
            self.Debug(f"[ACHAT] Prix {price}, RSI: {rsiValue}")

        # Conditions de vente
        elif self.Portfolio.Invested and (fastEmaValue < slowEmaValue * self.sell_margin or rsiValue < self.rsi_lower):
            self.Liquidate(self._btcUsdSymbol)
            self.Debug(f"[VENTE] Prix {price}, RSI: {rsiValue}")

    def InitializeCharts(self):
        chart = Chart("Performance")
        chart.AddSeries(Series("Price", SeriesType.Line, "$", Color.Blue))
        self.AddChart(chart)
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(0, 0),
                         self.DoPlots)

    def DoPlots(self):
        if self._btcUsdSymbol not in self.Securities or not self.Securities[self._btcUsdSymbol].HasData:
            return
        price = self.Securities[self._btcUsdSymbol].Price
        self.Plot("Performance", "Price", price)
