from aiogram.fsm.state import State, StatesGroup


class OnboardingFSM(StatesGroup):
    gender = State()
    goal = State()
    level = State()
    days = State()


class WorkoutFSM(StatesGroup):
    exercise_card = State()   # show exercise card
    rating_effort = State()   # rate effort: easy / on_point / hard
    rest_timer = State()      # waiting for rest timer
    replacing = State()       # picking a replacement exercise
    finished = State()        # post-workout summary screen
