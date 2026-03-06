import asyncio
import logging
import time
from typing import Dict, Optional, Any
from ib_insync import IB, util

# Importar configuración de logs (idealmente en common o utils)
# Se asume la existencia de un logger preconfigurado para errores críticos.
logger = logging.getLogger(__name__)
critical_logger = logging.getLogger("critical")

class ConnectionManager:
    """
    Gestiona la conexión con IBKR, incluyendo reconexión automática y backoff exponencial.
    Absorbe interrupciones del broker e implementa degradación ante pacing limits.
    """
    
    PACING_CODES = {162, 420, 10167}
    
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        
        self._ib = IB()
        self._is_connecting = False
        self._shutdown_requested = False
        self._reconnect_task: Optional[asyncio.Task] = None
        
        # Secuencia de backoff en segundos
        self._backoff_sequence = [1, 2, 4, 8, 16, 32, 60]
        self._current_backoff_index = 0
        
        # Estado de Pacing (throttling)
        self._last_pacing_violation: float = 0
        self._consecutive_pacing_rejects: int = 0
        self._pacing_backoff_until: float = 0
        
        # Callbacks y suscripciones
        self._ib.disconnectedEvent += self._on_disconnected
        self._ib.errorEvent += self._on_error

    async def connect(self) -> bool:
        """Conecta asíncronamente a IBKR."""
        if self.is_connected():
            self._is_connecting = False
            return True
            
        if not self._is_connecting:
            self._is_connecting = True
        
        while not self._shutdown_requested:
            try:
                # Utilizamos connectAsync que no bloquea el event loop
                await self._ib.connectAsync(
                    self.host, 
                    self.port, 
                    clientId=self.client_id, 
                    timeout=5.0
                )
                logger.info("Conectado a IBKR de forma exitosa.")
                self._current_backoff_index = 0  # Reset backoff tras éxito
                self._is_connecting = False
                return True
                
            except asyncio.CancelledError:
                logger.info("Tarea de conexión cancelada.")
                self._is_connecting = False
                raise
            except Exception as e:
                wait_time = self._backoff_sequence[self._current_backoff_index]
                logger.warning(f"Error conectando a IBKR: {e}. Reintentando en {wait_time}s...")
                
                # Avanzar en la secuencia de backoff sin superar el máximo (60s)
                if self._current_backoff_index < len(self._backoff_sequence) - 1:
                    self._current_backoff_index += 1
                    
                try:
                    await asyncio.sleep(wait_time)
                except asyncio.CancelledError:
                    logger.info("Espera de reconexión cancelada.")
                    self._is_connecting = False
                    raise
                
        self._is_connecting = False
        return False

    def is_connected(self) -> bool:
        """Retorna si existe conexión activa con el broker."""
        return self._ib.isConnected()

    def disconnect(self) -> None:
        """Cierra la conexión explícitamente y detiene intentos de reconexión."""
        self._shutdown_requested = True
        
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            
        if self.is_connected():
            self._ib.disconnect()
            logger.info("Desconectado de IBKR por solicitud del sistema.")

    def _on_disconnected(self) -> None:
        """Callback ejecutado por ib_insync al detectar desconexión (ej. reinicio TWS)."""
        if self._shutdown_requested or self._is_connecting:
            return
            
        if self._reconnect_task and not self._reconnect_task.done():
            return
            
        critical_logger.error("Desconexión detectada. Posible reinicio de TWS. Registrando hueco esperado.")
        
        self._is_connecting = True
        
        # Se lanza la tarea de reconexión en el event loop activo
        if util.isAsyncIO():
            self._reconnect_task = asyncio.create_task(self.connect())

    def _on_error(self, reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
        """
        Intercepta errores del broker, específicamente enfocándose en
        límites de pacing para aplicar las políticas correspondientes.
        """
        # Pacing violation / Throttling codes en IBKR suelen ser 162 o códigos de la familia 160+
        # y rechazos repetitivos (200, etc. relacionados con saturación).
        if "pacing violation" in errorString.lower() or errorCode in self.PACING_CODES:
            self._handle_pacing_limit(reqId, errorCode, errorString)
            
    def _handle_pacing_limit(self, reqId: int, errorCode: int, errorString: str) -> None:
        """Aplica la política de degradación ante pacing limits prescrita en Fase 0."""
        now = time.monotonic()
        
        # Ante un nuevo límite, si ocurrió poco tiempo después del anterior, contamos como consecutivo.
        if now - self._last_pacing_violation < 60:
            self._consecutive_pacing_rejects += 1
        else:
            self._consecutive_pacing_rejects = 1
            
        self._last_pacing_violation = now
        
        if self._consecutive_pacing_rejects >= 3:
            # Backoff exponencial adicional, máximo 5 minutos (300 segundos)
            pause_time = min(10 * (2 ** (self._consecutive_pacing_rejects - 3)), 300)
            self._pacing_backoff_until = now + pause_time
            critical_logger.error(
                f"Pacing limit crítico (>3 rechazos). Pausando solicitudes por {pause_time}s. "
                f"reqId: {reqId}, error: {errorCode} - {errorString}"
            )
        else:
            # Pausa mínima de 10 segundos ante throttling sencillo
            self._pacing_backoff_until = now + 10
            critical_logger.warning(
                f"Throttling del broker. Pausando solicitudes por 10s. "
                f"reqId: {reqId}, error: {errorCode} - {errorString}"
            )

    def _reset_pacing_state(self) -> None:
        """Restablece el estado de los rechazos consecutivos por pacing."""
        self._consecutive_pacing_rejects = 0

    def can_request(self) -> bool:
        """Verifica si el Manager está habilitado para realizar solicitudes al broker."""
        return (
            self.is_connected()
            and not self._is_connecting
            and time.monotonic() >= self._pacing_backoff_until
        )

    # --------------------------------------------------------------------------
    # Interfaces públicas hacia handlers (Historical y RealTime)
        
    async def request_historical_bars(self, *args, **kwargs) -> Any:
        """
        Interfaz provisional de Fase 0.
        Será reemplazado por HistoricalHandler en Stage 2.
        ConnectionManager no debe acumular lógica de datos: su responsabilidad es gestionar el canal.
        """
        if not self.can_request():
            logger.warning("Solicitud ignorada: Pacing timeout activo o sistema desconectado.")
            return None
        return await self._ib.reqHistoricalDataAsync(*args, **kwargs)

    def subscribe_realtime_bars(self, *args, **kwargs) -> Any:
        """
        Interfaz provisional de Fase 0.
        Será reemplazado por RealTimeHandler en Stage 3.
        ConnectionManager no debe acumular lógica de datos: su responsabilidad es gestionar el canal.
        """
        if not self.can_request():
            logger.warning("Suscripción ignorada: Pacing timeout activo o sistema desconectado.")
            return None
        return self._ib.reqRealTimeBars(*args, **kwargs)
