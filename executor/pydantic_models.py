# from pydantic import BaseModel, Field
# from typing import List, Optional

# class TestCaseSchema(BaseModel):
#     input: str
#     expected_output: str
#     is_sample: bool
#     test_type: str

# class SampleIOSchema(BaseModel):
#     input: str
#     output: str

# class QuestionSchema(BaseModel):
#     title: str
#     description: str
#     explanation: Optional[str] = ""
#     constraints: Optional[str] = ""
#     testcase_description: Optional[str] = ""
#     year_asked: Optional[int] = None
#     topics: List[str] = Field(default_factory=list)
#     companies_asked: List[str] = Field(default_factory=list)
#     sample_io: List[SampleIOSchema] = Field(default_factory=list)
#     test_cases: List[TestCaseSchema] = Field(default_factory=list)



# class PublicTestcaseResult(BaseModel):
#     input: str
#     expected_output: str
#     user_output: str
#     passed: bool

# class GradingSchema(BaseModel):
#     score: int
#     feedback: str
#     rubric: Optional[str] = None
#     test_case_results: List[PublicTestcaseResult]

