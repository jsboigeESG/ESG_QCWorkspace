#region imports
from AlgorithmImports import *
#endregion

def reset_and_warm_up(algorithm, data_dict, resolution, lookback=None):
    """
    Réinitialise l'indicateur 'logr' et lui injecte de l'historique 
    pour démarrer avec un RollingWindow déjà rempli.

    Args:
        algorithm: instance QCAlgorithm
        data_dict: dict contenant "symbol", "logr", "consolidator"
        resolution: resolution des barres (ex: Resolution.Hourly)
        lookback: nombre de barres historiques à récupérer (défaut: WarmUpPeriod de l'indicateur)
    """
    indicator = data_dict["logr"]
    consolidator = data_dict["consolidator"]
    symbol = data_dict["symbol"]

    if not lookback:
        lookback = indicator.WarmUpPeriod

    # Récupérer l'historique sous forme de liste
    # On reste en DataNormalizationMode.Raw, c'est OK.
    bars = list(algorithm.History[TradeBar](
        symbol, 
        lookback, 
        resolution,
        dataNormalizationMode=DataNormalizationMode.Raw
    ))

    if len(bars) == 0:
        algorithm.Log(f"No history for {symbol}.")
        return consolidator  # On ne fait rien de plus

    # Reset de l'indicateur
    indicator.Reset()

    # Retirer l'ancien consolidator
    algorithm.SubscriptionManager.RemoveConsolidator(symbol, consolidator)
    # En Hourly, on peut consolider via un TradeBarConsolidator(TimeSpan.FromHours(1)) 
    # Mais celui-ci s'adapte automatiquement au 'resolution' s'il est déjà planifié.
    new_cons = TradeBarConsolidator(timedelta(hours=1))
    algorithm.RegisterIndicator(symbol, indicator, new_cons)

    # "Replay" des barres historiques pour remplir l'indicateur
    for bar in bars:
        new_cons.Update(bar)

    data_dict["consolidator"] = new_cons
    return new_cons

