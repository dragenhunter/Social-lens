def score(post):
    s = 1.0
    if not post.get("caption"): s -= 0.3
    if post.get("likes") is None: s -= 0.2
    if post.get("comments") is None: s -= 0.2
    return max(s, 0.0)
