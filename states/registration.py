"""FSM states for user registration flow."""
from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """States for МЭШ registration process."""

    waiting_for_mesh_login = State()      # Waiting for user to enter МЭШ login
    waiting_for_mesh_password = State()   # Waiting for МЭШ password
    waiting_for_sms_code = State()        # Waiting for SMS code from mos.ru
    selecting_children = State()          # User selecting which children to add
