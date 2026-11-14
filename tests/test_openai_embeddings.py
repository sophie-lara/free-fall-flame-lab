import unittest
from types import SimpleNamespace

from combustion_atlas.providers import OpenAIEmbeddingProvider, ProviderConfig


class FakeEmbeddings:
    def create(self, **kwargs: object) -> SimpleNamespace:
        inputs = kwargs["input"]
        dimensions = kwargs["dimensions"]
        assert isinstance(inputs, list)
        assert isinstance(dimensions, int)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(index + 1)] * dimensions)
                for index, _ in enumerate(inputs)
            ]
        )


class OpenAIEmbeddingTests(unittest.TestCase):
    def test_batches_and_preserves_response_order(self) -> None:
        config = ProviderConfig(
            embedding_provider="openai",
            answer_provider="disabled",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=3,
            embedding_batch_size=2,
            answer_model="",
            openai_api_key_present=True,
        )
        client = SimpleNamespace(embeddings=FakeEmbeddings())
        provider = OpenAIEmbeddingProvider(config, client=client)

        vectors = provider.embed(["one", "two", "three"])

        self.assertEqual(vectors, [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [1.0, 1.0, 1.0]])
        self.assertEqual(provider.model_key, "openai:text-embedding-3-small:3")
