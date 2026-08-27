"""Forma de referência do relatório de perfilamento.

Não é executado pelo harness — é material que o agente lê para saber o
formato esperado da saída.
"""

import pandas as pd


def perfil(caminho: str) -> pd.DataFrame:
    df = pd.read_csv(caminho)
    return pd.DataFrame(
        {
            "tipo": df.dtypes.astype(str),
            "ausentes": df.isna().sum(),
            "ausentes_pct": (df.isna().mean() * 100).round(1),
            "unicos": df.nunique(),
            "exemplo": df.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else None),
        }
    )
