from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..models import Order, OrderCreate, OrderStatusUpdate

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _next_order_id() -> str:
    db = get_db()
    last = db.orders.find_one(sort=[("created", -1)])
    if not last:
        return "ord-1001"
    try:
        n = int(str(last["id"]).split("-")[-1])
        return f"ord-{n + 1}"
    except Exception:
        return f"ord-{int(datetime.now(timezone.utc).timestamp())}"


@router.get("")
def list_orders(status: str | None = Query(None)) -> dict:
    db = get_db()
    q: dict = {}
    if status:
        q["status"] = status
    orders = [_clean(d) for d in db.orders.find(q).sort("created", -1)]
    return {"orders": orders}


@router.get("/{order_id}")
def get_order(order_id: str) -> dict:
    doc = get_db().orders.find_one({"id": order_id})
    if not doc:
        raise HTTPException(404, "Order not found")
    return _clean(doc)


@router.post("", status_code=201)
def create_order(body: OrderCreate) -> dict:
    db = get_db()
    subtotal = sum(line.subtotal for line in body.items)
    total = subtotal + body.delivery
    order = Order(
        id=_next_order_id(),
        channel=body.channel,
        created=datetime.now(timezone.utc),
        status="new",
        customer=body.customer,
        address=body.address,
        phone=body.phone,
        table=body.table,
        items=body.items,
        subtotal=subtotal,
        delivery=body.delivery,
        total=total,
        etaMinutes=body.etaMinutes,
    )
    db.orders.insert_one(order.model_dump())
    return order.model_dump()


@router.patch("/{order_id}/status")
def set_status(order_id: str, body: OrderStatusUpdate) -> dict:
    db = get_db()
    res = db.orders.update_one({"id": order_id}, {"$set": {"status": body.status}})
    if res.matched_count == 0:
        raise HTTPException(404, "Order not found")
    return _clean(db.orders.find_one({"id": order_id}))


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: str) -> None:
    res = get_db().orders.delete_one({"id": order_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Order not found")
