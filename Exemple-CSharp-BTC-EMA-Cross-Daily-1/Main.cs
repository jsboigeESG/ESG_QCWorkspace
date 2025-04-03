#region imports
    using System;
    using System.Collections;
    using System.Collections.Generic;
    using System.Linq;
    using System.Globalization;
    using System.Drawing;
    using QuantConnect;
    using QuantConnect.Algorithm.Framework;
    using QuantConnect.Algorithm.Framework.Selection;
    using QuantConnect.Algorithm.Framework.Alphas;
    using QuantConnect.Algorithm.Framework.Portfolio;
    using QuantConnect.Algorithm.Framework.Portfolio.SignalExports;
    using QuantConnect.Algorithm.Framework.Execution;
    using QuantConnect.Algorithm.Framework.Risk;
    using QuantConnect.Algorithm.Selection;
    using QuantConnect.Api;
    using QuantConnect.Parameters;
    using QuantConnect.Benchmarks;
    using QuantConnect.Brokerages;
    using QuantConnect.Configuration;
    using QuantConnect.Util;
    using QuantConnect.Interfaces;
    using QuantConnect.Algorithm;
    using QuantConnect.Indicators;
    using QuantConnect.Data;
    using QuantConnect.Data.Auxiliary;
    using QuantConnect.Data.Consolidators;
    using QuantConnect.Data.Custom;
    using QuantConnect.Data.Custom.IconicTypes;
    using QuantConnect.DataSource;
    using QuantConnect.Data.Fundamental;
    using QuantConnect.Data.Market;
    using QuantConnect.Data.Shortable;
    using QuantConnect.Data.UniverseSelection;
    using QuantConnect.Notifications;
    using QuantConnect.Orders;
    using QuantConnect.Orders.Fees;
    using QuantConnect.Orders.Fills;
    using QuantConnect.Orders.OptionExercise;
    using QuantConnect.Orders.Slippage;
    using QuantConnect.Orders.TimeInForces;
    using QuantConnect.Python;
    using QuantConnect.Scheduling;
    using QuantConnect.Securities;
    using QuantConnect.Securities.Equity;
    using QuantConnect.Securities.Future;
    using QuantConnect.Securities.Option;
    using QuantConnect.Securities.Positions;
    using QuantConnect.Securities.Forex;
    using QuantConnect.Securities.Crypto;
    using QuantConnect.Securities.CryptoFuture;
    using QuantConnect.Securities.Interfaces;
    using QuantConnect.Securities.Volatility;
    using QuantConnect.Storage;
    using QuantConnect.Statistics;
    using QCAlgorithmFramework = QuantConnect.Algorithm.QCAlgorithm;
    using QCAlgorithmFrameworkBridge = QuantConnect.Algorithm.QCAlgorithm;
#endregion
namespace QuantConnect 
{   
    
     /// <summary>
    /// Algorithme de trading pour BTCUSDT utilisant un croisement d'EMAs (Exponential Moving Averages).
    /// </summary>
    public class BtcEmaCrossDaily1Algorithm : QCAlgorithm
    {
        // Symbole pour BTCUSDT
        private Symbol _btcUsdSymbol;

        // Résolution des données (journalière)
        private readonly Resolution _resolution = Resolution.Daily;

        // Paramètres pour les EMAs rapide et lente
        [Parameter("ema-fast")]
        public int FastPeriod = 18;

        [Parameter("ema-slow")]
        public int SlowPeriod = 23;

        // Marges pour les croisements à la hausse et à la baisse
        [Parameter("ema-upcross-margin")]
        public decimal UpCrossMargin = 1.001m;

        [Parameter("ema-downcross-margin")]
        public decimal DownCrossMargin = 0.999m;

        // Indicateurs EMAs
        private ExponentialMovingAverage _fastEma;
        private ExponentialMovingAverage _slowEma;

        // Noms pour les graphiques
        private const string ChartName = "EMA Plot";
        private const string PriceSeriesName = "Price";
        private const string PortfolioValueSeriesName = "Portfolio Value";
        private const string FastEmaSeriesName = "Fast EMA";
        private const string SlowEmaSeriesName = "Slow EMA";


        /// <summary>
        /// Initialise l'algorithme.
        /// </summary>
        public override void Initialize()
        {
            
            // Initialisation de la période du backtest
            InitPeriod();

            // Configuration de la période de chauffe pour les indicateurs
            SetWarmUp(TimeSpan.FromDays(Math.Max(FastPeriod, SlowPeriod)));

            // Configuration du modèle de courtage (Binance, compte Cash)
            SetBrokerageModel(BrokerageName.Binance, AccountType.Cash);

            // Initialisation du capital de départ en USDT
            SetAccountCurrency("USDT");   // Devise du compte
            SetCash(600000);              // Capital initial de 600 000 USDT

            // Définition des propriétés par défaut des ordres (ici, les valeurs par défaut suffisent)
            DefaultOrderProperties = new BinanceOrderProperties
            {
                TimeInForce = TimeInForce.GoodTilCanceled,
                PostOnly = false
            };

            // Ajout du symbole BTCUSDT avec la résolution définie
            _btcUsdSymbol = AddCrypto("BTCUSDT", _resolution, Market.Binance).Symbol;

            // Initialisation des indicateurs EMA rapide et lente
            _fastEma = EMA(_btcUsdSymbol, FastPeriod, _resolution);
            _slowEma = EMA(_btcUsdSymbol, SlowPeriod, _resolution);

            this.SetBenchmark(_btcUsdSymbol);
            // Initialisation des graphiques
            InitializeCharts();
        }

