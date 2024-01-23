import contextlib
import dataclasses
import enum
import inspect
import re
import typing

from .parameters import Parameters
from .typing import ParserFeature
from .utils import PY39, REGEX_FALSE, REGEX_TRUE, CustomType

__all__ = (
    'build_value',
    'can_has_default',
    'supported_annotation',
)

# message argument regex
DEFAULT_REGEX = r"(?:(?P<key>[^=\s]+)=)?(?P<valuequote>['\"])?(?P<value>(?(2)(?:\\\2|[^\2])*?|[^\s]+))(?(2)\2)"
QUOTEDKEY_REGEX = r"(?:(?P<keyquote>['\"])?(?P<key>(?(1)(?:\\\1|[^\1])*?|[^=\s]+))(?(1)\1)=)?(?P<valuequote>['\"])?(?P<value>(?(3)(?:\\\3|[^\3])*?|[^\s]+))(?(3)\3)"
# intern checker util
ALLOW_TYPES: typing.List[type] = [typing.Any, object]  # type: ignore
ARRAY_SEPARATOR = ','
MAPPING_SEPARATOR = ':'
BOOL_REGEX: typing.Dict[bool, re.Pattern[str]] = {
    True: REGEX_TRUE,
    False: REGEX_FALSE
}
TYPE_WRAPPER: typing.List[type] = [typing.Annotated, typing.Union]  # type: ignore
if PY39:
    from types import UnionType
    TYPE_WRAPPER.append(UnionType)

PATTERNS: typing.Dict[ParserFeature, str] = {
    'default': DEFAULT_REGEX,
    'quotedkey': QUOTEDKEY_REGEX
}


@dataclasses.dataclass
class Argument:
    key: typing.Optional[str]
    value: str
    start: int
    end: int


def parse_args(message: str, feature: ParserFeature = 'default') -> typing.List[Argument]:
    return [Argument(m.group('key'), m.group('value'), m.start(), m.end()) for m in re.finditer(PATTERNS[feature], message)]
    

def from_array_group(text: str, dtype: typing.Type[typing.Sequence[typing.Any]]) -> typing.Any:
    assert DataGroup.ARRAY.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.ARRAY, dtype)
    origin, args = typing.cast(typing.Callable[[typing.Sequence[typing.Any]], typing.Any], typing.get_origin(dtype) or tuple), typing.get_args(dtype) or (typing.Any, ...)
    arguments = list(map(lambda s: s.strip(), text.split(ARRAY_SEPARATOR)))
    if len(args) == 2 and args[1] is Ellipsis:
        args = tuple([args[0]] * len(arguments))
    result: typing.List[typing.Any] = []
    argument_iterator = iter(arguments)
    for expected in typing.cast(typing.Tuple[type, ...], args):
        try:
            value = next(argument_iterator)
        except StopIteration:
            value = ''
        if expected not in ALLOW_TYPES:
            value = build_value(value, expected)
        result.append(value)
    return origin(result)


def from_boolean_group(text: str, dtype: type) -> typing.Any:
    assert DataGroup.BOOLEAN.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.BOOLEAN, dtype)
    for bool_value, pattern in BOOL_REGEX.items():
        if pattern.match(text):
            return dtype(bool_value)
    return dtype()


def from_list_group(text: str, dtype: typing.Type[typing.Iterable[typing.Any]]) -> typing.Any:
    assert DataGroup.LIST.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.LIST, dtype)
    origin, args = typing.cast(typing.Callable[[typing.Sized], typing.Any], typing.get_origin(dtype) or dtype), typing.get_args(dtype)
    expected = args[0] if args else typing.Any
    partial = from_array_group(text, tuple)
    result = [build_value(value, expected) for value in partial]
    return origin(result)


def from_literal_group(text: str, dtype: type) -> typing.Any:
    assert DataGroup.LITERAL.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.LITERAL, dtype)
    args = typing.get_args(dtype)
    dtypes = set(type(arg) for arg in args)
    for arg_dtype in dtypes:
        value = build_value(text, arg_dtype)
        if value in args:
            return value
    else:
        return args[0]


