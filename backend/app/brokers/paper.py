"""Paper execution adapter - the only execution adapter in this build.

It never contacts a broker. Fills are produced by `app.engines.execution`, so a
paper order and a backtest order are filled identically.
"""

from __future__ import annotations

import uuid

from app.brokers.base import ExecutionAdapter, OrderRequest, OrderResponse
from app.core.enums import Direction, OrderStatus
from app.core.logging import get_logger
from app.engines.execution import SlippageModel, simulate_entry

log = get_logger(__name__)


class PaperExecutionAdapter(ExecutionAdapter):
    name = "paper"
    is_paper = True

    def __init__(self, slippage: SlippageModel | None = None) -> None:
        self.slippage = slippage or SlippageModel()
        self._orders: dict[str, OrderResponse] = {}

    def place_order(self, request: OrderRequest) -> OrderResponse:
        order_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"
        reference = request.price or 0.0
        fill = simulate_entry(
            reference_price=reference,
            direction=Direction(request.side),
            quantity=request.quantity,
            slippage=self.slippage,
        )
        response = OrderResponse(
            order_id=order_id,
            status=OrderStatus.COMPLETE,
            message="Simulated fill - no order was sent to any broker.",
            average_price=fill.price,
            filled_quantity=request.quantity,
            is_simulated=True,
        )
        self._orders[order_id] = response
        log.info(
            "paper_order_placed",
            order_id=order_id,
            symbol=request.tradingsymbol,
            side=request.side,
            quantity=request.quantity,
        )
        return response

    def cancel_order(self, order_id: str) -> OrderResponse:
        existing = self._orders.get(order_id)
        if existing is None:
            return OrderResponse(order_id, OrderStatus.REJECTED, "Unknown simulated order.")
        existing.status = OrderStatus.CANCELLED
        existing.message = "Simulated order cancelled."
        return existing

    def order_status(self, order_id: str) -> OrderResponse:
        return self._orders.get(
            order_id,
            OrderResponse(order_id, OrderStatus.REJECTED, "Unknown simulated order."),
        )
