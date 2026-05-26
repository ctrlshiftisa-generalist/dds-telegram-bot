"""FSM states for bot conversations."""

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Registration flow states."""
    waiting_for_name = State()


class RequestCreation(StatesGroup):
    """Financial request creation flow states."""
    choosing_operation = State()
    entering_amount = State()
    choosing_project = State()
    entering_card = State()
    entering_purpose = State()
    confirming = State()
    editing_field = State()
