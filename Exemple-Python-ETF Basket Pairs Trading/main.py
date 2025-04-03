# region imports
from AlgorithmImports import *
from universe import SectorETFUniverseSelectionModel
from portfolio import CointegratedVectorPortfolioConstructionModel
from risk import TrailingStopRiskManagementModel
from alpha import FilteredPairsAlphaModel
# endregion

class ETFPairsTrading(QCAlgorithm):

    def Initialize(self):
        # CONFIG GÉNÉRALE
        self.SetStartDate(2020, 1, 1)   # on commence plus tôt
        self.SetEndDate(2024, 3, 1)
        self.SetCash(1000000)
        # Paramètre unique pour la résolution
        self.resolution = Resolution.Hour  # ou Resolution.Daily, etc.
        # ACTIVER LE "FILL FORWARD" POUR LES DONNÉES
        self.Settings.FillForwardDataEnabled = True
        # Définition d'un benchmark
        self.SetBenchmark("SPY")

        

        # CHOIX DE LA RÉSOLUTION => Hourly
        self.UniverseSettings.Resolution = self.resolution
        # Optionnel : Adjusted pour splits/dividendes
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Adjusted

        # PARAMÈTRES
        lookback_param = self.GetParameter("lookback") or "20"
        threshold_param = self.GetParameter("threshold") or "2.2"
        self.lookback = int(lookback_param)
        self.zscore_threshold = float(threshold_param)

        # BROKERAGE & MARGIN
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetSecurityInitializer(lambda s: s.SetMarginModel(PatternDayTradingMarginModel()))

        # UNIVERSE
        self.SetUniverseSelection(SectorETFUniverseSelectionModel(self.UniverseSettings))

        # ALPHA
        # On utilise FilteredPairsAlphaModel : lookback=20, threshold=2.0, etc.
        self.filteredAlpha = FilteredPairsAlphaModel(
            lookback=self.lookback,
            resolution=self.resolution,
            threshold=self.zscore_threshold,
            pairs=[],
            cooldown_days=2  # plus court
        )
        self.AddAlpha(self.filteredAlpha)

        # PORTFOLIO CONSTRUCTION
        self.pcm = CointegratedVectorPortfolioConstructionModel(
            algorithm=self,
            lookback=120,            # plus long que l'alpha
            resolution=self.resolution,
            rebalance=Expiry.EndOfWeek,
            max_position_size=0.20
        )
        # Désactive le rebalance auto sur changement de l'univers
        self.pcm.rebalance_portfolio_on_security_changes = False
        self.SetPortfolioConstruction(self.pcm)

        # RISK MANAGEMENT
        # On passe le trailing stop à 8% pour plus de marge en Hourly
        self.AddRiskManagement(TrailingStopRiskManagementModel(stop_loss_percentage=0.08))

        # WARM UP => 14 jours en Hourly
        self.SetWarmUp(14, self.resolution)

        # Planifier un log chaque vendredi juste après la clôture
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.AfterMarketClose("USA", 0),
            Action(self.WeeklySummaryLog)
        )

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        # Gérer splits et dividendes
        if slice.Splits or slice.Dividends:
            self.pcm.handle_corporate_actions(self, slice)

        # Ex. rebalancing manuel
        # self.RebalancePairs()

    def RebalancePairs(self):
        """
        (Option B) Découverte manuelle de paires + ajout forcé des symboles
        """
        symbols = [s.Symbol for s in self.ActiveSecurities.Values]
        if len(symbols) < 2:
            self.Log("Not enough active securities for pair analysis.")
            return

        # 500 barres Hourly => ~ 3-4 semaines
        history = self.History(symbols, 500, self.resolution)
        if history.empty:
            self.Log("No historical data available for these symbols.")
            return

        prices = history.close.unstack(level=0)
        results = []
        from itertools import combinations
        from arch.unitroot.cointegration import engle_granger

        for etf1, etf2 in combinations(symbols, 2):
            etf1_prices = prices[etf1].dropna()
            etf2_prices = prices[etf2].dropna()
            if len(etf1_prices) == len(etf2_prices) and len(etf1_prices) > 50:
                model = engle_granger(etf1_prices, etf2_prices, trend="n", lags=0)
                corr = etf1_prices.corr(etf2_prices)
                vol = etf1_prices.std() + etf2_prices.std()
                # On desserre => pvalue < 0.1 et corr > 0.6
                if model.pvalue < 0.1 and corr > 0.6 and vol > 0.01:
                    results.append((etf1, etf2, model.pvalue, corr, vol))

        if not results:
            self.Log("No valid cointegrated pairs found.")
            return

        # Trier par corr * vol, puis pvalue
        results.sort(key=lambda x: (-x[3] * x[4], x[2]))
        top_pairs = [(etf1, etf2) for etf1, etf2, _, _, _ in results[:3]]

        # Ajout forcé en Hourly
        for etf1, etf2 in top_pairs:
            if etf1 not in self.Securities:
                self.Log(f"Forcing AddEquity for {etf1.Value}")
                self.AddEquity(etf1.Value, self.resolution)
            if etf2 not in self.Securities:
                self.Log(f"Forcing AddEquity for {etf2.Value}")
                self.AddEquity(etf2.Value, self.resolution)

        self.filteredAlpha.update_pairs(top_pairs)
        self.Log(f"Top pairs discovered and forced add: {[f'{etf1.Value}-{etf2.Value}' for etf1, etf2 in top_pairs]}")

    def WeeklySummaryLog(self):
        equity = self.Portfolio.TotalPortfolioValue
        invested_symbols = [kvp.Key.Value for kvp in self.Portfolio if kvp.Value.Invested]
        self.Log(f"[Weekly Summary] {self.Time} | Equity: {equity:0.2f} | Invested: {invested_symbols}")
