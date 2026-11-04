from claude_code.replay_mcp import respond
from evals.atlas import Call, Record, exposed, facts, reply, tools, usable
from evals.truth import Claims, score_answer, score_fold

_PROMPT = "Can you get me the year the repository of the shooter game assaultcube was created?"


def test_a_claims_facts_are_its_numbers_quoted_titles_and_names_the_prompt_does_not_give():
    found = facts('The AssaultCube repository "AC" was created in 2013 by Rabid Viper.', _PROMPT)
    assert {(f.kind, f.text) for f in found} == {
        ("number", "2013"),
        ("name", "AC"),  # too short to be a quoted title: a name
        ("name", "Rabid"),
        ("name", "Viper"),
    }
    quoted = facts('The painting is "Young Woman with a Water Pitcher".', "Which painting?")
    assert [(f.kind, f.text) for f in quoted] == [("quote", "Young Woman with a Water Pitcher")]


def test_a_claim_holds_on_its_numbers_and_quotes_and_two_thirds_of_its_names():
    claim = facts("Anne Perry wrote The Cater Street Hangman, which sold 1,250 copies at $7.99.", "Who?")
    truth = Claims((claim,))
    assert score_answer(truth, "It was Anne Perry's Cater Street Hangman: 1250 copies, $7.99 each.").correct
    assert not score_answer(truth, "Anne Perry's Cater Street Hangman sold 1,200 copies at $7.99.").correct
    assert score_answer(truth, "Perry's Cater Street Hangman: 1,250 at 8.0 dollars").correct  # within 1%
    assert not score_answer(truth, "1,250 copies at $7.99, by someone.").correct  # no names


def _record() -> Record:
    big = "x" * 9000 + " Rabid Viper 2013"
    calls = (
        Call("github_search_repositories", {"query": "assaultcube"}, big),
        Call("github_get_repo", {"owner": "assaultcube", "repo": "AC"}, '{"created_at": "2013-11-28"}'),
        Call("github_get_repo", {"owner": "rabid", "repo": "viper"}, '{"created_at": "2001"}'),
    )
    return Record("t1", _PROMPT, ("The repository was created in 2013 by Rabid Viper.",), calls)


def test_a_record_is_usable_with_one_large_output_and_every_fact_in_the_data():
    r = _record()
    assert usable(r)
    computes = Record(r.task, r.prompt, r.claims, (*r.calls, Call("calculator_calculate", {"x": "1+1"}, "2")))
    assert not usable(computes)
    unanswerable = Record(r.task, r.prompt, ("It was created in 1999.",), r.calls)
    assert not usable(unanswerable)


def test_the_replay_offers_the_recorded_tools_and_answers_with_the_closest_call():
    r = _record()
    names = [t["name"] for t in tools(r)]
    assert names == ["github_search_repositories", "github_get_repo"]
    assert tools(r)[1]["inputSchema"]["properties"] == {
        "owner": {"type": "string"},
        "repo": {"type": "string"},
    }
    assert (
        reply(r, "github_get_repo", {"owner": "AssaultCube", "repo": "AC"}).output
        == '{"created_at": "2013-11-28"}'
    )
    assert reply(r, "github_get_repo", {"owner": "someone"}).output == '{"created_at": "2013-11-28"}'
    assert reply(r, "github_delete_repo", {}) is None
    ok = respond(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "github_get_repo", "arguments": {"owner": "rabid", "repo": "viper"}},
        },
        r,
    )
    assert ok["result"] == {"content": [{"type": "text", "text": '{"created_at": "2001"}'}], "isError": False}
    missing = respond(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nope", "arguments": {}}}, r
    )
    assert (
        missing["result"]["isError"]
        and "the tools are: github_search_repositories" in missing["result"]["content"][0]["text"]
    )
    long = "clinicaltrialsgov-mcp-server_clinicaltrials_list_studies_extra"
    assert len(exposed(long)) == 56 and exposed(long) != exposed(long + "s")


def test_a_fold_is_sufficient_when_it_keeps_the_answers_facts_the_large_output_holds():
    claim = facts("The repository was created in 2013 by Rabid Viper.", _PROMPT)
    truth = Claims((claim,), claim)
    assert score_fold(truth, "... Rabid Viper (2013) ...").correct
    assert not score_fold(truth, "... Rabid ...").correct
