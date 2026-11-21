from enum import Enum

from pydantic import BaseModel


class ContextType(str, Enum):
    WORKSPACE = "WORKSPACE"

    PROJECT = "PROJECT"
    BOARD = "BOARD"

    SPRINT = "SPRINT"
    TASK = "TASK"

    PAGE = "PAGE"
    BLOCK = "BLOCK"

    COMMENT = "COMMENT"


class CurrentContext(BaseModel):
    type: ContextType
    id: str