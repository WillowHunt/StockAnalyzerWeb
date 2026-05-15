import threading
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QStatusBar, QTabWidget
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from data.fetcher import fetch_and_store, load_prices, list_stored_tickers
from data.predefined import DANISH_STOCKS
from analysis.backtester import generate_signals, run_backtest, run_atr_backtest, load_signal_details
from gui.charts.price_chart import PriceChart
from gui.widgets.backtest_panel import BacktestPanel
from gui.widgets.news_window import NewsWindow


class FetchSignals(QObject):
    finished = pyqtSignal(str, int)
    error = pyqtSignal(str, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Analyzer")
        self.setMinimumSize(1200, 800)
        self._combo_tickers = []
        self._fetch_signals = FetchSignals()
        self._fetch_signals.finished.connect(self._on_fetched)
        self._fetch_signals.error.connect(lambda t, e: self.status_bar.showMessage(f"Fejl: {e}"))
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Toolbar
        toolbar = QHBoxLayout()
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("Ticker (f.eks. AAPL)")
        self.ticker_input.setMaximumWidth(150)
        self.ticker_input.returnPressed.connect(self._on_fetch)

        self.stored_combo = QComboBox()
        self.stored_combo.setMinimumWidth(180)
        self.stored_combo.addItem("— Gemte aktier —")
        self.stored_combo.currentIndexChanged.connect(self._on_stored_selected)
        self._refresh_stored_combo()

        self.period_combo = QComboBox()
        self.period_combo.addItems(["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"])
        self.period_combo.setCurrentText("1y")

        fetch_btn = QPushButton("Hent data")
        fetch_btn.clicked.connect(self._on_fetch)

        backtest_btn = QPushButton("Kør backtest")
        backtest_btn.clicked.connect(self._on_backtest)

        atr_btn = QPushButton("ATR Stop")
        atr_btn.clicked.connect(self._on_atr_backtest)
        atr_btn.setToolTip("Backtest med ATR Trailing Stop som exit-strategi (2× ATR, maks 60 dage)")

        news_btn = QPushButton("Nyheder")
        news_btn.clicked.connect(self._on_news)

        toolbar.addWidget(QLabel("Aktie:"))
        toolbar.addWidget(self.ticker_input)
        toolbar.addWidget(self.stored_combo)
        toolbar.addWidget(QLabel("Periode:"))
        toolbar.addWidget(self.period_combo)
        toolbar.addWidget(fetch_btn)
        toolbar.addWidget(backtest_btn)
        toolbar.addWidget(atr_btn)
        toolbar.addWidget(news_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Tabs
        self.tabs = QTabWidget()
        self.price_chart = PriceChart()
        self.backtest_panel = BacktestPanel()
        self.tabs.addTab(self.price_chart, "Kursgraf")
        self.tabs.addTab(self.backtest_panel, "Backtest")
        layout.addWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _start_fetch(self, ticker: str, period: str):
        signals = self._fetch_signals

        def run():
            try:
                count = fetch_and_store(ticker, period)
                generate_signals(ticker)
                signals.finished.emit(ticker, count)
            except Exception as e:
                signals.error.emit(ticker, str(e))

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _on_fetch(self):
        ticker = self.ticker_input.text().strip().upper()
        if not ticker:
            return
        period = self.period_combo.currentText()
        self._start_fetch(ticker, period)

    def _refresh_stored_combo(self):
        self.stored_combo.blockSignals(True)

        stored = {t: (n, span) for t, n, span in list_stored_tickers()}

        all_tickers = dict(DANISH_STOCKS)
        for t, (n, _) in stored.items():
            if t not in all_tickers:
                all_tickers[t] = n

        labels = ["— Vælg aktie —"]
        self._combo_tickers = [None]
        for ticker, name in sorted(all_tickers.items()):
            if ticker in stored:
                _, span = stored[ticker]
                label = f"{ticker}  {name}  [{span}]" if span else f"{ticker}  {name}"
            else:
                label = f"{ticker}  {name}  ·"
            labels.append(label)
            self._combo_tickers.append(ticker)

        model = QStandardItemModel(len(labels), 1, self.stored_combo)
        for i, label in enumerate(labels):
            model.setItem(i, 0, QStandardItem(label))
        self.stored_combo.setModel(model)

        self.stored_combo.blockSignals(False)

    def _on_stored_selected(self, index: int):
        if index < 0 or index >= len(self._combo_tickers):
            return
        ticker = self._combo_tickers[index]
        if not ticker:
            return
        self.ticker_input.setText(ticker)
        df = load_prices(ticker)
        if not df.empty:
            self.price_chart.plot(df, ticker)
            self.tabs.setCurrentIndex(0)
        else:
            period = self.period_combo.currentText()
            self.status_bar.showMessage(f"Henter {ticker}...")
            self._start_fetch(ticker, period)

    def _on_fetched(self, ticker: str, count: int):
        self.status_bar.showMessage(f"{ticker}: {count} nye rækker gemt.")
        self._refresh_stored_combo()
        df = load_prices(ticker)
        self.price_chart.plot(df, ticker)

    def _on_backtest(self):
        ticker = self.ticker_input.text().strip().upper()
        if not ticker:
            return
        results = run_backtest(ticker)
        details = load_signal_details(ticker)
        self.backtest_panel.show_results(ticker, results, details)
        self.tabs.setCurrentIndex(1)

    def _on_atr_backtest(self):
        ticker = self.ticker_input.text().strip().upper()
        if not ticker:
            return
        summary, details = run_atr_backtest(ticker)
        label = f"{ticker} — ATR Trailing Stop (2× ATR, maks 60 dage)"
        self.backtest_panel.show_results(label, summary, details)
        self.tabs.setCurrentIndex(1)

    def _on_news(self):
        ticker = self.ticker_input.text().strip().upper()
        if not ticker:
            return
        date_from, date_to = self.price_chart.get_visible_dates()
        dlg = NewsWindow(ticker, date_from, date_to, parent=self)
        dlg.show()
