import asyncio
import logging
import pandas as pd
from ib_insync import Contract, BarData

from .connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class HistoricalHandler:
    """
    Gestiona la descarga y normalización de datos históricos desde IBKR.

    Responsabilidades:
    - Solicitar datos históricos mediante ConnectionManager.
    - Gestionar la recepción completa de la respuesta.
    - Normalizar barras recibidas al Canonical Data Model.
    - Entregar barras normalizadas al DataDispatcher (que lo invocará).

    Restricciones:
    - No persiste datos.
    - No realiza resampling.
    - No imputa valores ausentes (ADR-001).
    - No accede al estado interno del ConnectionManager.
    """

    def __init__(self, connection_manager: ConnectionManager):
        self._cm = connection_manager

    # ------------------------------------------------------------------
    # Normalización
    # ------------------------------------------------------------------

    def _normalize_to_canonical(self, bars: list[BarData]) -> pd.DataFrame:
        """
        Convierte una lista de ib_insync.BarData al Canonical Data Model.

        Canonical Data Model (estructura obligatoria de salida):
            index : DatetimeIndex[datetime64[ns, UTC], name="timestamp"]
            open  : float64
            high  : float64
            low   : float64
            close : float64
            volume: Int64   (nullable — None si IBKR devuelve -1)
            barCount: Int64 (nullable — None si IBKR devuelve -1)

        Nota sobre volume == 0:
            IBKR puede devolver volume=0 tanto para barras con cero operaciones
            reales como en contextos donde el dato no está disponible. No se
            interpreta aquí; se persiste el valor tal como llega. La distinción
            semántica corresponde a Strategy (ADR-001).

        No se aplica fillna, ffill ni bfill. Los NaN se propagan tal como
        los produce la fuente. (ADR-001)
        """
        if not bars:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume", "barCount"],
                index=pd.DatetimeIndex([], name="timestamp", tz="UTC"),
            ).astype({
                "open":     "float64",
                "high":     "float64",
                "low":      "float64",
                "close":    "float64",
                "volume":   "Int64",
                "barCount": "Int64",
            })

        data = []
        for bar in bars:
            data.append({
                "timestamp": bar.date,
                "open":      float(bar.open),
                "high":      float(bar.high),
                "low":       float(bar.low),
                "close":     float(bar.close),
                "volume":    int(bar.volume)   if bar.volume   != -1 else None,
                "barCount":  int(bar.barCount) if bar.barCount != -1 else None,
            })

        df = pd.DataFrame(data)

        # Timestamp — errors="coerce" convierte valores no parseables en NaT
        # en lugar de lanzar excepción, evitando corrupciones silenciosas.
        # IBKR puede entregar bar.date en múltiples formatos dependiendo del
        # tipo de barra y del parámetro formatDate; utc=True normaliza todos.
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        df = df[["timestamp", "open", "high", "low", "close", "volume", "barCount"]]
        df = df.astype({
            "open":     "float64",
            "high":     "float64",
            "low":      "float64",
            "close":    "float64",
            "volume":   "Int64",
            "barCount": "Int64",
        })
        df = df.set_index("timestamp")

        # Eliminar filas con timestamp inválido (NaT producido por errors="coerce").
        # Una barra sin timestamp no es una barra válida.
        df = df[~df.index.isna()]

        # Garantizar índice monotónicamente creciente.
        # IBKR casi siempre entrega barras ordenadas, pero no es contractual.
        # Resampling y rolling requieren este invariante.
        df = df.sort_index()

        # Eliminar duplicados de timestamp. IBKR puede producirlos en
        # reconexiones o reintentos bajo pacing. Se conserva la última
        # barra recibida para cada timestamp, asumiendo que es la más completa.
        df = df[~df.index.duplicated(keep="last")]

        return df

    # ------------------------------------------------------------------
    # Solicitud a IBKR
    # ------------------------------------------------------------------

    async def fetch_historical_bars(
        self,
        contract: Contract,
        endDateTime: str = "",
        durationStr: str = "1 D",
        barSizeSetting: str = "1 min",
        whatToShow: str = "TRADES",
        useRTH: bool = True,
        formatDate: int = 2,
        keepUpToDate: bool = False,
    ) -> pd.DataFrame:
        """
        Solicita datos históricos a IBKR y retorna un DataFrame canónico.

        El DataDispatcher es quien orquesta la activación de RealTimeBars
        después de confirmar la recepción completa del histórico. Este método
        solo gestiona la descarga histórica; keepUpToDate debe ser False en
        Fase 0.

        Retorna un DataFrame canónico vacío (esquema válido, cero filas) ante
        cualquier condición que impida obtener datos, para no romper el pipeline.
        Todos los fallos quedan registrados en log con contexto de contrato completo.
        """
        uid_str = (
            f"{contract.symbol} | conId={contract.conId} "
            f"| exchange={contract.exchange} | secType={contract.secType}"
        )

        # --- Verificación de disponibilidad del ConnectionManager ---
        request_status = self._cm.get_request_status()

        if request_status == "disconnected":
            logger.error(
                f"[HistoricalHandler] Desconectado de IBKR. "
                f"Fetch abortado. Contrato: {uid_str}"
            )
            return self._normalize_to_canonical([])

        if request_status == "pacing_limited":
            logger.warning(
                f"[HistoricalHandler] Pacing limit activo. "
                f"Fetch abortado. Contrato: {uid_str}"
            )
            return self._normalize_to_canonical([])

        # --- Solicitud ---
        try:
            logger.info(
                f"[HistoricalHandler] Solicitando historical bars. "
                f"Contrato: {uid_str} | duration={durationStr} | barSize={barSizeSetting}"
            )

            bars = await self._cm.request_historical_bars(
                contract,
                endDateTime=endDateTime,
                durationStr=durationStr,
                barSizeSetting=barSizeSetting,
                whatToShow=whatToShow,
                useRTH=useRTH,
                formatDate=formatDate,
                keepUpToDate=keepUpToDate,
            )

            if bars is None:
                logger.warning(
                    f"[HistoricalHandler] request_historical_bars retornó None. "
                    f"Posible pacing o desconexión durante solicitud. Contrato: {uid_str}"
                )
                return self._normalize_to_canonical([])

            logger.info(
                f"[HistoricalHandler] Barras recibidas: {len(bars)}. "
                f"Contrato: {uid_str}"
            )

            # Notificar al ConnectionManager que la solicitud completó exitosamente.
            # La gestión interna del estado de pacing es responsabilidad exclusiva del CM.
            self._cm.notify_request_complete()

            return self._normalize_to_canonical(bars)

        except asyncio.CancelledError:
            raise

        except Exception as e:
            logger.error(
                f"[HistoricalHandler] Excepción durante fetch. "
                f"Contrato: {uid_str} | error={type(e).__name__}: {e}",
                exc_info=True,
            )
            return self._normalize_to_canonical([])