"""
Unit tests for IntentClassifier module
Tests intent classification accuracy for commands and chat inputs
"""

import unittest
from intent_classifier import IntentClassifier


class TestIntentClassifier(unittest.TestCase):
    """Test suite for IntentClassifier"""
    
    def setUp(self):
        """Initialize classifier before each test"""
        self.classifier = IntentClassifier()
    
    def test_commands(self):
        """Test command recognition"""
        test_data = [
            ("Follow me", 'follow_me'),
            ("Stop", 'stop'),
            ("Go forward", 'forward'),
            ("Turn left", 'left'),
            ("Spray water", 'spray'),
            ("Come back", 'return'),
            ("Battery status", 'battery')
        ]
        for text, expected_cmd in test_data:
            intent, command, _ = self.classifier.classify(text)
            self.assertEqual(intent, 'COMMAND')
            self.assertEqual(command, expected_cmd)
    
    def test_chat(self):
        """Test chat classification"""
        test_cases = [
            "Hello",
            "How are you?",
            "What is your name?",
            "Tell me a joke",
            "I love you"
        ]
        for text in test_cases:
            intent, command, _ = self.classifier.classify(text)
            self.assertEqual(intent, 'CHAT')
            self.assertIsNone(command)
    
    def test_question_detection(self):
        """Test question detection heuristic"""
        self.assertTrue(self.classifier._is_question("What is this?"))
        self.assertTrue(self.classifier._is_question("could you help me"))
        self.assertFalse(self.classifier._is_question("Go forward"))
    
    def test_empty_input(self):
        """Test empty input handling"""
        intent, command, metadata = self.classifier.classify("")
        self.assertEqual(intent, 'UNKNOWN')
        self.assertIsNone(command)
        self.assertEqual(metadata['confidence'], 0.0)
    
    def test_custom_command(self):
        """Test custom command addition"""
        self.classifier.add_custom_command('dance', [r'\b(dance|shake)\b'])
        intent, command, _ = self.classifier.classify("Dance now")
        self.assertEqual(intent, 'COMMAND')
        self.assertEqual(command, 'dance')
    
    def test_case_insensitivity(self):
        """Test case-insensitive classification"""
        for text in ["FOLLOW ME", "follow me", "FoLLoW mE"]:
            intent, command, _ = self.classifier.classify(text)
            self.assertEqual(intent, 'COMMAND')
            self.assertEqual(command, 'follow_me')


def run_tests():
    """Run all tests and print results"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestIntentClassifier)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n{'='*60}")
    print(f"Tests run: {result.testsRun} | "
          f"Passed: {result.testsRun - len(result.failures) - len(result.errors)} | "
          f"Failed: {len(result.failures)} | "
          f"Errors: {len(result.errors)}")
    print('='*60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
