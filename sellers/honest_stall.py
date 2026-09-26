"""The honest stall: two reasonably-priced, correctly-configured x402
sellers Arjun's agent should be happy to pay. Real USDC, real Base Sepolia,
prices well inside the purse's per-call ceiling.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

load_dotenv()

NETWORK = os.environ.get("X402_NETWORK", "eip155:84532")
PAY_TO_ADDRESS = os.environ["HONEST_SELLER_PAY_TO_ADDRESS"]
FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://x402.org/facilitator")

facilitator_client = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServer(facilitator_client).register(NETWORK, ExactEvmServerScheme())

routes = {
    "GET /rainfall-grid": RouteConfig(
        accepts=PaymentOption(scheme="exact", pay_to=PAY_TO_ADDRESS, price="$0.02", network=NETWORK),
        description="Bengaluru-region rainfall grid, last 30 days.",
        mime_type="application/json",
    ),
    "GET /mandi-price-feed": RouteConfig(
        accepts=PaymentOption(scheme="exact", pay_to=PAY_TO_ADDRESS, price="$0.03", network=NETWORK),
        description="Daily mandi crop price feed for Karnataka markets.",
        mime_type="application/json",
    ),
}

app = FastAPI(title="Honest Stall")
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=resource_server)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rainfall-grid")
async def rainfall_grid():
    return {
        "region": "Bengaluru Rural + Urban",
        "period": "last_30_days",
        "grid_mm": [12.4, 0.0, 3.2, 45.1, 8.0, 0.0, 21.7],
        "source": "honest-stall-mock",
    }


@app.get("/mandi-price-feed")
async def mandi_price_feed():
    return {
        "market": "Karnataka",
        "commodity": "tomato",
        "prices_per_quintal_inr": [1450, 1600, 1520, 1780, 1690],
        "source": "honest-stall-mock",
    }
