# region imports
from datetime import datetime
from AlgorithmImports import *
from alpha import custom_alpha

# endregion


class CompetitionAlgorithm(QCAlgorithm):
    
    def Initialize(self):

        # Backtest parameters
        self.SetStartDate(2020, 6, 18)
        self.SetEndDate(2020, 9, 18)
        self.SetCash(1000000)
        self.SetWarmUp(10)

        # Parameters: 
        self.final_universe_size = 600

        # Universe selection
        self.rebalanceTime = self.time
        self.universe_type = "equity"

        if self.universe_type == "equity":
            self.AddUniverse(self.CoarseFilter, self.FineFilter)

        self.UniverseSettings.Resolution = Resolution.Hour

        self.set_portfolio_construction(self.MyPCM())
        self.set_alpha(custom_alpha(self))
        self.set_execution(VolumeWeightedAveragePriceExecutionModel())
        self.add_risk_management(NullRiskManagementModel())
 
        # set account type
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        
    def CoarseFilter(self, coarse):
        # Rebalancing monthly
        if self.Time <= self.rebalanceTime:
            return self.Universe.Unchanged
        self.rebalanceTime = self.Time + timedelta(days=300)
        
        sortedByDollarVolume = sorted(coarse, key=lambda x: x.DollarVolume, reverse=True)
        return [x.Symbol for x in sortedByDollarVolume if x.HasFundamentalData][:1000]
    
    def FineFilter(self, fine):
        sortedbyVolume = sorted(fine, key=lambda x: x.DollarVolume, reverse=True ) 
        fine_output = [x.Symbol for x in sortedbyVolume if x.price > 10 and x.MarketCap > 2000000000][:self.final_universe_size]
        return fine_output
    
    class MyPCM(InsightWeightingPortfolioConstructionModel): 
        # override to set leverage higher
        def CreateTargets(self, algorithm, insights): 
            targets = super().CreateTargets(algorithm, insights) 
            return [PortfolioTarget(x.Symbol, x.Quantity * 1.85) for x in targets]
 
