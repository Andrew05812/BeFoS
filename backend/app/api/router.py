from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import auth, chat, discover, health, matches, safety, tests, users
from app.core.rate_limit import rate_limit_dependency

api_router = APIRouter()

# `/health` is the one route left unthrottled: a load balancer or a monitor that is being
# rate-limited reports the service as down, which turns a busy minute into an outage.
# `/health/db` carries its own loose bucket instead of sharing that exemption, because it opens
# a database connection per call and an anonymous loop against it starves the pool that real
# traffic borrows from. /auth carries its own stricter bucket (credential stuffing), and
# everything below it shares the default one — every route there either writes a row or ranks
# up to 150 candidates, so an unauthenticated-adjacent loop against them is bounded by the
# bucket rather than by the caller's patience.
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router, dependencies=[Depends(rate_limit_dependency)])
api_router.include_router(tests.router, dependencies=[Depends(rate_limit_dependency)])
api_router.include_router(discover.router, dependencies=[Depends(rate_limit_dependency)])
api_router.include_router(matches.router, dependencies=[Depends(rate_limit_dependency)])
api_router.include_router(chat.router, dependencies=[Depends(rate_limit_dependency)])
api_router.include_router(safety.router, dependencies=[Depends(rate_limit_dependency)])
