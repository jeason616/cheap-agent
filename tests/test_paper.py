"""Tests for paper writing assistance tools."""

import sys
import tempfile
from pathlib import Path


def test_latex_parser_sections():
    from cheap_agent.parsers.latex_parser import parse_latex_sections

    tex = r"""
\section{Introduction}
Some text here.
\subsection{Related Work}
More text.
\subsubsection{DINO-Based Detectors}
Details.
\section{Method}
Our approach.
"""
    sections = parse_latex_sections(tex, "main.tex")
    assert len(sections) >= 4
    assert sections[0]["level"] == "section"
    assert sections[0]["title"] == "Introduction"
    assert sections[1]["level"] == "subsection"
    assert sections[1]["title"] == "Related Work"
    print("[PASS] parse_latex_sections")


def test_latex_parser_inputs():
    from cheap_agent.parsers.latex_parser import parse_latex_inputs

    tex = r"""
\input{sections/introduction}
\include{sections/method}
\input{sections/experiments}
"""
    inputs = parse_latex_inputs(tex)
    assert len(inputs) == 3
    assert "sections/introduction" in inputs
    assert "sections/method" in inputs
    print("[PASS] parse_latex_inputs")


def test_latex_parser_citations():
    from cheap_agent.parsers.latex_parser import parse_latex_citations

    tex = r"""
As shown in \cite{dino2022}, the method works.
\citep{zhang2023,li2024} also support this.
\citet{wang2021} proposed the baseline.
"""
    cites = parse_latex_citations(tex, "main.tex")
    keys = {c["key"] for c in cites}
    assert "dino2022" in keys
    assert "zhang2023" in keys
    assert "li2024" in keys
    assert "wang2021" in keys
    print("[PASS] parse_latex_citations")


def test_latex_parser_labels():
    from cheap_agent.parsers.latex_parser import parse_latex_labels

    tex = r"""
\section{Introduction}\label{sec:intro}
\begin{figure}\caption{Framework}\label{fig:framework}\end{figure}
"""
    labels = parse_latex_labels(tex, "main.tex")
    label_names = {l["label"] for l in labels}
    assert "sec:intro" in label_names
    assert "fig:framework" in label_names
    print("[PASS] parse_latex_labels")


def test_latex_parser_figures():
    from cheap_agent.parsers.latex_parser import parse_latex_figures

    tex = r"""
\begin{figure}
\includegraphics{figs/framework.pdf}
\caption{The proposed framework.}
\label{fig:framework}
\end{figure}
"""
    figures = parse_latex_figures(tex, "main.tex")
    assert len(figures) == 1
    assert figures[0]["caption"] == "The proposed framework."
    assert figures[0]["label"] == "fig:framework"
    print("[PASS] parse_latex_figures")


def test_latex_parser_tables():
    from cheap_agent.parsers.latex_parser import parse_latex_tables

    tex = r"""
\begin{table}
\caption{Main results on COCO.}
\label{tab:main}
\begin{tabular}{l|c}
Method & AP \\
\hline
Ours & 45.2
\end{tabular}
\end{table}
"""
    tables = parse_latex_tables(tex, "main.tex")
    assert len(tables) == 1
    assert tables[0]["caption"] == "Main results on COCO."
    assert tables[0]["label"] == "tab:main"
    print("[PASS] parse_latex_tables")


def test_latex_parser_refs():
    from cheap_agent.parsers.latex_parser import parse_latex_refs

    tex = r"""
As shown in Figure~\ref{fig:framework} and Table~\ref{tab:main}.
See Section~\autoref{sec:intro} for details.
"""
    refs = parse_latex_refs(tex, "main.tex")
    ref_names = {r["ref"] for r in refs}
    assert "fig:framework" in ref_names
    assert "tab:main" in ref_names
    assert "sec:intro" in ref_names
    print("[PASS] parse_latex_refs")


def test_latex_parser_title_abstract():
    from cheap_agent.parsers.latex_parser import parse_latex_title, parse_latex_abstract

    tex = r"""
\documentclass{IEEEtran}
\title{A Novel Method for Object Detection}
\begin{abstract}
We propose a novel method that achieves state-of-the-art performance.
\end{abstract}
\begin{document}
"""
    title = parse_latex_title(tex)
    assert "Novel Method" in title

    abstract = parse_latex_abstract(tex)
    assert "novel method" in abstract
    print("[PASS] parse_latex_title / parse_latex_abstract")


