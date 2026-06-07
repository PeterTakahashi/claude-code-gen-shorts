"""Plan a serialized adaptation via Gemini CLI.

Three sequential stages:
  S1 research:      subject → timeline + characters + motifs + themes + quotes
  S2 episodes:      research + episode count → N episodes (in-media-res ch1, cliffhanger every ep)
  S3 foreshadowing: research + episodes → 10-18 cross-episode payoff chains

Output: projects/<id>/series_plan.yaml

Existing chapters (anything with work/chapters/<id>/scenes.json already on disk)
are passed to S2 as FIXED context — S2 designs future episodes to harmonize
with what's already been made, rather than overwriting it.

Usage:
  uv run python -m src.plan_series <project_id>
  uv run python -m src.plan_series elonmusk --episodes 14 --force
  uv run python -m src.plan_series elonmusk --subject "イーロン・マスク" --episodes 12
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .llm import REPO_ROOT, extract_json, run_gemini_api, run_gemini_p
from .project import ProjectContext, load


PROMPTS_DIR = REPO_ROOT / "prompts"


def _existing_chapters_summary(project: ProjectContext) -> str:
    """Human-readable bullet list of chapters that already have scenes.json."""
    lines: list[str] = []
    for ch in project.chapters:
        if not ch.scenes_json.exists():
            continue
        try:
            scenes_data = json.loads(ch.scenes_json.read_text(encoding="utf-8"))
            scene_titles = [
                s.get("title") or s.get("id", "?") for s in scenes_data.get("scenes", [])
            ]
            lines.append(f"- {ch.id}: 「{ch.title}」 — scenes: {', '.join(scene_titles)}")
        except Exception:
            lines.append(f"- {ch.id}: 「{ch.title}」 (scenes.json unreadable)")
    return "\n".join(lines) if lines else "(no chapters completed yet)"


def _parse_or_dump(raw: str, debug_path: Path, stage_name: str):
    """Parse JSON or save raw response for debugging."""
    js = extract_json(raw)
    try:
        return json.loads(js)
    except json.JSONDecodeError as e:
        debug_path.write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"{stage_name} returned invalid JSON: {e}.\n"
            f"Raw response saved to {debug_path} for inspection."
        )


def plan(
    project: ProjectContext,
    *,
    subject: str,
    episode_count: int,
    model: str = "gemini-2.5-pro",
    transport: str = "api",
    force: bool = False,
) -> Path:
    out_path = project.project_dir / "series_plan.yaml"
    if out_path.exists() and not force:
        print(f"series_plan.yaml exists — pass --force to overwrite ({out_path})")
        return out_path

    def call_gemini(prompt: str, force_json: bool = True) -> str:
        if transport == "api":
            return run_gemini_api(
                prompt,
                model=model,
                response_mime_type="application/json" if force_json else None,
            )
        return run_gemini_p(prompt, model=model)

    existing = _existing_chapters_summary(project)

    # --- S1 RESEARCH ---
    print(f"\n[S1/research] researching {subject}… (transport={transport}, model={model})")
    s1_template = (PROMPTS_DIR / "series_research.md").read_text(encoding="utf-8")
    s1_prompt = s1_template.replace("{{subject}}", subject)
    s1_raw = call_gemini(s1_prompt)
    s1_data = _parse_or_dump(
        s1_raw,
        project.project_dir / "series_plan_s1_raw.txt",
        "S1/research",
    )
    print(
        f"[S1/research] OK — {len(s1_data.get('timeline', []))} timeline entries, "
        f"{len(s1_data.get('key_characters', []))} characters, "
        f"{len(s1_data.get('recurring_motifs', []))} motifs"
    )

    # --- S2 EPISODES ---
    print(f"\n[S2/episodes] planning {episode_count} episodes…")
    s2_template = (PROMPTS_DIR / "series_episodes.md").read_text(encoding="utf-8")
    s2_prompt = (
        s2_template.replace("{{subject}}", subject)
        .replace("{{episode_count}}", str(episode_count))
        .replace("{{existing_chapters}}", existing)
        .replace("{{research_json}}", json.dumps(s1_data, ensure_ascii=False, indent=2))
    )
    s2_raw = call_gemini(s2_prompt)
    s2_data = _parse_or_dump(
        s2_raw,
        project.project_dir / "series_plan_s2_raw.txt",
        "S2/episodes",
    )
    print(f"[S2/episodes] OK — {len(s2_data)} episodes")

    # --- S3 FORESHADOWING ---
    print(f"\n[S3/foreshadowing] designing payoff chains…")
    s3_template = (PROMPTS_DIR / "series_foreshadowing.md").read_text(encoding="utf-8")
    s3_prompt = (
        s3_template.replace("{{subject}}", subject)
        .replace("{{research_json}}", json.dumps(s1_data, ensure_ascii=False, indent=2))
        .replace("{{episodes_json}}", json.dumps(s2_data, ensure_ascii=False, indent=2))
    )
    s3_raw = call_gemini(s3_prompt)
    s3_data = _parse_or_dump(
        s3_raw,
        project.project_dir / "series_plan_s3_raw.txt",
        "S3/foreshadowing",
    )
    print(f"[S3/foreshadowing] OK — {len(s3_data)} chains")

    # --- COMBINE ---
    series_plan = {
        "subject": subject,
        "total_episodes": episode_count,
        "model_used": model,
        "transport": transport,
        "research": s1_data,
        "episodes": s2_data,
        "foreshadowing": s3_data,
    }
    out_path.write_text(
        yaml.safe_dump(series_plan, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )

    # Cleanup debug files if everything succeeded
    for stage in ("s1", "s2", "s3"):
        debug = project.project_dir / f"series_plan_{stage}_raw.txt"
        if debug.exists():
            debug.unlink()

    print(f"\n✅ {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("project_id", help="Project id under projects/")
    parser.add_argument(
        "--subject",
        help="Subject name (defaults to project.title_ja or project.subject)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=12,
        help="Total episode count (default: 12)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Gemini model (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--transport",
        default="api",
        choices=["api", "cli"],
        help="Use direct REST (api) or gemini CLI (cli). Default: api.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing series_plan.yaml",
    )
    args = parser.parse_args()

    project = load(args.project_id)
    subject = (
        args.subject
        or project.raw.get("subject")
        or project.title_ja
        or project.id
    )
    plan(
        project,
        subject=subject,
        episode_count=args.episodes,
        model=args.model,
        transport=args.transport,
        force=args.force,
    )


if __name__ == "__main__":
    main()
