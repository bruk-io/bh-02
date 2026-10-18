---
id: TASK-0141
title: A transcript whose last line is torn still resumes
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 13:47'
labels:
  - agent
  - size-2
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found designing TASK-0136 (noted there, filed at the owner's word 2026-10-18). FileTranscript reads every line of transcript.jsonl with json.loads (agent plugin transcript.py), so a process killed mid-write leaves a torn last line that makes the session impossible to resume: the transcript row fails to start. The appender (host_paths.Appender) would also glue the next entry onto the torn bytes. A torn last line is an entry that was never finished, so it can be dropped; a bad line anywhere else is damage the person must see.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A transcript file whose last line is torn (no newline, not JSON) resumes without that line, and the next entry is written on a line of its own (a test with a torn tail, then an append, then a resume that reads every entry)
- [x] #2 A line that is not JSON anywhere but the end still stops the transcript, with an error naming the file and the line number and saying what to do
- [x] #3 The dropped bytes are not silently lost: they are kept beside the transcript (or the error says where), and the notes say which; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) transcript.py: split FileTranscript's read into a pure _read(data, path) -> _Reading (messages, torn tail bytes, whether a whole last line lacks its newline) and a FileTranscript._mend that does the I/O. A bad line before the last, or a last line that ends in a newline and is not JSON, raises ValueError naming file, line number and what to do (file untouched). 2) A torn last line (no newline, not JSON): kept first beside the file via host_paths.write_beneath (0600, through no link) at transcript.jsonl.torn, then .torn.2, ... (the .bak convention: an earlier one is never replaced), then the file is cut to its last whole line (ftruncate on an O_NOFOLLOW fd) before the appender's first write. A whole last line missing only its newline gets one. 3) Tests in test_agent_transcript.py: torn tail then append then resume reads every entry; torn twice; bad middle line; bad last line with newline; torn kept first (a link at the .torn name refuses and nothing is cut); whole last line w/o newline; 0600. Watch them fail on the current code first, and with keep/cut swapped. 4) Docs: agent plugin README, CONTRACTS.md transcript row, transcript.py docstring. Check: scripts/check bh-02/plugins/agent-cordis-plugin; arch-check --no-fix (root pyproject budget unchanged: FileTranscript.* already excluded; pure _read stays pure).

Review round 1 (the one blocking finding: no failing repro on record). Order: (1) in the working tree only, put transcript.py back to its content before 80e157a (git show 80e157a~1:<path>) and leave test_agent_transcript.py as committed; (2) from the repo root run record-check TASK-0141 --repro -- uv run pytest bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py -k torn_last_line, which must fail and records the note against HEAD (the start commit, an ancestor of the round's commit, so the recorded sha survives the squash); (3) restore transcript.py from HEAD, so the tree carries the fix again; (4) run the tests on the restored code, board-check close TASK-0141 (not close-task: a worker never sets Done); (5) one commit. The non-blocking items (the _beside docstring, telling the person, the concurrent appender) stay as they are.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: agent plugin transcript.py (FileTranscript reads through a pure _read(data, path) -> _Reading; FileTranscript._mend does the I/O), its tests (test_agent_transcript.py), the plugin README, CONTRACTS.md (transcript row) and docs/bh-02/using/sessions.md.
Behaviour: a last line with no newline that is not JSON (or not UTF-8) is a write cut short. Before the appender's first write its bytes are kept beside the file through host_paths.write_beneath (0600, no link followed) as transcript.jsonl.torn, then .torn.2, ... the first name not taken (the .bak convention: an earlier file is never replaced; I chose this over appending to one .torn so no cap on reading an old one and nothing read back), and only then is the file cut to its last whole line (ftruncate on an O_NOFOLLOW descriptor). If the bytes cannot be kept (a link at the .torn name, no room) nothing is cut: OSError with a note, file untouched. A last line that is whole JSON but lacks its newline (cut at the final byte) is read and given a newline, since otherwise the next entry would glue onto it (same defect, same site, so done here). Any other non-JSON line (before the last, or a last line ending in a newline) raises ValueError '<file> line N is not JSON (...) ... Repair or remove that line in an editor ..., or leave this session and start a new one without --resume'; the file is untouched, no .torn. conversation.py already catches (OSError, ValueError) for /compact.
Evidence: AC1 test_a_torn_last_line_is_set_aside_and_the_next_entry_is_written_on_a_line_of_its_own (torn tail, append, flush, resume reads every entry; torn bytes in .torn). AC2 test_a_line_that_is_not_json_before_the_end_stops_the_transcript_naming_where_and_what_to_do (5 cases: first, middle, last ending in newline, after a blank line, damaged then torn; file, line number and --resume checked; file unchanged). AC3 the .torn files are kept at 0600 (test under umask 0), a second tear makes .torn.2, and test_nothing_is_cut_until_the_bytes_are_kept. Seen failing: the 10 new tests that exercise the change fail on the old transcript.py (JSONDecodeError at construction); with the cut moved before the keep, test_nothing_is_cut_until_the_bytes_are_kept fails (1 failed, 22 passed), restored. Ran: scripts/check bh-02/plugins/agent-cordis-plugin exit 0 (187 passed, 1 skipped; format, lint, mypy, gates, docs ok); scripts/arch-check --no-fix exit 0; app, subagents and memory plugin tests 575 passed. Not claimed: AC3's 'scripts/check passes' is the full scripts/check, which is the reviewer's to prove (member check passes). Not done: nothing tells the person a torn line was set aside (FileTranscript has no output channel); the README says where to look. A second process appending to the same session while another resumes could still have its in-flight line cut (decision-0009's noted 'two processes can append to one session').

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 33%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
..........................................................s..ss.....ss.s [ 47%]
.s.s..ss.s..ss...s.s.s..ss.s.s..sssss.s..........s...................... [ 49%]
........................................................................ [ 51%]
.........................s.............................................. [ 53%]
...................sssssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
ssssssssssssss................................ssssssssss..s............. [ 57%]
...s...................................................s................ [ 58%]
........................................................................ [ 60%]
...................................................................sss.. [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
........................                                                 [100%]
3796 passed, 118 skipped in 195.37s (0:03:15)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.96 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (philosophy:reviewer): not closed. Full scripts/check exit 0 (3796 passed, 118 skipped), tree unchanged; AC1-3 met and ticked. Blocking: close-task refuses a bug with no recorded repro. The worker saw the new tests fail on the old transcript.py but did not record it; record it with record-check TASK-0141 --repro -- uv run pytest bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py -k torn_last_line against the code before 80e157a, then re-run close. Nits: _beside docstring (transcript.py) gives only the .bak example; nothing tells the person a torn line was set aside; a concurrent appender during resume could have its in-flight line cut (known, decision-0009).

Repro at b5e975958a0a, test files: bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py; command: `uv run pytest bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py -k torn_last_line` exited 1

(2 earlier lines omitted)
```text
platform linux -- Python 3.15.0, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/bh-02
configfile: pyproject.toml
plugins: xdist-3.8.0, hypothesis-6.168.0, asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 23 items / 22 deselected / 1 selected

bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py F       [100%]

=================================== FAILURES ===================================
_ test_a_torn_last_line_is_set_aside_and_the_next_entry_is_written_on_a_line_of_its_own _

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-2425/test_a_torn_last_line_is_set_a0')

    async def test_a_torn_last_line_is_set_aside_and_the_next_entry_is_written_on_a_line_of_its_own(
        tmp_path: Path,
    ) -> None:
        """A process killed mid-write leaves a last line with no newline that is not JSON: an entry that
        was never finished. The session resumes without it, the next entry does not glue onto it, and
        the bytes cut are kept beside the file."""
        path = tmp_path / "transcript.jsonl"
        torn = '{"role": "assistant", "content": [{"type": "te'
        path.write_text(_line("one") + _line("two") + torn)
>       async with FileTranscript(str(path)) as transcript:
                   ^^^^^^^^^^^^^^^^^^^^^^^^^

bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py:175: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/transcript.py:85: in __init__
    super().append(json.loads(line))
                   ^^^^^^^^^^^^^^^^
/root/.local/share/uv/python/cpython-3.15.0-linux-x86_64-gnu/lib/python3.15/json/__init__.py:371: in loads
    return _default_decoder.decode(s)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
/root/.local/share/uv/python/cpython-3.15.0-linux-x86_64-gnu/lib/python3.15/json/decoder.py:358: in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <json.decoder.JSONDecoder object at 0x7f7759364050>
s = '{"role": "assistant", "content": [{"type": "te', idx = 0

    def raw_decode(self, s, idx=0):
        """Decode a JSON document from ``s`` (a ``str`` beginning with
        a JSON document) and return a 2-tuple of the Python
        representation and the index in ``s`` where the document ended.
    
        This can be used to decode a JSON document from a string that may
        have extraneous data at the end.
    
        """
        try:
>           obj, end = self.scan_once(s, idx)
                       ^^^^^^^^^^^^^^^^^^^^^^
E           json.decoder.JSONDecodeError: Unterminated string starting at: line 1 column 44 (char 43)

/root/.local/share/uv/python/cpython-3.15.0-linux-x86_64-gnu/lib/python3.15/json/decoder.py:374: JSONDecodeError
=========================== short test summary info ============================
FAILED bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py::test_a_torn_last_line_is_set_aside_and_the_next_entry_is_written_on_a_line_of_its_own
======================= 1 failed, 22 deselected in 1.71s =======================
```

Round 2 (review round 1: the repro was not on record). Changed: the board only, no code. I put transcript.py back to its content before 80e157a in the working tree (git show 80e157a~1:bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/transcript.py), left test_agent_transcript.py as committed, ran record-check TASK-0141 --repro -- uv run pytest bh-02/plugins/agent-cordis-plugin/tests/test_agent_transcript.py -k torn_last_line from the repo root (exit 0 = the failure was recorded; the note above reads 'Repro at b5e975958a0a ... exited 1': 1 failed, 22 deselected, JSONDecodeError at construction in the old transcript.py line 85), then restored transcript.py from b5e9759 (git diff b5e9759 -- bh-02 is empty, tree clean). The recorded commit is b5e9759, the start of this round, so it stays an ancestor of the round's commit; the test file is byte-identical at b5e9759 and at 80e157a's tests (git diff --quiet b5e9759 -- the test file: exit 0). Seen passing on the restored code: the same command gives 1 passed, 22 deselected; the whole test_agent_transcript.py gave 23 passed. python3 <philosophy>/scripts/board-check close TASK-0141: 'ok: TASK-0141 can close' (exit 0). I did not run close-task: it sets Done, which is the reviewer's. The -k torn_last_line expression selects the one AC1 test; the other nine new tests were seen failing on the old code in round 1 but that run is not the recorded one. Left alone as not blocking: the _beside docstring's .bak-only example, telling the person a torn line was set aside, a concurrent appender's in-flight line (decision-0009). No code changed, so no member check was run; the reviewer's full scripts/check (exit 0, 3796 passed) stands for the unchanged code.

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 33%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
..........................................................s...s...ssss.. [ 47%]
ss.s..ss.s.s....ss..ss..ss..ss.s.ssss..s................................ [ 49%]
........................................................................ [ 51%]
.................s...................................................... [ 53%]
....................ssssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
ssssssssssssss....s...........................sssssssss...ss..........s. [ 57%]
......................................................s................. [ 58%]
........................................................................ [ 60%]
....................................................................sss. [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
........................                                                 [100%]
3796 passed, 118 skipped in 200.54s (0:03:20)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.62 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
