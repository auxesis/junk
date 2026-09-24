from pr_review.plain_language.hunks import git_diff, hunk_for

DIFF = """diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
@@ -10,4 +11,5 @@ def main():
     a = 1
-    b = 2
+    b = 3
+    c = 4
     return a
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""


def test_finds_the_hunk_containing_the_line():
    out = hunk_for(DIFF, "src/app.py", 13)
    assert out.startswith("@@ -10,4 +11,5 @@")
    assert "+    c = 4" in out
    assert "import sys" not in out


def test_removed_lines_do_not_count_as_new_lines():
    out = hunk_for(DIFF, "src/app.py", 12)
    assert "+    b = 3" in out
    assert "-    b = 2" in out


def test_another_file_in_the_same_diff():
    assert hunk_for(DIFF, "README.md", 1).splitlines() == ["@@ -1 +1 @@", "-old", "+new"]


def test_a_line_or_path_outside_the_diff_gives_nothing():
    assert hunk_for(DIFF, "src/app.py", 99) == ""
    assert hunk_for(DIFF, "missing.py", 1) == ""


def test_context_limits_the_rows_around_the_line():
    body = "\n".join(f"+line {i}" for i in range(1, 101))
    diff = f"diff --git a/f b/f\n--- /dev/null\n+++ b/f\n@@ -0,0 +1,100 @@\n{body}\n"
    out = hunk_for(diff, "f", 50, context=2).splitlines()
    assert out == ["@@ -0,0 +1,100 @@", "+line 48", "+line 49", "+line 50", "+line 51", "+line 52"]


def test_git_diff_runs_a_three_dot_diff_in_the_workdir():
    calls = []

    class Done:
        stdout = "DIFF"

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        return Done()

    assert git_diff("/wd", "abc123", runner=runner) == "DIFF"
    cmd, kw = calls[0]
    assert cmd == ["git", "diff", "abc123...HEAD"]
    assert kw["cwd"] == "/wd"
