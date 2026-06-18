"""Tests for Phase 3 error diagnostics tools."""

import sys

SAMPLE_TRACEBACK = """Traceback (most recent call last):
  File "config.py", line 21, in <module>
    WORKSPACE_ROOT: Path = Path(os.getenv("WORKSPACE_ROOT") or os.getcwd()).resolve()
  File "workspace.py", line 30, in resolve_safe_path
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
  File "server.py", line 33, in _safe_call
    return fn(*args, **kwargs)
RuntimeError: some test error
"""

SAMPLE_IMPORT_ERROR = """Traceback (most recent call last):
  File "train.py", line 5, in <module>
    import ultralytics
ModuleNotFoundError: No module named 'ultralytics'
"""

SAMPLE_CUDA_OOM = """Traceback (most recent call last):
  File "train.py", line 100, in train
    loss.backward()
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
"""

SAMPLE_SHAPE_MISMATCH = """Traceback (most recent call last):
  File "model.py", line 50, in forward
    x = self.fc(x)
RuntimeError: mat1 and mat2 shapes cannot be multiplied (32x512 and 1024x10)
"""


def test_parse_python_traceback():
    from cheap_agent.tools.diagnostics import parse_python_traceback

    parsed = parse_python_traceback(SAMPLE_TRACEBACK)
    assert parsed["error_type"] == "RuntimeError"
    assert "some test error" in parsed["error_message"]
    assert parsed["has_traceback"] is True
    assert len(parsed["frames"]) >= 2
    print("[PASS] parse_python_traceback normal")

    parsed = parse_python_traceback("No traceback here")
    assert parsed["has_traceback"] is False
    print("[PASS] parse_python_traceback no traceback")


def test_extract_traceback_frames():
    from cheap_agent.tools.diagnostics import extract_traceback_frames

    frames = extract_traceback_frames(SAMPLE_TRACEBACK)
    assert len(frames) >= 2
    assert frames[0]["file"] == "config.py"
    assert frames[0]["line"] == 21
    assert frames[0]["function"] == "<module>"
    print("[PASS] extract_traceback_frames")

    frames = extract_traceback_frames("No frames here")
    assert len(frames) == 0
    print("[PASS] extract_traceback_frames no frames")


def test_analyze_traceback_with_context():
    from cheap_agent.tools.diagnostics import analyze_traceback_with_context_logic

    result = analyze_traceback_with_context_logic(SAMPLE_TRACEBACK, use_llm=False)
    assert "Traceback Summary" in result
    assert "Error type: RuntimeError" in result
    assert "some test error" in result
    print("[PASS] analyze_traceback_with_context without LLM")

    result = analyze_traceback_with_context_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] analyze_traceback_with_context empty input")


def test_diagnose_import_error():
    from cheap_agent.tools.diagnostics import diagnose_import_error_logic

    result = diagnose_import_error_logic(SAMPLE_IMPORT_ERROR, use_llm=False)
    assert "Import Error Diagnosis" in result
    assert "ultralytics" in result
    assert "Likely Causes" in result
    assert "Suggested Checks" in result
    print("[PASS] diagnose_import_error normal")

    result = diagnose_import_error_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] diagnose_import_error empty input")


def test_diagnose_training_error():
    from cheap_agent.tools.diagnostics import diagnose_training_error_logic

    result = diagnose_training_error_logic(SAMPLE_CUDA_OOM, use_llm=False)
    assert "Training Error Diagnosis" in result
    assert "cuda_oom" in result
    assert "batch_size" in result.lower()
    print("[PASS] diagnose_training_error CUDA OOM")

    result = diagnose_training_error_logic(SAMPLE_SHAPE_MISMATCH, use_llm=False)
    assert "shape_mismatch" in result
    print("[PASS] diagnose_training_error shape mismatch")

    result = diagnose_training_error_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] diagnose_training_error empty input")


def test_suggest_debug_steps():
    from cheap_agent.tools.diagnostics import suggest_debug_steps_logic

    result = suggest_debug_steps_logic("训练时 loss 为 NaN", use_llm=False)
    assert "Debug Plan" in result
    assert "Recommended steps" in result
    assert "Suggested MCP tools" in result
    print("[PASS] suggest_debug_steps normal")

    result = suggest_debug_steps_logic("CUDA OOM", error_log=SAMPLE_CUDA_OOM, use_llm=False)
    assert "Debug Plan" in result
    print("[PASS] suggest_debug_steps with error log")

    result = suggest_debug_steps_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] suggest_debug_steps empty input")


if __name__ == "__main__":
    print("=== diagnostics tools tests ===\n")
    test_parse_python_traceback()
    test_extract_traceback_frames()
    print()
    test_analyze_traceback_with_context()
    print()
    test_diagnose_import_error()
    print()
    test_diagnose_training_error()
    print()
    test_suggest_debug_steps()
    print("\n=== all diagnostics tools tests passed ===")
