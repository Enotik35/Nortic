from aiogram.fsm.state import StatesGroup, State


class BuySubscriptionState(StatesGroup):
    waiting_for_email = State()


class TrialSubscriptionState(StatesGroup):
    waiting_for_email = State()


class ChangeEmailState(StatesGroup):
    waiting_for_new_email = State()
