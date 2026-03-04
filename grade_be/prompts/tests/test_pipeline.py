import unittest
from unittest.mock import patch, AsyncMock

# Update with the actual module name
from prompts.src.pipeline import Pipeline, ChatOpenAIModel, PromptResponse


class PipelineTests(unittest.TestCase):

    @patch.object(ChatOpenAIModel, "create_model")
    @patch.object(PromptResponse, "get_response", new_callable=AsyncMock)
    async def test_openai_model_pipeline(
        self, mock_get_response, mock_create_model
    ):
        # Setup
        mock_create_model.return_value = AsyncMock()
        mock_get_response.return_value = (
            "Mocked response content",
            0.1,
        )  # Mock response content and cost

        # Input data
        model_dict = {
            "model": "gpt-4-1106-preview",
            "temperature": 0,
            "max_tokens": 200,
        }
        input_data = {
            "inputText": "Hello",
            "sourceLanguage": "English",
            "destinationLanguage": "Tamil",
        }

        pipeline = Pipeline()

        # Call the method
        response_content, cost = await pipeline.async_pipeline_process(
            "translate", model_dict, input_data
        )

        # Assertions
        self.assertEqual(response_content, "Mocked response content")
        self.assertEqual(cost, 0.1)

        # Check that the model and prompt were created and used
        mock_create_model.assert_called_once_with(model_dict)
        mock_get_response.assert_called_once()

    # Add more tests as needed for different scenarios


if __name__ == "__main__":
    unittest.main()
