from collections.abc import Callable


_ROUTE_HANDLERS: dict[str, Callable] = {}


def register_route_handlers(**handlers: Callable) -> None:
    _ROUTE_HANDLERS.update(handlers)


def get_route_handler(name: str) -> Callable:
    handler = _ROUTE_HANDLERS.get(name)
    if handler is None:
        raise KeyError(f"Route handler '{name}' has not been registered.")
    return handler