        /// <summary>
        /// Méthode principale appelée à chaque nouvelle donnée de marché.
        /// </summary>
        /// <param name="data">Données de marché pour le symbole suivi.</param>
        public override void OnData(Slice data)
        {
            // Attendre que la période de chauffe soit terminée et que les indicateurs soient prêts
            if (IsWarmingUp || !_fastEma.IsReady || !_slowEma.IsReady)
                return;

            // Vérifier que les données pour le symbole sont disponibles
            if (!data.ContainsKey(_btcUsdSymbol))
                return;

            // Récupération des valeurs actuelles des EMAs
            var fastEmaValue = _fastEma.Current.Value;
            var slowEmaValue = _slowEma.Current.Value;

            // Vérifier si nous ne sommes pas déjà investis et que l'EMA rapide croise au-dessus de l'EMA lente avec marge
            if (!Portfolio.Invested && fastEmaValue > slowEmaValue * UpCrossMargin)
            {
                // Investir 100% du capital disponible dans BTCUSDT
                SetHoldings(_btcUsdSymbol, 1);
                Debug($"Achat de {_btcUsdSymbol} au prix de {Securities[_btcUsdSymbol].Price}");
            }
            // Vérifier si nous sommes investis et que l'EMA rapide croise en dessous de l'EMA lente avec marge
            else if (Portfolio.Invested && fastEmaValue < slowEmaValue * DownCrossMargin)
            {
                // Liquider la position sur BTCUSDT
                Liquidate(_btcUsdSymbol);
                Debug($"Vente de {_btcUsdSymbol} au prix de {Securities[_btcUsdSymbol].Price}");
            }
        }

        /// <summary>
        /// Événements déclenchés lors de l'exécution d'ordres (achat/vente).
        /// </summary>
        /// <param name="orderEvent">Informations sur l'ordre exécuté.</param>
        public override void OnOrderEvent(OrderEvent orderEvent)
        {
            // Vérifie si l'ordre a été rempli
            if (orderEvent.Status == OrderStatus.Filled)
            {
                // Détermine le type d'opération (achat ou vente)
                string operation = orderEvent.Direction == OrderDirection.Buy ? "Achat" : "Vente";

                // Construction du message de journalisation
                var message = $"{Time.ToShortDateString()} - {operation} de {Math.Abs(orderEvent.FillQuantity)} unités de {_btcUsdSymbol} au prix de {orderEvent.FillPrice} USDT.";

                // Ajout des informations sur le portefeuille
                message += $" Valeur totale du portefeuille : {Portfolio.TotalPortfolioValue:N2} USDT.";

                // Enregistrement dans le journal
                Debug(message);
            }
        }

        /// <summary>
        /// Initialise les graphiques et séries pour la visualisation.
        /// </summary>
        private void InitializeCharts()
        {
            // Création du graphique principal
            var chart = new Chart(ChartName);

            // Séries pour le prix de l'actif, la valeur du portefeuille, EMA rapide et EMA lente
            var priceSeries = new Series(PriceSeriesName, SeriesType.Line, "$", Color.Blue);
            var portfolioValueSeries = new Series(PortfolioValueSeriesName, SeriesType.Line, "$", Color.Green);
            var fastEmaSeries = new Series(FastEmaSeriesName, SeriesType.Line, "$", Color.Red);
            var slowEmaSeries = new Series(SlowEmaSeriesName, SeriesType.Line, "$", Color.Yellow);

            // Ajout des séries au graphique
            chart.AddSeries(priceSeries);
            chart.AddSeries(portfolioValueSeries);
            chart.AddSeries(fastEmaSeries);
            chart.AddSeries(slowEmaSeries);

            // Ajout du graphique à l'algorithme
            AddChart(chart);

            // Planification de l'exécution de la méthode DoPlots chaque jour pour mettre à jour les graphiques
            Schedule.On(
                DateRules.EveryDay(),
                TimeRules.At(0, 0), // Les marchés crypto sont ouverts 24/7
                DoPlots);
        }

        /// <summary>
        /// Met à jour les graphiques avec les données actuelles.
        /// </summary>
        private void DoPlots()
        {
            // Vérifie que les données sont disponibles pour le symbole
            if (!Securities.ContainsKey(_btcUsdSymbol) || !Securities[_btcUsdSymbol].HasData)
                return;

            // Récupération des valeurs actuelles
            var price = Securities[_btcUsdSymbol].Price;
            var portfolioValue = Portfolio.TotalPortfolioValue;
            var fastEmaValue = _fastEma.Current.Value;
            var slowEmaValue = _slowEma.Current.Value;

            // Mise à jour des séries du graphique avec les valeurs actuelles
            Plot(ChartName, PriceSeriesName, price);
            Plot(ChartName, PortfolioValueSeriesName, portfolioValue);
            Plot(ChartName, FastEmaSeriesName, fastEmaValue);
            Plot(ChartName, SlowEmaSeriesName, slowEmaValue);
        }

        /// <summary>
        /// Initialise la période du backtest. Plusieurs périodes intéressantes sont proposées en commentaires.
        /// </summary>
        private void InitPeriod()
        {
            

            //SetStartDate(2017, 08, 08); // début backtest 3412
            //SetEndDate(2019, 02, 05); // fin backtest 3432

            //SetStartDate(2018, 01, 30); // début backtest 9971
            //SetEndDate(2020, 07, 26); // fin backtest 9945


            //SetStartDate(2017, 12, 15); // début backtest 17478
            //SetEndDate(2022, 12, 12); // fin backtest 17209

            //SetStartDate(2017, 11, 25); // début backtest 8718
            //SetEndDate(2020, 05, 1); // fin backtest 8832

            // SetStartDate(2021, 01, 01); // début backtest 29410
            // SetEndDate(2023, 10, 20); // fin backtest 29688

            SetStartDate(2021, 10, 16); 
            // SetEndDate(2025, 03, 27);

        }
    }
}





