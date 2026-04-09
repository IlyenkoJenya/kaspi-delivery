from aiogram import Router
from .cancel import cancel_router
from .order import order_router

main_router = Router()
main_router.include_router(cancel_router)
main_router.include_router(order_router)
