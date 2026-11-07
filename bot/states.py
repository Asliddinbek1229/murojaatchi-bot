from aiogram.fsm.state import State, StatesGroup


class AppealSG(StatesGroup):
    content = State()


class ReplySG(StatesGroup):
    content = State()


class RejectSG(StatesGroup):
    reason = State()


class AddAdminSG(StatesGroup):
    user = State()


class BotSG(StatesGroup):
    token = State()
    title = State()
    rename = State()
    new_token = State()


class BroadcastSG(StatesGroup):
    content = State()
    confirm = State()


class FindAppealSG(StatesGroup):
    appeal_id = State()


class EmojiSG(StatesGroup):
    single = State()
    wizard = State()
