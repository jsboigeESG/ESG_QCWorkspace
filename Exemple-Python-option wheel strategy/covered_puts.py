# Importer les dépendances nécessaires
from AlgorithmImports import *
import math

class WheelStrategyAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration initiale de l'algorithme
        self.SetStartDate(2020, 6, 1)      # Date de début du backtest
        self.SetCash(1_000_000)           # Montant initial pour le backtest
        
        # Gestion de la résolution en mode live ou backtest
        self.backtest_resolution = Resolution.Minute
        self.is_live = self.LiveMode
        resolution = Resolution.Minute if self.is_live else self.backtest_resolution
        self.Debug(f"Mode {'Live' if self.is_live else 'Backtest'}, résolution : {resolution}")
        
        # Configurer Interactive Brokers comme brokerage
        self.SetBrokerageModel(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.Cash)
        
        # Définir des propriétés par défaut pour les ordres
        self.DefaultOrderProperties = InteractiveBrokersOrderProperties()
        self.DefaultOrderProperties.TimeInForce = TimeInForce.GoodTilCanceled
        self.DefaultOrderProperties.OutsideRegularTradingHours = False

        # Initialisation des prix pour les nouveaux titres
        self.SetSecurityInitializer(
            BrokerageModelSecurityInitializer(
                self.BrokerageModel,
                FuncSecuritySeeder(self.GetLastKnownPrices)
            )
        )
        
        # Ajouter l'actif sous-jacent SPY (S&P 500 ETF)
        self._equity = self.AddEquity(
            "SPY",
            resolution=resolution,
            dataNormalizationMode=DataNormalizationMode.Raw  # Pas d'ajustement des prix pour dividendes/splits
        )

        # Définir le benchmark comme étant le SPY (S&P 500 ETF)
        self.SetBenchmark("SPY")

        # Paramètres optimisables
        self.days_to_expiry = int(self.GetParameter("days_to_expiry", 30))  # Nombre de jours avant expiration des options
        self.otm_threshold = float(self.GetParameter("otm_threshold", 0.05))  # Pourcentage en dehors de la monnaie (OTM)

        # Contrôle du buying power
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
        contract_symbols = self.OptionChainProvider.GetOptionContractList(self._equity.Symbol, self.Time)
        if not contract_symbols:
            self.Debug(f"Aucun contrat disponible pour {self._equity.Symbol} à {self.Time}.")
            return None

        future_dates = [s.ID.Date for s in contract_symbols if s.ID.Date.date() > self.Time.date() + timedelta(self.days_to_expiry)]
        if not future_dates:
            self.Debug("Aucune expiration disponible au-delà de la période demandée.")
            return None
        
        expiry = min(future_dates)
        filtered_symbols = (
            [s for s in contract_symbols if s.ID.Date == expiry and s.ID.OptionRight == right and 
             (s.ID.StrikePrice <= target_price if right == OptionRight.PUT else s.ID.StrikePrice >= target_price)]
        )
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
        equity_quantity = self._equity.Holdings.Quantity  # Nombre d'actions détenues
        options_positions = {
            sym: holding.Quantity
            for sym, holding in self.Portfolio.items() if holding.Type == SecurityType.Option
        }
        message = (
            f"{action} - Portefeuille Total: {portfolio_value:.2f}, Liquidités: {portfolio_cash:.2f}, "
            f"Actions Détenues: {equity_quantity}, Positions Options: {options_positions}"
        )
        if symbol:
            message += f", Instrument : {symbol.Value}"
        self.Debug(message)

    def OnData(self, data):
        """
        Gestion des données de marché et logique de trading.
        """
        if not self.Portfolio.Invested and self.IsMarketOpen(self._equity.Symbol):
            put_target_price = self._equity.Price * (1 - self.otm_threshold)
            put_symbol = self._get_target_contract(OptionRight.PUT, put_target_price)
            
            if put_symbol is not None:
                required_exposure = put_symbol.ID.StrikePrice * 100
                self.log_portfolio_state("Avant Vente PUT", put_symbol)
                
                if self._validate_order(required_exposure, "PUT"):
                    quantity_to_sell = math.floor(self.Portfolio.Cash / required_exposure)  # Quantité ajustée au cash disponible
                    self.MarketOrder(put_symbol, -quantity_to_sell)
                    self.log_portfolio_state("Après Vente PUT", put_symbol)
        
        elif [self._equity.Symbol] == [symbol for symbol, holding in self.Portfolio.items() if holding.Invested]:
            call_target_price = self._equity.Price * (1 + self.otm_threshold)
            call_symbol = self._get_target_contract(OptionRight.CALL, call_target_price)
            if call_symbol is not None:
                quantity_to_cover = math.floor(self._equity.Holdings.Quantity / 100)
                self.log_portfolio_state("Avant Vente CALL", call_symbol)
                if quantity_to_cover > 0:
                    self.MarketOrder(call_symbol, -quantity_to_cover)
                    self.log_portfolio_state("Après Vente CALL", call_symbol)

