from claude_code.comprehension import QUESTIONS, score


def test_every_question_has_a_computed_answer_of_a_few_items():
    for q in QUESTIONS:
        expected = q.expected()
        assert 2 <= len(expected) <= 30, (q.qid, expected)


def test_known_answers():
    by_id = {q.qid: q.expected() for q in QUESTIONS}
    assert "create_server" in by_id["async-methods"] and "run_forever" not in by_id["async-methods"]
    assert "_execute_child" in by_id["both-platforms"] and "kill" not in by_id["both-platforms"]
    assert {"Server", "BaseEventLoop"} <= by_id["close-methods"]


def test_score_counts_whole_words_only():
    assert score("create_server and getaddrinfo", frozenset({"create_server", "getaddrinfo"})) == 1.0
    assert score("_create_server_getaddrinfo", frozenset({"create_server"})) == 0.0
