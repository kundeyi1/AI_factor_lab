import ast

import numpy as np
import pandas as pd


ALLOWED_NAMES = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turn",
    "pctChg",
    "vwap",
    "log",
    "abs",
    "sign",
    "power",
    "ts_mean",
    "ts_std",
    "ts_rank",
    "ts_min",
    "ts_max",
    "ts_delta",
    "ts_delay",
    "ts_corr",
    "rank",
    "zscore",
}


class ExpressionValidator(ast.NodeVisitor):
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Mod,
    )

    def generic_visit(self, node):
        if not isinstance(node, self.allowed_nodes):
            raise ValueError(f"表达式包含不支持的语法：{type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id not in ALLOWED_NAMES:
            raise ValueError(f"表达式包含不支持的变量或函数：{node.id}")

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_NAMES:
            raise ValueError("表达式只能调用白名单函数。")
        for keyword in node.keywords:
            if keyword.arg is not None:
                raise ValueError("表达式不支持关键字参数。")
        self.generic_visit(node)


class FactorEngine:
    @staticmethod
    def calculate_factor(df: pd.DataFrame, expression: str) -> pd.Series:
        parsed = ast.parse(expression, mode="eval")
        ExpressionValidator().visit(parsed)

        df = df.sort_values(["stock_code", "date"]).copy()
        groups = df.groupby("stock_code", group_keys=False)
        dates = df["date"]

        def ts_rank(x, d):
            return x.groupby(df["stock_code"]).rolling(window=int(d)).rank(pct=True).reset_index(level=0, drop=True)

        def ts_corr(x, y, d):
            return x.groupby(df["stock_code"]).rolling(window=int(d)).corr(y).reset_index(level=0, drop=True)

        def zscore(x):
            mean = x.groupby(dates).transform("mean")
            std = x.groupby(dates).transform("std").replace(0, np.nan)
            return (x - mean) / std

        env = {
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": df["volume"],
            "amount": df["amount"],
            "turn": df["turn"],
            "pctChg": df["pctChg"],
            "vwap": df["vwap"],
            "log": np.log,
            "abs": np.abs,
            "sign": np.sign,
            "power": np.power,
            "ts_mean": lambda x, d: x.groupby(df["stock_code"]).rolling(window=int(d)).mean().reset_index(level=0, drop=True),
            "ts_std": lambda x, d: x.groupby(df["stock_code"]).rolling(window=int(d)).std().reset_index(level=0, drop=True),
            "ts_rank": ts_rank,
            "ts_min": lambda x, d: x.groupby(df["stock_code"]).rolling(window=int(d)).min().reset_index(level=0, drop=True),
            "ts_max": lambda x, d: x.groupby(df["stock_code"]).rolling(window=int(d)).max().reset_index(level=0, drop=True),
            "ts_delta": lambda x, d: x - groups[x.name].shift(int(d)) if getattr(x, "name", None) else x - x.groupby(df["stock_code"]).shift(int(d)),
            "ts_delay": lambda x, d: x.groupby(df["stock_code"]).shift(int(d)),
            "ts_corr": ts_corr,
            "rank": lambda x: x.groupby(dates).rank(pct=True),
            "zscore": zscore,
        }

        try:
            result = eval(compile(parsed, "<factor_expression>", "eval"), {"__builtins__": {}}, env)
        except Exception as exc:
            raise ValueError(f"因子表达式计算失败：{exc}") from exc

        series = pd.Series(result, index=df.index)
        return series.reindex(df.index)
