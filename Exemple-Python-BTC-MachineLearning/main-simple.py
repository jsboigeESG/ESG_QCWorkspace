# ======================================================================
# FICHIER: MyCryptoMlAlgorithm.py
# ======================================================================
from AlgorithmImports import *
import joblib
import numpy as np

class MyCryptoMlAlgorithm(QCAlgorithm):
    
    def Initialize(self):
       # 1) Période du backtest
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2023, 1, 1)
        
        # 2) Compte en USDT (capital 100k USDT)
        self.SetAccountCurrency("USDT")
        self.SetCash("USDT", 100000)  # 100k USDT
        
        # 3) Brokerage Binance, mode Cash
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        
        # 4) Ajouter la crypto BTCUSDT (Daily)
        self.symbol = self.AddCrypto("BTCUSDT", Resolution.Daily, Market.Binance).Symbol
        
        # (Optionnel) Normalisation en RAW pour crypto
        self.Securities[self.symbol].SetDataNormalizationMode(DataNormalizationMode.Raw)
        
        # 5) Benchmark = BTCUSDT
        self.SetBenchmark(self.symbol)
        
        # 4) Charger le modèle depuis l’Object Store
        model_key = "myCryptoMlModel.pkl"
        if self.ObjectStore.ContainsKey(model_key):
            file_path = self.ObjectStore.GetFilePath(model_key)
            self.model = joblib.load(file_path)
            self.Debug(f"Modèle chargé depuis l'Object Store: {model_key}")
        else:
            self.Debug(f"Clé {model_key} introuvable dans l'Object Store.")
            self.Quit("Impossible de poursuivre, aucun modèle n’a été trouvé.")
        
        # 5) Création des indicateurs
        self.rsi = self.RSI(
            self.symbol, 
            14, 
            MovingAverageType.Wilders, 
            Resolution.Daily
        )
        self.sma20 = self.SMA(self.symbol, 20, Resolution.Daily)
        
        # RollingWindow pour calculer DailyReturn
        self.prev_close = None

    def OnData(self, slice: Slice):
        # S’assurer qu’on dispose d’une QuoteBar / TradeBar sur BTCUSDT
        if not slice.ContainsKey(self.symbol):
            return
        
        # Vérifier que nos indicateurs sont prêts
        if not self.rsi.IsReady or not self.sma20.IsReady:
            return
        
        current_price = slice[self.symbol].Close
        # Initialisation de la prev_close
        if self.prev_close is None:
            self.prev_close = current_price
            return
        
        # Calcul du DailyReturn (Close(t) / Close(t-1) - 1)
        daily_return = (current_price - self.prev_close) / self.prev_close
        self.prev_close = current_price
        
        # On construit le vecteur de features : [SMA20, RSI, DailyReturn]
        X = np.array([[
            self.sma20.Current.Value,
            self.rsi.Current.Value,
            daily_return
        ]])
        
        # Prédiction du modèle : 1 = hausse, 0 = baisse
        prediction = self.model.predict(X)[0]  # [0] pour extraire la valeur
        if prediction == 1:
            # Prédit la hausse => on s’expose à 100 % BTCUSDT
            if not self.Portfolio[self.symbol].Invested:
                self.SetHoldings(self.symbol, 1.0)
                self.Debug(f"{self.Time}: Prédiction=UP => Achat BTCUSDT (Close={current_price:.2f})")
        else:
            # Prédit la baisse => on vend (liquidate)
            if self.Portfolio[self.symbol].Invested:
                self.Liquidate(self.symbol)
                self.Debug(f"{self.Time}: Prédiction=DOWN => Liquidation BTCUSDT (Close={current_price:.2f})")
