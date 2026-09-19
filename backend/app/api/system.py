from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_state_manager
from app.core.state_manager import StateManager
from app.models.system import RobotState

router = APIRouter()


@router.get("/status", response_model=RobotState)
async def get_system_status(
    state_manager: Annotated[StateManager, Depends(get_state_manager)],
) -> RobotState:
    _, state = await state_manager.snapshot()
    return state

