"""Row counts read straight out of a gzipped pg_dump, including empty tables."""

import gzip

from r3m import dump


def test_an_empty_table_counts_zero_and_does_not_swallow_the_next():
    text = (
        "COPY public.label_run (id) FROM stdin;\n1\n2\n\\.\n\n"
        "COPY public.quiz_session (id) FROM stdin;\n\\.\n\n"
        "COPY public.game_label (id) FROM stdin;\n7\n8\n9\n\\.\n"
    )
    counts = dump._counts_in(gzip.compress(text.encode()))
    assert counts["label_run"] == 2
    assert counts["quiz_session"] == 0
    assert counts["game_label"] == 3
