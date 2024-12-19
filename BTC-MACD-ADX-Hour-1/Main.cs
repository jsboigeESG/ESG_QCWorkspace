#region imports
using System;
using System.Collections.Generic;
using System.Linq;
using System.Drawing;
using QuantConnect;
using QuantConnect.Algorithm.Framework;
using QuantConnect.Algorithm.Framework.Selection;
using QuantConnect.Algorithm.Framework.Alphas;
using QuantConnect.Algorithm.Framework.Portfolio;
using QuantConnect.Algorithm.Framework.Portfolio.SignalExports;
using QuantConnect.Algorithm.Framework.Execution;
using QuantConnect.Algorithm.Framework.Risk;
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
using QuantConnect.Data.Market;
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
using QuantConnect.Securities.Crypto;
using QuantConnect.Securities.Interfaces;
using QuantConnect.Statistics;
#endregion

namespace QuantConnect.Algorithm.CSharp
{
    /// <summary>
    /// Algorithme de trading pour BTCUSDT utilisant MACD et ADX en résolution horaire,
    /// avec adaptation dynamique des seuils ADX via percentiles.
    /// </summary>
    public class BtcMacdAdxHour1Algorithm : QCAlgorithm
    {
        // Paramètres MACD
        [Parameter("macd-fast")]
        public int MacdFast = 8;

        [Parameter("macd-slow")]
        public int MacdSlow = 16;

        [Parameter("macd-signal")]
        public int MacdSignal = 12;

        // Paramètres ADX
        [Parameter("adx-period")]
        public int AdxPeriod = 25;

        // Rolling window pour ADX
        [Parameter("adx-window")]
        public int AdxWindowPeriod = 140;

        // Paramètres percentiles
        [Parameter("adx-lower-percentile")]
        public int AdxLowerPercentile = 6; // Ex: 10 signifie le 10ème percentile
        [Parameter("adx-upper-percentile")]
        public int AdxUpperPercentile = 86; // Ex: 90 signifie le 90ème percentile

        private RollingWindow<decimal> _adxWindow;

        // Symbole à trader
        private Symbol _symbol;

        private const string TradedPairTicker = "BTCUSDT";

        // Indicateurs
        private MovingAverageConvergenceDivergence _macd;
        private AverageDirectionalIndex _adx;

        // Noms graphiques
        private const string ChartName = "Trade Plot";
        private const string PriceSeriesName = "Price";
        private const string PortfolioValueSeriesName = "PortFolioValue";
        private const string MacdSeriesName = "MACD";
        private const string AdxSeriesName = "ADX";

        public override void Initialize()
        {
            // Période du backtest
            InitPeriod();

            SetAccountCurrency("USDT");
            SetCash(5000);
            SetBrokerageModel(BrokerageName.Binance, AccountType.Cash);

            var security = AddCrypto(TradedPairTicker, Resolution.Hour);
            _symbol = security.Symbol;
            SetBenchmark(_symbol);

            // Warm-up (1 an)
            SetWarmUp(TimeSpan.FromDays(365));

            // Initialisation des indicateurs
            _macd = MACD(_symbol, MacdFast, MacdSlow, MacdSignal, MovingAverageType.Exponential, Resolution.Hour, Field.Close);
            _adx = ADX(_symbol, AdxPeriod, Resolution.Hour);

            _adxWindow = new RollingWindow<decimal>(AdxWindowPeriod);

            InitializeCharts();
        }

        private void InitializeCharts()
        {
            var stockPlot = new Chart(ChartName);

            var assetPriceSeries = new Series(PriceSeriesName, SeriesType.Line, "$", Color.Blue);
            var portfolioValueSeries = new Series(PortfolioValueSeriesName, SeriesType.Line, "$", Color.Green);
            var macdSeries = new Series(MacdSeriesName, SeriesType.Line, "", Color.Purple);
            var adxSeries = new Series(AdxSeriesName, SeriesType.Line, "", Color.OrangeRed);

            stockPlot.AddSeries(assetPriceSeries);
            stockPlot.AddSeries(portfolioValueSeries);
            stockPlot.AddSeries(macdSeries);
            stockPlot.AddSeries(adxSeries);

            AddChart(stockPlot);

            Schedule.On(DateRules.EveryDay(), TimeRules.Every(TimeSpan.FromHours(1)), DoPlots);
        }

