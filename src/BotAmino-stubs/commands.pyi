from collections.abc import Callable, Sequence
from typing import (
    Any,
    Iterable
)
from typing_extensions import ParamSpec
from .parameters import Parameters
from .typing import (
    CallbackCategory,
    Callback,
    Condition,
    Events,
    LiteCallbackT
)

__all__ = ('CallbackInfo', 'CommandHandler')

P = ParamSpec("P")

class CallbackInfo:
    def __init__(
        self,
        names: Sequence[str],
        callback: Callback[P],
        condition: Condition | None
    ) -> None:
        self.names: set[str]
        self.callback: Callback[P]
        self.condition: Condition | None
    def __hash__(self) -> int: ...
    def __eq__(self, value: object) -> bool: ...
    def __contains__(self, key: object) -> bool: ...

class CommandHandler:
    def __init__(self) -> None:
        self.callbacks: dict[str, set[CallbackInfo]]
    def execute(self, name: str, data: Parameters, category: CallbackCategory = "command") -> Any: ...
    def category_exist(self, category: CallbackCategory) -> bool: ...
    def get_category(self, category: CallbackCategory) -> set[CallbackInfo]: ...
    def add_category(self, category: CallbackCategory) -> None: ...
    def commands_list(self) -> list[CallbackInfo]: ...
    def answer_list(self) -> list[CallbackInfo]: ...
    def get_command_info(self, name: str) -> CallbackInfo | None: ...
    def get_answer_info(self, name: str) -> CallbackInfo | None: ...
    def command(self, name: str | Iterable[str] | None = None, condition: Condition | None = None) -> Callable[[Callback[P]], Callback[P]]: ...
    def answer(self, name: str | Iterable[str] | None = None, condition: Condition | None = None) -> Callable[[Callback[P]], Callback[P]]: ...
    def on_member_join_chat(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_member_leave_chat(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_message(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_other(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_delete(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_remove(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_all(self, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
    def on_event(self, name: Iterable[Events] | Events, condition: Condition | None = None) -> Callable[[LiteCallbackT], LiteCallbackT]: ...
