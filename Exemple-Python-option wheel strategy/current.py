# Importer les dépendances nécessaires
from AlgorithmImports import *
import math

class WheelStrategyAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration initiale de l'algorithme
        self.SetStartDate(2020, 6, 1)      # Date de début du backtest
        self.SetCash(1_000_000)           # Montant initial pour le backtest

        # Définir le benchmark comme étant le SPY (S&P 500 ETF)
        self.SetBenchmark("SPY")
        
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
        
        # Ajouter l'actif sous-jacent SPY (S&P 500 ETF)
        self._equity = self.AddEquity(
            "SPY",
            dataNormalizationMode=DataNormalizationMode.Raw  # Pas d'ajustement des prix pour dividendes/splits
        )

    def _get_target_contract(self, right, target_price):
        """
        Obtenir le contrat d'option cible (PUT ou CALL) basé sur le prix cible.
        
        Args:
            right: OptionRight.PUT ou OptionRight.CALL
            target_price: Prix cible pour le strike

        Returns:
            Symbol du contrat sélectionné ou None si aucun contrat éligible
        """
        # Liste des contrats disponibles pour l'actif
        contract_symbols = self.OptionChainProvider.GetOptionContractList(self._equity.Symbol, self.Time)
        if not contract_symbols:
            self.Debug(f"Aucun contrat disponible pour {self._equity.Symbol} à {self.Time}.")
            return None

        # Filtrer les expirations disponibles (>= `days_to_expiry`)
        future_dates = [s.ID.Date for s in contract_symbols if s.ID.Date.date() > self.Time.date() + timedelta(self.days_to_expiry)]
        if not future_dates:
            self.Debug("Aucune expiration disponible au-delà de la période demandée.")
            return None
        
        expiry = min(future_dates)  # Prochaine date d'expiration disponible

        # Filtrer les contrats en fonction du type et du prix cible
        if right == OptionRight.PUT:
            # PUT : Strike <= target_price
            filtered_symbols = [s for s in contract_symbols if s.ID.Date == expiry and s.ID.OptionRight == OptionRight.PUT and s.ID.StrikePrice <= target_price]
            filtered_symbols = sorted(filtered_symbols, key=lambda s: s.ID.StrikePrice, reverse=True)
        else:
            # CALL : Strike >= target_price
            filtered_symbols = [s for s in contract_symbols if s.ID.Date == expiry and s.ID.OptionRight == OptionRight.CALL and s.ID.StrikePrice >= target_price]
            filtered_symbols = sorted(filtered_symbols, key=lambda s: s.ID.StrikePrice, reverse=False)

        if not filtered_symbols:
            self.Debug(f"Aucun contrat trouvé pour {right} autour de {target_price:.2f} avec expiration {expiry}.")
            return None

        # Sélectionner le contrat avec le strike le plus proche
        symbol = filtered_symbols[0]

        # Ajouter le contrat aux données suivies
        self.AddOptionContract(symbol)
        self.Debug(f"Contrat sélectionné: {symbol.Value}, Right={right}, Strike={symbol.ID.StrikePrice}, Expiry={symbol.ID.Date}")
        return symbol

    def OnData(self, data):
        """
        Gestion des données de marché et logique de trading.
        """
        # Si aucune position n'est ouverte, vendre un PUT
        if not self.Portfolio.Invested and self.IsMarketOpen(self._equity.Symbol):
            put_target_price = self._equity.Price * (1 - self.otm_threshold)  # Calcul du prix cible pour le PUT
            put_symbol = self._get_target_contract(OptionRight.PUT, put_target_price)
            if put_symbol is not None:
                # Vente d'un PUT avec une fraction du portefeuille
                self.SetHoldings(put_symbol, -self.position_fraction)
                self.Debug(f"Vente de PUT : {put_symbol.Value}, Strike : {put_symbol.ID.StrikePrice}, Expiry : {put_symbol.ID.Date}")
    
        # Si des actions sous-jacentes sont détenues, vendre un CALL
        elif [self._equity.Symbol] == [symbol for symbol, holding in self.Portfolio.items() if holding.Invested]:
            call_target_price = self._equity.Price * (1 + self.otm_threshold)  # Calcul du prix cible pour le CALL
            call_symbol = self._get_target_contract(OptionRight.CALL, call_target_price)

            if call_symbol is not None:
                # Calculer le nombre de contrats nécessaires pour couvrir les actions détenues
                quantity_to_cover = math.floor(self._equity.Holdings.Quantity / 100)  # Chaque contrat couvre 100 actions
                if quantity_to_cover > 0:
                    self.MarketOrder(call_symbol, -quantity_to_cover)
                    self.Debug(f"Vente de CALL : {call_symbol.Value}, Strike : {call_symbol.ID.StrikePrice}, Expiry : {call_symbol.ID.Date}, Quantity : {quantity_to_cover}")

        # Possibilité d'ajouter des améliorations :
        # - Rachat de PUT en cas de conditions défavorables
        # - Utilisation de stop de protection en cas de possession du sous-jacent
        # - Imposition d'une prime minimale pour les options sélectionnées

