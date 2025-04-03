# region imports
from AlgorithmImports import *
import numpy as np
from datetime import timedelta, datetime
#endregion

class FilteredPairsAlphaModel(PearsonCorrelationPairsTradingAlphaModel):
    """
    Version modifiée pour:
    1) Implémenter un cooldown plus court (2 jours) pour du Hourly.
    2) lookback = 20 barres (plus réactif)
    3) resolution = Hourly
    4) Z-score threshold paramétrable (par défaut 2.0)
    """

    def __init__(self, lookback=20, resolution=Resolution.Hour, threshold=2.0, pairs=[], cooldown_days=2):
        """
        Args:
            lookback: nombre de barres historiques (20 en Hourly ~ ~3 journées)
            resolution: Hourly
            threshold: z-score threshold (±2)
            pairs: liste initiale de paires
            cooldown_days: cooldown (2 jours) => ~ 2 * 6.5 = 13 barres
        """
        super().__init__(lookback, resolution, threshold)
        self.pairs = pairs
        # On estime ~6.5h de marché par jour, donc 2 jours ~ 13 barres
        self.cooldown = timedelta(days=cooldown_days)

        # Pour chaque paire : store {"beta","mean","std"}
        self.spread_stats = {pair: {"beta": 1.0, "mean": 0, "std": 1} for pair in pairs}

        self.last_signal_time = {pair: datetime.min for pair in pairs}

    def update_pairs(self, new_pairs):
        self.pairs = new_pairs
        removed_pairs = set(self.spread_stats.keys()) - set(new_pairs)
        for rp in removed_pairs:
            self.spread_stats.pop(rp, None)
            self.last_signal_time.pop(rp, None)

        for p in new_pairs:
            if p not in self.spread_stats:
                self.spread_stats[p] = {"beta": 1.0, "mean": 0, "std": 1}
            if p not in self.last_signal_time:
                self.last_signal_time[p] = datetime.min

    def generate_insights(self, algorithm, data):
        insights = []
        log_messages = []

        for etf1, etf2 in self.pairs:
            # Check data dispos
            if etf1 not in data or etf2 not in data:
                log_messages.append(f"Data not available for pair {etf1}-{etf2}.")
                continue

            # cooldown check
            if (algorithm.Time - self.last_signal_time[(etf1, etf2)]) < self.cooldown:
                continue

            price1 = data[etf1].Close
            price2 = data[etf2].Close
            if price2 == 0:
                continue

            stats = self.spread_stats[(etf1, etf2)]
            # Beta(t+1) = 0.9 * beta(t) + 0.1 * (p1/p2)
            new_beta = 0.9 * stats["beta"] + 0.1 * (price1 / price2)
            stats["beta"] = new_beta

            spread = price1 - stats["beta"] * price2

            old_mean = stats["mean"]
            old_std = stats["std"]

            new_mean = 0.9 * old_mean + 0.1 * spread
            stats["mean"] = new_mean
            new_std = 0.9 * old_std + 0.1 * abs(spread - new_mean)
            stats["std"] = max(new_std, 1e-5)

            z_score = (spread - new_mean) / stats["std"]

            if z_score > self.threshold:
                insights.append(Insight.price(etf1, timedelta(hours=6), InsightDirection.Down))
                insights.append(Insight.price(etf2, timedelta(hours=6), InsightDirection.Up))
                log_messages.append(f"[{algorithm.Time}] SHORT {etf1} / LONG {etf2}, Z-score: {z_score:.2f}")
                self.last_signal_time[(etf1, etf2)] = algorithm.Time

            elif z_score < -self.threshold:
                insights.append(Insight.price(etf1, timedelta(hours=6), InsightDirection.Up))
                insights.append(Insight.price(etf2, timedelta(hours=6), InsightDirection.Down))
                log_messages.append(f"[{algorithm.Time}] LONG {etf1} / SHORT {etf2}, Z-score: {z_score:.2f}")
                self.last_signal_time[(etf1, etf2)] = algorithm.Time

        if log_messages:
            max_logs = 5
            algorithm.Log("\n".join(log_messages[:max_logs]))
            if len(log_messages) > max_logs:
                algorithm.Log(f"{len(log_messages) - max_logs} additional logs suppressed.")

        return insights

