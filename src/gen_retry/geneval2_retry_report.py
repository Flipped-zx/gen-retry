"""Audit and report GenEval2 initial-generation retry trajectory readiness."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gen_retry.evaluators.geneval2_result_normalizer import load_geneval2_score_rows, normalize_geneval2_score_list
from gen_retry.offline_package_builder import select_manifest_rows
from gen_retry.offline_planner import is_passed
from gen_retry.schemas.actions import RetryReplanAction
from gen_retry.schemas.reports import NormalizedEvalReport
from gen_retry.utils.io import read_json, read_jsonl, write_json


DEFAULT_PROMPTS = "data/prompts/geneval2_balanced_100.jsonl"
DEFAULT_MANIFEST = "data/qwen_geneval2_balanced_100_x5_initial_gpt55_a100/generation_manifest.jsonl"
DEFAULT_INITIAL_PLAN_DIR = "data/plans/initial/geneval2_balanced_100_gpt55"
DEFAULT_PACKAGE_MANIFEST = "data/incoming_generation_results/geneval2_balanced_100_round0_initial_gpt55/package_manifest.jsonl"
DEFAULT_DIAGNOSTIC_JOBS = "data/geneval2_jobs/balanced100_candidate0/diagnostic_jobs.jsonl"
DEFAULT_EVAL_RESULTS = "data/geneval2_jobs/balanced100_candidate0/normalized_reports.jsonl"
DEFAULT_RETRY_MANIFEST = "data/outgoing_retry_actions/geneval2_balanced_100_round0_gpt55/retry_action_manifest.jsonl"
DEFAULT_TRAJECTORY_DIR = "data/raw_trajectories/geneval2_balanced_100_round0_gpt55"
DEFAULT_SFT_OUTPUT = "data/sft/geneval2_balanced_100_round0_retry_replan_sft.jsonl"


@dataclass(frozen=True)
class RetryStageReportConfig:
    prompts_path: str | Path = DEFAULT_PROMPTS
    manifest_path: str | Path = DEFAULT_MANIFEST
    initial_plan_dir: str | Path = DEFAULT_INITIAL_PLAN_DIR
    package_manifest_path: str | Path = DEFAULT_PACKAGE_MANIFEST
    diagnostic_jobs_path: str | Path = DEFAULT_DIAGNOSTIC_JOBS
    eval_results_path: str | Path = DEFAULT_EVAL_RESULTS
    raw_score_lists_path: str | Path | None = None
    benchmark_data_path: str | Path | None = None
    retry_manifest_path: str | Path = DEFAULT_RETRY_MANIFEST
    trajectory_dir: str | Path = DEFAULT_TRAJECTORY_DIR
    sft_output_path: str | Path = DEFAULT_SFT_OUTPUT
    candidate_index: int = 0
    all_candidates: bool = False
    limit: int = 100
    atom_threshold: float = 0.9
    markdown_output_path: str | Path | None = None
    summary_output_path: str | Path | None = None


def build_retry_stage_report(config: RetryStageReportConfig) -> dict[str, Any]:
    summary = summarize_retry_stage(config)
    markdown = render_retry_stage_markdown(summary)
    if config.markdown_output_path:
        target = Path(config.markdown_output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
    if config.summary_output_path:
        write_json(config.summary_output_path, summary)
    return {"summary": summary, "markdown": markdown}


def summarize_retry_stage(config: RetryStageReportConfig) -> dict[str, Any]:
    prompts = _jsonl_if_exists(config.prompts_path)
    manifest_rows = _jsonl_if_exists(config.manifest_path)
    selected_rows = select_manifest_rows(
        manifest_rows,
        candidate_index=config.candidate_index,
        all_candidates=config.all_candidates,
        limit=config.limit,
    )
    package_rows = _jsonl_if_exists(config.package_manifest_path)
    diagnostic_jobs = _jsonl_if_exists(config.diagnostic_jobs_path)
    eval_reports = _load_eval_reports(config)
    retry_outputs = _load_retry_outputs(config.retry_manifest_path)
    trajectory_rows = _load_trajectories(config.trajectory_dir)
    coverage = _coverage(selected_rows)
    failure_counts = _failure_counts(eval_reports)
    pass_count = sum(1 for report in eval_reports.values() if is_passed(report))
    fail_count = len(eval_reports) - pass_count if eval_reports else None
    pass_rate = (pass_count / len(eval_reports)) if eval_reports else None
    status_counts = Counter(str(row.get("status", "")) for row in trajectory_rows if str(row.get("status", "")))
    if retry_outputs and not status_counts:
        status_counts.update(str(row.get("status", "")) for row in retry_outputs if str(row.get("status", "")))
    valid_teacher_plans = sum(1 for row in retry_outputs if _has_valid_retry_action(row))

    return {
        "schema_version": "v1",
        "paths": {
            "prompts": str(config.prompts_path),
            "manifest": str(config.manifest_path),
            "initial_plan_dir": str(config.initial_plan_dir),
            "package_manifest": str(config.package_manifest_path),
            "diagnostic_jobs": str(config.diagnostic_jobs_path),
            "eval_results": str(config.eval_results_path),
            "raw_score_lists": str(config.raw_score_lists_path or ""),
            "retry_manifest": str(config.retry_manifest_path),
            "trajectory_dir": str(config.trajectory_dir),
            "sft_output": str(config.sft_output_path),
        },
        "selection": {
            "mode": "all_candidates" if config.all_candidates else "candidate_index",
            "candidate_index": config.candidate_index,
            "limit": config.limit,
        },
        "artifact_exists": {
            "prompts": Path(config.prompts_path).exists(),
            "manifest": Path(config.manifest_path).exists(),
            "initial_plan_dir": Path(config.initial_plan_dir).exists(),
            "package_manifest": Path(config.package_manifest_path).exists(),
            "diagnostic_jobs": Path(config.diagnostic_jobs_path).exists(),
            "eval_results": Path(config.eval_results_path).exists(),
            "raw_score_lists": bool(config.raw_score_lists_path and Path(config.raw_score_lists_path).exists()),
            "retry_manifest": Path(config.retry_manifest_path).exists(),
            "trajectory_dir": Path(config.trajectory_dir).exists(),
            "sft_output": Path(config.sft_output_path).exists(),
        },
        "counts": {
            "prompts": len(prompts),
            "manifest_rows": len(manifest_rows),
            "manifest_unique_prompt_ids": len({_prompt_id(row, index) for index, row in enumerate(manifest_rows)}),
            "selected_initial_images": len(selected_rows),
            "manifest_images_existing": sum(1 for row in manifest_rows if _image_exists(row)),
            "selected_images_existing": sum(1 for row in selected_rows if _image_exists(row)),
            "initial_plan_files": len(list(Path(config.initial_plan_dir).glob("*.json")))
            if Path(config.initial_plan_dir).exists()
            else 0,
            "package_rows": len(package_rows),
            "packages_with_initial_plan": sum(1 for row in package_rows if row.get("has_initial_plan")),
            "packages_with_eval_report": sum(1 for row in package_rows if row.get("has_eval_report")),
            "diagnostic_jobs": len(diagnostic_jobs),
            "eval_reports": len(eval_reports),
            "pass_count_before_retry": pass_count if eval_reports else None,
            "fail_count_before_retry": fail_count,
            "retry_outputs": len(retry_outputs),
            "raw_trajectories": len(trajectory_rows),
            "initial_success": int(status_counts.get("initial_success", 0)),
            "retry_ready": int(status_counts.get("retry_ready", 0)),
            "error": int(status_counts.get("error", 0)),
            "valid_teacher_retry_plans": valid_teacher_plans,
        },
        "metrics": {
            "pass_rate_before_retry": pass_rate,
            "score_min": min((report.score for report in eval_reports.values()), default=None),
            "score_max": max((report.score for report in eval_reports.values()), default=None),
            "score_mean": (
                sum(report.score for report in eval_reports.values()) / len(eval_reports)
                if eval_reports
                else None
            ),
        },
        "failure_type_distribution": dict(sorted(failure_counts.items())),
        "coverage": coverage,
        "status_distribution": dict(sorted(status_counts.items())),
        "candidate_mapping_available": bool(package_rows and diagnostic_jobs),
        "completion_state": _completion_state(eval_reports, retry_outputs, trajectory_rows),
    }


def render_retry_stage_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    metrics = summary["metrics"]
    paths = summary["paths"]
    artifacts = summary["artifact_exists"]
    completion_state = summary["completion_state"]
    selection = summary.get("selection", {})
    selection_label = (
        "all candidate images"
        if selection.get("mode") == "all_candidates"
        else f"candidate-{selection.get('candidate_index', 0)} images"
    )
    selection_flag = (
        "  --all-candidates \\\n  --limit 500 \\"
        if selection.get("mode") == "all_candidates"
        else "  --candidate-index 0 \\\n  --limit 100 \\"
    )
    selected_count = counts["selected_initial_images"]
    eval_output_dir = str(Path(paths["eval_results"]).parent)
    package_dir = str(Path(paths["package_manifest"]).parent)
    retry_output_dir = str(Path(paths["retry_manifest"]).parent)
    pass_rate = _pct(metrics["pass_rate_before_retry"])
    eval_note = "" if counts["eval_reports"] else "（当前缺少 normalized GenEval2 reports，无法计算真实 pass/fail）"
    teacher_note = "" if counts["retry_outputs"] else "（当前缺少 teacher retry action 输出）"
    lines = [
        "# GenEval2 Balanced-100 初始生成诊断与 Retry Trajectory 报告",
        "",
        "## 结论摘要",
        "",
        f"- 当前状态：`{completion_state}`。",
        f"- prompts: {counts['prompts']}；manifest rows: {counts['manifest_rows']}；selected {selection_label}: {counts['selected_initial_images']}。",
        f"- 本地存在初始图片：{counts['manifest_images_existing']} / {counts['manifest_rows']}；selected 图片：{counts['selected_images_existing']} / {counts['selected_initial_images']}。",
        f"- initial plan files: {counts['initial_plan_files']}；generation packages: {counts['package_rows']}；diagnostic jobs: {counts['diagnostic_jobs']}。",
        f"- GenEval2 eval reports: {counts['eval_reports']} {eval_note}",
        f"- pass before retry: {counts['pass_count_before_retry']}；fail before retry: {counts['fail_count_before_retry']}；pass rate: {pass_rate}。",
        f"- raw trajectories: {counts['raw_trajectories']}；`initial_success`: {counts['initial_success']}；`retry_ready`: {counts['retry_ready']}；valid teacher retry plans: {counts['valid_teacher_retry_plans']} {teacher_note}",
        "",
        "## 1. 数据位置与可用性",
        "",
        "| artifact | path | exists | count |",
        "|---|---|---:|---:|",
        f"| selected prompts | `{paths['prompts']}` | {_yes(artifacts['prompts'])} | {counts['prompts']} |",
        f"| initial plan cache | `{paths['initial_plan_dir']}` | {_yes(artifacts['initial_plan_dir'])} | {counts['initial_plan_files']} |",
        f"| Qwen initial generation manifest | `{paths['manifest']}` | {_yes(artifacts['manifest'])} | {counts['manifest_rows']} |",
        f"| generation packages | `{paths['package_manifest']}` | {_yes(artifacts['package_manifest'])} | {counts['package_rows']} |",
        f"| GenEval2 diagnostic jobs | `{paths['diagnostic_jobs']}` | {_yes(artifacts['diagnostic_jobs'])} | {counts['diagnostic_jobs']} |",
        f"| normalized GenEval2 reports | `{paths['eval_results']}` | {_yes(artifacts['eval_results'])} | {counts['eval_reports']} |",
        f"| retry action manifest | `{paths['retry_manifest']}` | {_yes(artifacts['retry_manifest'])} | {counts['retry_outputs']} |",
        f"| raw trajectories | `{paths['trajectory_dir']}` | {_yes(artifacts['trajectory_dir'])} | {counts['raw_trajectories']} |",
        f"| SFT output | `{paths['sft_output']}` | {_yes(artifacts['sft_output'])} | - |",
        "",
        f"可用 identifier：`prompt_id`、`candidate_id`、`candidate_index`、`image_id`、`source_index`、`seed`、`image_path`。candidate-level mapping 已由 package manifest、diagnostic jobs 和 eval image map 共同提供。当前选择模式：`{selection.get('mode', 'candidate_index')}`。",
        "",
        "## 2. Summary Statistics",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| number of prompts | {counts['prompts']} |",
        f"| number of initial images in manifest | {counts['manifest_rows']} |",
        f"| selected initial images | {counts['selected_initial_images']} |",
        f"| pass rate before retry | {pass_rate} |",
        f"| failed samples with valid teacher retry plans | {counts['valid_teacher_retry_plans']} |",
        f"| initial_success | {counts['initial_success']} |",
        f"| retry_ready | {counts['retry_ready']} |",
        "",
        "### Failure Type Distribution",
        "",
        _counter_table(summary["failure_type_distribution"], "failure_type"),
        "",
        "### Coverage",
        "",
        _counter_table(summary["coverage"], "coverage"),
        "",
        "## 3. 本阶段工作方式",
        "",
        "1. 从 initial-plan generation manifest 选择目标 candidate 图片；本次可用 `--all-candidates` 覆盖每个 prompt 的 5 张图。",
        "2. 运行或加载 GenEval2，归一化为包含 score、passed/failed/uncertain constraints 和 critical failure types 的 report。",
        "3. 为每个 candidate 写 round-0 raw trajectory；round-0 memory 使用 `persistent_failures = failed_constraints`、`new_failures = []`、`score_delta_from_previous = null`。",
        "4. 通过 stop rule 将通过样本标记为 `initial_success`。",
        "5. 对失败样本调用 teacher 一次，输入 original prompt、metadata、initial plan、generation metadata、normalized diagnostic、compact memory、best-so-far 和 previous action。",
        "6. teacher 返回 strict JSON `retry_replan` 后，将样本标记为 `retry_ready`。",
        "7. 默认不生成 retry 图片；本阶段只准备下一轮 retry generation 所需状态和 SFT 目标。",
        "",
        "## 4. Patched Files / Functions",
        "",
        "- `src/gen_retry/offline_planner.py`: round-0 memory、`retry_ready_action`、status、teacher request state。",
        "- `src/gen_retry/evaluators/geneval2_result_normalizer.py`: GenEval2 score-list/atom-row normalization。",
        "- `src/gen_retry/offline_package_builder.py`: manifest + initial plan + eval report package construction。",
        "- `src/gen_retry/retry_plan_batch.py`: package rebuild、preflight、teacher call、quality report batch orchestration。",
        "- `src/gen_retry/export/export_offline_sft.py`: candidate-level trajectory to step-level retry SFT export。",
        "- `src/gen_retry/geneval2_retry_report.py`: 本报告和 summary stats 生成。",
        "- `scripts/run_geneval2_batch.py`: GenEval2 batch runner；temporary work dir stays under output dir。",
        "- `scripts/prepare_geneval2_retry_inputs.py`: no-API prepare checkpoint。",
        "- `scripts/build_geneval2_retry_plans.py`: one-shot teacher retry planning batch。",
        "- `scripts/export_offline_retry_sft.py`: SFT export CLI。",
        "- `scripts/report_geneval2_retry_stage.py`: 本报告 CLI。",
        "",
        "## 5. Runnable Command Example",
        "",
        "```bash",
        "python3 scripts/run_geneval2_batch.py \\",
        f"  --manifest {paths['manifest']} \\",
        f"  --output-dir {eval_output_dir} \\",
        "  --geneval2-root ../GenEval2 \\",
        "  --qwen3vl-model-path /root/private_data/agentic_image/models/Qwen3-VL-8B-Instruct \\",
        selection_flag,
        "  --n-samples 5 \\",
        "  --method soft_tifa_gm \\",
        "  --atom-threshold 0.9 \\",
        "  --keep-eval-inputs \\",
        "  --resume",
        "```",
        "",
        "```bash",
        "python3 scripts/prepare_geneval2_retry_inputs.py \\",
        f"  --manifest {paths['manifest']} \\",
        f"  --package-dir {package_dir} \\",
        f"  --initial-plan-dir {paths['initial_plan_dir']} \\",
        f"  --diagnostic-jobs {paths['diagnostic_jobs']} \\",
        f"  --eval-results {paths['eval_results']} \\",
        selection_flag.rstrip(" \\"),
        "```",
        "",
        "```bash",
        "python3 scripts/build_geneval2_retry_plans.py \\",
        f"  --package-dir {package_dir} \\",
        f"  --output-dir {retry_output_dir} \\",
        f"  --trajectory-dir {paths['trajectory_dir']} \\",
        f"  --eval-results {paths['eval_results']} \\",
        f"  --diagnostic-jobs {paths['diagnostic_jobs']} \\",
        f"  --limit {selected_count} \\",
        "  --teacher gpt55 \\",
        "  --max-retry 3",
        "```",
        "",
        "```bash",
        "python3 scripts/export_offline_retry_sft.py \\",
        f"  --trajectories-dir {paths['trajectory_dir']} \\",
        f"  --output {paths['sft_output']} \\",
        "  --rejected-output data/rejected/geneval2_balanced_100x5_round0_retry_replan_rejected.jsonl",
        "```",
        "",
        "```bash",
        "python3 scripts/report_geneval2_retry_stage.py \\",
        f"  --package-manifest {paths['package_manifest']} \\",
        f"  --diagnostic-jobs {paths['diagnostic_jobs']} \\",
        f"  --eval-results {paths['eval_results']} \\",
        f"  --retry-manifest {paths['retry_manifest']} \\",
        f"  --trajectory-dir {paths['trajectory_dir']} \\",
        f"  --sft-output {paths['sft_output']} \\",
        "  --all-candidates \\",
        f"  --limit {selected_count} \\",
        "  --markdown-output docs/GENEVAL2_BALANCED100_RETRY_TRAJECTORY_REPORT.md \\",
        "  --summary-output data/analysis/geneval2_balanced100_retry_stage_summary.json",
        "```",
        "",
        "## 6. Blockers",
        "",
    ]
    if not counts["eval_reports"]:
        lines.append("- 当前没有 normalized GenEval2 diagnostics，因此 pass/fail 和 failure type stats 仍不可证明。")
    if not counts["retry_outputs"]:
        lines.append("- 当前没有 teacher retry action manifest；如果 `GEN_RETRY_TEACHER_*` 未设置，不能调用真实 GPT teacher。")
    if counts["eval_reports"] and counts["retry_outputs"]:
        lines.append("- 当前报告未发现数据层 blocker。")
    return "\n".join(lines) + "\n"


def _jsonl_if_exists(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    return read_jsonl(source)


def _load_eval_reports(config: RetryStageReportConfig) -> dict[str, NormalizedEvalReport]:
    path = Path(config.eval_results_path)
    if path.exists():
        reports: dict[str, NormalizedEvalReport] = {}
        for row in read_jsonl(path):
            candidate_id = str(row.get("candidate_id") or row.get("group_id") or "").strip()
            if not candidate_id:
                continue
            report_data = row.get("normalized_report") if isinstance(row.get("normalized_report"), dict) else row
            reports[candidate_id] = NormalizedEvalReport.from_dict(dict(report_data))
        return reports
    if config.raw_score_lists_path and Path(config.raw_score_lists_path).exists():
        rows = load_geneval2_score_rows(config.raw_score_lists_path, benchmark_data=config.benchmark_data_path)
        return normalize_geneval2_score_list(rows, aggregate_by="candidate_id", atom_threshold=config.atom_threshold)
    return {}


def _load_retry_outputs(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows = read_jsonl(source)
    outputs: list[dict[str, Any]] = []
    for row in rows:
        output_path = row.get("output_path")
        if output_path and Path(str(output_path)).exists():
            outputs.append(read_json(output_path))
        else:
            outputs.append(row)
    return outputs


def _load_trajectories(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    return [read_json(item) for item in sorted(source.glob("*.json"))]


def _coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        skills = {str(item) for item in metadata.get("skills", [])}
        tags = {str(item) for item in metadata.get("sampling_tags", [])}
        if "count" in skills:
            counts["count"] += 1
        if "object" in skills:
            counts["object"] += 1
        if skills & {"attribute", "color"}:
            counts["attribute"] += 1
        if skills & {"position", "verb", "relation"}:
            counts["relation"] += 1
        if "multi_constraint" in tags or len(skills) > 1:
            counts["multi_constraint"] += 1
    return dict(sorted(counts.items()))


def _failure_counts(reports: dict[str, NormalizedEvalReport]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for report in reports.values():
        values = list(report.critical_failure_types) or [item.type for item in report.failed_constraints if item.type]
        counts.update(str(item) for item in values if str(item))
    return counts


def _has_valid_retry_action(row: dict[str, Any]) -> bool:
    action = row.get("teacher_action") or row.get("retry_ready_action")
    if not isinstance(action, dict) or not action:
        return False
    try:
        RetryReplanAction.from_dict(action)
    except Exception:  # noqa: BLE001
        return False
    return True


def _completion_state(
    eval_reports: dict[str, NormalizedEvalReport],
    retry_outputs: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
) -> str:
    if not eval_reports:
        return "waiting_for_geneval2"
    failed = [candidate_id for candidate_id, report in eval_reports.items() if not is_passed(report)]
    if failed and not retry_outputs:
        return "waiting_for_teacher_retry_plans"
    if failed and len(retry_outputs) < len(eval_reports):
        return "partial_teacher_retry_plans"
    if not trajectories:
        return "waiting_for_raw_trajectories"
    return "retry_ready"


def _prompt_id(row: dict[str, Any], index: int) -> str:
    metadata = dict(row.get("metadata") or {})
    return str(metadata.get("prompt_id") or row.get("prompt_id") or row.get("sample_id") or index)


def _image_exists(row: dict[str, Any]) -> bool:
    value = row.get("image_path") or (row.get("metadata") or {}).get("image_path")
    return bool(value and Path(str(value)).exists())


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _pct(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value * 100:.2f}%"


def _counter_table(values: dict[str, int], label: str) -> str:
    if not values:
        return f"| {label} | count |\n|---|---:|\n| unavailable | 0 |"
    lines = [f"| {label} | count |", "|---|---:|"]
    for key, value in sorted(values.items()):
        lines.append(f"| `{key}` | {value} |")
    return "\n".join(lines)
