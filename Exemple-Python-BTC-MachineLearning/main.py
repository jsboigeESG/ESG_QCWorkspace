# =================================================================================================================
# FICHIER: MyEnhancedCryptoMlAlgorithm.py
# Notez que l'autre modèle (simple) fonctionne mieux: celui-ci a "trop" appris le régime baissier sur lequel il a été entraîné
# ==================================================================================================================
from AlgorithmImports import *
import joblib
import numpy as np

class MyEnhancedCryptoMlAlgorithm(QCAlgorithm):
    
    # --- PARAMÈTRES AJUSTABLES ---
    MODEL_KEY       = "myCryptoMlModel.pkl"  # Clé ObjectStore
    START_DATE      = datetime(2023, 1, 1)
    END_DATE        = datetime(2024, 1, 1)
    STARTING_CASH   = 100000
    SMA_PERIOD      = 20
    RSI_PERIOD      = 14
    EMA_PERIODS     = [10, 20, 50, 200]
    ADX_PERIOD      = 14
    ATR_PERIOD      = 14
    
    def Initialize(self):
        # 1) Dates du backtest
        self.SetStartDate(self.START_DATE.year, self.START_DATE.month, self.START_DATE.day)
        self.SetEndDate(self.END_DATE.year, self.END_DATE.month, self.END_DATE.day)
        
        # 2) Comptes
        self.SetAccountCurrency("USDT")
        self.SetCash("USDT", self.STARTING_CASH)
        
        # 3) Brokerage en Cash
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)
        
        # 4) Ajouter la crypto BTCUSDT (Daily, en TradeBar => High/Low/Close)
        self.symbol = self.AddCrypto("BTCUSDT", Resolution.Daily, Market.Binance).Symbol
        
        # DataNormalizationMode en RAW
        self.Securities[self.symbol].SetDataNormalizationMode(DataNormalizationMode.Raw)
        
        # 5) Benchmark
        self.SetBenchmark(self.symbol)
        
        # 6) Charger le modèle depuis l'Object Store
        if self.ObjectStore.ContainsKey(self.MODEL_KEY):
            file_path = self.ObjectStore.GetFilePath(self.MODEL_KEY)
            self.model = joblib.load(file_path)
            self.Debug(f"Modèle chargé depuis l'Object Store: {self.MODEL_KEY}")
        else:
            self.Debug(f"Clé {self.MODEL_KEY} introuvable dans l'ObjectStore.")
            self.Quit("Aucun modèle trouvé. Arrêt de l'algorithme.")
        
        # 7) Création des indicateurs
        #    a) SMA
        self.sma  = self.SMA(self.symbol, self.SMA_PERIOD, Resolution.Daily)
        
        #    b) RSI
        self.rsi = self.RSI(self.symbol, self.RSI_PERIOD, MovingAverageType.Wilders, Resolution.Daily)
        
        #    c) Multiple EMAs
        self.ema_dict = {}
        for period in self.EMA_PERIODS:
            self.ema_dict[period] = self.EMA(self.symbol, period, Resolution.Daily)
        
        #    d) ADX
        self.adx = self.ADX(self.symbol, self.ADX_PERIOD, Resolution.Daily)
        
        #    e) ATR
        self.atr = self.ATR(self.symbol, self.ATR_PERIOD, MovingAverageType.Simple, Resolution.Daily)
        
        # 8) Rolling variable pour daily_return
        self.prev_close = None
        
        # 9) WarmUp => on laisse du temps pour initialiser
        #    (surtout pour EMA(200), ADX, etc.)
        #    On peut mettre 200 + ADX_PERIOD = 214 par ex.
        warmup_bars = max(self.EMA_PERIODS) + self.ADX_PERIOD
        self.SetWarmUp(warmup_bars, Resolution.Daily)

    def OnData(self, slice: Slice):
        # Vérifier si data existe
        if not slice.Bars.ContainsKey(self.symbol):
            return
        
        bar = slice.Bars[self.symbol]  # TradeBar => .High, .Low, .Close, .Volume, etc.
        current_price = bar.Close
        
        # Vérifier que tous nos indicateurs sont "ready"
        # RSI, SMA, ADX, ATR, etc. + toutes les EMAs
        if self.IsWarmingUp:
            return
        
        if not self.sma.IsReady or not self.rsi.IsReady or not self.adx.IsReady or not self.atr.IsReady:
            return
        
        for period in self.EMA_PERIODS:
            if not self.ema_dict[period].IsReady:
                return
        
        # Calcul du daily_return
        if self.prev_close is None:
            self.prev_close = current_price
            return
        
        daily_return = (current_price - self.prev_close) / self.prev_close
        self.prev_close = current_price
        
        # Récupération de la valeur de nos indicateurs
        sma_val = self.sma.Current.Value
        rsi_val = self.rsi.Current.Value
        
        ema_10  = self.ema_dict[10].Current.Value
        ema_20  = self.ema_dict[20].Current.Value
        ema_50  = self.ema_dict[50].Current.Value
        ema_200 = self.ema_dict[200].Current.Value
        
        adx_val = self.adx.Current.Value
        atr_val = self.atr.Current.Value
        
        # Construction du vecteur X dans le même ordre que le Notebook:
        # 1) SMA20
        # 2) RSI14
        # 3) DailyReturn
        # 4) EMA_10
        # 5) EMA_20
        # 6) EMA_50
        # 7) EMA_200
        # 8) ADX_14
        # 9) ATR_14
        X = np.array([[
            sma_val,
            rsi_val,
            daily_return,
            ema_10,
            ema_20,
            ema_50,
            ema_200,
            adx_val,
            atr_val
        ]])
        
        # Prédiction
        pred = self.model.predict(X)[0]  # 1 = up, 0 = down
        
        if pred == 1:
            # Achat total
            if not self.Portfolio[self.symbol].Invested:
                self.SetHoldings(self.symbol, 1.0)
                self.Debug(f"{self.Time} => Pred=UP => Achat BTCUSDT @ {current_price:.2f}")
        else:
            # Baisse => on vend
            if self.Portfolio[self.symbol].Invested:
                self.Liquidate(self.symbol)
                self.Debug(f"{self.Time} => Pred=DOWN => Liquidation BTCUSDT @ {current_price:.2f}")
