"""Schema for a user question tied to official tariff branches."""

from typing import Dict, List

from pydantic import BaseModel, Field, model_validator


class DiscriminatorQuestion(BaseModel):
    session_id: str
    parameter_name: str
    question_text: str
    options: List[str] = Field(min_length=3, max_length=5)
    target_branches: Dict[str, str]

    @model_validator(mode="after")
    def validate_option_mapping(self) -> "DiscriminatorQuestion":
        expected = {str(index) for index in range(len(self.options))}
        if set(self.target_branches) != expected:
            raise ValueError("Her seçenek tam olarak bir resmî tarife dalına bağlanmalıdır.")
        return self
