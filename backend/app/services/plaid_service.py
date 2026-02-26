from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid import Configuration, ApiClient, Environment
from app.config import settings
from datetime import date, timedelta
from typing import List
import logging

logger = logging.getLogger(__name__)

ENV_MAP = {
    "sandbox": Environment.Sandbox,
    "development": Environment.Development,
    "production": Environment.Production,
}

def get_plaid_client() -> plaid_api.PlaidApi:
    configuration = Configuration(
        host=ENV_MAP.get(settings.PLAID_ENV, Environment.Sandbox),
        api_key={
            "clientId": settings.PLAID_CLIENT_ID,
            "secret": settings.PLAID_SECRET,
        }
    )
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)

async def create_link_token(user_id: str) -> str:
    client = get_plaid_client()
    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        client_name="BizTrack Receipts",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    response = client.link_token_create(request)
    return response["link_token"]

async def exchange_public_token(public_token: str) -> dict:
    client = get_plaid_client()
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return {
        "access_token": response["access_token"],
        "item_id": response["item_id"],
    }

async def fetch_transactions(access_token: str, days_back: int = 90) -> List[dict]:
    client = get_plaid_client()
    start = date.today() - timedelta(days=days_back)
    end = date.today()
    all_transactions = []
    total_transactions = None
    offset = 0

    while total_transactions is None or len(all_transactions) < total_transactions:
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start,
            end_date=end,
            options=TransactionsGetRequestOptions(count=500, offset=offset)
        )
        try:
            response = client.transactions_get(request)
            transactions = response["transactions"]
            if total_transactions is None:
                total_transactions = response["total_transactions"]
            all_transactions.extend(transactions)
            offset += len(transactions)
            if not transactions:
                break
        except Exception as e:
            logger.error(f"Plaid fetch error: {e}")
            break

    return all_transactions

async def get_accounts(access_token: str) -> List[dict]:
    from plaid.model.accounts_get_request import AccountsGetRequest
    client = get_plaid_client()
    request = AccountsGetRequest(access_token=access_token)
    response = client.accounts_get(request)
    return response["accounts"]