        private void DoPlots()
        {
            if (!Securities.ContainsKey(_symbol) || !Securities[_symbol].HasData)
                return;

            var price = Securities[_symbol].Price;
            Plot(ChartName, PriceSeriesName, price);
            Plot(ChartName, PortfolioValueSeriesName, Portfolio.TotalPortfolioValue);
            Plot(ChartName, MacdSeriesName, _macd);
            Plot(ChartName, AdxSeriesName, _adx);
        }

        public override void OnData(Slice data)
        {
            if (IsWarmingUp || !_macd.IsReady || !_adx.IsReady)
                return;

            if (!data.ContainsKey(_symbol))
                return;

            _adxWindow.Add(_adx.Current.Value);
            if (!_adxWindow.IsReady) return;

            var holdings = Portfolio[_symbol].Quantity;
            var currentPrice = data[_symbol].Close;

            var macdHistogram = _macd.Current.Value - _macd.Signal.Current.Value;

            var isMacdBullish = macdHistogram > 0;
            var isMacdBearish = macdHistogram < 0;

            var adxValue = _adx.Current.Value;
            var (medianAdx, lowerPercentilAdx, upperPercentilAdx) = ComputeAdxPercentiles(_adxWindow, AdxLowerPercentile, AdxUpperPercentile);

            // Conditions d'entrée/sortie dynamiques
            if (adxValue >= upperPercentilAdx && isMacdBullish)
            {
                if (!Portfolio.Invested)
                {
                    SetHoldings(_symbol, 1);
                }
            }
            else if (adxValue <= lowerPercentilAdx && isMacdBearish)
            {
                if (Portfolio.Invested)
                {
                    Liquidate(_symbol);
                }
            }
        }

        public (decimal median, decimal lowerPercentil, decimal upperPercentil) ComputeAdxPercentiles(RollingWindow<decimal> window, int lowerPercentile, int upperPercentile)
        {
            var sorted = window.OrderBy(x => x).ToList();
            int count = sorted.Count;
            if (count == 0) return (0, 0, 0);

            decimal median = sorted[count / 2];

            // Clamp les percentiles entre 0 et 100
            lowerPercentile = Math.Min(Math.Max(lowerPercentile, 0), 100);
            upperPercentile = Math.Min(Math.Max(upperPercentile, 0), 100);

            int lowerIndex = Math.Max(0, Math.Min(count - 1, count * lowerPercentile / 100));
            int upperIndex = Math.Max(0, Math.Min(count - 1, count * upperPercentile / 100));

            decimal lowerPercentil = sorted[lowerIndex];
            decimal upperPercentil = sorted[upperIndex];
            return (median, lowerPercentil, upperPercentil);
        }

        public override void OnOrderEvent(OrderEvent orderEvent)
        {
            if (orderEvent.Status == OrderStatus.Filled)
            {
                string operation = orderEvent.Direction == OrderDirection.Buy ? "Achat" : "Vente";
                string message = $"{Time.ToShortDateString()} - {operation} de {Math.Abs(orderEvent.FillQuantity)} {_symbol} @ {orderEvent.FillPrice} USDT. " +
                                 $"Portefeuille : {Portfolio.TotalPortfolioValue} USDT.";
                Log(message);
            }
        }

        private void InitPeriod()
        {
            // Période du backtest
            SetStartDate(2013, 04, 07);
            // Possibilité de définir une end date si nécessaire
            //SetEndDate(2023, 12, 31);
        }
    }
}
