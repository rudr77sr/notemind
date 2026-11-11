from main import chunk_text

def test_chunks_overlap():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert chunks[0][-100:] == chunks[1][:100]

def test_known_example():
    chunks = chunk_text("abcdefghijkl", chunk_size=5, overlap=2)
    assert chunks == ["abcde", "defgh", "ghijk", "jkl"]

def test_empty_chunk():
    chunks = chunk_text("")
    assert chunks == []

def test_short_text():
    chunks = chunk_text("hello")
    assert chunks == ["hello"]