def from_mapping_group(text: str, dtype: typing.Type[typing.Mapping[typing.Any, typing.Any]]) -> typing.Any:
    assert DataGroup.MAPPING.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.MAPPING, dtype)
    origin, args = typing.cast(typing.Callable[[typing.Mapping[typing.Any, typing.Any]], typing.Any], typing.get_origin(dtype) or dtype), typing.get_args(dtype) or (typing.Any, typing.Any)
    result = {}
    arguments = text.split(MAPPING_SEPARATOR, 1)
    if len(arguments) != 2:
        arguments += ['']
    k, v  = map(lambda s: s.strip(), arguments)
    key = build_value(k, args[0])
    value = build_value(v, args[1])
    result[key] = value
    return origin(result)


def from_numeric_group(text: str, dtype: type) -> typing.Any:
    assert DataGroup.NUMERIC.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.NUMERIC, dtype)
    text = text.replace('i', 'j') # math imaginary char
    try:
        if issubclass(dtype, (float, int)):
            return dtype(complex(text).real)
        elif issubclass(dtype, complex):
            return dtype(complex(text))
        else:
            raise ValueError
    except ValueError:
        return dtype()


def from_text_group(text: str, dtype: type) -> typing.Any:
    assert DataGroup.TEXT.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.TEXT, dtype)
    if issubclass(dtype, (bytearray, bytes)):
        return dtype(text, encoding='utf-8', errors='ignore')
    elif issubclass(dtype, str):
        return dtype(text)
    else:
        return dtype()


def from_custom_group(text: str, dtype: type) -> typing.Any:
    assert DataGroup.CUSTOM.supported(dtype), 'Invalid dtype. Expected %s, got %r' % (DataGroup.CUSTOM, dtype)
    return dtype(text)


GroupInfo = typing.NamedTuple("GroupInfo", [("dtypes", typing.Tuple[type, ...]), ("converter", typing.Callable[[str, type], typing.Any])])

class DataGroup(enum.Enum):
    ARRAY = GroupInfo((tuple,), from_array_group)
    BOOLEAN = GroupInfo((bool,), from_boolean_group)
    CUSTOM = GroupInfo((CustomType,), from_custom_group)
    LIST = GroupInfo((frozenset, list, set), from_list_group)
    LITERAL = GroupInfo((typing.Literal,), from_literal_group)  # type: ignore
    MAPPING = GroupInfo((dict,), from_mapping_group)
    NUMERIC = GroupInfo((complex, float, int), from_numeric_group)
    NONE = GroupInfo((type(None),), from_numeric_group)
    TEXT = GroupInfo((bytearray, bytes, str, typing.Any), from_text_group)  # type: ignore

    @classmethod
    def get_group(cls, dtype: typing.Any) -> typing.Optional['DataGroup']:
        for group in cls:
            if group.supported(dtype):
                return group
        else:
            return None

    def supported(self, dtype: typing.Any) -> bool:
        origin = typing.get_origin(dtype) or dtype
        try:
            return issubclass(origin, self.value.dtypes)
        except TypeError:
            return origin in self.value.dtypes


def build_value(text: typing.Optional[str], annotation: typing.Any, param: typing.Optional[inspect.Parameter] = None) -> typing.Any:
    if annotation in ALLOW_TYPES:
        annotation = str
    group = DataGroup.get_group(annotation)
    if group is None:
        if param is None or param.default is param.empty:
            return None
        return param.default
    if not isinstance(text, str):
        text = ''
    return group.value.converter(text.strip(), annotation)


def supported_annotation(annotation: type) -> bool:
    if annotation in ALLOW_TYPES:
        return True
    return any(group.supported(annotation) for group in DataGroup) and all(supported_annotation(a) for a in typing.get_args(annotation))


def can_has_default(obj: typing.Any) -> typing.TypeGuard[typing.Callable[[], typing.Any]]:
    origin = typing.get_origin(obj)
    if origin in TYPE_WRAPPER:
        return all(can_has_default(o) for o in typing.get_args(obj))
    elif obj in [typing.Any]:
        return True
    try:
        sign = inspect.signature(obj)
        annotations = extract_annotations(obj)
        for name, param in sign.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if not can_has_default(annotations.get(name, typing.Any)) and param.default is param.empty:
                return False
        else:
            return True
    except ValueError:
        return supported_annotation(obj)


