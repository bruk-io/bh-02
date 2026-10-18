---
id: TASK-0141
title: A transcript whose last line is torn still resumes
status: To Do
assignee: []
created_date: '2026-10-18 12:15'
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
- [ ] #1 A transcript file whose last line is torn (no newline, not JSON) resumes without that line, and the next entry is written on a line of its own (a test with a torn tail, then an append, then a resume that reads every entry)
- [ ] #2 A line that is not JSON anywhere but the end still stops the transcript, with an error naming the file and the line number and saying what to do
- [ ] #3 The dropped bytes are not silently lost: they are kept beside the transcript (or the error says where), and the notes say which; scripts/check passes
<!-- AC:END -->
