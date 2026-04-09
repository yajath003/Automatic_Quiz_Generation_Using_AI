from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def is_duplicate(new_text, existing_texts, threshold=0.8):
    """
    Checks if new_text is similar to any text in existing_texts.
    Returns True if similarity > threshold.
    """
    if not existing_texts:
        return False
        
    documents = [new_text] + existing_texts
    tfidf_vectorizer = TfidfVectorizer().fit_transform(documents)
    pairwise_similarity = cosine_similarity(tfidf_vectorizer[0:1], tfidf_vectorizer[1:])
    
    # Check if any similarity score exceeds threshold
    return (pairwise_similarity > threshold).any()
