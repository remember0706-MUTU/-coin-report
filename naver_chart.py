import io
from pathlib import Path


def make_btc_chart(ohlcv_4h: list[dict]) -> bytes | None:
    """최근 60캔들 close 기반 BTC 4H 라인 차트 → PNG bytes. 실패 시 None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime

        candles = ohlcv_4h[-60:] if len(ohlcv_4h) > 60 else ohlcv_4h
        if not candles:
            return None

        times = [datetime.strptime(c["time"], "%Y-%m-%d %H:%M") for c in candles]
        closes = [c["close"] for c in candles]

        fig, ax = plt.subplots(figsize=(10, 5), facecolor="#1a1a2e")
        ax.set_facecolor("#1a1a2e")

        ax.plot(times, closes, color="#00d4ff", linewidth=1.5)
        ax.fill_between(times, closes, min(closes), alpha=0.15, color="#00d4ff")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=30, color="#aaaaaa", fontsize=8)
        plt.yticks(color="#aaaaaa", fontsize=8)

        for spine in ax.spines.values():
            spine.set_edgecolor("#333355")
        ax.grid(color="#222244", linestyle="--", linewidth=0.5)

        ax.set_title(f"BTC/USDT 4H — {candles[-1]['time']} KST", color="white", fontsize=11, pad=10)
        ax.set_ylabel("Price (USDT)", color="#aaaaaa", fontsize=9)

        current_price = closes[-1]
        ax.annotate(
            f"${current_price:,.0f}",
            xy=(times[-1], current_price),
            xytext=(10, 0),
            textcoords="offset points",
            color="#00d4ff",
            fontsize=9,
            fontweight="bold",
        )

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#1a1a2e")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        print(f"⚠️ 차트 생성 실패: {e}")
        return None
