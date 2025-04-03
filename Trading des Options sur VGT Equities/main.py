# region imports
from AlgorithmImports import *
import math

class GainStrategy(QCAlgorithm):
    def Initialize(self):
        # Configuration initiale de l'algorithme
        self.SetStartDate(2023, 12, 1)      # Date de début du backtest
        self.SetCash(50_000)           # Montant initial pour le backtest

        # Définir le benchmark comme étant le SPY (S&P 500 ETF)
        self.SetBenchmark("VGT")
        
        # Paramètres optimisables : Permet de tester différents scénarios dans QC
        self.days_to_expiry = int(self.GetParameter("days_to_expiry", 30))  # Nombre de jours avant expiration des options
        self.otm_threshold = float(self.GetParameter("otm_threshold", 0.05))  # Pourcentage en dehors de la monnaie (OTM)
        self.position_fraction = float(self.GetParameter("position_fraction", 0.2))  # Fraction du portefeuille à engager dans chaque position

        # Initialisation des prix pour les nouveaux titres
        self.SetSecurityInitializer(
            BrokerageModelSecurityInitializer(
                self.BrokerageModel,
                FuncSecuritySeeder(self.GetLastKnownPrices)
            )
        )

        self._eqNames = ['NVDA','ORCL','CSCO','AMD','QCOM']
        self.otm_threshold_AddOn = {'NVDA':0.005 ,'ORCL':0.08,'CSCO':0.11,'AMD':0.009,'QCOM':0.05}

        # Ajouter les actifs NVDIA, Oracle, Cisco Systems, Advanced Micro Devices, QUALCOMM Incorporated on sélectionné 5 grandes dans le secteurs technology
        self._equities = {eq_tickers : self.AddEquity(eq_tickers,
            dataNormalizationMode=DataNormalizationMode.Raw  
            )
            for eq_tickers in self._eqNames}

        self.max_exposure_fraction = float(self.GetParameter("max_exposure_fraction", 1.0))  # Exposition max du portefeuille
        self.disable_margin = bool(self.GetParameter("disable_margin", 1))  # Forcer des positions cash-secured
 
    def _get_target_contract(self, right, target_price):
        """
        Obtenir le contrat d'option cible (PUT ou CALL) basé sur le prix cible.
        
        Args:
            right: OptionRight.PUT ou OptionRight.CALL
            target_price: Prix cible pour le strike

        Returns:
            Symbol du contrat sélectionné ou None si aucun contrat éligible
        """
        contract_symbols = {eq: self.OptionChainProvider.GetOptionContractList(self._equities[eq].Symbol, self.Time) for eq in self._eqNames}
        for eq in self._eqNames:
            if not contract_symbols[eq]:
                self.Debug(f"Aucun contrat disponible pour {self._equities[eq].Symbol} à {self.Time}.")
                return None

        future_dates = {eq: [s.ID.Date for s in contract_symbols[eq] if s.ID.Date.date() > self.Time.date() + timedelta(self.days_to_expiry)] for eq in self._eqNames}
        for eq in self._eqNames:
            if not future_dates[eq]:
                self.Debug("Aucune expiration disponible au-delà de la période demandée.")
                return None
        
        expiry = {eq: min(future_dates[eq]) for eq in self._eqNames}
        filtered_symbols =  [s for eq in self._eqNames for s in contract_symbols[eq] if s.ID.Date == expiry[eq] and s.ID.OptionRight == right and 
             (s.ID.StrikePrice <= target_price if right == OptionRight.PUT else s.ID.StrikePrice >= target_price)]
            
        filtered_symbols = sorted(filtered_symbols, key=lambda s: s.ID.StrikePrice, reverse=(right == OptionRight.PUT))

        if not filtered_symbols:
            self.Debug(f"Aucun contrat trouvé pour {right} autour de {target_price:.2f} avec expiration {expiry}.")
            return None

        symbol = filtered_symbols[0]
        self.AddOptionContract(symbol)
        return symbol

    def _validate_order(self, required_exposure, order_type="PUT"):
        """
        Valider si le portefeuille peut supporter l'exposition requise pour un ordre.

        Args:
            required_exposure: Exposition totale requise pour l'ordre
            order_type: Type d'ordre ("PUT" ou "CALL")

        Returns:
            bool: True si l'ordre est valide, False sinon
        """
        available_cash = self.Portfolio.MarginRemaining  # Liquidités après frais
        total_exposure = sum(
            abs(holding.Quantity) * holding.Price
            for holding in self.Portfolio.Values if holding.Type == SecurityType.Option
        )

        # Vérification de liquidités pour cash-secured
        if self.disable_margin and available_cash < required_exposure:
            self.Debug(f"Ordre {order_type} refusé : Liquidités insuffisantes ({available_cash:.2f} disponibles, {required_exposure:.2f} requis).")
            return False

        # Vérification d'exposition maximale
        new_exposure = total_exposure + required_exposure
        if new_exposure > self.Portfolio.TotalPortfolioValue * self.max_exposure_fraction:
            self.Debug(f"Ordre {order_type} refusé : Exposition maximale dépassée ({new_exposure:.2f} > {self.Portfolio.TotalPortfolioValue * self.max_exposure_fraction:.2f}).")
            return False

        return True
    
    def log_portfolio_state(self, action, symbol=None):
        """
        Fonction pour journaliser l'état du portefeuille avant et après une transaction.
        """
        portfolio_value = self.Portfolio.TotalPortfolioValue
        portfolio_cash = self.Portfolio.Cash
        equity_quantity = {eq: self._equities[eq].Holdings.Quantity for eq in self._eqNames} # Nombre d'actions détenues
        options_positions = {
            sym: holding.Quantity
            for sym, holding in self.Portfolio.items() if holding.Type == SecurityType.Option
        }
        message = (
            f"{action} - Portefeuille Total: {portfolio_value:.2f}, Liquidités: {portfolio_cash:.2f}, "
            f"Actions Détenues: {list(equity_quantity.keys())} = {list(equity_quantity.values())}, Positions Options: {options_positions}"
        )
        if symbol:
            message += f", Instrument : {symbol.Value}"
        self.Debug(message)
    

    def OnData(self, data):
        """
        Gestion des données de marché et logique de trading.
        """
        for eq in self._eqNames:
            if not self.Portfolio.Invested and self.IsMarketOpen(self._equities[eq].Symbol):
                put_target_price = self._equities[eq].Price * (1 - self.otm_threshold - self.otm_threshold_AddOn[eq])
                put_symbol = self._get_target_contract(OptionRight.PUT, put_target_price)
                
                if put_symbol is not None:
                    required_exposure = put_symbol.ID.StrikePrice * 100
                    self.log_portfolio_state("Avant Vente PUT", put_symbol)
                    
                    if self._validate_order(required_exposure, "PUT"):
                        quantity_to_sell = math.floor(self.Portfolio.Cash / required_exposure)  # Quantité ajustée au cash disponible
                        self.MarketOrder(put_symbol, -quantity_to_sell)
                        self.log_portfolio_state("Après Vente PUT", put_symbol)
            
            elif [self._equities[eq].Symbol] == [symbol for symbol, holding in self.Portfolio.items() if holding.Invested]:
                call_target_price = self._equities[eq].Price * (1 + self.otm_threshold + self.otm_threshold_AddOn[eq])
                call_symbol = self._get_target_contract(OptionRight.CALL, call_target_price)
                if call_symbol is not None:
                    quantity_to_cover = math.floor(self._equities[eq].Holdings.Quantity / 100)
                    self.log_portfolio_state("Avant Vente CALL", call_symbol)
                    if quantity_to_cover > 0:
                        self.MarketOrder(call_symbol, -quantity_to_cover)
                        self.log_portfolio_state("Après Vente CALL", call_symbol)


    

