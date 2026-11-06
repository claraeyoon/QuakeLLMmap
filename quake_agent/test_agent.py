from __future__ import annotations
import json
from pathlib import Path
from quake_agent.config import EventConfig, FilterConfig
from quake_agent.core.orchestrator import QuakeAgentOrchestrator

def run_quick_test():
    print("="*60)
    print("🧪 Running QuakeAgent End-to-End Local Test")
    print("="*60)

    # 1. Load Event Config
    event_cfg_path = Path("data/events/us7000pn9s/event_config.json")
    event_cfg = EventConfig.from_file(event_cfg_path)
    print(f"✅ Loaded Event Config: {event_cfg.name} (ID: {event_cfg.event_id})")

    # 2. Configure Orchestrator
    orchestrator = QuakeAgentOrchestrator(
        event_config=event_cfg,
        filter_config=FilterConfig()
    )

    # 3. Process Local Inbound Files
    inbound_dir = Path("data/events/us7000pn9s/inbound")
    print(f"🚀 Scanning inbound directory: {inbound_dir}")
    result = orchestrator.run_on_inbound_directory(inbound_dir)

    print("\n" + "="*60)
    print("📋 Execution Results:")
    print("="*60)
    print(json.dumps(result, indent=2))

    # 4. Verify Database Records
    verified = orchestrator.repo.get_verified_evaluations(event_cfg.event_id)
    print(f"\n📦 Verified Database Records in DuckDB/SQLite: {len(verified)}")
    for v in verified:
        print(f"   • {v.location_name or 'Location'} -> MMI: {v.mmi_estimation:.1f} | Conf: {v.confidence:.2f} | Rrup: {v.rrup_km or 0:.1f} km")

    # 5. Verify USGS ShakeMap Export
    shakemap_path = Path(result["shakemap_export_file"])
    if shakemap_path.exists():
        with open(shakemap_path, "r") as f:
            sm_data = json.load(f)
        feat_count = len(sm_data.get("features", []))
        print(f"\n🗺️ USGS ShakeMap v4 Input Exported: {shakemap_path}")
        print(f"   • Valid ShakeMap Observations: {feat_count}")
        if feat_count > 0:
            print("   • Sample ShakeMap Feature:")
            print(json.dumps(sm_data["features"][0], indent=2))

    print("\n🎉 Test Run Finished Successfully!")

if __name__ == "__main__":
    run_quick_test()
