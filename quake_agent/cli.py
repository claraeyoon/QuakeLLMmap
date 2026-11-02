from __future__ import annotations
import argparse
import sys
import json
from pathlib import Path

from quake_agent.config import EventConfig, FilterConfig, Settings
from quake_agent.core.orchestrator import QuakeAgentOrchestrator

def main():
    parser = argparse.ArgumentParser(
        description="QuakeAgent: Local-First Agentic AI Earthquake Intelligence & ShakeMap Workflow"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the full agentic pipeline on local files")
    run_parser.add_argument("--event-id", default="us7000pn9s", help="USGS Event ID or custom slug")
    run_parser.add_argument("--event-config", default=None, help="Path to custom event_config.yaml")
    run_parser.add_argument("--inbound-dir", default=None, help="Path to directory containing PDFs, images, videos")
    run_parser.add_argument("--file", default=None, help="Path to a single specific input file (PDF, image, video)")
    
    # Filter arguments
    run_parser.add_argument("--locations", nargs="+", default=None, help="Whitelist specific locations/townships")
    run_parser.add_argument("--docs", nargs="+", default=None, help="Whitelist specific document names or glob patterns")
    run_parser.add_argument("--platforms", nargs="+", default=None, help="Included platforms (e.g. local pdf reddit)")
    run_parser.add_argument("--max-rrup", type=float, default=None, help="Max distance to fault rupture in km")
    run_parser.add_argument("--web", action="store_true", help="Also harvest Reddit and Web content")
    
    # Model & Performance controls (Rate Limit & Latency Mitigation)
    run_parser.add_argument("--model", default=None, help="Gemini model to use (e.g. gemini-3.5-flash-lite, gemini-3.8-flash)")
    run_parser.add_argument("--thinking", default="low", choices=["minimal", "low", "medium", "high"], help="Gemini thinking level (low recommended to avoid timeouts)")
    run_parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds (default: 30.0)")
    run_parser.add_argument("--fallback-model", default="gemini-3.6-flash", help="Fallback model if primary model hits 503 or 429")
    run_parser.add_argument("--pace", type=float, default=2.0, help="Seconds to sleep between batch files to respect 15 RPM rate limits")

    # Command: shakemap
    sm_parser = subparsers.add_parser("shakemap", help="USGS ShakeMap v4 input generation and comparison")
    sm_parser.add_argument("--event-id", default="us7000pn9s", help="Event ID")
    sm_parser.add_argument("--fetch-official", action="store_true", help="Download official USGS ShakeMap from ComCat")

    # Command: test
    subparsers.add_parser("test", help="Run a quick synthetic test against local test files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "test":
        from quake_agent.test_agent import run_quick_test
        run_quick_test()
        sys.exit(0)

    # Load Event Config
    event_cfg = EventConfig.from_file(args.event_config) if getattr(args, "event_config", None) else EventConfig(event_id=args.event_id)

    # Build Filter Config
    filter_cfg = FilterConfig(
        allowed_locations=getattr(args, "locations", None),
        selected_documents=getattr(args, "docs", None),
        included_platforms=getattr(args, "platforms", None) or ["local", "pdf", "reddit", "web"],
        max_rrup_km=getattr(args, "max_rrup", None)
    )

    settings = Settings(
        deep_reasoning_model=getattr(args, "model", None) or os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        fallback_model=getattr(args, "fallback_model", "gemini-3.6-flash"),
        thinking_level=getattr(args, "thinking", "low"),
        timeout_seconds=getattr(args, "timeout", 30.0)
    )

    orchestrator = QuakeAgentOrchestrator(
        event_config=event_cfg,
        filter_config=filter_cfg,
        settings=settings
    )

    if args.command == "run":
        print(f"🚀 [QuakeAgent] Starting Agentic Workflow for Event: {event_cfg.name} ({event_cfg.event_id})")
        if filter_cfg.allowed_locations:
            print(f"   🎯 Location Filter Active: {filter_cfg.allowed_locations}")
        if filter_cfg.selected_documents:
            print(f"   📄 Document Filter Active: {filter_cfg.selected_documents}")

        if args.file:
            result = orchestrator.run_on_single_file(args.file)
        else:
            inbound = args.inbound_dir or f"./data/events/{event_cfg.event_id}/inbound"
            result = orchestrator.run_on_inbound_directory(inbound)

        # Optionally harvest web
        if args.web:
            web_res = orchestrator.run_web_harvest(limit_per_source=3)
            result["web_harvest"] = web_res

        if "generation" in result:
            print("\n" + "="*50)
            print("📋 CRAG Output Generation:")
            print("="*50)
            print(result["generation"])
            print("="*50)

        final = result.get("final_analysis", {})
        if final:
            if getattr(args, "file", None) and not final.get("file_name"):
                final["file_name"] = Path(args.file).name
            if getattr(args, "model", None) and not final.get("model_name"):
                final["model_name"] = args.model
            print(f"\n🎯 MMI Estimation: {final.get('mmi_estimation')}")
            print(f"🎯 Confidence: {final.get('confidence')}")
            print(f"📄 Input File: {final.get('file_name')}")
            print(f"🤖 Gemini Model: {final.get('model_name')}")
            print("\n📋 Final Analysis Object (with Initial Analysis & RAG):")
            print(json.dumps(final, indent=2))

        print("\n" + "="*50)
        print("📊 Workflow Execution Summary:")
        print("="*50)
        # Create a display summary excluding massive text blobs for clean viewing
        summary = {k: v for k, v in result.items() if k not in ("initial_analysis", "final_analysis", "generation")}
        print(json.dumps(summary, indent=2))
        print("="*50)

    elif args.command == "shakemap":
        print(f"🗺️ [ShakeMap] Processing ShakeMap v4 integration for {args.event_id}...")
        if args.fetch_official:
            print("   Fetching official ShakeMap from USGS ComCat...")
            official_res = orchestrator.shakemap_comparator.fetch_official_shakemap(args.event_id)
            print("   USGS ComCat Result:", json.dumps(official_res, indent=2))

        event_dir = Path(f"./data/events/{args.event_id}")
        out_file = event_dir / "agent_mmi_dat.json"
        orchestrator.shakemap_exporter.export_dat_json(args.event_id, out_file)
        print(f"✅ Exported USGS ShakeMap input file to: {out_file}")

if __name__ == "__main__":
    main()
