import pytest
import pandas as pd
from datetime import datetime
from ib_insync import BarData, Contract
from production.data_layer.historical_handler import HistoricalHandler

class DummyConnectionManager:
    # Simula la verificación de Pacing para el HistoricalHandler
    def can_request(self) -> bool:
        return True
        
    async def request_historical_bars(self, contract, **kwargs):
        return []
        
    def _reset_pacing_state(self):
        pass

@pytest.fixture
def connection_manager():
    return DummyConnectionManager()

@pytest.fixture
def handler(connection_manager):
    return HistoricalHandler(connection_manager)

def test_normalize_empty_bars(handler):
    df_empty = handler._normalize_to_canonical([])
    
    assert isinstance(df_empty, pd.DataFrame)
    assert len(df_empty) == 0
    
    # Verificar columnas exactas (Canonical Data Model)
    expected_cols = ["open", "high", "low", "close", "volume", "barCount"]
    assert list(df_empty.columns) == expected_cols
    assert df_empty.index.name == "timestamp"
    
    # Verificar que el timestamp es datetime64[ns, UTC]
    assert isinstance(df_empty.index, pd.DatetimeIndex)
    assert str(df_empty.index.tz) == "UTC"

def test_normalize_valid_bars(handler):
    # Simulamos Bars recibidos de IB
    dt1 = datetime(2026, 3, 6, 10, 0, 0)
    dt2 = datetime(2026, 3, 6, 10, 1, 0)
    
    # Notemos que en un caso real, BarData.date puede venir como datetime tz-aware o str
    bars = [
        BarData(date=dt1, open=150.0, high=151.0, low=149.0, close=150.5, volume=1000, average=150.2, barCount=50),
        BarData(date=dt2, open=150.5, high=152.0, low=150.0, close=151.8, volume=1500, average=151.0, barCount=75),
        BarData(date=datetime(2026, 3, 6, 10, 2, 0), open=151.8, high=152.0, low=151.0, close=151.5, volume=-1, average=151.5, barCount=-1)
    ]
    
    df = handler._normalize_to_canonical(bars)
    
    assert len(df) == 3
    expected_cols = ["open", "high", "low", "close", "volume", "barCount"]
    assert list(df.columns) == expected_cols
    assert df.index.name == "timestamp"
    
    # Tipos
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"
    assert df["volume"].dtype.name == "Int64"
    assert df["barCount"].dtype.name == "Int64"
    
    # Valores
    assert df.iloc[0]["open"] == 150.0
    assert df.iloc[1]["close"] == 151.8
    assert df.iloc[0]["volume"] == 1000
    assert df.iloc[1]["barCount"] == 75
    
    # Valores missing
    assert pd.isna(df.iloc[2]["volume"])
    assert pd.isna(df.iloc[2]["barCount"])

@pytest.mark.asyncio
async def test_fetch_abort_on_pacing(handler):
    # Forzamos fallo de can_request
    handler._cm.can_request = lambda: False
    
    contract = Contract(symbol="AAPL", secType="STK", exchange="SMART", currency="USD")
    
    # Esta llamada no debería fallar sino devolver df vacío canónico
    df = await handler.fetch_historical_bars(contract)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert df.index.name == "timestamp"
    
@pytest.mark.asyncio
async def test_fetch_handles_none_from_manager(handler):
    # Simula pacing timeout interno en ConnectionManager
    handler._cm.request_historical_bars = lambda *args, **kwargs: __import__('asyncio').sleep(0).then(lambda: None) if False else fetch_none()

    async def fetch_none():
        return None
    
    handler._cm.request_historical_bars = fetch_none
    
    contract = Contract(symbol="AAPL", secType="STK", exchange="SMART", currency="USD")
    
    df = await handler.fetch_historical_bars(contract)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert df.index.name == "timestamp"