def test_latex_parser_documentclass():
    from cheap_agent.parsers.latex_parser import parse_latex_documentclass

    tex = r"\documentclass[conference]{IEEEtran}"
    cls = parse_latex_documentclass(tex)
    assert cls == "IEEEtran"
    print("[PASS] parse_latex_documentclass")


def test_latex_parser_strip_comments():
    from cheap_agent.parsers.latex_parser import strip_latex_comments

    tex = "% This is a comment\nReal text % inline comment\n% Another comment"
    result = strip_latex_comments(tex)
    assert "Real text" in result
    assert "This is a comment" not in result
    print("[PASS] strip_latex_comments")


def test_bib_parser_entries():
    from cheap_agent.parsers.bib_parser import parse_bib_entries

    bib = """
@article{dino2022,
  title={DINO: DETR with Improved DeNoising Anchor Boxes},
  author={Zhang, Hao and Li, Feng},
  journal={arXiv},
  year={2022}
}

@inproceedings{zhang2023,
  title={A New Detector},
  author={Zhang, Wei},
  booktitle={CVPR},
  year={2023}
}
"""
    entries = parse_bib_entries(bib)
    assert len(entries) == 2
    assert entries[0]["key"] == "dino2022"
    assert entries[0]["type"] == "article"
    assert entries[0]["year"] == "2022"
    assert entries[1]["key"] == "zhang2023"
    assert entries[1]["type"] == "inproceedings"
    print("[PASS] parse_bib_entries")


def test_bib_parser_duplicate_keys():
    from cheap_agent.parsers.bib_parser import parse_bib_entries

    bib = """
@article{dup2022,
  title={First},
  year={2022}
}
@article{dup2022,
  title={Second},
  year={2023}
}
"""
    entries = parse_bib_entries(bib)
    assert len(entries) == 2
    assert entries[1]["is_duplicate"] is True
    print("[PASS] parse_bib_entries duplicate detection")


def test_bib_parser_keys_from_text():
    from cheap_agent.parsers.bib_parser import parse_bib_keys_from_text

    bib = """
@article{key1, title={T1}, year={2022}}
@inproceedings{key2, title={T2}, year={2023}}
"""
    keys = parse_bib_keys_from_text(bib)
    assert "key1" in keys
    assert "key2" in keys
    print("[PASS] parse_bib_keys_from_text")


def test_bib_parser_summarize():
    from cheap_agent.parsers.bib_parser import parse_bib_entries, summarize_bib_entries

    bib = "@article{test2022, title={Test}, year={2022}}"
    entries = parse_bib_entries(bib)
    summary = summarize_bib_entries(entries)
    assert "Total entries: 1" in summary
    assert "test2022" in summary
    print("[PASS] summarize_bib_entries")


def test_detect_paper_project():
    from cheap_agent.tools.paper import detect_paper_project_logic

    result = detect_paper_project_logic(use_llm=False)
    assert "Paper Project Detection" in result
    assert "Detected:" in result
    assert "Suggested next tools:" in result
    print("[PASS] detect_paper_project")


def test_find_paper_sections():
    from cheap_agent.tools.paper import find_paper_sections_logic

    result = find_paper_sections_logic(query="")
    assert "Paper Sections" in result or "Error" in result
    print("[PASS] find_paper_sections")


def test_parse_bib_file():
    from cheap_agent.tools.paper import parse_bib_file_logic

    result = parse_bib_file_logic(bib_file="")
    assert "BibTeX Summary" in result or "Error" in result
    print("[PASS] parse_bib_file")


def test_check_citation_coverage():
    from cheap_agent.tools.paper import check_citation_coverage_logic

    result = check_citation_coverage_logic(main_file="", bib_file="")
    assert "Citation Coverage" in result or "Error" in result
    print("[PASS] check_citation_coverage")


if __name__ == "__main__":
    print("=== paper tools tests ===\n")

    test_latex_parser_sections()
    test_latex_parser_inputs()
    test_latex_parser_citations()
    test_latex_parser_labels()
    test_latex_parser_figures()
    test_latex_parser_tables()
    test_latex_parser_refs()
    test_latex_parser_title_abstract()
    test_latex_parser_documentclass()
    test_latex_parser_strip_comments()
    print()
    test_bib_parser_entries()
    test_bib_parser_duplicate_keys()
    test_bib_parser_keys_from_text()
    test_bib_parser_summarize()
    print()
    test_detect_paper_project()
    test_find_paper_sections()
    test_parse_bib_file()
    test_check_citation_coverage()
    print("\n=== all paper tools tests passed ===")
