"""FSM states for bot conversations."""

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Registration flow states."""
    waiting_for_name = State()
    waiting_for_position = State()


class RequestCreation(StatesGroup):
    """Financial request creation flow states."""
    choosing_operation  = State()
    choosing_project    = State()   # only for operations with needs_project=True
    entering_amount     = State()
    entering_requisites = State()   # card-only (16 digits) OR free-text "card + purpose"
    confirming          = State()
    editing_field       = State()


class AdminManagement(StatesGroup):
    """Admin management flow states."""
    # Add project
    waiting_op_type_for_project = State()   # choose which operation type
    waiting_project_name        = State()   # type project name

    # Add entity (operation type)
    waiting_entity_name         = State()
    waiting_entity_needs_project = State()  # Yes / No
    waiting_entity_range        = State()   # Sheets range if needs_project
    waiting_entity_auto_project = State()   # fixed project name if not needs_project

    # Add / remove admin (developer only)
    waiting_new_admin_id        = State()
    waiting_remove_admin_id     = State()
