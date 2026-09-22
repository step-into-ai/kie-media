import unittest
from kie_media.catalog import CatalogEntry, DocsCatalog
from kie_media.models import ModelValidationError, prepare_model_input


def document(properties, required="[]"):
    return '''```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model: {type: string, const: test/operation}
                input:
                  type: object
                  additionalProperties: false
                  required: ''' + required + '''
                  properties:
''' + properties + '\n```'


class OperationTests(unittest.TestCase):
    def spec(self, doc, kind="image"):
        return DocsCatalog._extract_model(CatalogEntry("Operation", "https://docs.kie.ai/market/op.md", kind, kind), doc)

    def test_promptless_operation_and_nested_validation(self):
        spec = self.spec(document('''                    task_id: {type: string}
                    segments:
                      type: array
                      items:
                        type: object
                        required: [index]
                        additionalProperties: false
                        properties:
                          index: {type: integer, minimum: 0}''', '[task_id, segments]'))
        values = {"task_id": "previous", "segments": [{"index": 1}]}
        self.assertEqual(prepare_model_input(spec, values), values)
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {"task_id": "previous", "segments": [{"index": -1}]})
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {"task_id": "previous", "segments": [{}]})

    def test_ambiguous_model_enum_rejected(self):
        doc = document('                    prompt: {type: string}').replace('const: test/operation', 'enum: [one, two]')
        with self.assertRaises(ValueError):
            self.spec(doc)

    def test_dynamic_boolean_does_not_pass_integer_validation(self):
        spec = self.spec(document('                    seed: {type: integer}', '[seed]'))
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {"seed": True})

    def test_chat_category_is_first_class(self):
        entries = DocsCatalog._parse_index('- Chat Models > GPT [GPT](https://docs.kie.ai/market/chat/gpt.md): chat')
        self.assertEqual(entries[0].kind, "chat")

    def test_plural_selector_examples_and_input_alternatives(self):
        doc = document('                    task_id: {type: string}').replace('const: test/operation', 'examples: [test/operation]')
        spec = self.spec(doc)
        self.assertEqual(spec.id, "test/operation")
        doc = '''```yaml
paths:
  /api/v1/jobs/createTask:
    post:
      requestBody:
        content:
          application/json:
            schema:
              properties:
                model: {type: string, enum: [segment/map]}
                input:
                  oneOf:
                    - type: object
                      required: [task_id]
                      properties:
                        task_id: {type: string, minLength: 1}
                    - type: object
                      required: [image_url]
                      properties:
                        image_url: {type: string}
```'''
        spec = self.spec(doc)
        self.assertEqual(prepare_model_input(spec, {"task_id": "previous"}), {"task_id": "previous"})
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {})
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {"task_id": "previous", "image_url": "https://example.test/frame.png"})
