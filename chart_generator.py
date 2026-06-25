#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
import mplfinance as mpf

KST = timezone(timedelta(hours=9))


def generate_chart(ohlcv_data: list, hours: int, output_path: str) -> str:
    """OHLCV 데이터로 4H 캔들차트 PNG 생성.

    Args:
        ohlcv_data: [{"time": "YYYY-MM-DD HH:MM", "open":..., "high":..., "low":..., "close":..., "volume":...}]
        hours: 표시할 시간 범위 (48 또는 72)
        output_path: 저장할 PNG 파일 경로

    Returns:
        저장된 파일 경로 (output_path 그대로)
    """
    n_candles = hours // 4
    data = ohlcv_data[-n_candles:] if len(ohlcv_data) >= n_candles else ohlcv_data

    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['time'])
    df = df.set_index('Date')
    df = df.rename(columns={
        'open': 'Open', 'high': 'High',
        'low': 'Low', 'close': 'Close', 'volume': 'Volume'
    })
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

    current_price = float(df['Close'].iloc[-1])

    mc = mpf.make_marketcolors(
        up='#26a69a', down='#ef5350',
        edge='inherit', wick='inherit',
        volume={'up': '#26a69a80', 'down': '#ef535080'}
    )
    style = mpf.make_mpf_style(
        base_mpf_style='nightclouds',
        marketcolors=mc,
        gridstyle='--',
        gridcolor='#2a2a2a',
        facecolor='#131722',
        figcolor='#131722',
        rc={'axes.labelcolor': '#b2b5be', 'xtick.color': '#b2b5be', 'ytick.color': '#b2b5be'}
    )

    current_line = mpf.make_addplot(
        [current_price] * len(df),
        color='#FFD700', width=1.2, linestyle='--', alpha=0.8
    )

    now_str = datetime.now(KST).strftime('%Y.%m.%d %H:%M KST')
    title = f'BTCUSDT 4H  ·  ${current_price:,.0f}  ·  {now_str}'

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    mpf.plot(
        df,
        type='candle',
        volume=True,
        style=style,
        title=title,
        addplot=current_line,
        figsize=(12, 7),
        savefig=dict(fname=output_path, dpi=150, bbox_inches='tight'),
        warn_too_much_data=500
    )

    return output_path
