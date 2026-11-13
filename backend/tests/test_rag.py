from app.rag import cosine, retrieve


def test_semantic_retrieval_ranks_similar_vectors():
    chunks = [
        {"text": "Cats climb trees", "embedding": [1.0, 0.0], "filename": "a.txt", "page_number": 1},
        {"text": "Quarterly revenue rose", "embedding": [0.0, 1.0], "filename": "b.txt", "page_number": 1},
    ]
    assert cosine([1, 0], [1, 0]) == 1
    assert retrieve("felines", chunks, [0.9, 0.1])[0]["text"] == "Cats climb trees"


def test_retrieval_without_embeddings_uses_lexical_match():
    chunks = [{"text": "The policy renews every April", "embedding": None, "filename": "policy.txt", "page_number": 4}]
    assert retrieve("when does the policy renew", chunks, None)[0]["page_number"] == 4
