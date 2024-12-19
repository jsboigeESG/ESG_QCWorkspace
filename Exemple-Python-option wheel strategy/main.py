# Importer les dépendances nécessaires
from AlgorithmImports import *
import math

class WheelStrategyAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Configuration de base
        self.SetStartDate(2020, 6, 1)      # Date de début du backtest
        self.SetCash(1_000_000)            # Montant initial

        # Initialiser le benchmark sur SPY
        self.SetBenchmark("SPY")
        
        # Initialiser les paramètres optimisables
        # Si non spécifiés dans l'interface QC, ils prennent des valeurs par défaut
        self.days_to_expiry = int(self.GetParameter("days_to_expiry", 30))
        self.otm_threshold = float(self.GetParameter("otm_threshold", 0.05))
        self.position_fraction = float(self.GetParameter("position_fraction", 0.2))

        self.SetSecurityInitializer(
            BrokerageModelSecurityInitializer(
                self.BrokerageModel,
                FuncSecuritySeeder(self.GetLastKnownPrices)
            )
        )
        
        # Ajouter l'actif sous-jacent (SPY)
        self._equity = self.AddEquity(
            "SPY",
            dataNormalizationMode=DataNormalizationMode.Raw  # Pas d'ajustement prix
        )

    def _get_target_contract(self, right, target_price):
        """
        Obtenir le contrat d'option cible (PUT ou CALL) basé sur le prix cible.
        
        right: OptionRight.PUT ou OptionRight.CALL
        target_price: prix cible pour le strike
        """
        contract_symbols = self.OptionChainProvider.GetOptionContractList(self._equity.Symbol, self.Time)

        # Filtrer les expirations disponibles pour avoir la plus proche >= days_to_expiry
        future_dates = [s.ID.Date for s in contract_symbols if s.ID.Date.date() > self.Time.date() + timedelta(self.days_to_expiry)]
        if not future_dates:
            self.Debug("Aucune expiration disponible au-delà de la période demandée.")
            return None
        
        expiry = min(future_dates)

        # Filtrer les contrats par expiration, type (PUT ou CALL) et strike
        if right == OptionRight.PUT:
            # PUT: Strike <= target_price
            filtered_symbols = [s for s in contract_symbols if s.ID.Date == expiry and s.ID.OptionRight == OptionRight.PUT and s.ID.StrikePrice <= target_price]
            # Trier pour obtenir le strike le plus proche de target_price (le plus grand possible)
            filtered_symbols = sorted(filtered_symbols, key=lambda s: s.ID.StrikePrice, reverse=True)
        else:
            # CALL: Strike >= target_price
            filtered_symbols = [s for s in contract_symbols if s.ID.Date == expiry and s.ID.OptionRight == OptionRight.CALL and s.ID.StrikePrice >= target_price]
            # Trier pour obtenir le strike le plus proche de target_price (le plus petit possible)
            filtered_symbols = sorted(filtered_symbols, key=lambda s: s.ID.StrikePrice, reverse=False)

        if not filtered_symbols:
            self.Debug(f"Aucun contrat trouvé pour {right} autour de {target_price:.2f}")
            return None

        # Optionnel : filtrer les contrats trop éloignés du target price, par exemple écarter les strikes > 10% au-delà du target.
        # filtered_symbols = [s for s in filtered_symbols if abs(s.ID.StrikePrice - target_price) / target_price < 0.1]
        # if not filtered_symbols:
        #     self.Debug("Aucun contrat assez proche du prix cible.")
        #     return None

        symbol = filtered_symbols[0]
        
        # Ajouter le contrat au pipeline de données
        self.AddOptionContract(symbol)
        self.Debug(f"Contrat sélectionné: {symbol.Value}, Right={right}, Strike={symbol.ID.StrikePrice}, Expiry={symbol.ID.Date}")
        return symbol

    def OnData(self, data):
        """
        Gestion des données et de la logique de trading.
        """
        # Conditions pour la vente de PUT
        if not self.Portfolio.Invested and self.IsMarketOpen(self._equity.Symbol):
            put_target_price = self._equity.Price * (1 - self.otm_threshold)
            put_symbol = self._get_target_contract(OptionRight.PUT, put_target_price)

            if put_symbol is not None:
                # Vente d'un PUT avec une fraction du portefeuille
                self.SetHoldings(put_symbol, -self.position_fraction)
                self.Debug(f"Vente de PUT sur {put_symbol.Value} pour {self.position_fraction*100}% du portefeuille.")

        # Conditions pour la vente de CALL une fois qu'on détient l'underlying
        elif [self._equity.Symbol] == [symbol for symbol, holding in self.Portfolio.items() if holding.Invested and symbol.SecurityType == SecurityType.Equity]:
            call_target_price = self._equity.Price * (1 + self.otm_threshold)
            call_symbol = self._get_target_contract(OptionRight.CALL, call_target_price)

            if call_symbol is not None:
                # Calculer le nombre de contrats à vendre en fonction de la quantité d'actions détenues
                # 1 contrat = 100 actions
                quantity_to_cover = math.floor(self._equity.Holdings.Quantity / 100)
                if quantity_to_cover > 0:
                    self.MarketOrder(call_symbol, -quantity_to_cover)
                    self.Debug(f"Vente de CALL sur {call_symbol.Value} pour couvrir {quantity_to_cover * 100} actions.")

        # (Améliorations futures possibles)
        # Par exemple, racheter le PUT si la position devient trop risquée
        # Ou encore imposer une prime minimum sur l'option (en récupérant la data de l'option une fois ajoutée)

