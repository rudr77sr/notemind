from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

sentence = "Deadlocks occur when processes wait on each other indefinitely."
embedding = model.encode(sentence)

print(embedding.shape)
print(embedding[:5])