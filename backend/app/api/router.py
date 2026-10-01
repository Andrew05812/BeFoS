from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, chat, discover, health, matches, safety, tests, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(tests.router)
api_router.include_router(discover.router)
api_router.include_router(matches.router)
api_router.include_router(chat.router)
api_router.include_router(safety.router)
