def rrf_score(rank):
    return 1.0 / (60.0 + rank)


print(rrf_score(1) * 0.7)
