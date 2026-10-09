from typing import Annotated

from fastapi import Query

PageOffset = Annotated[int, Query(ge=0, le=2_147_483_647)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