def extract_annotations(callback: typing.Callable[..., typing.Any]) -> typing.Dict[str, typing.Any]:
    with contextlib.suppress(AttributeError):
        for name, dtype in callback.__annotations__.copy().items():
            if not isinstance(dtype, str) or dtype != Parameters.__name__:
                continue
            callback.__annotations__[name] = Parameters
    with contextlib.suppress(TypeError):
        return dict(typing.get_type_hints(callback))
    return {}


def validate_lite_callback(callback: typing.Callable[..., typing.Any]) -> None:
    sign = inspect.signature(callback)
    if not sign.parameters:
        raise ValueError("Invalid callback. An argument for BotAmino.Parameters is required") from None
    annotations = extract_annotations(callback)
    first_param = True
    for param in sign.parameters.values():
        annotation = annotations.get(param.name, typing.Any)
        if first_param:
            if annotation not in (typing.Any, Parameters):
                classname = getattr(annotation, '__name__', type(annotation).__name__)
                raise ValueError("Invalid {!r} annotation. {!r} is not compatible with BotAmino.Parameters".format(param.name, classname)) from None
            first_param = False
            continue
        raise ValueError("Invalid parameters. Lite callback should have only 1 parameter")


def validate_callback(callback: typing.Callable[..., typing.Any]) -> None:
    sign = inspect.signature(callback)
    if not sign.parameters:
        raise ValueError("Invalid callback. An argument for BotAmino.Parameters is required") from None
    annotations = extract_annotations(callback)
    first_param = True
    for name, param in sign.parameters.items():
        annotation = annotations.get(name, typing.Any)
        if first_param:
            if annotation not in (typing.Any, Parameters):
                classname = getattr(annotation, '__name__', type(annotation).__name__)
                raise ValueError("Invalid {!r} annotation. {!r} is not compatible with BotAmino.Parameters".format(name, classname))
            first_param = False
            continue
        if supported_annotation(annotation):
            continue
        if param.default is param.empty and not can_has_default(annotation):
            classname = getattr(annotation, '__name__', type(annotation).__name__)
            raise ValueError("Invalid {!r} annotation. {!r} requires default value".format(name, classname))


def bind_callback(callback: typing.Callable[..., typing.Any], data: Parameters, arguments: typing.List[Argument]) -> typing.Any:
    annotations = extract_annotations(callback)
    args: typing.List[typing.Any] = [data]
    kwargs: typing.Dict[str, typing.Any] = {}
    parameters = list(inspect.signature(callback).parameters.values())[1:]
    positional_params = filter(lambda param: param.kind in [param.POSITIONAL_ONLY, param.VAR_POSITIONAL], parameters)
    pos_or_kw_params = list(filter(lambda param: param.kind == param.POSITIONAL_OR_KEYWORD, parameters))
    keyword_params = list(filter(lambda param: param.kind in [param.KEYWORD_ONLY, param.VAR_KEYWORD], parameters))
    positional_arguments = filter(lambda argument: argument.key is None, arguments)
    keyword_arguments: typing.Dict[str, str] = {}
    for argument in filter(lambda argument: argument.key is not None, arguments):
        keyword_arguments[typing.cast(str, argument.key)] = argument.value
    # parsing positional only arguments
    for param in positional_params:
        annotation = annotations.get(param.name, typing.Any)
        if param.kind == param.VAR_POSITIONAL:
            args.extend(build_value(argument.value, annotation, param) for argument in positional_arguments)
            break
        try:
            argument = next(positional_arguments)
        except StopIteration:
            value = build_value(None, annotation, param)
        else:
            value = build_value(argument.value, annotation, param)
        args.append(value)
    # parsing positional or keyword arguments
    for param in pos_or_kw_params:
        annotation = annotations.get(param.name, typing.Any)
        try:
            argument = next(positional_arguments)
            arg_default = argument.value
        except StopIteration:
            arg_default = None
        kwargs[param.name] = build_value(keyword_arguments.pop(param.name, arg_default), annotation, param)
    # parsing keyword only arguments
    for param in keyword_params:
        annotation = annotations.get(param.name, typing.Any)
        if param.kind == param.VAR_KEYWORD:
            kwargs.update({key: build_value(value, annotation, param) for key, value in keyword_arguments.items()})
            break
        kwargs[param.name] = build_value(keyword_arguments.pop(param.name, None), annotation, param)
    return tuple(args), dict(kwargs)
