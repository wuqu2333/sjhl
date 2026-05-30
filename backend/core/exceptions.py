from __future__ import annotations

import traceback
from fastapi import HTTPException
from utils.logging import logger


def raise_bad_request(error: Exception):
    logger.error(f"请求错误: {error}")
    logger.debug(traceback.format_exc())
    raise HTTPException(status_code=400, detail=str(error))
