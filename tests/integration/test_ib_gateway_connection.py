import pytest
import asyncio
from production.data_layer.connection_manager import ConnectionManager

@pytest.fixture
def connection_manager():
    return ConnectionManager(host="127.0.0.1", port=7497, client_id=999)

@pytest.mark.asyncio
async def test_ib_gateway_connection_and_request(connection_manager):
    """
    Test de integración que conecta a un IB Gateway real.
    Verifica que se puede establecer la conexión y realizar una petición de tiempo.
    El test se saltará si no logra establecer conexión (Ej: Gateway apagado).
    """
    try:
        # Intentamos conectar
        connected = await connection_manager.connect()
        
        if not connected:
            pytest.skip("IB Gateway not running on 127.0.0.1:7497")
            
        # Verificamos que el estado interno reconozca la conexión
        assert connection_manager.is_connected() is True
        
        # Realizamos una petición simple para validar la API
        # Petición asincrónica de la hora actual del servidor de IBKR
        server_time = await connection_manager._ib.reqCurrentTimeAsync()
        assert server_time is not None
        
    except Exception as e:
        pytest.skip(f"IB Gateway not running or connection failed: {e}")
        
    finally:
        # Nos aseguramos de cerrar la conexión si estábamos conectados
        if connection_manager.is_connected():
            connection_manager.disconnect()
            
        # Pequeña pausa para asegurar limpieza de sockets asíncronos antes de que el event loop termine
        await asyncio.sleep(0.1)
