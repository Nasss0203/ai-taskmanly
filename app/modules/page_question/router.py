from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.page_question.schemas import PageQuestionRequest, PageQuestionResponse
from app.modules.page_question.service import PageQuestionService

router = APIRouter()


def get_page_question_service(request: Request) -> PageQuestionService:
    return request.app.state.page_question_service


@router.post("", response_model=PageQuestionResponse)
async def answer_page_question(
    request: PageQuestionRequest,
    service: Annotated[PageQuestionService, Depends(get_page_question_service)],
) -> PageQuestionResponse:
    return await service.process(request)
