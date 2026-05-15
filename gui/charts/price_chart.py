import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHBoxLayout, QComboBox, QLabel
from PyQt6.QtGui import QPainter, QBrush, QPen
from PyQt6.QtCore import QPointF, QRectF
import pandas as pd
import numpy as np


def _visible_data(data, vb):
    if not data or vb is None:
        return data
    x_min, x_max = vb.viewRange()[0]
    lo = max(0, int(x_min) - 1)
    hi = min(len(data) - 1, int(x_max) + 2)
    return data[lo:hi + 1]


class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self._data = data  # list of (x, open, close, low, high)

    def paint(self, p, opt, widget=None):
        if not self._data:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = 0.4
        for x, open_, close, low, high in _visible_data(self._data, self.getViewBox()):
            if not (np.isfinite(open_) and np.isfinite(close) and
                    np.isfinite(low) and np.isfinite(high)):
                continue
            color = pg.mkColor('#26a69a') if close >= open_ else pg.mkColor('#ef5350')
            wick = QPen(color)
            wick.setWidthF(1.0)
            wick.setCosmetic(True)
            p.setPen(wick)
            p.drawLine(QPointF(x, low), QPointF(x, high))
            body = QPen(color)
            body.setWidthF(0)
            p.setPen(body)
            p.setBrush(QBrush(color))
            p.drawRect(QRectF(x - w, min(open_, close), w * 2, abs(close - open_) or 0.01))

    def boundingRect(self):
        if not self._data:
            return QRectF()
        xs = [d[0] for d in self._data]
        lows = [d[3] for d in self._data if np.isfinite(d[3]) and np.isfinite(d[4])]
        highs = [d[4] for d in self._data if np.isfinite(d[3]) and np.isfinite(d[4])]
        if not lows:
            return QRectF()
        return QRectF(min(xs) - 0.5, min(lows), max(xs) - min(xs) + 1, max(highs) - min(lows))


class OHLCItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self._data = data  # list of (x, open, close, low, high)

    def paint(self, p, opt, widget=None):
        if not self._data:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = 0.3
        for x, open_, close, low, high in _visible_data(self._data, self.getViewBox()):
            if not (np.isfinite(open_) and np.isfinite(close) and
                    np.isfinite(low) and np.isfinite(high)):
                continue
            color = pg.mkColor('#26a69a') if close >= open_ else pg.mkColor('#ef5350')
            pen = QPen(color)
            pen.setWidthF(1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(QPointF(x, low), QPointF(x, high))
            p.drawLine(QPointF(x - w, open_), QPointF(x, open_))
            p.drawLine(QPointF(x, close), QPointF(x + w, close))

    def boundingRect(self):
        if not self._data:
            return QRectF()
        xs = [d[0] for d in self._data]
        lows = [d[3] for d in self._data if np.isfinite(d[3]) and np.isfinite(d[4])]
        highs = [d[4] for d in self._data if np.isfinite(d[3]) and np.isfinite(d[4])]
        if not lows:
            return QRectF()
        return QRectF(min(xs) - 0.5, min(lows), max(xs) - min(xs) + 1, max(highs) - min(lows))


def heikin_ashi(df: pd.DataFrame) -> list:
    close = df["close"].values
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    ha_close = (open_ + high + low + close) / 4
    ha_open = np.empty(n)
    ha_open[0] = (open_[0] + close[0]) / 2
    for i in range(1, n):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2
    ha_high = np.maximum(high, np.maximum(ha_open, ha_close))
    ha_low = np.minimum(low, np.minimum(ha_open, ha_close))
    return list(zip(ha_open, ha_close, ha_low, ha_high))


class DateAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dates = []

    def set_dates(self, dates):
        self._dates = list(dates)

    def tickStrings(self, values, scale, spacing):
        result = []
        for v in values:
            idx = int(round(v))
            if 0 <= idx < len(self._dates):
                d = self._dates[idx]
                result.append(d.strftime('%d %b %y') if hasattr(d, 'strftime') else str(d))
            else:
                result.append('')
        return result


class PriceChart(QWidget):
    def __init__(self):
        super().__init__()
        self.df = None
        self._updating = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        toggle_row = QHBoxLayout()

        self.chart_type = QComboBox()
        self.chart_type.addItems(["Candlestick", "Heikin-Ashi", "OHLC", "Linje"])
        self.chart_type.currentIndexChanged.connect(self._redraw)
        toggle_row.addWidget(QLabel("Graftype:"))
        toggle_row.addWidget(self.chart_type)
        toggle_row.addSpacing(16)

        self.cb_sma20 = QCheckBox("SMA 20")
        self.cb_sma50 = QCheckBox("SMA 50")
        self.cb_sma200 = QCheckBox("SMA 200")
        self.cb_bb = QCheckBox("Bollinger Bands")
        self.cb_stoch = QCheckBox("Stochastic")
        for cb in (self.cb_sma20, self.cb_sma50, self.cb_sma200, self.cb_bb, self.cb_stoch):
            cb.setChecked(True)
            cb.stateChanged.connect(self._redraw)
            toggle_row.addWidget(cb)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        self.graphics = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics)

        self._x_axis = DateAxis(orientation='bottom')
        self.price_plot = self.graphics.addPlot(row=0, col=0, axisItems={'bottom': self._x_axis})
        self.price_plot.showGrid(x=True, y=True, alpha=0.3)
        self.price_plot.setLabel("left", "Kurs")
        self.price_plot.getAxis('bottom').setStyle(showValues=False)

        self.volume_plot = self.graphics.addPlot(row=1, col=0)
        self.volume_plot.showGrid(x=True, y=True, alpha=0.3)
        self.volume_plot.setLabel("left", "Volumen")
        self.volume_plot.setMaximumHeight(120)
        self.volume_plot.setXLink(self.price_plot)
        self.volume_plot.getAxis('bottom').setStyle(showValues=False)

        self.rsi_plot = self.graphics.addPlot(row=2, col=0)
        self.rsi_plot.showGrid(x=True, y=True, alpha=0.3)
        self.rsi_plot.setLabel("left", "RSI")
        self.rsi_plot.setMaximumHeight(100)
        self.rsi_plot.setXLink(self.price_plot)
        self.rsi_plot.addLine(y=70, pen=pg.mkPen("r", style=pg.QtCore.Qt.PenStyle.DashLine))
        self.rsi_plot.addLine(y=30, pen=pg.mkPen("g", style=pg.QtCore.Qt.PenStyle.DashLine))
        self.rsi_plot.getAxis('bottom').setStyle(showValues=False)

        self.stoch_plot = self.graphics.addPlot(row=3, col=0)
        self.stoch_plot.showGrid(x=True, y=True, alpha=0.3)
        self.stoch_plot.setLabel("left", "Stoch")
        self.stoch_plot.setMaximumHeight(100)
        self.stoch_plot.setXLink(self.price_plot)
        self.stoch_plot.addLine(y=80, pen=pg.mkPen("r", style=pg.QtCore.Qt.PenStyle.DashLine))
        self.stoch_plot.addLine(y=20, pen=pg.mkPen("g", style=pg.QtCore.Qt.PenStyle.DashLine))
        self.stoch_plot.getAxis('bottom').setStyle(showValues=False)

        self._sel_axis = DateAxis(orientation='bottom')
        self.selector_plot = self.graphics.addPlot(row=4, col=0, axisItems={'bottom': self._sel_axis})
        self.selector_plot.setMaximumHeight(60)
        self.selector_plot.showGrid(x=False, y=False)
        self.selector_plot.setLabel("left", "")
        self.selector_plot.getAxis('left').setWidth(45)
        self.selector_plot.setMouseEnabled(x=False, y=False)
        self.selector_plot.hideButtons()

        self.region = pg.LinearRegionItem()
        self.region.setZValue(10)
        self.selector_plot.addItem(self.region)

        self.region.sigRegionChanged.connect(self._on_region_changed)
        self.price_plot.sigXRangeChanged.connect(self._on_price_range_changed)
        self._first_load = True
        self._saved_range = (0, 90)

        self.graphics.ci.layout.setRowStretchFactor(0, 4)
        self.graphics.ci.layout.setRowStretchFactor(1, 1)
        self.graphics.ci.layout.setRowStretchFactor(2, 1)
        self.graphics.ci.layout.setRowStretchFactor(3, 1)
        self.graphics.ci.layout.setRowStretchFactor(4, 0)

    def _on_region_changed(self):
        if self._updating:
            return
        self._updating = True
        rmin, rmax = self.region.getRegion()
        self.price_plot.setXRange(rmin, rmax, padding=0)
        self._updating = False

    def _on_price_range_changed(self, _, range_):
        if self._updating:
            return
        self._updating = True
        self.region.setRegion(range_)
        self._updating = False

    def get_visible_dates(self):
        if self.df is None or self.df.empty:
            return None, None
        x_min, x_max = self.region.getRegion()
        dates = self.df["date"].tolist()
        n = len(dates)
        i_min = max(0, int(x_min))
        i_max = min(n - 1, int(x_max))
        import datetime
        def to_dt(d, end=False):
            t = datetime.time(23, 59, 59) if end else datetime.time()
            return datetime.datetime.combine(d, t) if hasattr(d, 'year') else d
        return to_dt(dates[i_min]), to_dt(dates[i_max], end=True)

    def plot(self, df: pd.DataFrame, ticker: str = ""):
        self.df = df
        self._first_load = True
        self.price_plot.setTitle(ticker)
        self._redraw()

    def _redraw(self):
        try:
            self._do_redraw()
        except Exception as e:
            import traceback
            with open("/tmp/stockapp_crash.log", "a") as f:
                f.write(traceback.format_exc())
            print(f"REDRAW FEJL: {e}")

    def _do_redraw(self):
        if self.df is None or self.df.empty:
            return
        if not self._first_load:
            self._saved_range = self.region.getRegion()

        df = self.df
        x = np.arange(len(df))
        dates = df["date"].tolist()

        self._x_axis.set_dates(dates)
        self._sel_axis.set_dates(dates)

        self.price_plot.clear()
        self.volume_plot.clear()
        self.rsi_plot.clear()
        self.stoch_plot.clear()
        self.selector_plot.clear()
        self.selector_plot.addItem(self.region)

        n = len(x)
        if self._first_load:
            init_start = max(0, n - 90)
        else:
            init_start, _ = self._saved_range

        self._updating = True
        self.price_plot.setXRange(int(init_start), n - 1, padding=0)
        self.price_plot.enableAutoRange(axis='x', enable=False)
        self._updating = False

        chart = self.chart_type.currentText()
        if chart == "Linje":
            self.price_plot.plot(x, df["close"].values, pen=pg.mkPen("w", width=1.5), connect='finite')
        elif chart == "OHLC":
            ohlc_data = list(zip(x, df["open"].values, df["close"].values,
                                 df["low"].values, df["high"].values))
            self.price_plot.addItem(OHLCItem(ohlc_data))
        elif chart == "Heikin-Ashi":
            ha = heikin_ashi(df)
            ha_data = list(zip(x, [h[0] for h in ha], [h[1] for h in ha],
                               [h[2] for h in ha], [h[3] for h in ha]))
            self.price_plot.addItem(CandlestickItem(ha_data))
        else:
            candle_data = list(zip(x, df["open"].values, df["close"].values,
                                   df["low"].values, df["high"].values))
            self.price_plot.addItem(CandlestickItem(candle_data))

        kw = dict(connect='finite')
        if self.cb_sma20.isChecked() and "sma_20" in df:
            self.price_plot.plot(x, df["sma_20"].values, pen=pg.mkPen("y", width=1), **kw)
        if self.cb_sma50.isChecked() and "sma_50" in df:
            self.price_plot.plot(x, df["sma_50"].values, pen=pg.mkPen("c", width=1), **kw)
        if self.cb_sma200.isChecked() and "sma_200" in df:
            self.price_plot.plot(x, df["sma_200"].values, pen=pg.mkPen("m", width=1), **kw)
        if self.cb_bb.isChecked() and "bb_upper" in df:
            self.price_plot.plot(x, df["bb_upper"].values, pen=pg.mkPen((100, 100, 255), width=1), **kw)
            self.price_plot.plot(x, df["bb_lower"].values, pen=pg.mkPen((100, 100, 255), width=1), **kw)

        vol = np.nan_to_num(df["volume"].values, nan=0.0, posinf=0.0, neginf=0.0)
        self.volume_plot.addItem(pg.BarGraphItem(x=x, height=vol, width=0.8, brush="b"))

        if "rsi_14" in df:
            self.rsi_plot.plot(x, df["rsi_14"].values, pen=pg.mkPen("g", width=1.2), **kw)
            self.rsi_plot.addLine(y=70, pen=pg.mkPen("r", style=pg.QtCore.Qt.PenStyle.DashLine))
            self.rsi_plot.addLine(y=30, pen=pg.mkPen("g", style=pg.QtCore.Qt.PenStyle.DashLine))

        self.stoch_plot.setVisible(self.cb_stoch.isChecked())
        if self.cb_stoch.isChecked() and "stoch_k" in df:
            self.stoch_plot.plot(x, df["stoch_k"].values, pen=pg.mkPen("y", width=1.2), **kw)
            self.stoch_plot.plot(x, df["stoch_d"].values, pen=pg.mkPen("r", width=1), **kw)
            self.stoch_plot.addLine(y=80, pen=pg.mkPen("r", style=pg.QtCore.Qt.PenStyle.DashLine))
            self.stoch_plot.addLine(y=20, pen=pg.mkPen("g", style=pg.QtCore.Qt.PenStyle.DashLine))

        self.selector_plot.plot(x, df["close"].values, pen=pg.mkPen((150, 150, 150), width=1), connect='finite')

        self.price_plot.setXRange(int(init_start), n - 1, padding=0)
        self.region.setBounds([0, n - 1])
        if self._first_load:
            self.region.setRegion([max(0, n - 90), n - 1])
            self._first_load = False
        else:
            rmin, rmax = self._saved_range
            self.region.setRegion([max(0, rmin), min(n - 1, rmax)])
