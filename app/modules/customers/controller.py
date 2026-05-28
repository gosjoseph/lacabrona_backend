from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schema import CustomerCreate, CustomerUpdate
from app.modules.customers.service import CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def get_customers_service() -> CustomerService:
    return CustomerService(CustomerRepository(get_db()))


@router.get("")
def list_customers(
    q: str | None = Query(None),
    service: CustomerService = Depends(get_customers_service),
) -> dict:
    return service.list_customers(q)


@router.get("/{customer_id}")
def get_customer(
    customer_id: str, service: CustomerService = Depends(get_customers_service)
) -> dict:
    return service.get_customer(customer_id)


@router.post("", status_code=201)
def create_customer(
    body: CustomerCreate,
    service: CustomerService = Depends(get_customers_service),
) -> dict:
    return service.create_customer(body)


@router.put("/{customer_id}")
def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    service: CustomerService = Depends(get_customers_service),
) -> dict:
    return service.update_customer(customer_id, body)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: str, service: CustomerService = Depends(get_customers_service)
) -> None:
    service.delete_customer(customer_id)


@router.post("/backfill")
def backfill(service: CustomerService = Depends(get_customers_service)) -> dict:
    return service.backfill()
