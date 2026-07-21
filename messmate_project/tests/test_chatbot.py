from types import SimpleNamespace

from django.test import SimpleTestCase

from core.ai_services import get_chatbot_response


class ChatbotServiceTests(SimpleTestCase):
    def test_missing_api_key_returns_unavailable_message_for_general_query(self):
        with self.settings(GEMINI_API_KEY=''):
            response = get_chatbot_response('Tell me a fun fact about the platform.')
        self.assertIn('unavailable', response.lower())

    def test_student_context_response_mentions_wallet(self):
        user = SimpleNamespace(role='student')
        response = get_chatbot_response('How do I check my wallet balance?', user=user)
        self.assertIn('wallet', response.lower())
