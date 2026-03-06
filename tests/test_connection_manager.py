import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from production.data_layer.connection_manager import ConnectionManager
import time


@pytest.fixture
def connection_manager():
    return ConnectionManager(host="127.0.0.1", port=7497, client_id=999)


@pytest.mark.asyncio
async def test_connect_success(connection_manager):
    with patch.object(connection_manager.ib, "connectAsync", new_callable=AsyncMock) as mock_connect:
        result = await connection_manager.connect()
        
        assert result is True
        assert connection_manager._current_backoff_index == 0
        mock_connect.assert_called_once_with("127.0.0.1", 7497, clientId=999, timeout=5.0)


@pytest.mark.asyncio
async def test_connect_retry_backoff(connection_manager):
    # Simulamos que falla las 2 primeras veces y conecta en la 3ra
    connection_manager.ib.connectAsync = AsyncMock(side_effect=[Exception("1"), Exception("2"), None])
    
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await connection_manager.connect()
        
        assert result is True
        assert mock_sleep.call_count == 2
        
        # Debe haber hecho sleep(1) y sleep(2) según secuencia: [1, 2, 4...]
        expected_calls = [1, 2]
        actual_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_calls == expected_calls
        
        assert connection_manager._current_backoff_index == 0


def test_disconnect(connection_manager):
    connection_manager.ib.isConnected = MagicMock(return_value=True)
    connection_manager.ib.disconnect = MagicMock()
    
    connection_manager.disconnect()
    
    assert connection_manager._shutdown_requested is True
    connection_manager.ib.disconnect.assert_called_once()


def test_pacing_limit_handling(connection_manager):
    reqId = 1
    errorCode = 162
    errorString = "Historical Market Data Service error message:API pacing violation"
    
    now = time.time()
    
    # 1er rechazo
    with patch("time.time", return_value=now):
        connection_manager._handle_pacing_limit(reqId, errorCode, errorString)
        assert connection_manager._consecutive_pacing_rejects == 1
        assert connection_manager._pacing_backoff_until == now + 10 # Pausa mínima 10s
        
    # 2do rechazo (< 60s después)
    with patch("time.time", return_value=now + 5):
        connection_manager._handle_pacing_limit(reqId, errorCode, errorString)
        assert connection_manager._consecutive_pacing_rejects == 2
        assert connection_manager._pacing_backoff_until == now + 5 + 10
        
    # 3er rechazo crítico
    with patch("time.time", return_value=now + 10):
        connection_manager._handle_pacing_limit(reqId, errorCode, errorString)
        assert connection_manager._consecutive_pacing_rejects == 3
        # 10 * 2^(3-3) = 10s adicionales
        assert connection_manager._pacing_backoff_until == now + 10 + 10
        
    # 4to rechazo crítico
    with patch("time.time", return_value=now + 15):
        connection_manager._handle_pacing_limit(reqId, errorCode, errorString)
        assert connection_manager._consecutive_pacing_rejects == 4
        # 10 * 2^(4-3) = 20s
        assert connection_manager._pacing_backoff_until == now + 15 + 20
